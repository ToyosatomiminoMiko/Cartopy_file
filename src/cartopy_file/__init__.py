# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Shared code for the Cartopy_file project; see ``docs/overview.md``.

本仓只做地理: 数据定位、地形/晕渲、边界重合剪枝与纯几何 SVG 出图; 文字与版面由
miko_svg_editor 的前端排版接管, 所以这里不再导出字体/标签相关符号.
"""

from __future__ import annotations

from .data import (
    configure_cartopy,
    natural_earth_paths,
    prepare_matplotlib_env,
    project_root,
    shared_data_dir,
)
from .output import SVG_SUFFIX, apply_svg_output, save_svg

__all__ = [
    "SVG_SUFFIX",
    "apply_svg_output",
    "configure_cartopy",
    "natural_earth_paths",
    "prepare_matplotlib_env",
    "project_root",
    "save_svg",
    "shared_data_dir",
]
