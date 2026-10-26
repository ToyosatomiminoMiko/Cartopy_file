#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Project-wide figure output: self-contained SVG.

是什么: 所有地图产物统一保存为单个自包含的 SVG(``apply_svg_output`` + ``save_svg``),
文字以真 ``<text>`` 写出, 用到的字体按字形裁剪成 WOFF 内嵌(``@font-face``).
完整说明(SVG 的理由、文字外置的做法与风险)见 ``docs/reference/output.md``.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["SVG_SUFFIX", "apply_svg_output", "save_svg"]

# 唯一的交付格式后缀; 脚本里的输出路径统一用它拼.
SVG_SUFFIX = ".svg"

# 固定 hashsalt 让 SVG 内部的 id 稳定(见 matplotlib rcParam svg.hashsalt).
_HASHSALT = "cartopy-file"


def apply_svg_output() -> None:
    """把 SVG 出图相关的 rcParams 固定下来, 可重复调用.

    必须在导入 matplotlib 之后、创建 Figure 之前调用. 显式写出来而不是依赖
    matplotlib 的默认值, 是为了让"字体转路径 / 栅格内嵌 / 时间戳不写"这三条
    约定集中在本文件里; 换 matplotlib 版本或用户自己的 matplotlibrc 也改不掉.

    注意: ``svg.fonttype="path"`` 只是兜底. ``save_svg`` 默认会把文字改成 ``<text>``
    并内嵌字体子集(见 ``docs/reference/output.md``); 这里设成 path 是为了不经过
    ``save_svg`` 的 ``Figure.savefig`` 调用(比如临时调试)仍然能被阅读器打开.
    """
    import matplotlib

    matplotlib.rcParams.update(
        {
            # 汉字转路径, 阅读器不需要 CJK 字体(理由见 docs/reference/output.md).
            "svg.fonttype": "path",
            # 晕渲栅格 base64 内嵌, 保证产物只有一个 .svg 文件.
            "svg.image_inline": True,
            # 内部 id 用固定盐, 重复出图内容一致.
            "svg.hashsalt": _HASHSALT,
            # 路径没写后缀时(不该发生)也落到 SVG, 不退回 PNG.
            "savefig.format": "svg",
        }
    )


def save_svg(
    fig,
    path: str | Path,
    *,
    dpi: float | None = None,
    embed_text: bool = True,
    placements: str | Path | None = "auto",
    **kwargs,
) -> Path:
    """把 Figure 保存为单个自包含的 SVG 文件, 返回写入的路径.

    path: 必须是 ``.svg`` 结尾; 传 PNG 会直接报错, 避免脚本漏改路径后
        又悄悄写出 PNG 产物.
    dpi: 只影响内嵌晕渲栅格的像素密度, 矢量元素与它无关. 缺省用 Figure
        自身的 dpi; 各脚本统一显式传 ``--dpi``(默认 300).
    embed_text: 默认 True, 文字以 ``<text>`` 写出并内嵌本图用到的字体子集, 这样
        产物里的文字可以选中/复制/检索, 也能在 Inkscape 里按内容直接改坐标;
        False 回到地把文字转成字形路径的老行为(任何查看器都不依赖字体, 但不
        能检索).
    placements: 手工标签布局文件. 缺省 ``"auto"``: 产物旁边存在同名的
        ``<name>.labels.json`` 就自动读取并施加, 不存在则照常出图(见
        ``docs/reference/labels.md``); 传路径则强制读取, 文件缺失直接报错;
        传 None 则忽略布局, 出纯默认位置.
    kwargs: 原样转给 ``Figure.savefig``, 例如 ``bbox_inches="tight"``.
    """
    import matplotlib

    from . import labels, svgtext

    path = Path(path)
    if path.suffix.lower() != SVG_SUFFIX:
        raise ValueError(
            f"项目只输出 SVG 产物, 不接受后缀 {path.suffix!r}: {path}"
        )
    document = _apply_label_placements(fig, path, placements, kwargs)

    # Date=None 让 matplotlib 不写 <dc:date>; 否则每次出图内容都不同.
    kwargs.setdefault("format", "svg")
    kwargs.setdefault("metadata", {"Date": None})
    if dpi is not None:
        kwargs.setdefault("dpi", dpi)

    if not embed_text:
        fig.savefig(path, **kwargs)
        _write_layout_marker(path, document)
        return path

    # 文字外置: 摘掉白色的 path effect → 用 fonttype="none" 写出 <text> →
    # 裁字体子集塞进 @font-face, 再把描边补成 CSS stroke. 任何一步失败都回退到
    # 字形路径写法, 保证出图不会因为本功能报错.
    state = svgtext.prepare_text(fig)
    previous = matplotlib.rcParams["svg.fonttype"]
    try:
        matplotlib.rcParams["svg.fonttype"] = "none"
        fig.savefig(path, **kwargs)
        svgtext.embed_font_subsets(path, state)
    except Exception as exc:  # noqa: BLE001 - 出图失败要降级而不是中断
        print(f"警告: 文字外置失败({exc}); 回退为字形路径: {path}")
        svgtext.restore_text(state)
        matplotlib.rcParams["svg.fonttype"] = "path"
        fig.savefig(path, **kwargs)
        _write_layout_marker(path, document)
        return path
    finally:
        matplotlib.rcParams["svg.fonttype"] = previous
        svgtext.restore_text(state)
    _write_layout_marker(path, document)
    return path


def _apply_label_placements(
    fig, path: Path, placements: str | Path | None, kwargs: dict
):
    """读取并施加手工标签布局, 返回被施加的 Placements(没有布局时返回 None).

    为什么放在 save_svg 里而不是让每个脚本自己调用: 布局是"产物的属性"而不是
    "绘图的步骤", 六个脚本共用一套行为才不会有人忘; 关闭方式也统一(传 None).
    """
    from . import labels

    if placements is None:
        return None
    if placements == "auto":
        source = labels.placement_path(path)
        if not source.is_file():
            return None
    else:
        source = Path(placements)
        if not source.is_file():
            raise FileNotFoundError(f"指定的标签布局文件不存在: {source}")

    document = labels.load(source)
    if document.figure and document.figure != path.name:
        print(
            f"警告: 标签布局记录的产物是 {document.figure!r}, "
            f"当前产物是 {path.name!r}; 请确认没有读错布局文件"
        )
    if not document:
        return None
    # 新增标注按"SVG 画布 = Figure 画布"定位; bbox_inches="tight" 会改变画布尺寸,
    # 坐标会整体错位. 这里直接拒绝, 不悄悄画歪.
    if document.added and kwargs.get("bbox_inches") not in (None, "none"):
        raise ValueError(
            "布局文件里有新增标注, 其坐标以整张 Figure 为基准, "
            "不支持 bbox_inches='tight'"
        )
    labels.apply(fig, document)
    return document


def _write_layout_marker(path: Path, document) -> None:
    """把"这张图实际施加了哪份布局"记进 SVG 注释.

    编辑器靠它区分"布局已经烤进图里"和"布局比 SVG 新", 才不会把同一段位移叠加
    两遍; 标记本身只是注释, 对查看器没有任何影响(见 ``docs/reference/labels.md``).
    """
    if document is None:
        return
    from . import labels

    labels.write_marker(path, document)
