# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Shared code for the Cartopy_file project; see ``docs/overview.md``.

本仓只做地理: 读数据清单,实例规格,地形/晕渲,边界重合剪枝与纯几何 SVG 出图; 数据获取/
下载/入库在独立项目 miko_gis_data, 本包不下载任何东西.
文字与版面由 miko_svg_editor 的前端排版接管, 所以这里不再导出字体/标签相关符号.

只重导出「纯数据/纯标准库」模块: 导入本包不该连带拉进 matplotlib/cartopy, 否则
tools/ 里的检查脚本会被迫承担绘图栈的启动成本(见 docs/add-map.md).
"""

from __future__ import annotations

from .catalog import Catalog, DatasetView, SourceInfo, catalog_for
from .data import (
    configure_cartopy,
    data_root,
    manifest_path,
    natural_earth_paths,
    prepare_matplotlib_env,
    project_root,
    subproject_dirs,
)
from .output import SVG_SUFFIX, apply_svg_output, save_svg
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
    "Catalog",
    "City",
    "DatasetView",
    "Extent",
    "Graticule",
    "Label",
    "Projection",
    "Relief",
    "SVG_SUFFIX",
    "Sheet",
    "SourceInfo",
    "apply_svg_output",
    "catalog_for",
    "configure_cartopy",
    "data_root",
    "manifest_path",
    "natural_earth_paths",
    "prepare_matplotlib_env",
    "project_root",
    "save_svg",
    "sheets_of",
    "subproject_dirs",
]
