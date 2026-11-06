# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Myanmar subproject: dataset inventory and per-sheet render config.

是什么: 缅甸子项目的唯一配置入口——数据集清单(从哪下、版本、下载范围、本地路径)与
每张图的规格(画框、投影、色带、经纬网、地名、文案). 数据准备脚本与绘图脚本都从这里
取参数, 下载范围和绘图范围不会再各写一份.
完整说明(数据集层与实例规格层怎么分工)见 ``docs/reference/datasets.md`` 与
``docs/reference/spec.md``; 各图种的设计取舍见 ``docs/maps/myanmar.md`` 等页面.
"""

from __future__ import annotations

from pathlib import Path

from cartopy_file.datasets import Dataset, dataset_set
from cartopy_file.sources import erddap_url, ne_url
from cartopy_file.spec import City, Extent, Graticule, Label, Projection, Relief, Sheet

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# ============================
# 画框
# ============================
# 缅甸全境图: 国土约 92.17~101.17°E / 9.79~28.54°N, 四周各留约 5° 让邻国与海域进入画面.
EXTENT_MYANMAR = Extent(87.0, 106.0, 5.0, 31.0)
# 掸邦放大图: 画框比国土小, 数字取改前成品.
EXTENT_NORTHERN_SHAN = Extent(95.3, 101.5, 19.0, 24.75)
# 行政区划图: 画框也要容下整国轮廓与邻国参照.
EXTENT_ADMIN = Extent(91.0, 102.5, 8.8, 29.4)

# ETOPO 下载范围由画框外扩: 圆锥投影的矩形画框顶边会张开(详见 docs/data-preparation.md),
# 所以纬度方向也要留余量; 数字与改前的下载范围一致, 不能随手改(会让已下载的缓存作废).
ETOPO_BBOX_MYANMAR = EXTENT_MYANMAR.padded(lon=1.7, lat=0.1)
ETOPO_BBOX_NORTHERN_SHAN = Extent(94.6, 102.1, 18.8, 25.2)

# ============================
# 数据集
# ============================
# 共享缓存里的 Natural Earth 图层用 cartopy-ne: 只登记出处, 由 cartopy 的下载器管理,
# 全项目共用 data/cartopy 一份.
ETOPO_MYANMAR = Dataset(
    id="etopo-myanmar",
    kind="file",
    source_id="etopo-2022",
    url=erddap_url(
        "etopo-2022",
        stride=2,
        lon_range=(ETOPO_BBOX_MYANMAR.lon_min, ETOPO_BBOX_MYANMAR.lon_max),
        lat_range=(ETOPO_BBOX_MYANMAR.lat_min, ETOPO_BBOX_MYANMAR.lat_max),
    ),
    dest="raw/ETOPO_2022_v1_15s_myanmar_stride2.nc",
    files=("raw/ETOPO_2022_v1_15s_myanmar_stride*.nc",),
    bbox=ETOPO_BBOX_MYANMAR,
    stride=2,
    note="ETOPO 2022 缅甸区域高程(stride 2 = 30 弧秒)",
)

ETOPO_NORTHERN_SHAN = Dataset(
    id="etopo-northern-shan",
    kind="file",
    source_id="etopo-2022",
    url=erddap_url(
        "etopo-2022",
        stride=1,
        lon_range=(ETOPO_BBOX_NORTHERN_SHAN.lon_min, ETOPO_BBOX_NORTHERN_SHAN.lon_max),
        lat_range=(ETOPO_BBOX_NORTHERN_SHAN.lat_min, ETOPO_BBOX_NORTHERN_SHAN.lat_max),
    ),
    dest="raw/ETOPO_2022_v1_15s_northern_shan_stride1.nc",
    files=("raw/ETOPO_2022_v1_15s_northern_shan_stride*.nc",),
    bbox=ETOPO_BBOX_NORTHERN_SHAN,
    stride=1,
    note="ETOPO 2022 掸邦区域高程(15 弧秒)",
)

NE_COUNTRIES = Dataset(
    id="ne-countries-10m",
    kind="cartopy-ne",
    source_id="natural-earth",
    resolution="10m",
    category="cultural",
    name="admin_0_countries",
    version_file="ne_10m_admin_0_countries.VERSION.txt",
    note="Natural Earth 10m 国家多边形(海陆底色与国界轮廓)",
)

NE_COASTLINE = Dataset(
    id="ne-coastline-10m",
    kind="cartopy-ne",
    source_id="natural-earth",
    resolution="10m",
    category="physical",
    name="coastline",
    note="Natural Earth 10m 海岸线(国界剪掉沿海段的蒙版)",
)

NE_BORDERS = Dataset(
    id="ne-borders-10m",
    kind="cartopy-ne",
    source_id="natural-earth",
    resolution="10m",
    category="cultural",
    name="admin_0_boundary_lines_land",
    note="Natural Earth 10m 陆上国界(邻国参照线)",
)

NE_RIVERS = Dataset(
    id="ne-rivers-10m",
    kind="zip",
    source_id="natural-earth",
    # 这份是 5.0.0 的旧副本(改前成品就是它画的), 所以钉住版本而不是跟共享缓存走;
    # 换成 5.1.1 会改变河网几何, 属于要单独评审的改动(见 docs/reference/datasets.md).
    version="5.0.0",
    url=ne_url("10m", "physical", "rivers_lake_centerlines"),
    dest="raw/ne_10m_rivers_lake_centerlines",
    version_file="raw/ne_10m_rivers_lake_centerlines/ne_10m_rivers_lake_centerlines.VERSION.txt",
    files=("raw/ne_10m_rivers_lake_centerlines/ne_10m_rivers_lake_centerlines.shp",),
    note="Natural Earth 10m 河流(缅甸administrative图, 版本 5.0.0 旧副本)",
)

ADMIN_GEOJSON = Dataset(
    id="myanmar-admin1",
    kind="derived",
    dest="derived/myanmar_admin1.geojson",
    note="省/邦级行政区 GeoJSON(由 prepare_admin_data.py 生成)",
)

SHAN_REGIONS = Dataset(
    id="osm-shan-regions",
    kind="script",
    source_id="openstreetmap",
    dest="raw/regions/shan_north_boundaries.geojson",
    note="掸邦北部各特区/民地武控制区边界(Overpass 抓取)",
)

OSM_COUNTRY_BORDERS = Dataset(
    id="osm-country-borders",
    kind="script",
    source_id="openstreetmap",
    dest="raw/regions/osm_country_borders.geojson",
    note="画框附近国界(Overpass 抓取)",
)

GADM_MMR_RAW = Dataset(
    id="gadm41-mmr",
    kind="script",
    source_id="gadm-4.1",
    dest="raw/gadm41_MMR/gadm41_MMR_1.json",
    optional=True,
    note="GADM 4.1 缅甸一级行政区原始 JSON(生成 admin1 用)",
)

NAYPYIDAW_CACHE = Dataset(
    id="osm-naypyidaw",
    kind="script",
    source_id="openstreetmap",
    dest="raw/osm_naypyidaw_union_territory.json",
    optional=True,
    note="内比都联邦区 OSM 缓存",
)

DATASETS = dataset_set(
    "缅甸",
    DATA,
    [
        ETOPO_MYANMAR,
        ETOPO_NORTHERN_SHAN,
        NE_COUNTRIES,
        NE_COASTLINE,
        NE_BORDERS,
        NE_RIVERS,
        ADMIN_GEOJSON,
        SHAN_REGIONS,
        OSM_COUNTRY_BORDERS,
        GADM_MMR_RAW,
        NAYPYIDAW_CACHE,
    ],
)

# ============================
# 图规格
# ============================
# 兰勃特等角圆锥: 中央经线取国土中部 96.5°E, 标准纬线 10°N / 27°N, 全国范围比例误差最小.
PROJECTION_LCC = Projection(
    "lambert_conformal",
    {
        "central_longitude": 96.5,
        "central_latitude": 19.5,
        "standard_parallels": (10.0, 27.0),
    },
)

# 高程/水深双色带: 水面到 -1 m, 陆地从 +1 m 起, 0 m 处直接跳变——本图不画海岸线,
# 海陆界线就靠这条跳变(理由见 docs/maps/myanmar.md).
MYANMAR_RELIEF = Relief(
    vmin=-5000,
    vmax=5000,
    name="myanmar_relief",
    sea=(
        (-5000, "#06213d"),
        (-3500, "#0d3355"),
        (-2000, "#0f3c66"),
        (-1250, "#1b628f"),
        (-700, "#2f82b5"),
        (-300, "#5aa2cd"),
        (-100, "#75b3db"),
        (-20, "#8cc4e7"),
        (-1, "#a2d0ee"),
    ),
    land=(
        (1, "#dce4a2"),
        (75, "#dde3a4"),
        (175, "#e8dd92"),
        (300, "#dbc786"),
        (500, "#c8aa72"),
        (800, "#ad8a5f"),
        (1100, "#937147"),
        (1500, "#7d613e"),
        (2000, "#84725c"),
        (3000, "#b9aa97"),
        (4200, "#dddad2"),
        (5000, "#f6f5f1"),
    ),
    ticks=(-4000, -2000, 0, 2000, 4000),
    title="高程 / 水深",
    unit="m",
)

# 经纬网: 经度每 3°、纬度每 5°; 取值写死成网线的精确位置(与改前 FixedLocator 一致).
GRATICULE_3X5 = Graticule(
    lon_step=3.0,
    lat_step=5.0,
    lon_ticks=(87.0, 90.0, 93.0, 96.0, 99.0, 102.0, 105.0),
    lat_ticks=(5.0, 10.0, 15.0, 20.0, 25.0, 30.0),
    stroke="#808080",
    width_pt=0.6,
    opacity=0.55,
)

# 地名: 邻国名 -> 海域名 -> 国名 -> 城名(顺序就是前端叠放顺序).
# 字号是生成端唯一保留的样式数据; 颜色/描边由前端 role 表决定.
MYANMAR_LABELS = (
    Label(99.6, 29.9, "中国", role="country", font_size_pt=13.0),
    Label(89.2, 25.4, "印度", role="country", font_size_pt=13.0),
    Label(89.6, 22.8, "孟加拉国", role="country", font_size_pt=13.0),
    Label(101.3, 16.0, "泰国", role="country", font_size_pt=13.0),
    Label(103.4, 19.6, "老挝", role="country", font_size_pt=13.0),
    Label(89.8, 15.8, "孟加拉湾", role="sea", font_size_pt=12.0),
    Label(96.8, 9.3, "安达曼海", role="sea", font_size_pt=12.0),
    Label(95.6, 23.5, "缅甸", role="country-name", font_size_pt=22.0),
    # 城名贴在城点左下: 旧版是 (城点 + 0.18°E, -0.05°N) + ha="left".
    Label(96.10 + 0.18, 19.75 - 0.05, "内比都", role="city", font_size_pt=10.0, ha="left"),
    Label(96.16 + 0.18, 16.87 - 0.05, "仰光", role="city", font_size_pt=10.0, ha="left"),
    Label(96.08 + 0.18, 21.98 - 0.05, "曼德勒", role="city", font_size_pt=10.0, ha="left"),
)

MYANMAR_CITIES = (
    City(96.10, 19.75, 13, "#ffd200", "black", 0.8, capital=True, name="内比都"),
    City(96.16, 16.87, 5, "white", "black", 1.0, name="仰光"),
    City(96.08, 21.98, 5, "white", "black", 1.0, name="曼德勒"),
)

SHEET_MYANMAR = Sheet(
    id="myanmar",
    out="myanmar_topography_etopo2022_lambert_conformal.svg",
    extent=EXTENT_MYANMAR,
    projection=PROJECTION_LCC,
    figsize=(12, 15),
    axes=(0.075, 0.05, 0.78, 0.85),
    relief=MYANMAR_RELIEF,
    graticule=GRATICULE_3X5,
    regrid_shape=3200,
    dataset_ids=(
        "etopo-myanmar",
        "ne-countries-10m",
        "ne-coastline-10m",
        "ne-borders-10m",
    ),
    dem_id="etopo-myanmar",
    labels=MYANMAR_LABELS,
    cities=MYANMAR_CITIES,
    title="缅甸联邦共和国全境地形图",
    subtitle=(
        "NOAA ETOPO 2022 | 兰勃特等角圆锥投影"
        "(中央经线 96.5°E, 标准纬线 10°N / 27°N)"
    ),
    colorbar_title="高程 / 水深",
)

# ============================
# 行政区划图 (myanmar_admin.py)
# ============================
# 地形只作底纹: 4 个锚点等距落在 0~4200 m 上, 与改前用的 from_list 色带同色同序;
# 0 m 以下的像元在绘图脚本里直接把 alpha 置 0(海面保留底色), 所以不需要海面锚点.
# stops=256 是 from_list(纯色表)的默认采样数, 取同一个值才能得到逐位相同的查找表.
ADMIN_RELIEF = Relief(
    vmin=0,
    vmax=4200,
    name="myanmar_relief",
    sea=((0, "#fbf8f0"),),
    land=((1400, "#eee5d4"), (2800, "#d9c8aa"), (4200, "#b7a17f")),
    ticks=(0, 1000, 2000, 3000, 4000),
    title="高程",
    unit="m",
    stops=256,
    azimuth=315,  # 西北来光, 与项目内其他地形图一致
    altitude=45,
    vert_exag=1.35,
    alpha=0.55,
    zorder=2,
)

# 经纬网: 经度每 2°、纬度每 5°; 取值写死成改前 FixedLocator 的位置.
ADMIN_GRATICULE = Graticule(
    lon_step=2.0,
    lat_step=5.0,
    lon_ticks=(92.0, 94.0, 96.0, 98.0, 100.0, 102.0),
    lat_ticks=(10.0, 15.0, 20.0, 25.0),
    color="#6f6f6f",
    stroke="#6f6f6f",
    width_pt=0.45,
    opacity=0.38,
    zorder=3.5,
)

SHEET_ADMIN = Sheet(
    id="myanmar-admin",
    out="myanmar_administrative_divisions_bilingual.svg",
    extent=EXTENT_ADMIN,
    projection=PROJECTION_LCC,
    figsize=(13, 17),
    # 右侧原来放图例面板的那一条留白保留(geojson 的图例由前端排版, 不进底图).
    axes=(0.075, 0.045, 0.655, 0.855),
    relief=ADMIN_RELIEF,
    graticule=ADMIN_GRATICULE,
    regrid_shape=3000,
    # 海陆底色与全国地形图不同: 行政区填色要压在上面, 底色要更浅.
    base_ocean="#d8e8f3",
    base_land="#f7f2e6",
    dataset_ids=(
        "etopo-myanmar",
        "ne-countries-10m",
        "ne-coastline-10m",
        "ne-borders-10m",
        "ne-rivers-10m",
        "gadm41-mmr",
        "osm-naypyidaw",
        "myanmar-admin1",
    ),
    title="缅甸联邦共和国行政区划图",
    subtitle="ADMINISTRATIVE DIVISIONS OF THE REPUBLIC OF THE UNION OF MYANMAR",
    notes=(
        "七邦（冷色）· 七省（暖色）· 内比都联邦区　　"
        "7 States (cool colours) · 7 Regions (warm colours) · Naypyidaw Union Territory",
        "地名均为中文 + English 双语（All place names are bilingual）",
        "7 邦 · 7 省 · 1 联邦区",
    ),
    colorbar_title="高程",
)

# ============================
# 掸邦/特区地形图 (northern_shan.py)
# ============================
# 投影与全国图不同: 中央经线取掸邦中部 98.4°E, 标准纬线夹住画框南北界.
PROJECTION_NORTHERN_SHAN = Projection(
    "lambert_conformal",
    {
        "central_longitude": 98.4,
        "central_latitude": 22.0,
        "standard_parallels": (20.0, 24.0),
    },
)

# 高程色带用 matplotlib 的命名色带 terrain; scalar 模式意味着底图与 geo.relief
# 共用 plt.get_cmap("terrain") 这一条色带(本区域河谷不会像全国图 ±5000 m 那样发白).
NORTHERN_SHAN_RELIEF = Relief(
    vmin=-1000,
    vmax=3000,
    name="terrain",
    mode="scalar",
    ticks=(0, 500, 1000, 1500, 2000, 2500, 3000),
    title="高程",
    unit="m",
    azimuth=315,  # 西北来光, 符合制图惯例
    altitude=45,
    vert_exag=1.6,  # 15 弧秒数据在 1:100 万级地图上起伏仍偏弱, 略作夸张
    zorder=1,
)

# 经纬网: 经度/纬度都是每 1°, 线型与改前一致.
NORTHERN_SHAN_GRATICULE = Graticule(
    lon_step=1.0,
    lat_step=1.0,
    color="#808080",
    stroke="#808080",
    width_pt=0.45,
    opacity=0.5,
    zorder=7,
)

# 城市表: (经度, 纬度, 名称, 类型, 文字偏移经度, 文字偏移纬度).
# 类型 capital=特区首府(星形), major=区域中心城市(方点), town=普通城镇(小圆点);
# 偏移是改前成品文字的落点, 现在只用来产出 geo.labels 的锚点, 不再画文字.
NORTHERN_SHAN_PLACES = (
    (98.764, 23.695, "老街", "capital", 0.0, 0.14),
    (99.167, 22.179, "邦康", "capital", 0.05, -0.10),
    (100.022, 21.676, "勐拉", "capital", 0.06, -0.06),
    (96.095, 21.960, "曼德勒", "major", 0.06, 0.0),
    (97.036, 20.784, "东枝", "major", 0.06, 0.0),
    (99.882, 20.447, "大其力", "major", 0.06, 0.0),
    (97.209, 19.674, "垒固", "major", 0.06, 0.0),
    (97.745, 22.942, "腊戍", "major", 0.05, -0.10),
    (97.901, 23.998, "木姐", "town", 0.04, 0.05),
    (97.683, 23.835, "南坎", "town", -0.04, -0.12),
    (97.932, 23.458, "贵概", "town", 0.04, -0.10),
    (97.966, 23.304, "木邦", "town", 0.04, -0.10),
    (98.655, 23.418, "滚弄", "town", 0.04, -0.10),
    (98.825, 23.477, "清水河", "town", 0.04, 0.05),
    (98.308, 24.101, "勐古", "town", 0.04, 0.06),
    (98.100, 23.580, "大勐宜", "town", 0.04, -0.10),
    (98.965, 22.971, "勐冒", "town", 0.04, -0.10),
    (99.307, 22.009, "勐波", "town", 0.04, -0.10),
    (100.652, 21.395, "南板", "town", 0.04, -0.10),
    (99.805, 21.851, "色勒", "town", 0.0, 0.10),
    (99.600, 21.290, "景栋", "town", 0.04, -0.10),
    (98.395, 22.494, "当阳", "town", 0.04, -0.10),
    (97.562, 20.925, "莱林", "town", 0.04, -0.10),
)

# 方点标记的城镇名; 其余非首府都用空心圆点(标记形状不属于 City 的数据字段).
NORTHERN_SHAN_MAJOR = frozenset({"曼德勒", "东枝", "大其力", "垒固", "腊戍"})

# 三类城镇的标记样式: (尺寸, 填充色, 描边色, 描边宽).
_NORTHERN_SHAN_MARKER_STYLE = {
    "capital": (14.0, "#ffd200", "black", 0.8),
    "major": (6.0, "#ffd200", "black", 0.9),
    "town": (3.8, "white", "black", 0.8),
}

NORTHERN_SHAN_CITIES = tuple(
    City(
        lon,
        lat,
        _NORTHERN_SHAN_MARKER_STYLE[kind][0],
        _NORTHERN_SHAN_MARKER_STYLE[kind][1],
        _NORTHERN_SHAN_MARKER_STYLE[kind][2],
        _NORTHERN_SHAN_MARKER_STYLE[kind][3],
        capital=kind == "capital",
        name=name,
    )
    for lon, lat, name, kind, _dx, _dy in NORTHERN_SHAN_PLACES
)

# 地名: 顺序按改前 zorder 升序(前端 scene 按 order 叠放): 邻国/省邦 -> 特区/区域名
# -> 河名 -> 城名. id 前缀沿用旧版(area/region/river/city), 由 id_kind/role 决定.
NORTHERN_SHAN_LABELS = (
    # 邻国/省邦注记: 旧图 label-area-<slug>.
    Label(99.05, 24.62, "中国 云南省", role="country", font_size_pt=13.0,
          id_kind="area", name="中国云南省"),
    Label(101.25, 20.45, "老挝", role="country", font_size_pt=12.0,
          id_kind="area", name="老挝"),
    Label(100.60, 19.35, "泰国", role="country", font_size_pt=12.0,
          id_kind="area", name="泰国"),
    Label(96.75, 23.78, "掸邦", role="area-muted", font_size_pt=13.0,
          id_kind="area", name="掸邦"),
    Label(95.72, 22.45, "曼德勒省", role="area-muted", font_size_pt=11.0,
          id_kind="area", name="曼德勒省"),
    Label(97.18, 19.32, "克耶邦", role="area-muted", font_size_pt=11.0,
          id_kind="area", name="克耶邦"),
    Label(99.02, 20.30, "佤邦(南)", role="area-accent-3", font_size_pt=13.0,
          id_kind="area", name="佤邦南"),
    # 特区/区域名: 旧图 label-region-<slug>; 前端按区域家族处理, 样式仍由 role 决定.
    Label(98.30, 23.72, "缅甸联邦第一特区", role="area-accent-1", font_size_pt=13.5,
          id_kind="region", name="缅甸联邦第一特区"),
    Label(98.25, 23.08, "MNDAA 实控区\n(大致范围)", role="area-accent-1", font_size_pt=9.5,
          id_kind="region", name="MNDAA实控区大致范围"),
    Label(97.00, 23.34, "德昂邦", role="area-accent-2", font_size_pt=14,
          id_kind="region", name="德昂邦"),
    Label(97.00, 23.12, "(TNLA 控制)", role="area-accent-2", font_size_pt=9.5,
          id_kind="region", name="TNLA控制"),
    Label(98.60, 24.00, "原果敢自治区", role="area-accent-1", font_size_pt=9,
          id_kind="region", name="原果敢自治区"),
    Label(98.99, 22.60, "佤邦", role="area-accent-3", font_size_pt=16,
          id_kind="region", name="佤邦"),
    Label(99.79, 21.73, "掸邦东部\n第四特区", role="area-accent-4", font_size_pt=10.0,
          id_kind="region", name="掸邦东部第四特区"),
    # 两条大江的河名.
    Label(95.75, 22.90, "伊洛瓦底江", role="river", font_size_pt=10.5, name="伊洛瓦底江"),
    Label(98.33, 21.55, "萨尔温江", role="river", font_size_pt=10.5, name="萨尔温江"),
    # 城名: 落点跟着点位偏移; 字号按城市等级分两档, 普通城镇居中对齐.
    *(
        Label(
            lon + dx,
            lat + dy,
            name,
            role="city",
            font_size_pt=9.0 if kind == "town" else 10.5,
            ha="center" if kind == "town" else "left",
            name=name,
        )
        for lon, lat, name, kind, dx, dy in NORTHERN_SHAN_PLACES
    ),
)

SHEET_NORTHERN_SHAN = Sheet(
    id="northern-shan",
    out="northern_shan_topography_etopo2022_lambert_conformal.svg",
    extent=EXTENT_NORTHERN_SHAN,
    projection=PROJECTION_NORTHERN_SHAN,
    # 画布 16x15: 投影后画框约 653x636 km(宽高比 1.026), 轴区域与之匹配,
    # 避免 GeoAxes 为保持等比例而留下过大空白.
    figsize=(16, 15),
    axes=(0.045, 0.062, 0.80, 0.831),
    relief=NORTHERN_SHAN_RELIEF,
    graticule=NORTHERN_SHAN_GRATICULE,
    regrid_shape=3000,
    # 数据未覆盖区域的底色(本图 ETOPO 已覆盖全部画框, 仅作兜底).
    base_ocean="#cfe0ee",
    base_land="#efe9cf",
    dataset_ids=(
        "etopo-northern-shan",
        "ne-countries-10m",
        "ne-rivers-10m",
        "osm-shan-regions",
        "osm-country-borders",
    ),
    labels=NORTHERN_SHAN_LABELS,
    cities=NORTHERN_SHAN_CITIES,
    title="缅甸掸邦特区与地方武装控制区地形图（2026年10月）",
    subtitle=(
        "NOAA ETOPO 2022 | 边界: OpenStreetMap | 底图: Natural Earth 10m | "
        "兰勃特等角圆锥投影(中央经线 98.4°E)"
    ),
    notes=(
        "注: 国界与区域边界同源 OSM, 重合段按国界样式绘制",
        "原果敢自治区为第一特区前身, 以同色系加深表示其含于第一特区",
        "MNDAA 实控区与第一特区辖区大体重合, 以斜线示意",
        "范围据 OSM 公开边界绘制, 仅供参考",
    ),
    colorbar_title="高程",
    # 图例/注记里的缩写表; 追加到自动生成的数据来源末尾.
    extra_source="MNDAA=缅甸民族民主同盟军, TNLA=德昂民族解放军",
)

SHEETS = (SHEET_MYANMAR, SHEET_ADMIN, SHEET_NORTHERN_SHAN)
