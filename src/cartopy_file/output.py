# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""项目统一的 SVG 出图入口 (纯几何地图).

是什么: ``apply_svg_output`` 固定与 SVG 有关的 rcParams, ``save_svg`` 把 Figure 保存成单个
自包含的 ``.svg``; 产物只含地理图形, 不再有任何文字、图例、色标、标题、刻度文字或字体.

为什么: 文字与版面由另一个仓库 (miko_svg_editor) 的前端排版接管, 本仓只负责地理;
因此这里不再做文字外置/字体子集/标签布局, 也不写 ``@font-face``. 内嵌的晕渲栅格仍以
base64 内联, 保证产物始终只有一个 ``.svg`` 文件.

完整说明(为什么统一 SVG、确定性是怎么保证的)见 ``docs/reference/output.md``.
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
    matplotlib 的默认值, 是为了让"栅格内嵌 / 时间戳不写 / 落到 SVG"这三条约定
    集中在本文件里; 换 matplotlib 版本或用户自己的 matplotlibrc 也改不掉.
    """
    import matplotlib

    matplotlib.rcParams.update(
        {
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
    **kwargs,
) -> Path:
    """把 Figure 保存为单个自包含的纯几何 SVG 文件, 返回写入的路径.

    path: 必须是 ``.svg`` 结尾; 传别的后缀直接报错, 避免脚本漏改路径后又悄悄写出 PNG.
    dpi: 只影响内嵌晕渲栅格的像素密度, 矢量元素与它无关. 缺省用 Figure 自身的 dpi;
        各脚本统一显式传 ``--dpi``(默认 300).
    kwargs: 原样转给 ``Figure.savefig``, 例如 ``bbox_inches="tight"``.
    """
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
    fig.savefig(path, **kwargs)
    return path
