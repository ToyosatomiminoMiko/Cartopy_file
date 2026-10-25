#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Compatibility shim: Myanmar scripts import the shared relief helpers from here.

是什么: 缅甸系列地形图的共用绘图工具入口(读取 ETOPO 高程、生成晕渲、读取国界、
铺海陆底色); 实现已上移到 cartopy_file.relief, 这里只保留导入名与缓存目录设置.
完整说明(为什么保留这个兼容层)见 ``docs/Myanmar/map_lib.md``.
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
