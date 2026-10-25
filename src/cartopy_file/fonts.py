#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Project-wide matplotlib font configuration.

是什么: 设置全项目字体(拉丁/数字 JetBrains Mono Slashed Medium, 汉字 Noto Sans Mono CJK SC).
完整说明(字体名对应、逐字符回退原理、font.sans-serif 的坑、安装与用法)见
``docs/reference/fonts.md``.
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
