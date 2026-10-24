#!/usr/bin/python3
# -*- coding: utf-8 -*-


import cartopy.crs as ccrs
import matplotlib.pyplot as plt

# 全局字体: 根目录 fonts.py 是项目里唯一的字体设置来源, 中英文字体统一.
from fonts import apply_matplotlib_fonts

apply_matplotlib_fonts()

f = plt.figure(figsize=(16,9))
ax = plt.axes(projection=ccrs.Robinson())
ax.stock_img()

# Confidential Association

plt.show()

