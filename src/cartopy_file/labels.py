#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Hand-tuned map label layout stored beside each figure, outside the drawing code.

是什么: 把"标签最终写在哪、转到什么角度"从绘图脚本里拆出来, 存成与产物同名的
``<name>.labels.json``; ``save_svg`` 出图时自动读取并施加位移与旋转, 并在图上补画
新增的文字标注. 这样一个标签被哪个数字挡住时, 用鼠标调一次就固化成布局文件,
重跑脚本不会丢掉手工调整.
完整说明(文件格式、坐标系、编辑器用法)见 ``docs/reference/labels.md``.
"""

from __future__ import annotations

import base64
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "LABEL_PREFIX",
    "MARKER_PREFIX",
    "PLACEMENT_SUFFIX",
    "Placements",
    "apply",
    "apply_moved",
    "apply_svg_transforms",
    "dump",
    "label_id",
    "load",
    "placement_path",
    "read_marker",
    "write_marker",
]

# 可编辑标签的 id 前缀. 编辑器和本模块都靠它从整张 SVG 里认出"这是标签".
# 用前缀而不是清单: 脚本给标签设 gid 即可, 布局文件只需要记录被改过的那些.
LABEL_PREFIX = "label-"

# 布局文件后缀: 与产物同名, 只把最后的 .svg 换掉, 例如 a.svg -> a.labels.json.
PLACEMENT_SUFFIX = ".labels.json"

# 文件格式标记与版本; 结构不兼容时靠它给出明确报错而不是静默错位.
FORMAT = "cartopy-file-labels"
# v2 相对 v1 只多了一个可选字段 moved[*].rotation(已有标签的旋转增量).
# 旧的 v1 布局仍可读(按没有旋转处理); 写盘一律写 v2, 这样 v1 代码读到新文件
# 会明确报"版本不支持", 而不是静默丢掉手工旋转.
VERSION = 2
_READABLE_VERSIONS = (1, VERSION)

# 出图时写进 SVG 的标记: 记录"这张图实际施加了哪份布局".
# 为什么需要: 编辑器要区分"SVG 里已经烤进布局"和"布局比 SVG 新(还没重跑脚本)",
# 否则重开会把同一段位移算两遍. 标记用 base64 包住 JSON, 避免注释里出现 "--".
MARKER_PREFIX = "cartopy-file-labels:"
_MARKER_RE = re.compile(
    r"<!--\s*" + re.escape(MARKER_PREFIX) + r"([A-Za-z0-9+/=]+)\s*-->"
)

# 新增标注的默认样式. 编辑器从图上已有标签抄样式写进文件, 缺字段时按这里兜底.
_STYLE_DEFAULTS: dict[str, Any] = {
    "font_size": 10.0,
    "color": "#000000",
    "italic": False,
    "weight": "normal",
    "halo_color": "#ffffff",
    "halo_width": 2.5,
    "anchor": "start",
}

# SVG text-anchor -> matplotlib horizontalalignment.
_ANCHORS = {"start": "left", "middle": "center", "end": "right"}

# 坐标与位移保留 3 位小数: SVG 用户单位是 pt, 0.001pt 远小于一个像素,
# 但能让 JSON 的 git diff 不被浮点尾数噪声淹没.
_DIGITS = 3

# 出图后往 SVG 的标签组里补变换时用到的解析规则. matplotlib 只写 translate / rotate,
# 但按完整 transform 列表实现, 免得将来换写法时静默算错锚点.
_TRANSFORM_RE = re.compile(
    r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", re.IGNORECASE
)
_ATTRIBUTE_RE = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_TEXT_OPEN_RE = re.compile(r"<text\b[^>]*>", re.IGNORECASE)
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


@dataclass
class Placements:
    """一张图的标签布局: 已有标签的位移/旋转 + 新增的文字标注.

    moved: 标签 id -> ``{"dx": float, "dy": float, "rotation": float, "text": str}``.
        dx/dy 是相对脚本默认位置的位移, 单位是 SVG 用户单位(= pt), y 轴向下(与 SVG 一致);
        rotation 是相对脚本默认角度的旋转增量(度, 正值顺时针, 与 SVG 的 ``rotate`` 一致).
        存增量而不是绝对坐标/角度: 脚本改了默认位置或自动算出的河名角度后, 手工调整仍然
        跟着那个新位置/新角度走.
    added: 新增标注的列表, 每项见 ``docs/reference/labels.md`` 的字段说明.
    source: 读取时对应的布局文件路径; 编辑器界面用来显示"保存到哪".
    figure: 布局文件里记录的产物名, load 时用来检查是否读错了文件.
    """

    moved: dict[str, dict[str, Any]] = field(default_factory=dict)
    added: list[dict[str, Any]] = field(default_factory=list)
    source: Path | None = None
    figure: str = ""

    def __bool__(self) -> bool:
        """没有任何调整时视为空, 方便调用方判断"这张图要不要处理"."""
        return bool(self.moved or self.added)


def label_id(kind: str, name: str, index: int | None = None) -> str:
    """拼一个跨版本稳定的标签 id, 同时就是布局文件里的键.

    是什么: ``label-<kind>-<name>[-<index>]``, 例如 ``label-city-莫斯科``.
    kind: 标签类别(city/river/sea/country/highland/republic/...), 由脚本自己定.
    name: 人类可读的净名, 例如数据结构的英文键或图上的中文名; 不要带换行和空格.
    index: 同一类别同一名字出现多次时(例如两条"伏尔加河"), 传 1 起算的序号.
    """
    base = f"{LABEL_PREFIX}{kind}-{name.strip()}"
    if index is None:
        return base
    return f"{base}-{int(index)}"


def placement_path(svg_path: str | Path) -> Path:
    """产物路径对应的布局文件路径: 只替换最后的后缀, 不改目录."""
    return Path(svg_path).with_suffix(PLACEMENT_SUFFIX)


def load(path: str | Path) -> Placements:
    """读取并校验布局文件.

    文件不存在或结构不合法时抛 ValueError/OSError: 出图宁可失败也不静默忽略
    手工调整, 否则产物会悄悄退回默认位置.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # 报错要带文件名, 否则不知道该改哪个
        raise ValueError(f"标签布局文件不是合法 JSON: {path}: {exc}") from exc
    return from_document(data, source=path)


