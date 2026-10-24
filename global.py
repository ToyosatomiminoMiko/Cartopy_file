#!/usr/bin/python3
# -*- coding: utf-8 -*-


# 缓存目录必须在导入 matplotlib 之前指定; 本机 ~/.config 只读, 不能写默认位置.
# (见 cartopy_file.data)
from cartopy_file.data import configure_cartopy, prepare_matplotlib_env

prepare_matplotlib_env()

import cartopy.crs as ccrs
import matplotlib.pyplot as plt

# cartopy 的 Natural Earth 底图缓存统一到仓库 data/cartopy(见 cartopy_file.data).
configure_cartopy()

# 全局字体: 由项目包 cartopy_file 统一提供, 中英文字体与其他脚本一致.
from cartopy_file.fonts import apply_matplotlib_fonts

apply_matplotlib_fonts()

f = plt.figure(figsize=(16,9))
ax = plt.axes(projection=ccrs.Robinson())
ax.stock_img()

# Confidential Association

plt.show()

