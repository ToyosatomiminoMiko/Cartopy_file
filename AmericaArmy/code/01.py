import matplotlib.pyplot as plt

import cartopy.crs as ccrs
import cartopy.feature as cfeature

from time import sleep
from longlat import ffloat

list = []
with open('baseinfo.txt', 'r', encoding='utf-8') as f:
    for line in f.readlines():
        l = line.split('\n')[0].split(' ', 1)
        if 'N' in l[1]:
            l0 = l[1].split('N')
            l0[0] += 'N'
        elif 'S' in l[1]:
            l0 = l[1].split('S')
            l0[0] += 'S'
        # 名字，经度，纬度
        name, long, lat = l[0], ''.join(l0[0].split(' ')), ''.join(l0[1].split(' '))
        list.append([name, ffloat(long), ffloat(lat)])

'''
fig = plt.figure(figsize=(10, 5))
ax = fig.add_subplot(1, 1, 1, projection=ccrs.Robinson())
#使地图成为全局地图，而不是将其范围放大到任何绘制数据的范围
ax.set_global()
ax.stock_img()
ax.coastlines()
'''

fig = plt.figure(figsize=(10, 7.5))
ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
# 东,西,,
# ax.set_extent([-180, 0, 10, 80], crs=ccrs.PlateCarree())
ax.stock_img()
# ax.set_global()

ax.add_feature(cfeature.LAND)
ax.add_feature(cfeature.OCEAN)
ax.add_feature(cfeature.COASTLINE)
ax.add_feature(cfeature.BORDERS, linestyle=':')
ax.add_feature(cfeature.LAKES, alpha=0.5)
ax.add_feature(cfeature.RIVERS)

'''
E:东经+
W:西经-
N:北纬+
S:南纬-
'''
# ax.plot([-0.08, 132], [51.53, 43.17], transform=ccrs.PlateCarree())
# ax.plot([-0.08, 132], [51.53, 43.17], transform=ccrs.Geodetic())
# ax.plot(-116.14816944444445,34.295252777777776 , '.', transform=ccrs.PlateCarree())

for i in list:
    ax.plot(i[2], i[1], '.', transform=ccrs.PlateCarree())

plt.show()