def from_document(data: Any, *, source: Path | None = None) -> Placements:
    """把解析后的 JSON 对象转成 Placements.

    是什么: 一处校验所有字段. 出图与编辑器保存都走这里, 两边格式不会漂移.
    """
    if not isinstance(data, dict):
        raise ValueError("标签布局文件顶层必须是 JSON 对象")
    if data.get("format") != FORMAT:
        raise ValueError(
            f"不是标签布局文件(format 应为 {FORMAT!r}): {data.get('format')!r}"
        )
    if data.get("version") not in _READABLE_VERSIONS:
        raise ValueError(
            f"标签布局文件版本不支持: {data.get('version')!r}"
            f"(本程序支持 {_READABLE_VERSIONS})"
        )

    moved_raw = data.get("moved", {})
    if not isinstance(moved_raw, dict):
        raise ValueError("标签布局文件的 moved 必须是对象")
    moved: dict[str, dict[str, Any]] = {}
    for key, record in moved_raw.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            raise ValueError(f"moved 里的项必须是 字符串 -> 对象: {key!r}")
        dx = _finite(record.get("dx"), f"moved[{key!r}].dx")
        dy = _finite(record.get("dy"), f"moved[{key!r}].dy")
        entry: dict[str, Any] = {"dx": dx, "dy": dy}
        # rotation 是 v2 新增的可选字段; v1 文件没有它, 按 "没有旋转增量" 处理.
        if "rotation" in record:
            entry["rotation"] = _finite(
                record.get("rotation"), f"moved[{key!r}].rotation"
            )
        text = record.get("text")
        if text is not None:
            if not isinstance(text, str):
                raise ValueError(f"moved[{key!r}].text 必须是字符串")
            entry["text"] = text
        moved[key] = entry

    added_raw = data.get("added", [])
    if not isinstance(added_raw, list):
        raise ValueError("标签布局文件的 added 必须是数组")
    added = [_added_record(record, i) for i, record in enumerate(added_raw)]

    keys = [record["key"] for record in added]
    if len(set(keys)) != len(keys):
        raise ValueError(f"新增标注的 id 重复: {keys}")

    return Placements(
        moved=moved,
        added=added,
        source=source,
        figure=str(data.get("figure") or ""),
    )


