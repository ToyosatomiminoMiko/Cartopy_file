# -*- coding: utf-8 -*-
# ============================================================
# __init__.py
# 项目共享代码包. 目前只包含 fonts: 所有绘图脚本共用的全局字体设置.
# 之所以做成可安装的包: 脚本分布在 AmericaArmy/ 等子目录里, 直接运行时
# 只有脚本所在目录在 sys.path 上; 把共享代码放进已安装的包里, 各脚本
# 用普通的 import 即可, 不必再用 sys.path.insert 操作外层目录.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Shared code for the Cartopy_file project."""

from __future__ import annotations

from .fonts import CJK_FONT, FALLBACK_FONT, LATIN_FONT, apply_matplotlib_fonts

__all__ = [
    "CJK_FONT",
    "FALLBACK_FONT",
    "LATIN_FONT",
    "apply_matplotlib_fonts",
]
