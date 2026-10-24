#!/usr/bin/python3
# -*- coding: utf-8 -*-


import cartopy.crs as ccrs
import matplotlib.pyplot as plt

# 全局字体: 由项目包 cartopy_file 统一提供, 中英文字体与其他脚本一致.
from cartopy_file.fonts import apply_matplotlib_fonts

apply_matplotlib_fonts()

f = plt.figure(figsize=(16,9))
ax = plt.axes(projection=ccrs.Robinson())
ax.stock_img()

# Confidential Association

plt.show()

