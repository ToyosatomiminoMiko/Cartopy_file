# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""AmericaArmy demo: world basemap + base markers, rendered through the shared pipeline.

是什么: 框架用法的最小示例——``config.py`` 里放数据清单与 Sheet, 本文件只写一对回调
(``draw`` 画图种特有图层, ``collect`` 登记 geo 元数据), 其余(建画布、定范围、量地图框、
保存纯几何 SVG 与同名 geo.json)由 ``cartopy_file.runner`` 统一完成.
为什么底图要素显式钉死 Natural Earth 110m: cartopy 的 ``cfeature.*`` 默认用
AdaptiveScaler, 会按当前视野自动换成 50m/10m, 缩放重绘时就会联网下载(50m 不在预取
清单里), 违背「出图时不联网」的约定. 这不是需要维护的图种, 只用来演示新增子项目
最少要写什么, 见 ``docs/add-map.md``.
"""

from __future__ import annotations

import os
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT.parent / "data" / ".mplcache"))

import cartopy.crs as ccrs
import cartopy.feature as cfeature

# 子项目配置(数据集清单 + Sheet), 见 docs/reference/spec.md.
import config

# 共享图层原语与统一出图流程, 见 docs/reference/layers.md / docs/reference/runner.md.
from cartopy_file import layers, runner

SHEET = config.SHEET_WORLD
DATASETS = config.DATASETS

# 预取清单只准备了 110m(见 docs/data-preparation.md), 这里钉死, 缩放也不换分辨率.
SCALE = "110m"


def draw(ctx: runner.RenderContext) -> None:
    """画世界底图要素与基地点位; 底图用 cfeature 是为了演示「固定分辨率」的写法."""
    for feature, style in (
        (cfeature.LAND, {}),
        (cfeature.OCEAN, {}),
        (cfeature.COASTLINE, {}),
        (cfeature.BORDERS, {"linestyle": ":"}),
        (cfeature.LAKES, {"alpha": 0.5}),
        (cfeature.RIVERS, {}),
    ):
        # with_scale 返回一份固定 Scaler 的要素, 缩放重绘时不会再去解析视野.
        ctx.ax.add_feature(feature.with_scale(SCALE), **style)

    # 经纬度符号约定: E 东经为正, W 西经为负, N 北纬为正, S 南纬为负.
    for feature in config.BASES:
        lon, lat = feature["geometry"]["coordinates"]
        ctx.ax.plot(lon, lat, "+", transform=ccrs.PlateCarree())

    layers.add_gridlines(ctx.ax, SHEET)


def collect(doc, ctx: runner.RenderContext) -> None:
    """登记 geo: 地名(基地名) + 经纬刻度 + 文案; 本图没有高程, 所以不登记色标."""
    layers.standard_collect(doc, ctx.ax, SHEET, DATASETS)


def main() -> None:
    runner.run(
        SHEET,
        root=ROOT,
        catalog=DATASETS,
        draw=draw,
        collect=collect,
        description=__doc__,
    )


if __name__ == "__main__":
    main()
