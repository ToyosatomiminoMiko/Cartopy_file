# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""USSR subproject: the render spec of the USSR topography map.

是什么: 苏联图的规格(画框,投影,色带,经纬网,文案). 数据清单与下载范围已拆到数据项目
miko_gis_data, 这里只留绘图需要的数值.
完整说明见 ``docs/reference/spec.md``; 投影/范围/数据源的设计取舍见 ``docs/maps/ussr.md``.
"""

from __future__ import annotations

from pathlib import Path

from cartopy_file.spec import Extent, Graticule, Projection, Relief, Sheet, sheets_of

ROOT = Path(__file__).resolve().parent

# 数据项目 miko_gis_data 里这个区域的 manifest 键(group).
DATA_GROUP = "ussr"

# ============================
# 画框
# ============================
# 苏联全境: 经度 15°E 向东跨过 180° 到 165°W, 纬度 15°N~90°N.
# 为什么右端写 195 而不是 -165: cartopy 的 set_extent 不接受「最小值大于最大值」,
# 而 ERDDAP 的经度本来就是 0~360°, 同一个数(main 里 -165 + 360)可以直接用于下载.
EXTENT_USSR = Extent(15.0, 195.0, 15.0, 90.0)

# ============================
# 图规格
# ============================
# 兰勃特等面积方位投影: 以苏联主体附近 (105°E, 55°N) 为投影中心, 减少边缘形变.
# 注意: 旧成品副标题写的是「中心 90°E」, 那只是旧稿文案; 实际参数以这里为准.
PROJECTION_LAEA = Projection(
    "lambert_azimuthal_equal_area",
    {"central_longitude": 105.0, "central_latitude": 55.0},
)

# 高程配色: 改前成品直接用 matplotlib 的 terrain 色带, 范围 ±5000 m(陆海两端饱和),
# mode="scalar" 表示不合成晕渲, zorder=None 表示不传 zorder(留给 matplotlib 默认).
RELIEF_TERRAIN = Relief(
    vmin=-5000.0,
    vmax=5000.0,
    name="terrain",
    mode="scalar",
    ticks=(-4000, -2000, 0, 2000, 4000),
    title="Elevation",
    unit="m",
    alpha=0.9,
    zorder=None,
)

# 经纬网: 经度每 15°,纬度每 10°, 取值写死成旧脚本 FixedLocator 的精确位置
# (np.arange(15, 196, 15) / np.arange(20, 91, 10)); 多一条线 SVG 字节就会变.
GRATICULE_15X10 = Graticule(
    lon_step=15.0,
    lat_step=10.0,
    lon_ticks=(
        15.0,
        30.0,
        45.0,
        60.0,
        75.0,
        90.0,
        105.0,
        120.0,
        135.0,
        150.0,
        165.0,
        180.0,
        195.0,
    ),
    lat_ticks=(20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0),
    # 网线颜色原样传给 ax.gridlines("gray" 与 #808080 不是同一个颜色值);
    # stroke 是写进 geo.graticule.style 的 #rrggbb 副本, 两边必须同色.
    color="gray",
    stroke="#808080",
    width_pt=0.8,
    opacity=0.6,
    # 旧脚本的 gridlines 用默认 zorder(2), 这里保持同一个叠放位置.
    zorder=2.0,
)

SHEET_USSR = Sheet(
    id="ussr",
    out="ussr_topography_etopo2022_lambert_azimuthal.svg",
    extent=EXTENT_USSR,
    projection=PROJECTION_LAEA,
    figsize=(16.0, 12.0),
    # 版式就是 plt.subplots 默认布局; 旧脚本在量地图框前先调 plt.tight_layout(),
    # runner 用 tight_layout=True 保留这个顺序.
    axes=None,
    tight_layout=True,
    # 本图不铺共享海陆底色(旧成品四角是白的), 国界与海岸线由脚本自己画.
    basemap=False,
    relief=RELIEF_TERRAIN,
    graticule=GRATICULE_15X10,
    dpi=300,
    dataset_ids=("etopo-ussr", "ne-countries-10m", "ne-coastline-110m"),
    dem_id="etopo-ussr",
    # 旧成品没有地名/城市点/图例, 这些字段保持空, 免得前端初始化出旧图没有的版面.
    # 旧成品只有经纬网线,没有刻度文字: 交给 standard_collect 时只登记线型.
    graticule_ticks=False,
    title="USSR (ETOPO 2022,本地 NetCDF)",
    subtitle="兰勃特等面积方位投影(平面/方位投影)|中心 90°E, 55°N",
    colorbar_title="Elevation",
)

SHEETS = sheets_of([SHEET_USSR])
