# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""AmericaArmy 基地点位演示图: 世界底图 + data.geojson 里的基地经纬度点位.

是什么: 早期演示脚本, 只弹窗看效果, 不落盘, 不在维护范围.
为什么: 底图要素显式钉死 Natural Earth 110m, 与 ``download_data.py`` 的预取清单一致;
cartopy 的 ``cfeature.*`` 默认用 AdaptiveScaler, 会按当前视野自动换成 50m/10m,
在窗口里缩放重绘时就会联网下载(50m 不在预取清单里), 违背"出图时不联网"的约定.
完整说明见 ``docs/data-preparation.md``(预取清单)与 ``docs/reference/data.md``(缓存定位).
"""

from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy, prepare_matplotlib_env

prepare_matplotlib_env()

import json  # 解析 data.geojson

import matplotlib.pyplot as plt

import cartopy.crs as ccrs
import cartopy.feature as cfeature

# cartopy 底图缓存统一到仓库 data/cartopy(见 docs/reference/data.md).
configure_cartopy()

# 脚本所在目录; 数据路径以它为准, 不依赖当前工作目录.
ROOT = Path(__file__).resolve().parent

# 底图分辨率: 预取清单只准备了 110m(见 docs/data-preparation.md), 显式钉死,
# 让缩放只改变显示范围, 不改变分辨率, 也就不会触发下载.
SCALE = "110m"


def main() -> None:
    with (ROOT / "data.geojson").open("r", encoding="utf-8") as f:
        data = json.load(f)

    # 名字,经度,纬度;GeoJSON 坐标顺序固定为 [经度, 纬度]
    points = [
        [feat["properties"]["name"], *feat["geometry"]["coordinates"]]
        for feat in data["features"]
    ]

    fig = plt.figure(figsize=(10, 7.5))
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    # 世界范围与 110m 分辨率配套: 固定视野, 避免任何"按范围自动选分辨率"的余地.
    ax.set_global()
    ax.stock_img()

    # with_scale 返回一份固定 Scaler 的要素, 缩放重绘时不会再去解析视野.
    for feature, style in (
        (cfeature.LAND, {}),
        (cfeature.OCEAN, {}),
        (cfeature.COASTLINE, {}),
        (cfeature.BORDERS, {"linestyle": ":"}),
        (cfeature.LAKES, {"alpha": 0.5}),
        (cfeature.RIVERS, {}),
    ):
        ax.add_feature(feature.with_scale(SCALE), **style)

    # 经纬度符号约定: E 东经为正, W 西经为负, N 北纬为正, S 南纬为负.
    for _, lon, lat in points:
        ax.plot(lon, lat, "+", transform=ccrs.PlateCarree())

    plt.show()


if __name__ == "__main__":
    main()
