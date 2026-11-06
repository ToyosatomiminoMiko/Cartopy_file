# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Shared code for the Cartopy_file project; see ``docs/overview.md``.

本仓只做地理: 数据定位、数据集清单、实例规格、地形/晕渲、边界重合剪枝与纯几何 SVG 出图;
文字与版面由 miko_svg_editor 的前端排版接管, 所以这里不再导出字体/标签相关符号.

只重导出「纯数据/纯标准库」模块: 导入本包不该连带拉进 matplotlib/cartopy, 否则数据准备
脚本与 tools/ 里的检查脚本会被迫承担绘图栈的启动成本(见 docs/add-map.md).
"""

from __future__ import annotations

from .data import (
    configure_cartopy,
    natural_earth_paths,
    prepare_matplotlib_env,
    project_root,
    shared_data_dir,
    subproject_dirs,
)
from .datasets import CheckLine, Dataset, DatasetSet, dataset_set
from .output import SVG_SUFFIX, apply_svg_output, save_svg
from .sources import Source, source
from .spec import (
    City,
    Extent,
    Graticule,
    Label,
    Projection,
    Relief,
    Sheet,
    sheets_of,
)

__all__ = [
    "CheckLine",
    "City",
    "Dataset",
    "DatasetSet",
    "Extent",
    "Graticule",
    "Label",
    "Projection",
    "Relief",
    "SVG_SUFFIX",
    "Sheet",
    "Source",
    "apply_svg_output",
    "configure_cartopy",
    "dataset_set",
    "natural_earth_paths",
    "prepare_matplotlib_env",
    "project_root",
    "save_svg",
    "shared_data_dir",
    "sheets_of",
    "source",
    "subproject_dirs",
]
