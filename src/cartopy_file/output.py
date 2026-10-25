#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# output.py
# 项目统一的出图格式: 所有地图产物都保存为 SVG, 不再输出 PNG.
# 属于可安装的项目包 cartopy_file, 是所有绘图脚本唯一的出图入口.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Project-wide figure output: SVG only.

是什么:
    - ``apply_svg_output()``: 在导入 matplotlib 之后调用一次, 把 SVG 相关的
      rcParams 固定成本项目要求的取值;
    - ``save_svg()``: 把 Figure 保存成单个 ``.svg`` 文件, 并强制后缀为
      ``.svg``(防止某个脚本漏改路径又生成 PNG).

为什么统一用 SVG:
    1. 地图上的文字、国界/州界、河流、填色、经纬网都是矢量. PNG 在 300 dpi
       下放大会糊, 而 SVG 任意缩放都清晰, 排版时也不会因为再采样丢细节;
       文字宽度用 pt 定义, 与 dpi 无关, 换输出尺寸不用重调字号.
    2. 唯一无法矢量化的是山体晕渲: ``relief.make_relief`` 用高程数组算出
       RGB 栅格, 它本来就没有边界可描. matplotlib 会把它编码成 PNG 并以
       base64 内嵌进 SVG(``svg.image_inline=True``), 所以产物仍然只有一个
       自包含的 ``.svg`` 文件, 不会在旁边再掉一个 ``_1.png``.
       ``--dpi`` 参数因此只影响这块内嵌栅格的分辨率, 矢量部分与它无关.
    3. ``svg.fonttype="path"``: 汉字转成字形路径轮廓. 这样阅读器(浏览器、
       Inkscape、Word)不需要装 Noto Sans Mono CJK SC 也能正确显示, 不会出现
       方框/替换字体; 代价是 SVG 里的文字不能选中和检索. 本项目要的是
       "换台机器打开也一模一样"的成品图, 所以取前者.
    4. ``metadata={"Date": None}`` + 固定 ``svg.hashsalt``: 同一份数据重复出图
       得到相同内容(SVG 里不再写生成时间, 内部 id 也不再随机), 提交到 git
       不会每次刷新时间戳和 id 而造成无意义改动.

警告:
    本模块不设置 ``MPLCONFIGDIR``. 调用方仍必须在导入 matplotlib 之前调用
    ``cartopy_file.data.prepare_matplotlib_env()``, 否则本机只读的
    ``~/.config`` 会让 matplotlib 每次重建字体缓存.
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
    """
    import matplotlib

    matplotlib.rcParams.update(
        {
            # 汉字转路径, 阅读器不需要 CJK 字体(见模块说明第 3 条).
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
    **kwargs,
) -> Path:
    """把 Figure 保存为单个自包含的 SVG 文件, 返回写入的路径.

    path: 必须是 ``.svg`` 结尾; 传 PNG 会直接报错, 避免脚本漏改路径后
        又悄悄写出 PNG 产物.
    dpi: 只影响内嵌晕渲栅格的像素密度, 矢量元素与它无关. 缺省用 Figure
        自身的 dpi; 各脚本统一显式传 ``--dpi``(默认 300).
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
