#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# map_lib.py
# 缅甸系列地形图共用的绘图工具入口: 读取 ETOPO 高程、生成晕渲配色、
# 读取 Natural Earth 国家边界、铺海陆底色.
# 实际实现已上移到项目共享包 cartopy_file.relief(乌克兰图也要用同一套算法),
# 本模块只保留缅甸脚本使用的导入名, 以及导入 matplotlib 前的缓存目录设置.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Compatibility shim: Myanmar scripts import the shared helpers from here.

为什么保留这个文件: myanmar.py / northern_shan.py 里写的是 ``import map_lib``,
函数名保持不变可以避免大范围改脚本; 具体实现见
``src/cartopy_file/relief.py``, 两个图种共用同一份代码.
"""

from __future__ import annotations

import os
from pathlib import Path

# matplotlib 的缓存目录必须在导入 matplotlib 之前确定; 本机 ~/.config 不可写.
# 放在 data/ 下(已被 .gitignore 忽略), 避免每次启动重建字体缓存.
# 各主脚本也会设置同样的路径; 这里再设一次是为了让本模块可被单独导入.
DATA_DIR = Path(__file__).resolve().parent / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

# 导入即注册共享实现; cartopy_file.relief 会导入 matplotlib/cartopy,
# 因此上面必须先把 MPLCONFIGDIR 设好.
from cartopy_file.relief import (  # noqa: E402 - 必须在设置 MPLCONFIGDIR 之后
    add_base_map,
    find_etopo,
    load_countries,
    load_elevation,
    make_relief,
)

__all__ = [
    "add_base_map",
    "find_etopo",
    "load_countries",
    "load_elevation",
    "make_relief",
]
