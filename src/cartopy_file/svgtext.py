#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""SVG 文字外置: 真 ``<text>`` + 内嵌字体子集.

是什么: 配合 ``output.save_svg`` 把图里的文字从"字形轮廓路径"改成真正的 ``<text>``,
并把用到的字体按字形裁剪成 WOFF 内嵌进 ``@font-face``; 文字上的白色描边(halo)改写成
``<text>`` 的 ``stroke`` + ``paint-order: stroke``.

为什么: matplotlib 在 ``svg.fonttype="path"`` 下把文字转成轮廓路径, 带 ``path_effects``
(白描边)时更会整段合并成一条 ``<path>`` —— 产物里的文字既不能选中/复制/检索, 也无法在
Inkscape 里按名字找到后单独挪位置. 内嵌字体子集是"既不依赖查看器装字体, 又保留真 <text>"
的折中: 子集只含本图用到的字形, 体积远小于整套 CJK 字体.

坑与风险(见 ``docs/reference/output.md``):
- 不认 ``@font-face`` 的查看器(librsvg/ImageMagick/部分 Office 导入)会回退系统字体,
  缺字体时显示方框; 这是路径写法没有的风险, 因此 ``save_svg`` 保留了关掉本功能的开关;
- 只处理项目在用的单层 ``withStroke`` 描边; 其它 path effect 不动(该文字仍以路径写出);
- 子集从本机安装的字体文件裁剪, 字体缺失时跳过内嵌, 文字退回查看器字体.
"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import unescape

__all__ = ["TextState", "embed_font_subsets", "prepare_text", "restore_text"]

# 文字内容: matplotlib 在 fonttype="none" 下写成单行 <text ...>内容</text>.
_TEXT_BODY_RE = re.compile(r"<text\b[^>]*>(.*?)</text>", re.S)
_TEXT_TAG_RE = re.compile(r"<text\b[^>]*>")
_FAMILY_RE = re.compile(r'font-family:\s*([^;"]+)')
_GROUP_TAG_RE = re.compile(r"<(/?)g\b")

# 内嵌字体来自 OFL / Bitstream Vera 许可的字体, 按许可要求在产物里带上来源声明.
_LICENSE = (
    "内嵌字体子集仅含本图用到的字形: Noto Sans Mono CJK SC (SIL OFL 1.1), "
    "JetBrains Mono Slashed Medium (SIL OFL 1.1), DejaVu Sans (Bitstream Vera License)."
)


@dataclass
class _Halo:
    """一层白描边: 颜色 + 线宽(单位与 SVG 用户单位一致, 即 pt)."""

    color: str
    width: float


@dataclass
class _Face:
    """matplotlib 实际用的字体文件; TTC 要记住面序号才能裁到正确的字族."""

    path: Path
    index: int | None
    cmap: set[int] = field(default_factory=set)


@dataclass
class TextState:
    """``prepare_text`` 的返回值: 保存后用来写回 halo / 还原原始 path_effects."""

    artist_effects: list[tuple[object, list]] = field(default_factory=list)
    halos: dict[str, _Halo] = field(default_factory=dict)


def prepare_text(fig) -> TextState:
    """给带描边的文字分配稳定 id, 并临时摘掉 ``path_effects``.

    必须在内嵌字体模式(``svg.fonttype="none"``)保存之前调用: 带 path effect 的文字会被
    matplotlib 交给 ``PathEffectRenderer`` 转成合并路径, 只有摘掉才能写出 ``<text>``.
    描边参数记下来, 保存后由 ``embed_font_subsets`` 写成 CSS ``stroke``.
    """
    import matplotlib.colors as mcolors
    import matplotlib.patheffects as path_effects
    from matplotlib.text import Text

    state = TextState()
    for artist in fig.findobj(match=lambda item: isinstance(item, Text)):
        if not artist.get_visible():
            continue
        effects = artist.get_path_effects()
        if not effects:
            continue
        if len(effects) != 1 or not isinstance(effects[0], path_effects.withStroke):
            # 项目只用"单层白描边"; 其它效果原样保留(该文字仍以轮廓路径写出, 只是不可检索).
            print(
                f"警告: 文字 {artist.get_text()!r} 的 path_effects 不是单层 withStroke, "
                "保留路径写法"
            )
            continue
        gid = artist.get_gid() or f"label-{len(state.halos)}"
        artist.set_gid(gid)
        effect = effects[0]
        # withStroke 把参数放在 _gc(新版是 dict, 旧版是属性); 两种都兼容.
        gc = getattr(effect, "_gc", None)
        if isinstance(gc, dict):
            foreground = gc.get("foreground", "white")
            width = float(gc.get("linewidth", 3.0))
        else:  # pragma: no cover - 兼容旧版 matplotlib
            foreground = getattr(effect, "_foreground", "white")
            width = float(getattr(effect, "_linewidth", 3.0))
        state.halos[gid] = _Halo(
            color=mcolors.to_hex(mcolors.to_rgba(foreground)), width=width
        )
        state.artist_effects.append((artist, effects))
        artist.set_path_effects([])
    return state


def restore_text(state: TextState) -> None:
    """把 ``prepare_text`` 摘掉的 path_effects 装回去, 让 Figure 回到调用前的状态."""
    for artist, effects in state.artist_effects:
        artist.set_path_effects(effects)


