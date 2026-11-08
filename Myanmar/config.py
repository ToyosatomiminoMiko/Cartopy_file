# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Myanmar subproject: dataset inventory and per-sheet render config.

是什么: 缅甸子项目的唯一配置入口--数据集清单(从哪下,版本,下载范围,本地路径)与
每张图的规格(画框,投影,色带,经纬网,地名,图例,图面配色,文案). 数据准备脚本与绘图
脚本都从这里取参数, 下载范围和绘图范围不会再各写一份; 图例与地图共用同一份颜色,
改色时图例跟着变.
完整说明(数据集层与实例规格层怎么分工)见 ``docs/reference/datasets.md`` 与
``docs/reference/spec.md``; 各图种的设计取舍见 ``docs/maps/myanmar.md`` 等页面.
"""

from __future__ import annotations

from pathlib import Path

from cartopy_file.datasets import Dataset, dataset_set
from cartopy_file.sources import erddap_url, ne_url
from cartopy_file.spec import (
    City,
    Extent,
    Graticule,
    Label,
    LegendEntry,
    Projection,
    Relief,
    Sheet,
)

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
# 图面配色(三个图种共用的固定色)
# ============================
# 国界: 红色半透明实线, 让地形与下层要素透出来(与 Ukraine 图口径一致);
# 邻国国界: 中性灰虚线, 只作定位参照, 不与红色国界争视觉层级.
# 图例与地图共用同一份, 改色时两边一起变.
COLOR_BORDER = "#c62828"
BORDER_ALPHA = 0.62
BORDER_WIDTH = 2.7
COLOR_NEIGHBOR = "#8a8a8a"

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

# 高程/水深双色带: 水面到 -1 m, 陆地从 +1 m 起, 0 m 处直接跳变--本图不画海岸线,
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

# 经纬网: 经度每 3°,纬度每 5°; 取值写死成网线的精确位置(与改前 FixedLocator 一致).
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
# 只登记语义与落点; 字号/颜色/描边等样式由前端 role 表决定.
# name 是 id 的标识符段(小写 ASCII slug), 中文只进 text; 见 docs/reference/spec.md 的 Label.
MYANMAR_LABELS = (
    Label(99.6, 29.9, "中国", role="country", name="china"),
    Label(89.2, 25.4, "印度", role="country", name="india"),
    Label(89.6, 22.8, "孟加拉国", role="country", name="bangladesh"),
    Label(101.3, 16.0, "泰国", role="country", name="thailand"),
    Label(103.4, 19.6, "老挝", role="country", name="laos"),
    Label(89.8, 15.8, "孟加拉湾", role="sea", name="bay-of-bengal"),
    Label(96.8, 9.3, "安达曼海", role="sea", name="andaman-sea"),
    Label(95.6, 23.5, "缅甸", role="country-name", name="myanmar"),
    # 城名贴在城点左下: 旧版是 (城点 + 0.18°E, -0.05°N) + ha="left".
    Label(96.10 + 0.18, 19.75 - 0.05, "内比都", role="city",
          ha="left", name="naypyidaw"),
    Label(96.16 + 0.18, 16.87 - 0.05, "仰光", role="city",
          ha="left", name="yangon"),
    Label(96.08 + 0.18, 21.98 - 0.05, "曼德勒", role="city",
          ha="left", name="mandalay"),
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
# 行政区属性表: GADM 名称 -> (键名, 中文名, 英文名, 类型, 行政中心中文, 行政中心英文,
# 中心经度, 中心纬度). 派生脚本用它生成 GeoJSON; 绘图模块与图例/标注也从这里取同一份
# 事实, 不再在 prepare 与 render 两个文件里各抄一遍.
# 行政中心坐标来自 Natural Earth 10m populated places, 实皆省的行政中心按现行建制
# 改用蒙育瓦(Monywa), 不用 Natural Earth 里过时的实皆(Sagaing).
# 类型: state=邦, region=省, union=联邦区.
ADMIN_INFO: dict[str, tuple[str, str, str, str, str, str, float, float]] = {
    "Kachin": (
        "kachin",
        "克钦邦",
        "Kachin State",
        "state",
        "密支那",
        "Myitkyina",
        97.392753,
        25.359627,
    ),
    "Kayah": (
        "kayah",
        "克耶邦",
        "Kayah State",
        "state",
        "垒固",
        "Loikaw",
        97.206004,
        19.665000,
    ),
    "Kayin": (
        "kayin",
        "克伦邦",
        "Kayin State",
        "state",
        "帕安",
        "Hpa-an",
        97.616701,
        16.849998,
    ),
    "Chin": (
        "chin",
        "钦邦",
        "Chin State",
        "state",
        "哈卡",
        "Hakha",
        93.616705,
        22.650003,
    ),
    "Mon": (
        "mon",
        "孟邦",
        "Mon State",
        "state",
        "毛淡棉",
        "Mawlamyine",
        97.670048,
        16.500426,
    ),
    "Rakhine": (
        "rakhine",
        "若开邦",
        "Rakhine State",
        "state",
        "实兑",
        "Sittwe",
        92.880005,
        20.139997,
    ),
    "Shan": (
        "shan",
        "掸邦",
        "Shan State",
        "state",
        "东枝",
        "Taunggyi",
        97.038001,
        20.781999,
    ),
    "Ayeyarwady": (
        "ayeyarwady",
        "伊洛瓦底省",
        "Ayeyarwady Region",
        "region",
        "勃生",
        "Pathein",
        94.749968,
        16.770409,
    ),
    "Bago": (
        "bago",
        "勃固省",
        "Bago Region",
        "region",
        "勃固",
        "Bago",
        96.514977,
        17.320014,
    ),
    "Magway": (
        "magway",
        "马圭省",
        "Magway Region",
        "region",
        "马圭",
        "Magway",
        94.919570,
        20.144544,
    ),
    "Mandalay": (
        "mandalay",
        "曼德勒省",
        "Mandalay Region",
        "region",
        "曼德勒",
        "Mandalay",
        96.083083,
        21.971934,
    ),
    "Sagaing": (
        "sagaing",
        "实皆省",
        "Sagaing Region",
        "region",
        "蒙育瓦",
        "Monywa",
        95.149996,
        22.104993,
    ),
    "Tanintharyi": (
        "tanintharyi",
        "德林达依省",
        "Tanintharyi Region",
        "region",
        "土瓦",
        "Dawei",
        98.194978,
        14.097963,
    ),
    "Yangon": (
        "yangon",
        "仰光省",
        "Yangon Region",
        "region",
        "仰光",
        "Yangon",
        96.164732,
        16.785300,
    ),
    # 键名里的 npt 是 Naypyitaw/Naypyidaw 的缩写; 联邦区不是邦也不是省,
    # 绘图时单独使用中性色, 避免被误读为暖色的省.
    "Naypyitaw": (
        "npt",
        "内比都联邦区",
        "Naypyidaw Union Territory",
        "union",
        "内比都",
        "Naypyidaw",
        96.116673,
        19.768503,
    ),
}

# 按 key 查属性, 给图例/标注的建表函数用; 顺序沿用 ADMIN_INFO 的插入顺序
# (派生 GeoJSON 就是这个顺序, 所以前端叠放顺序不会变).
ADMIN_UNITS_BY_KEY = {info[0]: info for info in ADMIN_INFO.values()}

# 行政区颜色. 冷色 = 邦, 暖色 = 省; 色相分散, 保证相邻单元也能区分.
# 透明度在绘制时统一加, 这样底纹和地形仍能透出一点, 不至于变成纯色拼图.
STATE_COLORS = {
    "kachin": "#0088e5",
    "kayah": "#00d4fa",
    "kayin": "#007d32",
    "chin": "#0024aa",
    "mon": "#00acc1",
    "rakhine": "#00897b",
    "shan": "#006bc0",
}
REGION_COLORS = {
    # 伊洛瓦底省与勃固省有很长的公共边界, 旧色 #ffb74d(浅橙) 与勃固省的
    # #f9a825(琥珀) 色相几乎相同(约 36°),亮度也接近, 半透明叠在米色地形上
    # 几乎分不出界线; 改用 #ff8a65(deep orange 300) 把色相拉到橙红一侧,
    # 两者色差放大到约 3 倍, 同时与相邻的仰光省品红,若开邦青绿仍保持足够区分.
    "ayeyarwady": "#ff8a00",
    "bago": "#f9a800",
    "magway": "#d84300",
    "mandalay": "#ef6c00",
    "sagaing": "#b71c00",
    "tanintharyi": "#e64a00",
    "yangon": "#c21800",
}
UNION_COLOR = "#f3e5ab"
FILL_ALPHA = 0.58
BOUNDARY_COLOR = "#2f2f2f"
# 内比都联邦区: 中性浅色 + 斜线, 表示既不是邦也不是省.
UNION_EDGE_COLOR = "#6b4e00"
UNION_HATCH = "////"
# 图例与地图共用的其它固定色: 行政单元描边,行政中心符号,河流强调线.
UNIT_EDGE_COLOR = "#ffffff"
UNIT_EDGE_WIDTH = 0.6
CAPITAL_FILL = "#ffd200"
CAPITAL_EDGE = "#111111"
ADMIN_RIVER_COLOR = "#1565c0"

# 图例顺序按旧面板: 先 7 邦(冷色), 再 7 省(暖色), 最后联邦区; geojson 里的
# 行政区顺序不是旧面板顺序, 所以单独列一份.
LEGEND_STATE_KEYS = ("kachin", "kayah", "kayin", "chin", "mon", "rakhine", "shan")
LEGEND_REGION_KEYS = (
    "sagaing",
    "magway",
    "mandalay",
    "bago",
    "ayeyarwady",
    "yangon",
    "tanintharyi",
)

# ============================
# 行政区划图: 图例(14 个行政区 + 联邦区 + 6 个符号, 顺序同旧面板)
# ============================
ADMIN_LEGEND_TITLE = "图例"
# 图例文案一律单行: 中文 + 英文写进同一个 label, 分行/排版由前端负责.
# 分组标题(邦/省/联邦区)与说明文字无法用条目表达, 已放进 Sheet.notes.
ADMIN_LEGEND = (
    *(
        LegendEntry(
            f"{ADMIN_UNITS_BY_KEY[key][1]} {ADMIN_UNITS_BY_KEY[key][2]}",
            "rect",
            stroke=UNIT_EDGE_COLOR,
            width_pt=UNIT_EDGE_WIDTH,
            fill=STATE_COLORS[key],
        )
        for key in LEGEND_STATE_KEYS
    ),
    *(
        LegendEntry(
            f"{ADMIN_UNITS_BY_KEY[key][1]} {ADMIN_UNITS_BY_KEY[key][2]}",
            "rect",
            stroke=UNIT_EDGE_COLOR,
            width_pt=UNIT_EDGE_WIDTH,
            fill=REGION_COLORS[key],
        )
        for key in LEGEND_REGION_KEYS
    ),
    LegendEntry(
        f"{ADMIN_UNITS_BY_KEY['npt'][1]} {ADMIN_UNITS_BY_KEY['npt'][2]}",
        "rect",
        stroke=UNION_EDGE_COLOR,
        width_pt=1.0,
        fill=UNION_COLOR,
        hatch=UNION_HATCH,
    ),
    LegendEntry(
        "联邦首都 Union capital",
        "point",
        stroke=CAPITAL_EDGE,
        width_pt=0.7,
        fill=CAPITAL_FILL,
        marker="star",
    ),
    LegendEntry(
        "行政中心 Administrative centre",
        "point",
        stroke=CAPITAL_EDGE,
        width_pt=0.9,
        fill="#ffffff",
        marker="circle",
    ),
    LegendEntry(
        "河流 River",
        "line",
        stroke=ADMIN_RIVER_COLOR,
        width_pt=2.25,
    ),
    LegendEntry(
        "邦/省界 State & region boundary",
        "line",
        stroke=BOUNDARY_COLOR,
        width_pt=1.05,
    ),
    LegendEntry(
        "国界 International boundary",
        "line",
        stroke=COLOR_BORDER,
        width_pt=BORDER_WIDTH,
        opacity=BORDER_ALPHA,
    ),
    LegendEntry(
        "邻国国界 Neighbour boundary",
        "line",
        stroke=COLOR_NEIGHBOR,
        width_pt=0.45,
        dash=(5.0, 3.0),
    ),
)

# ============================
# 行政区划图: 标注(双语各一条: 中文行在上,英文行在下)
# ============================
# 旧版用 annotate 的 offset points 排版(中文行在锚点上方 4~4.2 pt, 英文行在下方
# 5~7 pt, 行距与字号相关), 而 geo.labels 只认经纬度. 兰勃特投影在画框各处的比例
# 不同, 所以不存在一个统一的换算系数: 下面的落点是按旧版每条磅偏移,在当处投影
# 比例下换算出来的经纬度(已含偏移, 不再是锚点), 换投影/画幅要重算, 见
# docs/maps/myanmar-admin.md.
# 行格式: (中文行经度, 中文行纬度, 英文行经度, 英文行纬度, 中文文案, 英文文案, id slug).
NEIGHBOUR_LABELS = (
    (99.85164071, 28.37792102, 99.84713262, 28.16359130, "中国", "CHINA", "china"),
    (92.19791887, 26.47834436, 92.20363714, 26.26285924, "印度", "INDIA", "india"),
    (91.54764566, 23.62881493, 91.55411472, 23.41204904, "孟加拉国", "BANGLADESH",
     "bangladesh"),
    (99.45136104, 18.47918623, 99.44762119, 18.26142337, "泰国", "THAILAND", "thailand"),
    (100.80200896, 20.62910673, 100.79648882, 20.41155246, "老挝", "LAOS", "laos"),
)
SEA_LABELS = (
    (91.44799893, 15.26917564, 91.45371206, 15.07154270, "孟加拉湾", "BAY OF BENGAL",
     "bay-of-bengal"),
    (96.44998074, 10.26862821, 96.45003573, 10.07257804, "安达曼海", "ANDAMAN SEA",
     "andaman-sea"),
)
# 两条大江的名称与落点: 位置避开了主要行政区名和行政中心点.
RIVER_LABELS = (
    (95.11944275, 18.51929501, 95.12095425, 18.33120784, "伊洛瓦底江", "Irrawaddy River",
     "irrawaddy"),
    (98.55083805, 20.61923393, 98.54856493, 20.43130531, "萨尔温江", "Salween River",
     "salween"),
)
# 行政区名: key -> (中文行经度, 中文行纬度, 英文行经度, 英文行纬度).
# 多数放在单元内部.
ADMIN_LABEL_POSITIONS = {
    "kachin": (97.05028066, 27.13213977, 97.04953287, 26.91305850),
    "kayah": (97.45046254, 19.33314167, 97.44923011, 19.11142579),
    "kayin": (97.90067806, 18.43315444, 97.89887136, 18.21140877),
    "chin": (93.54852775, 23.50279343, 93.55245048, 23.28198631),
    "mon": (97.55050067, 15.73307410, 97.54916661, 15.51155531),
    "rakhine": (93.51855128, 19.08313743, 93.52241141, 18.86143404),
    "shan": (98.62105033, 22.28294449, 98.61825176, 22.06174038),
    "ayeyarwady": (95.09932481, 17.70315069, 95.10112386, 17.48141847),
    "bago": (96.34992724, 18.68315509, 96.35012110, 18.46140652),
    "magway": (94.29891811, 21.03305312, 94.30180079, 20.81156529),
    "mandalay": (95.94972944, 21.08305536, 95.95045034, 20.86156133),
    "sagaing": (94.67908209, 25.23252698, 94.68152780, 25.01242217),
    "tanintharyi": (98.56096724, 13.03280511, 98.55838995, 12.81201598),
    "yangon": (96.44997609, 16.23310453, 96.45003980, 16.01150228),
    "npt": (96.44997553, 20.24310740, 96.45004074, 20.02147859),
}
# 行政中心名: key -> (中文行经度, 中文行纬度, 英文行经度, 英文行纬度, 水平对齐).
# 旧版先按各中心的 (dx, dy) 磅偏移摆位, 中文行再 +2.6 pt,英文行 -5.0 pt.
CAPITAL_LABEL_POSITIONS = {
    "kachin": (97.54491001, 25.48850932, 97.54395577, 25.33924369, "left"),
    "kayah": (97.35291492, 19.79502882, 97.35216211, 19.64460697, "left"),
    "kayin": (97.76153126, 16.97972046, 97.76043589, 16.82928946, "left"),
    "chin": (93.46584814, 22.75824843, 93.46857351, 22.60825667, "right"),
    "mon": (97.81327741, 16.45197481, 97.81214057, 16.30158266, "left"),
    "rakhine": (93.02437836, 20.25351726, 93.02745415, 20.10315838, "left"),
    "shan": (97.18503177, 20.73405703, 97.18442379, 20.58372012, "left"),
    "ayeyarwady": (94.60667856, 16.72150594, 94.60832005, 16.57109683, "right"),
    "bago": (96.65938959, 17.47040591, 96.65925080, 17.31994689, "left"),
    "magway": (95.06680445, 20.07842560, 95.06807153, 19.92802831, "left"),
    "mandalay": (96.23110972, 22.12233327, 96.23135034, 21.97219753, "left"),
    "sagaing": (95.29744260, 22.23633246, 95.29851945, 22.08622052, "left"),
    "tanintharyi": (98.33796519, 14.22694574, 98.33639430, 14.07685952, "left"),
    "yangon": (96.02114445, 16.69789901, 96.02155956, 16.54748384, "right"),
}

def _add_bilingual_label(
    sink: list[Label],
    zh_position: tuple[float, float],
    en_position: tuple[float, float],
    zh: str,
    en: str,
    slug: str,
    *,
    role: str,
    id_kind: str,
    ha: str = "center",
) -> None:
    """登记一对中文/英文标注: 两条共用一个 role 与 id_kind, 只有落点不同.

    为什么英文单独一条: 旧版 en 是独立文字(位置另给), 前端要能分别拖动;
    id 用同一个 slug 加 ``-en`` 后缀, 与旧版命名一致.
    """
    sink.append(
        Label(
            zh_position[0], zh_position[1], zh,
            role=role, name=slug, id_kind=id_kind, ha=ha,
        )
    )
    sink.append(
        Label(
            en_position[0], en_position[1], en,
            role=role, name=f"{slug}-en", id_kind=id_kind, ha=ha,
        )
    )


def _build_admin_labels() -> tuple[Label, ...]:
    """按旧图叠放顺序建 76 条双语 Label: 邻国 -> 海域 -> 行政区 -> 行政中心 -> 河名.

    顺序就是前端 scene 的叠放顺序(旧图 zorder 升序: 邻国/海域 11,行政区名 13,
    行政中心与河名 14), 同一 zorder 内按旧版插入顺序.
    """
    labels: list[Label] = []
    for zh_lon, zh_lat, en_lon, en_lat, zh, en, slug in NEIGHBOUR_LABELS:
        _add_bilingual_label(
            labels, (zh_lon, zh_lat), (en_lon, en_lat), zh, en, slug,
            role="country", id_kind="country",
        )
    for zh_lon, zh_lat, en_lon, en_lat, zh, en, slug in SEA_LABELS:
        _add_bilingual_label(
            labels, (zh_lon, zh_lat), (en_lon, en_lat), zh, en, slug,
            role="sea", id_kind="sea",
        )
    for _gadm_name, info in ADMIN_INFO.items():
        key, name_zh, name_en, kind = info[0], info[1], info[2], info[3]
        zh_lon, zh_lat, en_lon, en_lat = ADMIN_LABEL_POSITIONS[key]
        # 内比都的英文全名太长, 在图上会压到隔壁单元, 用 U.T. 缩写;
        # 图例和标题里保留全称 Naypyidaw Union Territory.
        display_en = "Naypyidaw U.T." if kind == "union" else name_en
        _add_bilingual_label(
            labels, (zh_lon, zh_lat), (en_lon, en_lat), name_zh, display_en, key,
            role="area", id_kind=kind,
        )
    for _gadm_name, info in ADMIN_INFO.items():
        key, kind = info[0], info[3]
        # 联邦区标签已经用行政区名表达, 不再重复写一次 "内比都".
        if kind == "union":
            continue
        zh_lon, zh_lat, en_lon, en_lat, ha = CAPITAL_LABEL_POSITIONS[key]
        capital_en = info[5]
        _add_bilingual_label(
            labels, (zh_lon, zh_lat), (en_lon, en_lat), info[4], capital_en,
            capital_en.lower().replace(" ", "-"),
            role="city", id_kind="city", ha=ha,
        )
    for zh_lon, zh_lat, en_lon, en_lat, zh, en, slug in RIVER_LABELS:
        _add_bilingual_label(
            labels, (zh_lon, zh_lat), (en_lon, en_lat), zh, en, slug,
            role="river", id_kind="river",
        )
    return tuple(labels)


ADMIN_LABELS = _build_admin_labels()

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

# 经纬网: 经度每 2°,纬度每 5°; 取值写死成改前 FixedLocator 的位置.
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
    labels=ADMIN_LABELS,
    legend=ADMIN_LEGEND,
    legend_title=ADMIN_LEGEND_TITLE,
    title="缅甸联邦共和国行政区划图",
    subtitle="ADMINISTRATIVE DIVISIONS OF THE REPUBLIC OF THE UNION OF MYANMAR",
    notes=(
        "七邦(冷色)· 七省(暖色)· 内比都联邦区　　"
        "7 States (cool colours) · 7 Regions (warm colours) · Naypyidaw Union Territory",
        "地名均为中文 + English 双语(All place names are bilingual)",
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

# ============================
# 图面配色(绘图与图例共用这一份, 改色时图例与地图必须一起变)
# ============================
# 区域配色: 填充色 + 边界色. 透明度让下方地形仍可读.
# 德昂邦用绿色: 第一特区(紫),佤邦(蓝),四特(橙)已占三色, 绿色是
# 与三者色相距离最大,且不与环境色(山体晕渲)冲突的选择.
REGION_STYLES = {
    "sr1": {
        "fill": "#8c6bb1",
        "edge": "#4a1486",
        "alpha": 0.24,
        "linewidth": 2.2,
    },
    "taang": {
        "fill": "#2ca25f",
        "edge": "#005a32",
        "alpha": 0.26,
        "linewidth": 1.9,
    },
    "wa": {
        "fill": "#2b8cbe",
        "edge": "#045a8d",
        "alpha": 0.22,
        "linewidth": 1.9,
    },
    "sr4": {
        "fill": "#f16913",
        "edge": "#a63603",
        "alpha": 0.22,
        "linewidth": 1.9,
    },
}
# 区域内部县/特区界: 白色虚线, 在填充与地形上都看得清.
INTERNAL_EDGE_COLOR = "#ffffff"
# MNDAA 实控区斜线: 与第一特区同范围, 用斜线表示"实控", 填充色表示"辖区".
MNDAA_HATCH = "///"
MNDAA_HATCH_COLOR = "#4a1486"

# 国界: 用 OSM admin_level=2 数据(精度与区域边界一致); 颜色/透明度/线宽用
# 共享的 COLOR_BORDER/BORDER_ALPHA/BORDER_WIDTH(与全国图,行政区图一致).

# 原果敢自治区(第一特区前身): 与第一特区同色系,明显加深的填充, 用嵌套色块
# 表示"含于第一特区辖区". 只填色,不描内边界, 以免粗线压住区内的河流;
# 不加第二种底纹的原因见 docs/maps/northern-shan.md.
KOKANG_SAZ_FILL = "#54278f"
KOKANG_SAZ_ALPHA = 0.32

# 图例 / 绘图共用的其它固定色: 省/邦界,河流,特区首府点.
PROVINCE_EDGE_COLOR = "#7f7f7f"
RIVER_COLOR = "#1f78b4"
SHAN_CAPITAL_FILL = "#ffd200"
SHAN_CAPITAL_EDGE = "#000000"

# ============================
# 图例(声明在 config 里, 渲染模块只画图; 顺序与旧面板一致)
# ============================
# 图例文案一律单行: 分行/排版由前端负责, 生成端不写 label_lines.
NORTHERN_SHAN_LEGEND_TITLE = "图例"
NORTHERN_SHAN_LEGEND = (
    LegendEntry(
        "缅甸联邦第一特区(辖区)",
        "rect",
        stroke=REGION_STYLES["sr1"]["edge"],
        width_pt=1.5,
        fill=REGION_STYLES["sr1"]["fill"],
        opacity=0.6,
    ),
    LegendEntry(
        "原果敢自治区(2010–2023)",
        "rect",
        width_pt=0.0,
        fill=KOKANG_SAZ_FILL,
        opacity=0.8,
    ),
    # 图例色块只有约 20 pt 宽, 图上 "///" 在这个尺寸下几乎看不出斜线,
    # 所以图例用更密的 "////"; 颜色仍与图上斜线同色.
    LegendEntry(
        "MNDAA 实控区(大致)",
        "rect",
        stroke=MNDAA_HATCH_COLOR,
        width_pt=0.0,
        hatch="////",
    ),
    LegendEntry(
        "德昂邦(TNLA 控制)",
        "rect",
        stroke=REGION_STYLES["taang"]["edge"],
        width_pt=1.5,
        fill=REGION_STYLES["taang"]["fill"],
        opacity=0.6,
    ),
    LegendEntry(
        "佤邦",
        "rect",
        stroke=REGION_STYLES["wa"]["edge"],
        width_pt=1.5,
        fill=REGION_STYLES["wa"]["fill"],
        opacity=0.6,
    ),
    LegendEntry(
        "掸邦东部第四特区",
        "rect",
        stroke=REGION_STYLES["sr4"]["edge"],
        width_pt=1.5,
        fill=REGION_STYLES["sr4"]["fill"],
        opacity=0.6,
    ),
    LegendEntry(
        "国界",
        "line",
        stroke=COLOR_BORDER,
        width_pt=BORDER_WIDTH,
        opacity=BORDER_ALPHA,
    ),
    LegendEntry(
        "省/邦界",
        "line",
        stroke=PROVINCE_EDGE_COLOR,
        width_pt=1.0,
        dash=(6.0, 3.0),
    ),
    LegendEntry(
        "河流",
        "line",
        stroke=RIVER_COLOR,
        width_pt=0.9,
    ),
    LegendEntry(
        "特区首府",
        "point",
        stroke=SHAN_CAPITAL_EDGE,
        width_pt=1.0,
        fill=SHAN_CAPITAL_FILL,
        marker="star",
    ),
)

# 城市表: (经度, 纬度, 名称, id slug, 类型, 文字偏移经度, 文字偏移纬度).
# 类型 capital=特区首府(星形), major=区域中心城市(方点), town=普通城镇(小圆点);
# 偏移是改前成品文字的落点, 现在只用来产出 geo.labels 的锚点, 不再画文字.
# slug 是小写 ASCII(常用罗马化转写), 只进 id; 显示名只进 text.
NORTHERN_SHAN_PLACES = (
    (98.764, 23.695, "老街", "laukkai", "capital", 0.0, 0.14),
    (99.167, 22.179, "邦康", "pangkham", "capital", 0.05, -0.10),
    (100.022, 21.676, "勐拉", "mongla", "capital", 0.06, -0.06),
    (96.095, 21.960, "曼德勒", "mandalay", "major", 0.06, 0.0),
    (97.036, 20.784, "东枝", "taunggyi", "major", 0.06, 0.0),
    (99.882, 20.447, "大其力", "tachileik", "major", 0.06, 0.0),
    (97.209, 19.674, "垒固", "loikaw", "major", 0.06, 0.0),
    (97.745, 22.942, "腊戍", "lashio", "major", 0.05, -0.10),
    (97.901, 23.998, "木姐", "muse", "town", 0.04, 0.05),
    (97.683, 23.835, "南坎", "namhkam", "town", -0.04, -0.12),
    (97.932, 23.458, "贵概", "kutkai", "town", 0.04, -0.10),
    (97.966, 23.304, "木邦", "mong-yaw", "town", 0.04, -0.10),
    (98.655, 23.418, "滚弄", "kunlong", "town", 0.04, -0.10),
    (98.825, 23.477, "清水河", "chinshwehaw", "town", 0.04, 0.05),
    (98.308, 24.101, "勐古", "mongko", "town", 0.04, 0.06),
    (98.100, 23.580, "大勐宜", "tarmoenye", "town", 0.04, -0.10),
    (98.965, 22.971, "勐冒", "mongmao", "town", 0.04, -0.10),
    (99.307, 22.009, "勐波", "mong-pawk", "town", 0.04, -0.10),
    (100.652, 21.395, "南板", "nanban", "town", 0.04, -0.10),
    (99.805, 21.851, "色勒", "sele", "town", 0.0, 0.10),
    (99.600, 21.290, "景栋", "kengtung", "town", 0.04, -0.10),
    (98.395, 22.494, "当阳", "tangyan", "town", 0.04, -0.10),
    (97.562, 20.925, "莱林", "loilen", "town", 0.04, -0.10),
)

# 方点标记的城镇(按 id slug); 其余非首府都用空心圆点(标记形状不属于 City 的数据字段).
NORTHERN_SHAN_MAJOR = frozenset({"mandalay", "taunggyi", "tachileik", "loikaw", "lashio"})

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
        name=slug,
    )
    for lon, lat, _name, slug, kind, _dx, _dy in NORTHERN_SHAN_PLACES
)

# 地名: 顺序按改前 zorder 升序(前端 scene 按 order 叠放): 邻国/省邦 -> 特区/区域名
# -> 河名 -> 城名. id 前缀沿用旧版(area/region/river/city), 由 id_kind/role 决定;
# name 是 id 的 ASCII slug, 中文只进 text(见 docs/reference/spec.md 的 Label).
NORTHERN_SHAN_LABELS = (
    # 邻国/省邦注记: 旧图 label-area-<slug>.
    Label(99.05, 24.62, "中国 云南省", role="country",
          id_kind="area", name="china-yunnan"),
    Label(101.25, 20.45, "老挝", role="country",
          id_kind="area", name="laos"),
    Label(100.60, 19.35, "泰国", role="country",
          id_kind="area", name="thailand"),
    Label(96.75, 23.78, "掸邦", role="area-muted",
          id_kind="area", name="shan"),
    Label(95.72, 22.45, "曼德勒省", role="area-muted",
          id_kind="area", name="mandalay-region"),
    Label(97.18, 19.32, "克耶邦", role="area-muted",
          id_kind="area", name="kayah"),
    Label(99.02, 20.30, "佤邦(南)", role="area-accent-3",
          id_kind="area", name="wa-south"),
    # 特区/区域名: 旧图 label-region-<slug>; 前端按区域家族处理, 样式仍由 role 决定.
    Label(98.30, 23.72, "缅甸联邦第一特区", role="area-accent-1",
          id_kind="region", name="special-region-1"),
    Label(98.25, 23.08, "MNDAA 实控区(大致范围)", role="area-accent-1",
          id_kind="region", name="mndaa-control"),
    Label(97.00, 23.34, "德昂邦", role="area-accent-2",
          id_kind="region", name="taang"),
    Label(97.00, 23.12, "(TNLA 控制)", role="area-accent-2",
          id_kind="region", name="tnla-control"),
    Label(98.60, 24.00, "原果敢自治区", role="area-accent-1",
          id_kind="region", name="kokang-saz"),
    Label(98.99, 22.60, "佤邦", role="area-accent-3",
          id_kind="region", name="wa-state"),
    Label(99.79, 21.73, "掸邦东部第四特区", role="area-accent-4",
          id_kind="region", name="special-region-4"),
    # 两条大江的河名.
    Label(95.75, 22.90, "伊洛瓦底江", role="river", name="irrawaddy"),
    Label(98.33, 21.55, "萨尔温江", role="river", name="salween"),
    # 城名: 落点跟着点位偏移; 普通城镇居中对齐.
    *(
        Label(
            lon + dx,
            lat + dy,
            text,
            role="city",
            ha="center" if kind == "town" else "left",
            name=slug,
        )
        for lon, lat, text, slug, kind, dx, dy in NORTHERN_SHAN_PLACES
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
    legend=NORTHERN_SHAN_LEGEND,
    legend_title=NORTHERN_SHAN_LEGEND_TITLE,
    title="缅甸掸邦特区与地方武装控制区地形图(2026年10月)",
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
