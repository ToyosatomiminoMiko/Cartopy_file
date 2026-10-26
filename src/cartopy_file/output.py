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
    kwargs: 原样转给 ``Figure.savefig``, 例如 ``bbox_inches="tight"``.
    """
    import matplotlib

    from . import svgtext

    path = Path(path)
    if path.suffix.lower() != SVG_SUFFIX:
        raise ValueError(
            f"项目只输出 SVG 产物, 不接受后缀 {path.suffix!r}: {path}"
        )

    # Date=None 让 matplotlib 不写 <dc:date>; 否则每次出图内容都不同.
    kwargs.setdefault("format", "svg")
    kwargs.setdefault("metadata", {"Date": None})
    if dpi is not None:
        kwargs.setdefault("dpi", dpi)

    if not embed_text:
        fig.savefig(path, **kwargs)
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
        return path
    finally:
        matplotlib.rcParams["svg.fonttype"] = previous
        svgtext.restore_text(state)
    return path