def to_document(placements: Placements, *, figure: str = "") -> dict[str, Any]:
    """把 Placements 转成要写盘的 JSON 对象(位移/角度与坐标四舍五入到 3 位).

    为什么在这里舍入而不是读入时: 只有写盘需要稳定, 读入的旧值保持原样才能
    叠加第二次拖动而不丢精度.
    """
    moved: dict[str, Any] = {}
    for key in sorted(placements.moved):
        record = placements.moved[key]
        entry: dict[str, Any] = {
            "dx": _round(record["dx"]),
            "dy": _round(record["dy"]),
        }
        if _round(record.get("rotation") or 0.0):
            entry["rotation"] = _round(record.get("rotation") or 0.0)
        if record.get("text"):
            entry["text"] = record["text"]
        moved[key] = entry

    added: list[dict[str, Any]] = []
    for record in placements.added:
        style = dict(_STYLE_DEFAULTS)
        style.update(record.get("style") or {})
        added.append(
            {
                "key": record["key"],
                "text": record["text"],
                "x": _round(record["x"]),
                "y": _round(record["y"]),
                "rotation": _round(record["rotation"]),
                "style": {
                    "font_size": _round(style["font_size"]),
                    "color": style["color"],
                    "italic": bool(style["italic"]),
                    "weight": style["weight"],
                    "halo_color": style["halo_color"],
                    "halo_width": _round(style["halo_width"]),
                    "anchor": style["anchor"],
                },
            }
        )

    return {
        "format": FORMAT,
        "version": VERSION,
        "figure": figure or placements.figure,
        "moved": moved,
        "added": added,
    }


