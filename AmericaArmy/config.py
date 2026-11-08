# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""AmericaArmy demo subproject: one local GeoJSON and one demonstration sheet.

是什么: 框架用法的最小示例--一份仓库自带的点位 GeoJSON,一个 ``Sheet``, 以及
``main.py`` 里的一对 ``draw``/``collect`` 回调; 它走和正式图种完全相同的出图流水线
(纯几何 SVG + 同名 geo.json), 但不在图种目录体系内.
为什么单独留一个演示: 新增子项目时最容易漏掉的就是「config 里写什么,回调里写什么」,
这个目录就是可运行的最小答案, 见 ``docs/add-map.md`` 与 ``docs/reference/spec.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

from cartopy_file.datasets import Dataset, dataset_set
from cartopy_file.spec import Extent, Graticule, Label, Projection, Sheet

ROOT = Path(__file__).resolve().parent

# 仓库自带的点位数据(不入 data/raw, 也不下载), 见 docs/data-preparation.md.
BASES = json.loads((ROOT / "data.geojson").read_text(encoding="utf-8"))["features"]

# 演示图直接用 cartopy 的固定分辨率要素; 这些层必须登记, 否则根目录 download_data.py
# 不会预取,清单 --check 也发现不了, 出图时才联网下载(违反"出图不联网"), 或者离线直接失败.
NE_BASEMAP = (
    Dataset(
        id="ne-110m-land",
        kind="cartopy-ne",
        source_id="natural-earth",
        resolution="110m",
        category="physical",
        name="land",
        note="Natural Earth 110m 陆地(演示底图)",
    ),
    Dataset(
        id="ne-110m-ocean",
        kind="cartopy-ne",
        source_id="natural-earth",
        resolution="110m",
        category="physical",
        name="ocean",
        note="Natural Earth 110m 海洋(演示底图)",
    ),
    Dataset(
        id="ne-110m-coastline",
        kind="cartopy-ne",
        source_id="natural-earth",
        resolution="110m",
        category="physical",
        name="coastline",
        note="Natural Earth 110m 海岸线(演示底图)",
    ),
    Dataset(
        id="ne-110m-borders",
        kind="cartopy-ne",
        source_id="natural-earth",
        resolution="110m",
        category="cultural",
        name="admin_0_boundary_lines_land",
        note="Natural Earth 110m 国界(演示底图)",
    ),
    Dataset(
        id="ne-110m-lakes",
        kind="cartopy-ne",
        source_id="natural-earth",
        resolution="110m",
        category="physical",
        name="lakes",
        note="Natural Earth 110m 湖泊(演示底图)",
    ),
    Dataset(
        id="ne-110m-rivers",
        kind="cartopy-ne",
        source_id="natural-earth",
        resolution="110m",
        category="physical",
        name="rivers_lake_centerlines",
        note="Natural Earth 110m 河流(演示底图)",
    ),
)

DATASETS = dataset_set(
    "美军基地",
    ROOT,
    [
        Dataset(
            id="bases-geojson",
            kind="local",
            dest="data.geojson",
            note="基地点位 GeoJSON(仓库自带)",
        ),
        *NE_BASEMAP,
    ],
)

# 世界范围; 与 110m 分辨率配套, 固定视野, 不留给 AdaptiveScaler 自动换分辨率的余地.
WORLD = Extent(-180.0, 180.0, -90.0, 90.0)

# 演示图没有高程数据, 所以 relief=None; 点位名称只登记进 geo.labels, 不画文字.
SHEET_WORLD = Sheet(
    id="america-army",
    out="america_army_bases.svg",
    extent=WORLD,
    projection=Projection("plate_carree"),
    figsize=(10, 7.5),
    graticule=Graticule(
        lon_step=30.0,
        lat_step=30.0,
        lon_ticks=(-180.0, -150.0, -120.0, -90.0, -60.0, -30.0, 0.0, 30.0, 60.0, 90.0, 120.0, 150.0),
        lat_ticks=(-90.0, -60.0, -30.0, 0.0, 30.0, 60.0),
        width_pt=0.4,
        opacity=0.35,
    ),
    relief=None,
    basemap=False,
    dataset_ids=("bases-geojson", *(item.id for item in NE_BASEMAP)),
    labels=tuple(
        Label(
            feature["geometry"]["coordinates"][0],
            feature["geometry"]["coordinates"][1],
            feature["properties"]["name"],
            # id 用数据里的行号(基地名是中文, properties.id 在各州内会重复, 不能当 id);
            # 显示名仍在 text.
            name=f"base-{index}",
            role="city",
            # 世界图上一个点只有几像素, 偏移按屏幕可读性定, 不是地理量.
            dx=3.0,
            dy=1.0,
            ha="left",
        )
        for index, feature in enumerate(BASES, start=1)
    ),
    title="美军基地点位演示",
    subtitle="Natural Earth 110m 世界底图 | 等距圆柱投影(PlateCarree)",
    notes=("演示子项目: 点位来自 AmericaArmy/data.geojson, 只用于演示框架用法.",),
)

SHEETS = (SHEET_WORLD,)
