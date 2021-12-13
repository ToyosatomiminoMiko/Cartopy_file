#!/usr/bin/python3
# -*- coding: utf-8 -*-


import cartopy.crs as ccrs
import matplotlib.pyplot as plt

f = plt.figure(figsize=(16,9))
ax = plt.axes(projection=ccrs.Robinson())
ax.stock_img()

plt.show()