def dump(placements: Placements, path: str | Path, *, figure: str = "") -> Path:
    """原子地写出布局文件(先写临时文件再 rename), 返回写入路径."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = to_document(placements, figure=figure)
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    # 临时文件与目标同目录, 保证 rename 是同一个文件系统上的原子操作.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path


def apply(
    fig, placements: Placements, *, moved: bool = True, added: bool = True
) -> None:
    """把布局施加到一个已经画好、还没保存的 Figure 上.

    是什么: 已有标签按 id 平移/旋转, 新增标注作为 figure 级文字补画上去.
    moved / added: 只施加其中一部分. ``save_svg`` 出图时传 ``moved=False``:
    已有标签的变换在 SVG 写成后由 :func:`apply_svg_transforms` 直接补进标签组,
    与编辑器预览同构; 这里改 Figure 的 ``Text`` 只是给交互窗口用.
    注意: 同一个 Figure 只能施加一次, 重复施加会把位移与旋转叠加两遍.
    """
    if getattr(fig, "_cartopy_file_labels_applied", False):
        print("警告: 标签布局已施加过, 跳过重复施加(同一 Figure 只能施加一次)")
        return
    fig._cartopy_file_labels_applied = True  # noqa: SLF001 - 只作幂等标记
    if moved:
        apply_moved(fig, placements)
    if added:
        _apply_added(fig, placements)


def apply_moved(fig, placements: Placements, *, warn: bool = True) -> None:
    """只施加已有标签的位移/旋转, 不补画新增标注, 也不设幂等标记.

    ``save_svg`` 写文件后再调用它, 让 ``--show`` 的交互窗口也能看到手工布局
    (文件此时已经写完, 不受影响); 直接渲染到 PNG 等非 SVG 输出时也可以用它.
    warn=False 用于"SVG 侧已经打印过找不到的标签"的场合, 避免同一条警告两遍.
    """
    from matplotlib.text import Text

    by_gid: dict[str, list[Any]] = {}
    for artist in fig.findobj(match=lambda item: isinstance(item, Text)):
        gid = artist.get_gid()
        if gid:
            by_gid.setdefault(gid, []).append(artist)

    missing: list[str] = []
    unsupported: list[str] = []
    for gid, record in placements.moved.items():
        artists = by_gid.get(gid)
        if not artists:
            missing.append(gid)
            continue
        if len(artists) > 1:
            print(f"警告: 标签 id 重复({len(artists)} 个), 位移与旋转会同时作用: {gid}")
        for artist in artists:
            if not _adjust_artist(
                artist,
                float(record["dx"]),
                float(record["dy"]),
                float(record.get("rotation") or 0.0),
            ):
                unsupported.append(gid)

    if warn and missing:
        shown = ", ".join(missing[:5]) + ("" if len(missing) <= 5 else ", ...")
        print(
            f"警告: 布局文件里有 {len(missing)} 个标签在图里找不到, 已忽略: {shown}"
        )
    if warn and unsupported:
        shown = ", ".join(sorted(set(unsupported))[:5])
        print(
            f"警告: {len(set(unsupported))} 个标签是不支持位移/旋转的注释类型, "
            f"已跳过 Figure 同步: {shown}"
        )


def _apply_added(fig, placements: Placements) -> None:
    """按布局补画新增标注; 图上已有同 id 的文字时跳过并警告."""
    from matplotlib.text import Text

    existing = {
        artist.get_gid()
        for artist in fig.findobj(match=lambda item: isinstance(item, Text))
        if artist.get_gid()
    }
    for record in placements.added:
        if record["key"] in existing:
            print(f"警告: 新增标注的 id 与图上已有标签重复, 跳过: {record['key']}")
            continue
        _add_custom(fig, record)


def apply_svg_transforms(
    svg_path: str | Path, placements: Placements | None
) -> list[str]:
    """把已有标签的位移/旋转以标签组 transform 的形式补进已写出的 SVG.

    是什么: 给每个 ``<g id="label-...">`` 的 transform 前面加一段
    ``translate(dx dy) rotate(角度 锚点)``; 锚点按组里第一条 ``<text>`` 自己的
    transform / x / y 折算, 与编辑器给标签加的包装层完全同构.
    为什么不用 ``Text.set_rotation``: matplotlib 会按 ``rotation_mode`` 重新排字,
    default 或垂直居中的标签改角度时锚点会挪几 pt, 编辑器预览绕的是 SVG 里现有的
    旋转中心, 两边就对不上. 直接在 SVG 上施加同一段变换, 预览即产物.
    返回实际改写的标签 id(按布局顺序); 图里找不到的 id 打印一条汇总警告.
    """
    if placements is None:
        return []
    records = [
        (gid, record)
        for gid, record in sorted(placements.moved.items())
        if _has_moved_transform(record)
    ]
    if not records:
        return []

    path = Path(svg_path)
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    missing: list[str] = []
    for gid, record in records:
        # 标签组里没有嵌套 <g>(matplotlib 把 gid 写在一个只包文字的组上), 所以
        # 非贪婪地找到第一个 </g> 就是这个标签组的结尾. 多行标签是多条 <text>,
        # 旋转中心统一取第一条的锚点, 与编辑器一致.
        # (?<![:\w-]) 防止 data-id="..." 之类被当成 id; 单引号也认(matplotlib 只写双引号).
        name = re.escape(gid)
        pattern = re.compile(
            r'(<g\b[^>]*(?<![:\w-])id\s*=\s*(?:"'
            + name
            + r'"|\''
            + name
            + r'\')[^>]*>)(.*?)(</g>)',
            re.DOTALL,
        )
        changed = [False]

        def rewrite(match: re.Match[str], record=record) -> str:
            start, body, end = match.group(1), match.group(2), match.group(3)
            text_tag = _TEXT_OPEN_RE.search(body)
            if text_tag is None:
                # 标签被渲染成字形路径(例如带不支持的 path effect): 没有 <text> 就没法
                # 安全折算锚点, 交给下面的 missing 汇总警告, 不要静默记成已施加.
                return match.group(0)
            changed[0] = True
            attributes = _tag_attributes(text_tag.group(0))
            anchor = _transform_point(
                attributes.get("transform", ""),
                _svg_coord(attributes.get("x")),
                _svg_coord(attributes.get("y")),
            )
            group_transform = _tag_attributes(start).get("transform", "")
            if group_transform:
                anchor = _transform_point(group_transform, *anchor)
            prefix = _layout_transform(record, anchor)
            if not prefix:
                return match.group(0)
            transform = prefix + (f" {group_transform}" if group_transform else "")
            return _set_attribute(start, "transform", transform) + body + end

        text, _ = pattern.subn(rewrite, text)
        if changed[0]:
            applied.append(gid)
        else:
            missing.append(gid)

    if missing:
        shown = ", ".join(missing[:5]) + ("" if len(missing) <= 5 else ", ...")
        print(
            f"警告: {len(missing)} 个标签在 SVG 里找不到可加变换的标签组"
            f"(可能被写成字形路径), 已忽略: {shown}"
        )
    if applied:
        path.write_text(text, encoding="utf-8")
    return applied


def _adjust_artist(artist, dx: float, dy: float, rotation: float) -> bool:
    """把一个文字画师在画布上平移 (dx, dy) pt 并旋转 rotation 度; 不支持的画师返回 False.

    为什么不能用"改 transform"一招走完: 普通 ``Text`` 的位置是 transform 作用在
    (x, y) 上, 在显示坐标里补一段平移就行; 但 ``Annotation`` 每次绘制时自己把
    ``xytext``(可以是 "offset points") 换算成显示坐标并把 transform 换成单位阵,
    改 transform 会被它覆盖掉. 对 offset points 的注释位置直接加减 pt 才是稳的.

    旋转用 ``Text.set_rotation``, 方向取反(布局文件是 SVG 的顺时针正, matplotlib 是
    逆时针正). 注意这条路径只用于直接在 Figure 上施加布局(自定义渲染、交互窗口、
    文字外置回退): set_rotation 会按 ``rotation_mode`` 重新排字, 与编辑器预览绕固定
    锚点转的结果可能差几 pt; ``save_svg`` 的常规路径不走这里, 而是在 SVG 标签组上
    补同一段 transform(见 :func:`apply_svg_transforms`), 预览即产物.
    """
    from matplotlib.text import Annotation
    from matplotlib.transforms import ScaledTranslation

    # 先判断再改: 不支持的注释类型不能被改了一半.
    if isinstance(artist, Annotation) and artist.anncoords != "offset points":
        return False

    if rotation:
        artist.set_rotation(artist.get_rotation() - rotation)

    if isinstance(artist, Annotation):
        x, y = artist.xyann
        # annotation 的 y 轴向上, 布局文件沿用 SVG 约定 y 向下.
        artist.xyann = (x + dx, y - dy)
        return True

    # 位移量与 dpi 无关: 布局文件里的 dx/dy 是"图上量出来的 pt"(SVG 用户单位),
    # 用 ScaledTranslation(英寸 × 绘制时 dpi)表达, SVG 后端按 72dpi 绘制时正好得到
    # 同样的 pt 数, 交互窗口里则是同样的物理尺寸.
    # 组合顺序必须是 ``原变换 + 平移``: 先做投影/坐标变换, 再在显示坐标里平移;
    # 反过来会把 pt 当成经纬度加进数据坐标.
    figure = artist.get_figure(root=True)
    shift = ScaledTranslation(dx / 72.0, -dy / 72.0, figure.dpi_scale_trans)
    artist.set_transform(artist.get_transform() + shift)
    return True


def read_marker(svg_path: str | Path) -> Placements | None:
    """读出 SVG 里记录的"实际施加的布局"; 没有标记(或标记损坏)时返回 None.

    为什么不用文件时间戳判断"布局是否已经烤进图里": 复制/检出会改时间, 而内容
    标记不会骗人. 标记由 ``save_svg`` 写入, 编辑器靠它决定位移要不要再叠加.
    """
    path = Path(svg_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    return marker_from_svg(text)


def marker_from_svg(svg_text: str) -> Placements | None:
    """从 SVG 文本里解析布局标记; 未标记/无法解析时返回 None."""
    match = _MARKER_RE.search(svg_text)
    if match is None:
        return None
    try:
        data = json.loads(base64.b64decode(match.group(1)))
        return from_document(data)
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def write_marker(svg_path: str | Path, placements: Placements) -> None:
    """把"已施加的布局"以注释形式写进 SVG(紧跟 ``<svg ...>`` 开标签).

    标记只是自描述信息: 查看器会忽略注释, 去掉标记也不影响画面, 只是编辑器会
    认为这张图没有烤进任何布局.
    """
    path = Path(svg_path)
    text = path.read_text(encoding="utf-8")
    if _MARKER_RE.search(text) is not None:  # 重出图不该有旧标记, 有就先清掉
        text = _MARKER_RE.sub("", text, count=1)
    payload = json.dumps(
        to_document(placements),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    marker = f"<!-- {MARKER_PREFIX}{base64.b64encode(payload).decode('ascii')} -->"
    match = re.search(r"<svg\b[^>]*>", text)
    if match is None:
        raise ValueError(f"SVG 里找不到 <svg> 开标签, 无法写入布局标记: {path}")
    text = text[: match.end()] + "\n" + marker + text[match.end() :]
    path.write_text(text, encoding="utf-8")


def _add_custom(fig, record: dict[str, Any]) -> None:
    """按布局文件补画一条新增标注.

    SVG 的 ``y`` 是文字基线的位置(不是顶部/中心), 所以落到 Figure 上要用
    ``va="baseline"`` 才能与编辑器里看到的位置一致; 旋转方向也相反(SVG 顺时针为正).
    """
    import matplotlib.patheffects as path_effects

    style = dict(_STYLE_DEFAULTS)
    style.update(record.get("style") or {})

    width_in, height_in = fig.get_size_inches()
    x = float(record["x"]) / (72.0 * width_in)
    y = 1.0 - float(record["y"]) / (72.0 * height_in)

    effects = None
    if float(style["halo_width"]) > 0 and style["halo_color"]:
        effects = [
            path_effects.withStroke(
                linewidth=float(style["halo_width"]),
                foreground=style["halo_color"],
            )
        ]

    artist = fig.text(
        x,
        y,
        record["text"],
        transform=fig.transFigure,
        ha=_ANCHORS.get(style["anchor"], "left"),
        va="baseline",
        fontsize=float(style["font_size"]),
        color=style["color"],
        style="italic" if style["italic"] else "normal",
        weight=style["weight"],
        rotation=-float(record["rotation"]),
        rotation_mode="anchor",
        zorder=25,
        path_effects=effects,
    )
    artist.set_gid(record["key"])


def _added_record(record: Any, index: int) -> dict[str, Any]:
    """校验一条新增标注并补默认样式."""
    where = f"added[{index}]"
    if not isinstance(record, dict):
        raise ValueError(f"{where} 必须是对象")
    key = record.get("key")
    if not isinstance(key, str) or not key.startswith(LABEL_PREFIX):
        raise ValueError(f"{where}.key 必须以 {LABEL_PREFIX!r} 开头: {key!r}")
    if any(char.isspace() for char in key):
        raise ValueError(f"{where}.key 不能含空白: {key!r}")
    text = record.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError(f"{where}.text 必须是非空字符串")

    raw_style = record.get("style") or {}
    if not isinstance(raw_style, dict):
        raise ValueError(f"{where}.style 必须是对象")
    style = dict(_STYLE_DEFAULTS)
    for name, default in _STYLE_DEFAULTS.items():
        if name not in raw_style:
            continue
        value = raw_style[name]
        if isinstance(default, bool):
            style[name] = bool(value)
        elif isinstance(default, float):
            style[name] = _finite(value, f"{where}.style.{name}")
        else:
            if not isinstance(value, str):
                raise ValueError(f"{where}.style.{name} 必须是字符串")
            style[name] = value
    if style["anchor"] not in _ANCHORS:
        raise ValueError(f"{where}.style.anchor 只能是 {sorted(_ANCHORS)}")

    return {
        "key": key,
        "text": text,
        "x": _finite(record.get("x"), f"{where}.x"),
        "y": _finite(record.get("y"), f"{where}.y"),
        "rotation": _finite(record.get("rotation", 0.0), f"{where}.rotation"),
        "style": style,
    }


def _has_moved_transform(record: dict[str, Any]) -> bool:
    """这条 moved 记录是否需要往 SVG 里补变换(位移或旋转非 0 才算)."""
    return any(
        abs(float(record.get(name) or 0.0)) > 1e-9
        for name in ("dx", "dy", "rotation")
    )


def _layout_transform(record: dict[str, Any], anchor: tuple[float, float]) -> str:
    """拼出要加到标签组上的 transform 前缀; 都为 0 时返回空串."""
    dx = float(record.get("dx") or 0.0)
    dy = float(record.get("dy") or 0.0)
    rotation = float(record.get("rotation") or 0.0)
    parts: list[str] = []
    if abs(dx) > 1e-9 or abs(dy) > 1e-9:
        parts.append(f"translate({_svg_number(dx)} {_svg_number(dy)})")
    if abs(rotation) > 1e-9:
        parts.append(
            f"rotate({_svg_number(rotation)} {_svg_number(anchor[0])} {_svg_number(anchor[1])})"
        )
    return " ".join(parts)


def _transform_point(transform: str, x: float, y: float) -> tuple[float, float]:
    """把 SVG transform 列表作用到点上(列表外层在前, 对点要从右往左算)."""
    operations: list[tuple[str, list[float]]] = []
    for match in _TRANSFORM_RE.finditer(transform or ""):
        try:
            args = [
                float(part)
                for part in re.split(r"[\s,]+", match.group(2).strip())
                if part
            ]
        except ValueError:
            continue
        operations.append((match.group(1).lower(), args))

    for name, args in reversed(operations):
        if name == "matrix" and len(args) == 6:
            a, b, c, d, e, f = args
            x, y = a * x + c * y + e, b * x + d * y + f
        elif name == "translate" and args:
            x += args[0]
            y += args[1] if len(args) > 1 else 0.0
        elif name == "scale" and args:
            sx = args[0]
            sy = args[1] if len(args) > 1 else sx
            x *= sx
            y *= sy
        elif name == "rotate" and args:
            radians = math.radians(args[0])
            cos, sin = math.cos(radians), math.sin(radians)
            cx = args[1] if len(args) > 2 else 0.0
            cy = args[2] if len(args) > 2 else 0.0
            px, py = x - cx, y - cy
            x, y = cx + cos * px - sin * py, cy + sin * px + cos * py
        elif name == "skewx" and args:
            x += math.tan(math.radians(args[0])) * y
        elif name == "skewy" and args:
            y += math.tan(math.radians(args[0])) * x
    return x, y


def _tag_attributes(tag: str) -> dict[str, str]:
    """从一个 XML 开标签里取出属性(值不展开实体; 标签 id 由脚本生成, 不含实体)."""
    return {
        match.group(1): match.group(2) if match.group(2) is not None else match.group(3) or ""
        for match in _ATTRIBUTE_RE.finditer(tag)
    }


def _set_attribute(tag: str, name: str, value: str) -> str:
    """给开标签设置属性: 已有就替换值(保留原来的引号), 没有就补在结尾的 ``>`` 前."""
    pattern = re.compile(
        r'(\s' + re.escape(name) + r'\s*=\s*)(["\'])(.*?)(\2)'
    )
    if pattern.search(tag):
        def replace(match: re.Match[str]) -> str:
            return match.group(1) + match.group(2) + value + match.group(4)

        return pattern.sub(replace, tag, count=1)
    stripped = tag.rstrip()
    if stripped.endswith("/>"):
        return stripped[:-2].rstrip() + f' {name}="{value}"/>'
    return stripped[:-1].rstrip() + f' {name}="{value}">'


def _svg_coord(value: str | None, default: float = 0.0) -> float:
    """取 SVG 坐标属性的第一个数; 列表写法(x="1 2 3")只取第一个."""
    if value is None:
        return default
    match = _NUMBER_RE.search(value)
    return float(match.group()) if match else default


def _svg_number(value: float) -> str:
    """写进 SVG 属性的数字: 最多 6 位小数, 去掉尾零, -0 统一成 0."""
    number = float(value)
    if abs(number) < 5e-7:
        return "0"
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _finite(value: Any, where: str) -> float:
    """取值并确认是有限数值; 布局文件里的 NaN/Inf 会让矩阵变换直接出乱码."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{where} 必须是数值: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{where} 必须是有限数值: {value!r}")
    return number


def _round(value: float) -> float:
    """写盘用的定点小数; -0.0 统一成 0.0, 免得 diff 出现 "-0.0".

    顺带在此拒绝 NaN/Inf: JSON 没有这两个字面量, 写出去后连本模块自己都读不回来.
    读入路径(from_document)另有同样的校验, 这里补的是"直接构造 Placements 再 dump".
    """
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"写盘数值必须是有限值: {value!r}")
    rounded = round(number, _DIGITS)
    return 0.0 if rounded == 0 else rounded
