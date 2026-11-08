# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Ukraine subproject: dataset inventory and per-sheet render config.

是什么: 乌克兰子项目的唯一配置入口--数据集清单(从哪下,版本,下载范围,本地路径)与
每张图的规格(画框,投影,色带,经纬网,地名,图例,图面配色,文案). 数据准备脚本与绘图
脚本都从这里取参数, 下载范围和绘图范围不会再各写一份; 图例与地图共用同一份颜色.
完整说明: ``docs/reference/spec.md``(实例规格层)与 ``docs/reference/datasets.md``
(数据集层); 各图种的设计取舍见 ``docs/maps/ukraine.md``.
"""

from __future__ import annotations

from pathlib import Path

from cartopy_file.datasets import Dataset, dataset_set
from cartopy_file.sources import erddap_url, gadm_url
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
# 画框与下载范围
# ============================
# 乌克兰全图: 国土约 22.1~40.2°E / 44.4~52.4°N, 四周留出邻国与海域.
EXTENT_UKRAINE = Extent(21.0, 41.5, 43.2, 53.4)

# ETOPO 子集范围由画框外扩: 兰勃特等角圆锥投影的矩形画框四角向外张开, 反算到
# 经纬度约 18.8~43.8°E / 42.7~53.25°N, 这里再留余量. 数字与已下载的缓存一致,
# 不能随手改(会让 16 MB 的 NetCDF 作废); 这是全项目唯一一处 ETOPO 下载范围.
ETOPO_BBOX_UKRAINE = Extent(
    round(EXTENT_UKRAINE.lon_min - 2.5, 6),
    round(EXTENT_UKRAINE.lon_max + 2.5, 6),
    round(EXTENT_UKRAINE.lat_min - 0.8, 6),
    round(EXTENT_UKRAINE.lat_max + 0.1, 6),
)
ETOPO_STRIDE = 2  # 15 弧秒数据按索引步长 2 抽样 = 30 弧秒

# ============================
# 外部数据源的下载参数
# ============================
# OCHA HDX 直链: resources 页里的固定资源 id, 换版本时只改这一行.
OCHA_URL = (
    "https://data.humdata.org/dataset/0a24205d-084c-4ef9-9d53-9349bacbde1e/"
    "resource/86861957-a064-4427-b93a-2277738f0caa/download/2021-hno-gca_ngca.zip"
)
# OCHA 压缩包落在 raw/ 根, 解压到 raw/ocha_gca_ngca/(Dataset.dest 是解压目录).
OCHA_ARCHIVE = "raw/2021-hno-gca_ngca.zip"

# ---- OpenStreetMap (Overpass) 下载参数 ----
# 第聂伯河干流 relation(waterway=river): main_stream 成员首尾相接.
DNIEPER_RIVER_RELATION = 2086905
# 第聂伯河梯级水库(从上游到下游): OSM 里都是 natural=water 的 multipolygon
# relation. 只取 outer 成员: 水库里的岛屿(inner)在 1:330 万图上不足 1 px.
DNIEPER_RESERVOIRS: dict[int, str] = {
    1605938: "Київське водосховище",       # 基辅水库
    3173129: "Канівське водосховище",       # 卡尼夫水库
    2289192: "Кременчуцьке водосховище",    # 克列缅丘格水库
    287177: "Кам'янське водосховище",       # 卡缅斯克水库
    21217234: "Дніпровське водосховище",    # 第聂伯水库
}
# 卡霍夫卡水库: 2023-06 大坝被毁后放空, OSM 已删除其水面; 本图是 2022 年口径,
# 用 Natural Earth 10m 湖泊层里溃坝前的水库面补上.
KAKHOVKA_NE_NAME = "Kakhovka"
# 德涅斯特河干流 relation(waterway=river).
DNIESTER_RIVER_RELATION = 2474595
# 德左(德涅斯特河沿岸摩尔达维亚共和国, PMR)边界 relation.
TRANSNISTRIA_RELATION = 65335

# 南布格河/顿河: NE 10m 在河口前收笔(NE 收笔位置 31.749,47.259 / 39.378,47.111),
# 用 OSM 补下游段. bbox 用 Overpass 的 (south, west, north, east), 只覆盖收笔点
# 到河口的一小段; 跨出 bbox 的 way 仍带完整几何, 足够接上. 河名在 Python 里按
# osm_names 过滤: 同一段河在 OSM 里可能用不同语言/拼写标注.
RIVER_EXTENSIONS: tuple[dict, ...] = (
    {
        "key": "southern_bug",
        "ne_name": "Southern Bug",
        "osm_names": ("Південний Буг", "Южный Буг", "Southern Bug"),
        "bbox": (46.85, 31.55, 47.40, 32.10),
        "name_zh": "南布格河下游补段",
        "cache_id": "osm-southern-bug",
        "derived_id": "southern-bug-river",
    },
    {
        "key": "don",
        "ne_name": "Don",
        # 顿河下游在俄罗斯境内, OSM 用俄语名; 三角洲的汊道各有名字, 只要主河道.
        "osm_names": ("Дон",),
        "bbox": (47.00, 39.05, 47.25, 39.60),
        "name_zh": "顿河下游补段",
        "cache_id": "osm-don",
        "derived_id": "don-river",
    },
)

# Overpass QL: 键是数据集 id. 下载脚本从这里取查询体, 不再在脚本里拼 bbox/relation.
_RESERVOIR_IDS = ",".join(str(rel_id) for rel_id in DNIEPER_RESERVOIRS)
OSM_QUERIES: dict[str, str] = {
    "osm-dnieper-river": f"[out:json][timeout:300];rel({DNIEPER_RIVER_RELATION});out geom;",
    # 只取 outer 成员: inner 是水库里的岛(基辅水库一个 relation 就有 520 个
    # inner way), 数量和体积都远大于 outer, 图上却看不见.
    "osm-dnieper-reservoirs": (
        f'[out:json][timeout:300];rel(id:{_RESERVOIR_IDS})->.rels;'
        f'way(r.rels:"outer");out geom;'
    ),
    "osm-dniester-river": f"[out:json][timeout:300];rel({DNIESTER_RIVER_RELATION});out geom;",
    "osm-transnistria-boundary": (
        f"[out:json][timeout:300];rel({TRANSNISTRIA_RELATION});out geom;"
    ),
}
for _extension in RIVER_EXTENSIONS:
    _south, _west, _north, _east = _extension["bbox"]
    OSM_QUERIES[_extension["cache_id"]] = (
        f'[out:json][timeout:120];way["waterway"="river"]'
        f"({_south},{_west},{_north},{_east});out geom;"
    )

# ============================
# 数据集
# ============================
ETOPO_UKRAINE = Dataset(
    id="etopo-ukraine",
    kind="file",
    source_id="etopo-2022",
    url=erddap_url(
        "etopo-2022",
        stride=ETOPO_STRIDE,
        lon_range=(ETOPO_BBOX_UKRAINE.lon_min, ETOPO_BBOX_UKRAINE.lon_max),
        lat_range=(ETOPO_BBOX_UKRAINE.lat_min, ETOPO_BBOX_UKRAINE.lat_max),
    ),
    dest=f"raw/ETOPO_2022_v1_15s_ukraine_stride{ETOPO_STRIDE}.nc",
    files=("raw/ETOPO_2022_v1_15s_ukraine_stride*.nc",),
    bbox=ETOPO_BBOX_UKRAINE,
    stride=ETOPO_STRIDE,
    note="ETOPO 2022 乌克兰区域高程(stride 2 = 30 弧秒)",
)

GADM_UKR = Dataset(
    id="gadm41-ukr",
    kind="file",
    source_id="gadm-4.1",
    url=gadm_url("UKR"),
    dest="raw/gadm41_UKR/gadm41_UKR_1.json",
    note="GADM 4.1 乌克兰一级行政区原始 JSON(法理口径, 含克里米亚/塞瓦斯托波尔)",
)

OCHA_GCA_NGCA = Dataset(
    id="ocha-gca-ngca",
    kind="zip",
    source_id="ocha-hno-2021",
    url=OCHA_URL,
    dest="raw/ocha_gca_ngca",
    files=("raw/ocha_gca_ngca/*.shp",),
    note="OCHA/HDX 2021 HNO 顿巴斯 GCA/NGCA 分区(2021-hno-gca_ngca.zip)",
)

# 共享缓存里的 Natural Earth 图层用 cartopy-ne: 只登记出处, 由 cartopy 的下载器
# 管理, 全项目共用 data/cartopy 一份. 本子项目不再保留副本.
NE_COUNTRIES = Dataset(
    id="ne-countries-10m",
    kind="cartopy-ne",
    source_id="natural-earth",
    resolution="10m",
    category="cultural",
    name="admin_0_countries",
    note="Natural Earth 10m 国家多边形(海陆底色与国界轮廓)",
)

NE_COASTLINE = Dataset(
    id="ne-coastline-10m",
    kind="cartopy-ne",
    source_id="natural-earth",
    resolution="10m",
    category="physical",
    name="coastline",
    note="Natural Earth 10m 海岸线(1991 国界剪掉沿海段的蒙版)",
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
    kind="cartopy-ne",
    source_id="natural-earth",
    resolution="10m",
    category="physical",
    name="rivers_lake_centerlines",
    note="Natural Earth 10m 河网(一般河流与下游补段的 NE 上段)",
)

NE_LAKES = Dataset(
    id="ne-lakes-10m",
    kind="cartopy-ne",
    source_id="natural-earth",
    resolution="10m",
    category="physical",
    name="lakes",
    note="Natural Earth 10m 湖泊(卡霍夫卡水库溃坝前轮廓)",
)


def _osm_cache(dataset_id: str, dest: str, note: str) -> Dataset:
    """建一条 OSM 原始 JSON 缓存数据集; 查询体在 ``OSM_QUERIES`` 里."""
    return Dataset(
        id=dataset_id,
        kind="script",
        source_id="openstreetmap",
        dest=dest,
        note=note,
    )


OSM_DNIEPER_RIVER = _osm_cache(
    "osm-dnieper-river", "raw/osm_dnieper_river.json", "第聂伯河干流 OSM 原始关系(缓存)"
)
OSM_DNIEPER_WATER = _osm_cache(
    "osm-dnieper-reservoirs", "raw/osm_dnieper_reservoirs.json", "第聂伯河梯级水库 OSM 原始 way(缓存)"
)
OSM_DNIESTER_RIVER = _osm_cache(
    "osm-dniester-river", "raw/osm_dniester_river.json", "德涅斯特河干流 OSM 原始关系(缓存)"
)
OSM_TRANSNISTRIA = _osm_cache(
    "osm-transnistria-boundary",
    "raw/osm_transnistria_boundary.json",
    "德左(PMR)边界 OSM 原始关系(缓存)",
)
OSM_RIVER_EXTENSIONS = tuple(
    _osm_cache(
        extension["cache_id"],
        f"raw/osm_{extension['key']}_lower.json",
        f"{extension['name_zh']} OSM 原始 way(缓存)",
    )
    for extension in RIVER_EXTENSIONS
)


def _derived(dataset_id: str, filename: str, note: str) -> Dataset:
    """建一条由 ``prepare_data.py`` 生成的数据集; 绘图只读它的 GeoJSON."""
    return Dataset(id=dataset_id, kind="derived", dest=f"derived/{filename}", note=note)


OBLASTS = _derived("ukraine-oblasts", "ukraine_oblasts.geojson", "27 个一级行政区(含克里米亚/塞瓦斯托波尔)")
BORDER_1991 = _derived("ukraine-border-1991", "ukraine_1991.geojson", "1991 年国际承认边界(含克里米亚)")
CRIMEA_2014 = _derived("crimea-2014-line", "crimea_2014_line.geojson", "2014 年克里米亚陆上控制线")
OCCUPIED_2014 = _derived("occupied-2014", "occupied_2014.geojson", "2014 年顿巴斯分离武装控制区(顿/卢两州)")
CONTACT_2014 = _derived("contact-2014", "contact_line_2014.geojson", "2014 年顿巴斯接触线(近似)")
CLAIMED_2022 = _derived("claimed-2022", "claimed_2022.geojson", "2022 年俄方宣称的四州全境(面)")
TRANSNISTRIA = _derived("transnistria", "transnistria.geojson", "德左区域面(OSM PMR 按河心线/1991 国界裁切)")
DNIEPER_RIVER = _derived("dnieper-river", "dnieper_river_osm.geojson", "第聂伯河干流中心线(OSM)")
DNIEPER_WATER = _derived("dnieper-water", "dnieper_water_osm.geojson", "第聂伯河梯级水库水面(OSM + NE 卡霍夫卡)")
DNIESTER_RIVER = _derived("dniester-river", "dniester_river_osm.geojson", "德涅斯特河干流中心线(OSM)")
RIVER_EXTENSION_DERIVED = tuple(
    _derived(
        extension["derived_id"],
        f"{extension['key']}_river_osm.geojson",
        f"{extension['ne_name']} 中心线(NE 上段 + OSM 下段)",
    )
    for extension in RIVER_EXTENSIONS
)

DATASETS = dataset_set(
    "乌克兰",
    DATA,
    [
        ETOPO_UKRAINE,
        GADM_UKR,
        OCHA_GCA_NGCA,
        NE_COUNTRIES,
        NE_COASTLINE,
        NE_BORDERS,
        NE_RIVERS,
        NE_LAKES,
        OSM_DNIEPER_RIVER,
        OSM_DNIEPER_WATER,
        OSM_DNIESTER_RIVER,
        OSM_TRANSNISTRIA,
        *OSM_RIVER_EXTENSIONS,
        OBLASTS,
        BORDER_1991,
        CRIMEA_2014,
        OCCUPIED_2014,
        CONTACT_2014,
        CLAIMED_2022,
        TRANSNISTRIA,
        DNIEPER_RIVER,
        DNIEPER_WATER,
        DNIESTER_RIVER,
        *RIVER_EXTENSION_DERIVED,
    ],
)

# ============================
# 图规格
# ============================
# 兰勃特等角圆锥: 中央经线取国土中部 31°E, 标准纬线夹住南北缘 45°N / 52°N,
# 全国比例误差最小(理由见 docs/maps/ukraine.md 设计要点 1).
PROJECTION_LCC = Projection(
    "lambert_conformal",
    {
        "central_longitude": 31.0,
        "central_latitude": 48.5,
        "standard_parallels": (45.0, 52.0),
    },
)

# 高程/水深双色带: 深蓝(深水) -> 浅蓝(0 m 水面) | 浅绿(0 m 陆地) -> 黄 -> 棕 -> 雪白.
# 0 m 处直接跳变: 本图不画海岸线, 这条跳变就是岸线(理由见 docs/maps/ukraine.md
# 设计要点 2 与 9). 陆地锚点密集放在 0~500 m, 平原上的高程差异才拉得开.
UKRAINE_RELIEF = Relief(
    vmin=-2500,
    vmax=2500,
    name="ukraine_relief",
    sea=(
        (-2500, "#07203c"),
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
        (2300, "#c6bfb4"),
        (2500, "#f6f5f1"),
    ),
    ticks=(-2000, -1000, 0, 1000, 2000),
    title="高程 / 水深",
    unit="m",
    stops=2048,
    azimuth=315,       # 西北来光, 制图惯例
    altitude=45,
    vert_exag=2.5,     # 平原起伏只有几十米, 不夸张就看不出来
    shade_strength=1.5,
    shade_floor=0.55,
    zorder=1.0,
)

# 经纬网: 经度每 5°(20~40°E),纬度每 5°(45/50°N), 只画底边/左边刻度.
# dash 写成传给 ax.gridlines 的"未缩放"线型 (1, 1.65); matplotlib 的
# LineCollection 会再乘线宽 0.5 -> 实际 dash 0.5/0.825. geo 契约要的是缩放后的值,
# 所以用 geo_dash 单独给出, 不再在 collect 里手工写回.
GRATICULE_5X5 = Graticule(
    lon_step=5.0,
    lat_step=5.0,
    lon_ticks=(20.0, 25.0, 30.0, 35.0, 40.0),
    lat_ticks=(45.0, 50.0),
    color="gray",
    stroke="#808080",
    width_pt=0.5,
    dash=(1.0, 1.65),
    geo_dash=(0.5, 0.825),
    opacity=0.45,
    zorder=4.0,
)

# ============================
# 图面配色
# ============================
# 绘图与图例共用这一份颜色, 不允许两边各写一遍: 改色时图例必须跟着变.
COLOR_1991 = "#c62828"       # 1991 国际承认边界: 红
COLOR_1991_ALPHA = 0.62      # 1991 国界线半透明度: 让地形与下层边界透出来
COLOR_2014 = "#1565c0"       # 2014 实际控制线: 蓝
COLOR_2014_FILL = "#42a5f5"  # 2014 实际控制区填充
COLOR_KHARKIV = "#ef6c00"    # 2014 宣布的哈尔科夫人民共和国(未控制): 橙
COLOR_2022 = "#7b1fa2"       # 2022 俄方宣称边界: 紫
COLOR_OBLAST = "#5f6b73"     # 州界(背景参考线)
COLOR_RIVER = "#3f7fb5"      # 一般河流(Natural Earth 10m)
COLOR_RIVER_MAIN = "#2d6ea6"  # 第聂伯河/顿河等干流及其河名: 比一般河流深一档
COLOR_WATER = "#b3d2ea"      # 梯级水库水面填充
COLOR_WATER_EDGE = "#4a7fb0"  # 水面轮廓
COLOR_NEIGHBOR = "#8a8a8a"   # 邻国国界
# 地名样式(颜色/斜体/描边/字重/行高等)由前端 role 表统一决定, 生成端只登记 role;
# 这里只保留境外参照点与填色的几何颜色.
COLOR_REFERENCE = "#555555"  # 境外参照(德左/罗斯托夫): 中性灰, 不参与主题配色
# 境外参照区(德左)填色透明度: 比 2014 控制区(0.22~0.24)略深, 因为它没有
# 控制线/边界线可依靠, 只有这一层填色; 但也不能更深 -- 灰色压过地形会让人
# 以为这是本图的主题图层. 0.30 在黄色低地上是明显的灰绿色, 地形晕渲仍可辨.
COLOR_REFERENCE_FILL_ALPHA = 0.30

# 图例: 五种边界口径各一条. 文案一律单行, 分行/排版由前端负责;
# 2022 旧图是点划线(6, 2.0, 1.6, 2.0), legend.dash 只有 [实, 虚] 两项,
# 这里简化成 [6, 2](点划的"点"留给前端样式表).
LEGEND_TITLE = "图 例"
LEGEND = (
    LegendEntry(
        "1991 年国际承认边界(含克里米亚,仅陆上段)",
        "line", stroke=COLOR_1991, width_pt=2.7, opacity=COLOR_1991_ALPHA,
    ),
    LegendEntry(
        "2014 年实际控制线(克里米亚 · 顿巴斯接触线)",
        "line", stroke=COLOR_2014, width_pt=2.1,
    ),
    # 旧图是 Patch(edgecolor="none"): 只填色,不描边.
    LegendEntry(
        "2014 年俄方实际控制区(示意填色)",
        "rect", fill=COLOR_2014_FILL, width_pt=0.0, opacity=0.24,
    ),
    LegendEntry(
        "2014 年宣布的「哈尔科夫人民共和国」(未实际控制)",
        "line", stroke=COLOR_KHARKIV, width_pt=2.0, dash=(6.0, 3.0),
    ),
    LegendEntry(
        "2022 年俄方宣称四州全境边界(单方面宣称,非控制线)",
        "line", stroke=COLOR_2022, width_pt=2.1, dash=(6.0, 2.0),
    ),
)

# ============================
# 地名/城市/文案
# ============================
# 地名表统一写成 (经度, 纬度, 显示文案, id slug): slug 是小写 ASCII, 只进 id;
# 显示文案(中文)只进 text, 两者不混用(见 docs/reference/spec.md 的 Label).
# 国家标注: 放在画面中离边界线/城市较远的位置.
COUNTRY_LABELS = (
    (37.0, 52.55, "俄罗斯", "russia"),
    (27.6, 52.9, "白俄罗斯", "belarus"),
    (22.2, 51.9, "波兰", "poland"),
    (21.6, 48.8, "斯洛伐克", "slovakia"),
    (21.6, 47.95, "匈牙利", "hungary"),
    (24.7, 45.5, "罗马尼亚", "romania"),
    (28.3, 47.6, "摩尔多瓦", "moldova"),
)
SEA_LABELS = ((34.2, 44.25, "黑海", "black-sea"), (36.7, 46.35, "亚速海", "azov-sea"))
# 山系标注: 位置压在乔尔诺霍拉山体上 / 图幅右下角(索契以东); 旋转由前端处理.
MOUNTAIN_LABELS = (
    (24.32, 48.42, "喀尔巴阡山", "carpathians"),
    (40.42, 43.86, "高加索山", "caucasus"),
)
# 河名: 位置都放在河岸陆地上而不是水面上 -- 这张图要表达第聂伯河"河宽沿程变化",
# 河名压在水面上会用描边遮掉一段水面.
RIVER_LABELS = (
    (33.30, 49.60, "第聂伯河", "dnieper"),
    (40.15, 47.42, "顿河", "don"),
)

# 城市: (经度, 纬度, 显示名, id slug, 是否首都, 名称经度偏移, 纬度偏移, 对齐方式).
# 偏移都在 0.1~0.3°(约 10~25 km)量级, 只用于让文字离开边界线与其它标注.
CITIES = (
    (30.523, 50.450, "基辅", "kyiv", True, 0.20, 0.12, "left"),
    (36.230, 49.993, "哈尔科夫", "kharkiv", False, 0.16, 0.12, "left"),
    (30.732, 46.482, "敖德萨", "odesa", False, 0.16, -0.12, "left"),
    (35.046, 48.464, "第聂伯罗", "dnipro", False, 0.16, 0.12, "left"),
    # 顿涅茨克: 城点东南侧的 NGCA 空处, 文字整体在接触线以东, 不与线相交.
    (37.802, 48.015, "顿涅茨克", "donetsk", False, 0.10, -0.16, "left"),
    # 卢甘斯克: 城点正南, 避开北面的共和国名称与更北的 2014 接触线.
    (39.307, 48.574, "卢甘斯克", "luhansk", False, 0.00, -0.19, "center"),
    (35.139, 47.838, "扎波罗热", "zaporizhzhia", False, 0.16, 0.14, "left"),
    (32.617, 46.640, "赫尔松", "kherson", False, 0.16, -0.10, "left"),
    (37.556, 47.096, "马里乌波尔", "mariupol", False, -0.16, -0.06, "right"),
    (34.102, 44.952, "辛菲罗波尔", "simferopol", False, 0.16, 0.12, "left"),
    (33.522, 44.606, "塞瓦斯托波尔", "sevastopol", False, -0.16, 0.10, "right"),
    (24.031, 49.842, "利沃夫", "lviv", False, 0.16, 0.12, "left"),
)
# 境外参照城市: 灰圈白心 + 灰字, 与乌克兰境内城市区分; 不并进 CITIES,
# 否则会被读成乌克兰城市.
REFERENCE_CITIES = ((39.72, 47.23, "顿河畔罗斯托夫", "rostov-on-don", 0.06, -0.13),)
# 境外参照区域: 德左名称放在地带东侧敖德萨州的空地上.
# (文字经度, 纬度, 显示文案, id slug, 字号); 旧图的指引线契约 v2 没有 leader 字段, 暂不画.
REFERENCE_REGIONS = ((30.30, 47.14, "德涅斯特河沿岸摩尔达维亚共和国", "transnistria", 7.0),)

def _label(lon: float, lat: float, text: str, slug: str, role: str, size: float, **kwargs) -> Label:
    """写 Label 的短辅助函数; 顺序即前端叠放顺序, slug 是 id 的 ASCII 段."""
    return Label(lon, lat, text, role=role, font_size_pt=size, name=slug, **kwargs)


# 地名顺序按旧图 zorder 升序: 国名/海名 -> 山系 -> 河名 -> 主题区域名/境外参照 -> 城市.
UKRAINE_LABELS = (
    *(_label(lon, lat, text, slug, "country", 12.5) for lon, lat, text, slug in COUNTRY_LABELS),
    *(_label(lon, lat, text, slug, "sea", 11.5) for lon, lat, text, slug in SEA_LABELS),
    *(_label(lon, lat, text, slug, "highland", 11.0) for lon, lat, text, slug in MOUNTAIN_LABELS),
    *(_label(lon, lat, text, slug, "river", 10.5) for lon, lat, text, slug in RIVER_LABELS),
    # 2014 年宣布的"人民共和国": 卢甘斯克/顿涅茨克是实际控制区(蓝), 哈尔科夫只有
    # 宣称(橙), 强调色由 role 区分. 落点按"宣称全境"取中心, 不挤在 2014 控制区里.
    _label(
        39.03, 49.02, "卢甘斯克人民共和国", "luhansk-people-republic",
        "area-accent-3", 8.8, id_kind="republic",
    ),
    _label(
        37.70, 48.65, "顿涅茨克人民共和国", "donetsk-people-republic",
        "area-accent-3", 8.8, id_kind="republic",
    ),
    # 哈尔科夫: 纬度比州界折角高一截, 让开 2022 宣称边界的折角.
    _label(
        36.80, 49.50, "哈尔科夫人民共和国", "kharkiv-people-republic",
        "area-accent-4", 9.4, id_kind="republic",
    ),
    # 2022 年俄方宣称的两个州(顿/卢两州由上面的"人民共和国"标注覆盖): 放在远离
    # 第聂伯河/水库水面的州内陆地, 避免文字压住河宽变化的重点区域.
    _label(
        34.11, 46.52, "赫尔松州(俄宣称全境)", "kherson-oblast",
        "area-accent-1", 9.4, id_kind="region",
    ),
    _label(
        35.65, 47.08, "扎波罗热州(俄宣称全境)", "zaporizhzhia-oblast",
        "area-accent-1", 9.4, id_kind="region",
    ),
    _label(
        34.55, 45.40, "克里米亚(2014年俄实际控制)", "crimea",
        "area-accent-3", 9.6, id_kind="region",
    ),
    # 境外参照城市: 字号比境内城市(9.0)小一档, 只作定位参照.
    *(
        _label(lon + dx, lat + dy, name, slug, "city-reference", 8.4, ha="left")
        for lon, lat, name, slug, dx, dy in REFERENCE_CITIES
    ),
    # 境外狭长区域名: 只登记名字, 样式由 role=area-muted 决定.
    *(
        _label(lon, lat, text, slug, "area-muted", size, id_kind="region")
        for lon, lat, text, slug, size in REFERENCE_REGIONS
    ),
    # 城市: 文字跟着点位偏移; 首都与一般城市同字号, 只靠符号区分.
    *(
        _label(lon + dx, lat + dy, name, slug, "city", 9.0, ha=align)
        for lon, lat, name, slug, _capital, dx, dy, align in CITIES
    ),
)

# 城市点符号: 首都星形, 其余白心圆点, 境外参照灰圈白心; 只画符号不写城名.
UKRAINE_CITIES = (
    *(
        City(
            lon, lat, 15 if capital else 4.5,
            "#ffd200" if capital else "white", "black", 0.8 if capital else 0.9,
            capital=capital, name=slug,
        )
        for lon, lat, _name, slug, capital, _dx, _dy, _align in CITIES
    ),
    *(City(lon, lat, 3.6, "white", "#555555", 1.0, name=slug)
      for lon, lat, _name, slug, _dx, _dy in REFERENCE_CITIES),
)

TITLE = "乌克兰全图:1991 / 2014 / 2022 年边界"
SUBTITLE = "NOAA ETOPO 2022 地形 | 兰勃特等角圆锥投影(中央经线 31°E,标准纬线 45°N / 52°N)"

# 右栏口径说明: 一条注一个字符串, 生成端不折行(排版由前端负责);
# 内容(注 1~注 5)与旧图逐字一致.
NOTES = (
    "注 1:2014 年顿巴斯接触线以 OCHA 2021 年 GCA/NGCA 界线近似(明斯克协议线,2015 年后基本稳定),位置误差约 1–2 km.",
    "注 2:2022 年边界为俄方 2022-09 单方面宣称的赫尔松州,扎波罗热州,顿涅茨克人民共和国,卢甘斯克人民共和国全境,并非实际控制线.",
    "注 3:卢甘斯克,顿涅茨克两「人民共和国」于 2014 年宣布,名称标注在各自宣称全境范围内(顿涅茨克形心被城点与接触线占据,名称向北让开);实际控制范围见蓝色填充与接触线.哈尔科夫人民共和国只有 2014 年的宣称,图中按其宣称范围(哈尔科夫州)画出,未实际控制.",
    "注 4:哈尔科夫州界(橙)南段与 2022 年宣称边界(紫)完全重合,重合段只画紫线;紫/橙线与 1991 国界重合处只画红色 1991 线.1991 国界只画陆上段;海岸线不单独画,海陆界线由地形配色在 0 m 处的跳变表达.",
    "注 5:德涅斯特河沿岸摩尔达维亚共和国(德左)位于摩尔多瓦境内德涅斯特河东岸,1990 年单方面宣布独立,未获国际承认,俄方有军事存在;灰色填色与灰字仅为位置参照,不表示乌方立场.",
)

SHEET_UKRAINE = Sheet(
    id="ukraine-borders",
    out="ukraine_borders_1991_2014_2022_lambert_conformal.svg",
    extent=EXTENT_UKRAINE,
    projection=PROJECTION_LCC,
    figsize=(20, 12.5),
    axes=(0.035, 0.045, 0.735, 0.90),
    relief=UKRAINE_RELIEF,
    graticule=GRATICULE_5X5,
    basemap=True,
    tight_layout=False,
    base_ocean="#a2d0ee",
    base_land="#dce4a2",
    regrid_shape=3200,
    dpi=300,
    dataset_ids=(
        "etopo-ukraine",
        "gadm41-ukr",
        "ocha-gca-ngca",
        "ne-countries-10m",
        "ne-coastline-10m",
        "ne-borders-10m",
        "ne-rivers-10m",
        "ne-lakes-10m",
        "osm-dnieper-river",
        "osm-dnieper-reservoirs",
        "osm-dniester-river",
        "osm-transnistria-boundary",
        "osm-southern-bug",
        "osm-don",
    ),
    dem_id="etopo-ukraine",
    labels=UKRAINE_LABELS,
    cities=UKRAINE_CITIES,
    legend=LEGEND,
    legend_title=LEGEND_TITLE,
    title=TITLE,
    subtitle=SUBTITLE,
    notes=NOTES,
    colorbar_title="高程 / 水深",
)

SHEETS = (SHEET_UKRAINE,)
