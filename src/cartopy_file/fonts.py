#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ============================================================
# fonts.py
# 项目全局字体设置: 汉字用 Noto Sans Mono CJK SC,
# 英文与数字用 JetBrainsMonoSlashed-Medium.
# 属于可安装的项目包 cartopy_file, 是所有绘图脚本唯一的字体来源.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Project-wide matplotlib font configuration.

字体文件与 matplotlib 字体名的对应关系(matplotlib 按字体名表里的 family
字段匹配, 不是按文件名, 所以这里不能直接写字体文件名):
    JetBrainsMonoSlashed-Medium -> "JetBrains Mono Slashed Medium"
    Noto Sans Mono CJK SC       -> "Noto Sans Mono CJK SC"

中英文如何各自生效: matplotlib >= 3.6 支持逐字符回退. 把 ``font.family``
设成一个字体列表, 渲染每个字符时依次查找: 拉丁字母和数字命中第一个
JetBrains 字体, 汉字命中第二个 Noto 字体, 两者都没有的字符再回退
DejaVu Sans.
坑: 不能写成 ``font.family = "sans-serif"`` + ``font.sans-serif = [...]``.
通用族别名(sans-serif 等)只会被解析成单个字体, 不参与逐字符回退, 结果
汉字会报 "Glyph missing" 警告并画成方框.

用法: 本模块属于项目包 cartopy_file(源码在 src/cartopy_file/). 脚本能
``import cartopy_file`` 的前提是项目已以可编辑模式安装进当前环境:

    uv pip install -e .

之后在导入 matplotlib 之后、创建任何文字之前调用一次(可重复调用):

    from cartopy_file.fonts import apply_matplotlib_fonts
    apply_matplotlib_fonts()
"""

from __future__ import annotations

CJK_FONT = "Noto Sans Mono CJK SC"
LATIN_FONT = "JetBrains Mono Slashed Medium"
# 前两个字体都缺字时的兜底字体; 同时保证字体链最后一级总是存在.
FALLBACK_FONT = "DejaVu Sans"

__all__ = ["CJK_FONT", "LATIN_FONT", "FALLBACK_FONT", "apply_matplotlib_fonts"]


def apply_matplotlib_fonts() -> None:
    """把项目字体写入 matplotlib 的全局 rcParams.

    每次调用都重新检查字体是否已安装: 缺 JetBrains 或 Noto 时打印警告并
    自动缩短字体链, 让脚本在没装字体的机器上仍能出图(只是回退字体),
    而不是直接抛异常.
    """
    import matplotlib
    from matplotlib import font_manager

    installed = {font.name for font in font_manager.fontManager.ttflist}
    family = [
        name
        for name in (LATIN_FONT, CJK_FONT, FALLBACK_FONT)
        if name in installed
    ]
    if not family:
        family = [FALLBACK_FONT]

    missing = [name for name in (LATIN_FONT, CJK_FONT) if name not in installed]
    if missing:
        print(f"警告: 未找到字体 {missing}; 已用可用字体回退, 请安装后重试.")

    # 逐字符回退: 拉丁/数字 -> JetBrains, 汉字 -> Noto, 其余 -> DejaVu.
    matplotlib.rcParams["font.family"] = family
    # 用 ASCII 负号: 项目内所有地图统一, 避免不同字体的 U+2212 字宽不一致.
    matplotlib.rcParams["axes.unicode_minus"] = False
