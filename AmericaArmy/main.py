import json

import matplotlib.pyplot as plt

import cartopy.crs as ccrs
import cartopy.feature as cfeature

with open("./AmericaArmy/data.geojson", "r", encoding="utf-8") as f:
    data = json.load(f)

# 名字,经度,纬度;GeoJSON 坐标顺序固定为 [经度, 纬度]
points = [
    [feat["properties"]["name"], *feat["geometry"]["coordinates"]]
    for feat in data["features"]
]


fig = plt.figure(figsize=(10, 7.5))
ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
# 东,西,,
# ax.set_extent([-180, 0, 10, 80], crs=ccrs.PlateCarree())
ax.stock_img()
# ax.set_global()

ax.add_feature(cfeature.LAND)
ax.add_feature(cfeature.OCEAN)
ax.add_feature(cfeature.COASTLINE)
ax.add_feature(cfeature.BORDERS, linestyle=":")
ax.add_feature(cfeature.LAKES, alpha=0.5)
ax.add_feature(cfeature.RIVERS)

"""
E:东经+
W:西经-
N:北纬+
S:南纬-
"""
# ax.plot([-0.08, 132], [51.53, 43.17], transform=ccrs.PlateCarree())
# ax.plot([-0.08, 132], [51.53, 43.17], transform=ccrs.Geodetic())
# ax.plot(-116.14816944444445,34.295252777777776 , '.', transform=ccrs.PlateCarree())

for name, lon, lat in points:
    ax.plot(lon, lat, "+", transform=ccrs.PlateCarree())

plt.show()
