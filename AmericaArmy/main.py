# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy, prepare_matplotlib_env

prepare_matplotlib_env()

import json

import matplotlib.pyplot as plt

import cartopy.crs as ccrs
import cartopy.feature as cfeature

# cartopy 底图缓存统一到仓库 data/cartopy(见 docs/reference/data.md).
configure_cartopy()

# 全局字体: 由项目包 cartopy_file 统一提供, 与其他绘图脚本一致.
from cartopy_file.fonts import apply_matplotlib_fonts

apply_matplotlib_fonts()

with open("./AmericaArmy/data.geojson", "r", encoding="utf-8") as f:
    data = json.load(f)

# 名字,经度,纬度;GeoJSON 坐标顺序固定为 [经度, 纬度]
points = [
    [feat["properties"]["name"], *feat["geometry"]["coordinates"]]
    for feat in data["features"]
]


fig = plt.figure(figsize=(10, 7.5))
ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
ax.stock_img()

ax.add_feature(cfeature.LAND)
ax.add_feature(cfeature.OCEAN)
ax.add_feature(cfeature.COASTLINE)
ax.add_feature(cfeature.BORDERS, linestyle=":")
ax.add_feature(cfeature.LAKES, alpha=0.5)
ax.add_feature(cfeature.RIVERS)

# 经纬度符号约定: E 东经为正, W 西经为负, N 北纬为正, S 南纬为负.
for _, lon, lat in points:
    ax.plot(lon, lat, "+", transform=ccrs.PlateCarree())

plt.show()