def embed_font_subsets(path: str | Path, state: TextState) -> None:
    """把 ``path`` 里用到的字体裁成子集内嵌, 并给 halo 文字补上 CSS 描边.

    直接原地改写 SVG 文本; 字体文件按 SVG 里实际写出的 ``font-family`` 名字反查 matplotlib
    的字体表, 这样脚本里换字体/加字体都不用改本模块.
    """
    path = Path(path)
    svg = path.read_text(encoding="utf-8")
    chars = _used_chars(svg)
    css: list[str] = []
    for family in _families(svg):
        face = _resolve_face(family)
        if face is None:
            continue
        data = _subset_woff(face, chars)
        if not data:
            continue
        encoded = base64.b64encode(data).decode("ascii")
        css.append(
            f'@font-face {{ font-family: "{family}"; '
            f'src: url("data:font/woff;base64,{encoded}") format("woff"); }}'
        )
    if css:
        svg = _inject_style(svg, css)
    for gid, halo in state.halos.items():
        svg = _apply_halo(svg, gid, halo)
    path.write_text(svg, encoding="utf-8")


def _used_chars(svg: str) -> str:
    """SVG 里所有 ``<text>`` 的字符(去标签、反转义), 作为字体裁剪的依据."""
    chars: set[str] = set()
    for body in _TEXT_BODY_RE.findall(svg):
        chars.update(unescape(re.sub(r"<[^>]+>", "", body)))
    return "".join(sorted(chars))


def _families(svg: str) -> list[str]:
    """SVG 里 ``font-family`` 声明出现的字族, 按首次出现顺序去重."""
    families: list[str] = []
    for value in _FAMILY_RE.findall(svg):
        for family in value.split(","):
            family = family.strip().strip("'\"")
            if family and family not in families:
                families.append(family)
    return families


def _resolve_face(family: str) -> _Face | None:
    """按字体名找到 matplotlib 用的文件; TTC 时找出与字体名对应的面."""
    from matplotlib import font_manager
    from fontTools.ttLib import TTCollection, TTFont

    try:
        file = font_manager.findfont(
            font_manager.FontProperties(family=family), fallback_to_default=False
        )
    except Exception:
        return None
    file = Path(file)
    if file.suffix.lower() == ".ttc":
        collection = TTCollection(str(file), lazy=True)
        for index, font in enumerate(collection.fonts):
            names = {font["name"].getDebugName(1), font["name"].getDebugName(16)}
            if family in names:
                return _Face(file, index, set(font.getBestCmap()))
        return None
    return _Face(file, None, set(TTFont(str(file), lazy=True).getBestCmap()))


def _subset_woff(face: _Face, chars: str) -> bytes:
    """按字符裁剪字体并存成 WOFF(比整套 CJK 字体小两三个数量级).

    用 WOFF 而不是 WOFF2: WOFF2 要额外装 brotli, 项目没有这条依赖; WOFF 的 zlib 压缩
    对本场景已经够用.
    """
    from fontTools import subset
    from fontTools.ttLib import TTFont

    # recalcTimestamp=False: TTFont 保存时默认把 head.modified 改成"现在", 会让同一份
    # 数据的产物每次出图都不同(WOFF 的 base64 变了). 保留源字体自带的时间戳, 重复
    # 出图才字节级一致(项目约定见 docs/reference/output.md).
    font = (
        TTFont(str(face.path), fontNumber=face.index, recalcTimestamp=False)
        if face.index is not None
        else TTFont(str(face.path), recalcTimestamp=False)
    )
    keep = "".join(char for char in chars if ord(char) in face.cmap)
    if not keep:
        font.close()
        return b""
    options = subset.Options()
    # 地图文字不需要连字/字距等排版特性, 关掉能再小一截.
    options.layout_features = []
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables += ["DSIG"]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=keep)
    subsetter.subset(font)
    font.flavor = "woff"
    buffer = io.BytesIO()
    font.save(buffer)
    font.close()
    return buffer.getvalue()


def _inject_style(svg: str, css: list[str]) -> str:
    """把 ``@font-face`` 放进顶层 ``<defs>`` 的 ``<style>`` 里(CDATA 避免转义)."""
    block = (
        '  <style type="text/css"><![CDATA[\n'
        f"/* {_LICENSE} */\n" + "\n".join(css) + "\n]]></style>\n"
    )
    if "<defs>" not in svg:
        # 没有 defs 时自己补一个, 放在 <svg ...> 开标签之后.
        head = svg.find(">", svg.find("<svg")) + 1
        return svg[:head] + "\n <defs>\n" + block + " </defs>" + svg[head:]
    return svg.replace("<defs>", "<defs>\n" + block, 1)


def _apply_halo(svg: str, gid: str, halo: _Halo) -> str:
    """给 ``gid`` 组里的每条 ``<text>`` 补上 ``stroke``/``paint-order``.

    ``paint-order: stroke`` 保证白描边画在字下面(等价于 matplotlib 的 withStroke);
    没有它描边会盖住字心, 笔画会被吃细.
    """
    marker = f'<g id="{gid}">'
    start = svg.find(marker)
    if start < 0:
        return svg
    end = _group_end(svg, start + len(marker))
    if end < 0:
        return svg
    extra = (
        f"; stroke: {halo.color}; stroke-width: {halo.width:g}; paint-order: stroke"
    )

    def add_stroke(match: re.Match[str]) -> str:
        tag = match.group(0)
        style = re.search(r'style="([^"]*)"', tag)
        if style is None:
            return tag[:-1] + f' style="{extra[2:]}">'
        return tag.replace(
            f'style="{style.group(1)}"', f'style="{style.group(1)}{extra}"', 1
        )

    body = _TEXT_TAG_RE.sub(add_stroke, svg[start:end])
    return svg[:start] + body + svg[end:]


def _group_end(svg: str, start: int) -> int:
    """从 ``start`` 开始找与已打开的 ``<g>`` 配对的 ``</g>`` 位置(嵌套深度计数)."""
    depth = 1
    for match in _GROUP_TAG_RE.finditer(svg, start):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            return match.start()
    return -1
