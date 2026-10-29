#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Volga basin and neighbouring republics, topographic maps (two sheets).

是什么: 以 ETOPO 2022 地形晕渲为底图, 叠加 HydroSHEDS 伏尔加河流域、GADM 4.1
俄罗斯一级行政区、Natural Earth 10m 河网与梯级水库水面, 一次生成两张自包含
SVG: 只画流域的流域图, 与画框收窄、保留六个周边共和国的共和区图; 只绘制地理
要素, 不绘制任何文字/图例/色标/标题/比例尺/指北针.
完整说明: 见 ``docs/maps/volga.md``(两份画框、行政区取舍、河网分级与配色).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import geopandas as gpd  # 读取预加工好的 GeoJSON
import matplotlib.colors as mcolors  # 自定义高程/水深色带
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网线位置定位
import numpy as np  # 数组运算
from shapely.geometry import LineString, box  # 投影画框与湖库筛选
from shapely.ops import unary_union  # 流域/行政区几何合并

# cartopy 底图缓存统一到仓库 data/cartopy, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy

configure_cartopy()

# 重合线剪枝: 国界与海岸线/湖岸重合的段落只留一种线, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# 共享的 ETOPO/晕渲/底图工具(实现见 src/cartopy_file/relief.py).
from cartopy_file.relief import find_etopo, load_elevation, load_ne_layer, make_relief

from cartopy_file.output import apply_svg_output

# 底图 + geo.json 出图: save_map 同时写裁到地图框的 SVG 与同名 geo.json,
# 见 docs/reference/geo.md.
from cartopy_file.geo import (
    GeoDoc,
    figure_frame,
    relief_from_cmap,
    save_map,
)

# 产物统一为 SVG, 见 docs/reference/output.md.
apply_svg_output()


# ============================
# 配置
# ============================
# 流域图画框: [min_lon, max_lon, min_lat, max_lat].
# 西界留出瓦尔代丘陵(伏尔加河源头)以西约 1.7°; 东界到乌拉尔山西坡;
# 南界 44.4°N 覆盖里海西北岸与三角洲; 北界 62.3°N 留出上卡马河源地的余量.
EXTENT_BASIN = (30.3, 62.3, 44.4, 62.3)

# 周边共和国图画框: 不画科米与卡尔梅克后按内容收窄, 北到 59°N(科米南缘以南),
# 西到 40°E(上伏尔加), 东到 60°E(卡马河以东的乌拉尔西坡); 南界沿用 44.4°N,
# 保留流域三角洲与里海西北岸.
EXTENT_REPUBLICS = (40.0, 60.0, 44.4, 59.0)

# 投影参数: 中央经线取流域中部, 标准纬线夹住画框南北缘(47°N / 57°N),
# 使流域主体处于低形变区; 与 Ukraine/northern_shan 使用同一类投影.
PROJECTION = ccrs.LambertConformal(
    central_longitude=46.0,
    central_latitude=53.0,
    standard_parallels=(47.0, 57.0),
)

# 高程配色与晕渲参数. 画框内最低为里海约 -1000 m、黑海西北陆架, 最高为
# 南乌拉尔山约 1640 m; 取 -2500~2200 m 与 Ukraine 图一致的两端余量,
# 色带在 0 m 处断开(水/陆), 陆地锚点集中在 0~500 m 的伏尔加平原.
ELEV_VMIN, ELEV_VMAX = -2500, 2500
HILLSHADE_AZIMUTH = 315  # 西北来光, 制图惯例
HILLSHADE_ALTITUDE = 45
HILLSHADE_VERT_EXAG = 3.0  # 平原起伏只有几十米, 不夸张看不出河谷与丘陵
# 只压暗的乘法晕渲强度(见 relief.make_relief): 1.5 在 30″ ETOPO 上既能显出
# 丘陵/河谷, 又不会把大范围平原压成灰底; 与 Ukraine 图取值一致.
RELIEF_SHADE_STRENGTH = 1.7


def make_relief_cmap(vmin: float, vmax: float) -> mcolors.LinearSegmentedColormap:
    """高程/水深双色带: 深蓝(深水) -> 浅蓝(0 m 水面) | 浅绿(0 m 陆地) -> 黄 -> 棕 -> 灰.

    为什么要在 0 m 处断开(同 Ukraine 图的理由):
        "terrain" 一类单段色带把 ±2500 m 线性铺开, 海平面正好落在中点,
        0~300 m 的陆地只占 6% 的色带宽度; 而里海北部水深不足 20 m,
        0 m 水面与 0 m 陆地在归一化值上几乎重合, 图上分不出海陆.
        这里让水色在 0 m 处直接跳到偏黄的浅绿, 再把陆地锚点密集放在
        0~500 m, 伏尔加平原上的高程差异才拉得开.

    N=2048 让 0 m 处的水/陆跳变只占一个色阶宽度; 配合 Normalize 使用时,
    归一化横轴仍是线性, 只是 0 m 两侧颜色不连续.
    """
    sea = [
        (-2500, "#07203c"),
        (-2000, "#0f3c66"),
        (-1250, "#1b628f"),
        (-700, "#2f82b5"),
        (-300, "#5aa2cd"),
        (-100, "#75b3db"),
        (-20, "#8cc4e7"),
        (-1, "#a2d0ee"),
    ]
    land = [
        (1, "#c9d98d"),
        (40, "#cfd990"),
        (90, "#d9dd96"),
        (150, "#e0e19c"),
        (230, "#ddd596"),
        (340, "#d6c58a"),
        (500, "#c4a873"),
        (700, "#ab8a5e"),
        (950, "#8f7049"),
        (1200, "#7a5f40"),
        (1550, "#786a58"),
        (1900, "#9c9186"),
        (2500, "#d9d5cd"),
    ]

    def u(elev: float) -> float:
        return (elev - vmin) / (vmax - vmin)

    anchors = [(u(e), color) for e, color in sea] + [(u(e), color) for e, color in land]
    return mcolors.LinearSegmentedColormap.from_list("volga_relief", anchors, N=2048)


ELEV_CMAP = make_relief_cmap(ELEV_VMIN, ELEV_VMAX)

# 海陆底色(仅在 ETOPO 子集边缘露出时可见, 与 ELEV_CMAP 两端一致).
BASE_OCEAN_COLOR = "#a2d0ee"
BASE_LAND_COLOR = "#dce4a2"

# 图面配色: 主题层各一个固定颜色, 避免读图歧义.
COLOR_BASIN_FILL = "#3f8fc4"   # 流域面: 浅蓝, 叠在地形上不抢细节
COLOR_BASIN_EDGE = "#1b5c8c"   # 流域界: 深蓝
COLOR_BASIN_ALPHA = 0.15
COLOR_REPUBLIC_FILL = "#7b5aa6"   # 联邦主体共和国: 蓝紫, 与蓝色水系/暖色地形都分得开
COLOR_REPUBLIC_EDGE = "#4a2f6b"
COLOR_REPUBLIC_ALPHA = 0.23
COLOR_SUBJECT = "#5f6b73"      # 其余联邦主体界: 中性灰虚线, 只作背景
COLOR_BORDER = "#4a4a4a"       # 国界(GADM 4.1 口径)
COLOR_RIVER = "#5c93bf"        # 支流
COLOR_RIVER_TRUNK = "#2d6ea6"  # 干流(高等级/大流量河段)
COLOR_WATER = "#b9d7ee"        # 梯级水库水面
COLOR_WATER_EDGE = "#4a7fb0"

# 地名样式(颜色/斜体/描边/字重/行高等)由前端 role 表统一决定, 生成端只登记 role 与
# 字号; 这里不再定义任何标注专用颜色常量.

# 周边八个联邦主体共和国(GADM NAME_1): 流域直接覆盖/紧邻的民族共和国.
# 流域图不画行政区; 共和国图只保留前六个, 科米与卡尔梅克不画.
REPUBLICS = (
    "Tatarstan",
    "Bashkortostan",
    "Chuvash",
    "Mariy-El",
    "Mordovia",
    "Udmurt",
    "Kalmyk",
    "Komi",
)
REPUBLICS_SHOWN = REPUBLICS[:6]
REPUBLICS_HIDDEN = frozenset(REPUBLICS[6:])
# 轮廓小的共和国用略小字号, 防止两行文字的宽度超出共和国范围.
SMALL_REPUBLICS = frozenset({"Chuvash", "Mariy-El", "Mordovia", "Kalmyk"})

# 共和国名称: GADM NAME_1 -> (经度, 纬度, 文字). 放在各共和国境内的空旷处,
# 避开首府城点与主要河湖; 小共和国用两行文字, 字号见 SMALL_REPUBLICS.
REPUBLIC_LABELS: dict[str, tuple[float, float, str]] = {
    "Tatarstan": (50.30, 54.85, "鞑靼斯坦\n共和国"),
    "Bashkortostan": (56.60, 53.35, "巴什科尔托斯坦\n共和国"),
    "Chuvash": (47.05, 55.28, "楚瓦什\n共和国"),
    "Mariy-El": (48.90, 57.22, "马里埃尔\n共和国"),
    "Mordovia": (44.50, 54.85, "莫尔多瓦\n共和国"),
    "Udmurt": (52.60, 57.55, "乌德穆尔特\n共和国"),
    "Kalmyk": (45.25, 46.78, "卡尔梅克\n共和国"),
    "Komi": (54.50, 61.00, "科米\n共和国"),
}

# 城市: (经度, 纬度, 名称, 类型, 文字偏移经度, 文字偏移纬度, 水平对齐).
# 类型: capital=首都(星形), rep=共和国首府(方块), city=一般城市(圆点).
# 偏移与对齐是改前成品的文字落点, 现在只用来产出 geo.labels 的锚点, 不再画文字.
CITIES = [
    (37.617, 55.755, "莫斯科", "capital", 0.12, 0.14, "left"),
    (35.900, 56.858, "特维尔", "city", 0.10, 0.10, "left"),
    (39.873, 57.626, "雅罗斯拉夫尔", "city", -0.12, 0.16, "right"),
    (40.926, 57.768, "科斯特罗马", "city", 0.12, -0.16, "left"),
    (44.002, 56.326, "下诺夫哥罗德", "city", 0.10, 0.10, "left"),
    (49.660, 58.603, "基洛夫", "city", 0.10, 0.10, "left"),
    (56.248, 58.010, "彼尔姆", "city", 0.10, 0.10, "left"),
    (53.204, 56.852, "伊热夫斯克", "rep", 0.10, 0.10, "left"),
    (49.122, 55.788, "喀山", "rep", 0.10, 0.10, "left"),
    (55.972, 54.738, "乌法", "rep", 0.10, 0.10, "left"),
    (50.150, 53.195, "萨马拉", "city", 0.10, 0.10, "left"),
    (48.403, 54.317, "乌里扬诺夫斯克", "city", 0.10, 0.10, "left"),
    (46.034, 51.533, "萨拉托夫", "city", 0.10, 0.10, "left"),
    (44.501, 48.708, "伏尔加格勒", "city", 0.10, 0.10, "left"),
    (48.034, 46.349, "阿斯特拉罕", "city", 0.10, 0.10, "left"),
    (47.251, 56.132, "切博克萨雷", "rep", -0.10, -0.12, "right"),
    (47.890, 56.638, "约什卡尔奥拉", "rep", 0.10, -0.12, "left"),
    (45.184, 54.183, "萨兰斯克", "rep", 0.10, -0.10, "left"),
    (45.000, 53.195, "奔萨", "city", 0.10, -0.10, "left"),
    (39.741, 54.626, "梁赞", "city", 0.10, 0.10, "left"),
    (55.097, 51.768, "奥伦堡", "city", 0.10, 0.10, "left"),
    (44.256, 46.307, "埃利斯塔", "rep", -0.12, -0.12, "right"),
    (50.836, 61.668, "瑟克特夫卡尔", "rep", 0.10, 0.10, "left"),
]

# 河名: (经度, 纬度, 文字). 文字放在河道旁的陆地上; 旋转由前端处理, 生成端不再存
# 河道走向参考点(旧版用它算投影平面内的旋转角).
RIVER_LABELS = [
    (43.05, 56.10, "伏尔加河"),
    (45.35, 49.90, "伏尔加河"),
    (53.40, 55.35, "卡马河"),
    (41.55, 54.85, "奥卡河"),
    (56.30, 54.15, "别拉亚河"),
    (50.20, 57.45, "维亚特卡河"),
]

# 邻国名称: 只标画框内可见的三个邻国.
COUNTRY_LABELS = [
    (55.10, 47.60, "哈萨克斯坦"),
    (30.95, 53.45, "白俄罗斯"),
    (33.10, 48.75, "乌克兰"),
]

# 海域名称.
SEA_LABELS = [
    (50.60, 45.35, "里海"),
    (31.20, 45.05, "黑海"),
    (36.80, 46.05, "亚速海"),
]

# 地貌名称: (经度, 纬度, 文字). 旧版给乌拉尔山配了 78° 的走向旋转, 现在旋转由
# 前端处理, 生成端只登记位置与字号.
HIGHLAND_LABELS = [
    (33.10, 57.55, "瓦尔代丘陵"),
    (46.90, 52.20, "伏尔加高地"),
    (47.40, 48.60, "里海低地"),
    (59.30, 56.80, "乌拉尔山"),
]

# 河网分级: Natural Earth 10m 河流的 scalerank(数值越小越主要)分三档.
# 画框约 1:770 万比例尺, 正好是 Natural Earth 10m 的设计尺度, 直接用缓存
# 数据即可; 不引入 HydroRIVERS 那样几十 MB 的逐段河网(本图不需要支流级细节).
RIVER_TRUNK_MAX_SCALERANK = 3   # 伏尔加干流
RIVER_MEDIUM_MAX_SCALERANK = 7  # 卡马/奥卡/维亚特卡/别拉亚等
RIVER_EXCLUDE_FEATURECLA = {"Canal"}

# 版式尺寸(英寸): 地图区高固定, 宽度按投影后的画框宽高比算, 再据此定画布宽,
# 这样两张画框不同的图都能让地图正好填满左侧地图区, 不靠留白对齐.
FIG_HEIGHT_IN = 12.2
MAP_LEFT_IN = 0.54
MAP_BOTTOM_IN = 0.8784
MAP_HEIGHT_IN = 9.8942
# 右侧原图例/色标/注面板的占位: 只删了文字、未重排版面, 画布宽度仍计入
# 这三项, 地图区的位置与大小因此与改前完全一致; 右侧留白等后续版面设计再处理.
PANEL_GAP_IN = 0.218
PANEL_WIDTH_IN = 4.23
FIG_RIGHT_IN = 0.144


# 数据文件(由 Volga/download_data.py 生成).
SUBJECTS_GEOJSON = DATA_DIR / "volga_subjects.geojson"
BASIN_GEOJSON = DATA_DIR / "volga_basin.geojson"
BORDER_GEOJSON = DATA_DIR / "russia_border.geojson"


# ============================
# 图纸规格
# ============================
@dataclass(frozen=True)
class MapSpec:
    """一张图的画框、行政区主题开关、默认文案与产物路径.

    为什么用规格对象而不是给每张图写一套流程: 两张图共用投影、色带、地形、
    河网与版式, 差异只有画框、画哪些行政区与文案(geo.suggestions); 把这些
    差异收敛成数据, 图层函数与 geo 收集只需按 spec 取参数.
    """

    key: str
    extent: tuple[float, float, float, float]
    title: str
    subtitle: str
    out_svg: Path
    draw_admin: bool
    area_label_in_map: bool
    republics: tuple[str, ...] = ()
    hidden_subjects: frozenset[str] = frozenset()


SPEC_BASIN = MapSpec(
    key="basin",
    extent=EXTENT_BASIN,
    title="伏尔加河流域地形图",
    subtitle="ETOPO 2022 | 流域: HydroSHEDS | 国界: GADM 4.1 | 兰勃特等角圆锥投影",
    out_svg=ROOT / "volga_basin_topography_etopo2022_lambert_conformal.svg",
    draw_admin=False,
    area_label_in_map=False,
)

SPEC_REPUBLICS = MapSpec(
    key="republics",
    extent=EXTENT_REPUBLICS,
    title="伏尔加河流域与周边联邦主体共和国地形图",
    subtitle="ETOPO 2022 | 流域: HydroSHEDS | 行政区: GADM 4.1 | 兰勃特等角圆锥投影",
    out_svg=ROOT / "volga_basin_republics_topography_etopo2022_lambert_conformal.svg",
    draw_admin=True,
    area_label_in_map=True,
    republics=REPUBLICS_SHOWN,
    hidden_subjects=REPUBLICS_HIDDEN,
)

SPECS = (SPEC_BASIN, SPEC_REPUBLICS)


@dataclass(frozen=True)
class Layout:
    """画布与地图区的位置(figure 分数), 由画框的投影宽高比算出."""

    figsize: tuple[float, float]
    map_rect: tuple[float, float, float, float]
    map_width_in: float


def _projected_aspect(extent: tuple[float, float, float, float]) -> float:
    """画框在目标投影下的宽高比.

    为什么不用经纬度跨度直接算: 兰勃特投影下纬线是弧, 同一纬度带的东西向
    跨度随经度变化; 用 cartopy set_extent 的同一套投影几何(画框四边的
    LineString)取包围盒, 得到的比例才能让地图正好填满坐标区.
    """
    x0, x1, y0, y1 = extent
    ring = LineString([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])
    bounds = PROJECTION.project_geometry(ring, ccrs.PlateCarree()).bounds
    return (bounds[2] - bounds[0]) / (bounds[3] - bounds[1])


def make_layout(spec: MapSpec) -> Layout:
    """按画框宽高比定画布宽度, 并给出地图区的位置.

    画布宽度仍计入右侧面板的旧占位(见 PANEL_* 常量), 因此地图区的位置与大小
    与改前一致; 右侧留白等后续版面设计再处理.
    """
    map_width_in = MAP_HEIGHT_IN * _projected_aspect(spec.extent)
    fig_width_in = (
        MAP_LEFT_IN + map_width_in + PANEL_GAP_IN + PANEL_WIDTH_IN + FIG_RIGHT_IN
    )
    map_rect = (
        MAP_LEFT_IN / fig_width_in,
        MAP_BOTTOM_IN / FIG_HEIGHT_IN,
        map_width_in / fig_width_in,
        MAP_HEIGHT_IN / FIG_HEIGHT_IN,
    )
    return Layout(
        figsize=(fig_width_in, FIG_HEIGHT_IN),
        map_rect=map_rect,
        map_width_in=map_width_in,
    )


# ============================
# Natural Earth 图层缓存
# ============================
@lru_cache(maxsize=None)
def _ne_layer(resolution: str, category: str, name: str):
    """缓存一份 Natural Earth 图层: 两张图共用同一份 shapefile, 只读一次."""
    return load_ne_layer(resolution, category, name)


@lru_cache(maxsize=None)
def _ne_union(resolution: str, category: str, name: str):
    """缓存整层几何合并结果; 海洋/湖泊并集在掩版与水陆判识里要反复用."""
    layer = _ne_layer(resolution, category, name)
    return None if layer is None else layer.union_all()


# ============================
# 数据读取
# ============================
def _require(path: Path) -> Path:
    """检查数据文件存在, 缺失时给出可操作提示."""
    if not path.exists():
        raise FileNotFoundError(
            f"未找到数据: {path}\n请先运行: python Volga/download_data.py"
        )
    return path


def load_vectors(extent: tuple[float, float, float, float]) -> tuple[gpd.GeoDataFrame, object, object]:
    """读取绘图所需的三份本地 GeoJSON, 返回 (行政区, 流域面, 国界线).

    流域取联合后的单个几何; 国界线合并成一个 MultiLineString. 河网与湖泊
    来自仓库 data/cartopy 里已缓存的 Natural Earth 10m 图层(见 add_rivers /
    add_water), 不需要各图种再下载一份.
    """
    subjects = gpd.read_file(_require(SUBJECTS_GEOJSON))
    basin = unary_union(gpd.read_file(_require(BASIN_GEOJSON)).geometry)
    # 流域面裁到俄罗斯陆地: HydroBASINS 的单元边界在里海岸边比 GADM 岸线
    # 略靠外, 不裁的话浅蓝填色会在海面上多出一圈岸线误差(约 1500 km²);
    # 行政区的陆地并集与国界同源, 裁完岸线才与国界对齐.
    land = unary_union(subjects.geometry)
    # 再减去 Natural Earth 10m 海洋面: 行政区的陆地并集在里海西岸包含部分
    # 管辖水域, 只裁陆地仍会在三角洲以南留一条伸进里海的尾巴; 海洋面把
    # 水域部分彻底去掉, 流域南界落在真实岸线上.
    ocean = _ne_union("10m", "physical", "ocean")
    if ocean is not None:
        view = box(extent[0] - 1.0, extent[2] - 1.0, extent[1] + 1.0, extent[3] + 1.0)
        land = land.difference(ocean.intersection(view))
    basin = unary_union(polygon_parts(basin.intersection(land)))
    border = unary_union(gpd.read_file(_require(BORDER_GEOJSON)).geometry)
    return subjects, basin, border


def basin_area_km2(basin) -> float:
    """流域面积(km²): 在等积投影 EPSG:6933 下计算, 与图注「约 141 万 km²」同口径."""
    # EPSG:6933 的单位是米, 面积是 m²; 先换成 km² 再返回.
    return float(
        gpd.GeoSeries([basin], crs="EPSG:4326").to_crs("EPSG:6933").area.iloc[0] / 1.0e6
    )


# ============================
# 几何工具
# ============================
def polygon_parts(geom, *, min_area_deg2: float = 1e-4):
    """把 (Multi)Polygon 拆成面部件并丢掉面积过小的缝合碎片.

    为什么需要: HydroBASINS 单元 union 后会在相邻单元接缝处留下面积为 0 的
    针状碎屑; 直接画边界会在图上出现孤立小点/毛刺(见 docs/maps/volga.md).
    """
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom] if geom.area > min_area_deg2 else []
    if geom.geom_type == "MultiPolygon":
        return [part for part in geom.geoms if part.area > min_area_deg2]
    # 面与面求交偶尔返回 GeometryCollection(夹杂线/点), 递归取其中的面.
    parts: list = []
    for child in getattr(geom, "geoms", []):
        parts.extend(polygon_parts(child, min_area_deg2=min_area_deg2))
    return parts


def in_extent(
    lon: float,
    lat: float,
    extent: tuple[float, float, float, float],
    *,
    pad: float = 0.0,
) -> bool:
    """点是否落在画框内; 用来跳过画框外的城市点, 避免符号画到地图区之外."""
    x0, x1, y0, y1 = extent
    return x0 - pad <= lon <= x1 + pad and y0 - pad <= lat <= y1 + pad


# ============================
# 图层
# ============================
def negative_land_as_land(
    z: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
    extent: tuple[float, float, float, float],
) -> np.ndarray:
    """把海平面以下、但不在海洋/湖泊多边形内的陆地像元改成 0.5 m 再配色.

    为什么需要: ETOPO 的高程是相对海平面的, 里海沿岸低地(约 -28~0 m)与里海
    水面(-28 m)都落在负值段. 若按 z<0 一刀切, 里海低地会被画成浅蓝色水面,
    在伏尔加下游/卡尔梅克一带连成一片假海. 这里用 Natural Earth 10m 的
    ocean + lakes 判定真正的水域, 只有水域保留负高程配色, 其余负高程陆地
    抬到 0.5 m(仍用陆地色, 视觉上抬升可忽略).
    """
    try:
        from shapely import contains_xy
    except ImportError:  # pragma: no cover - shapely 2.x 才有向量化谓词
        return z
    ocean = _ne_union("10m", "physical", "ocean")
    lakes = _ne_union("10m", "physical", "lakes")
    geoms = [geom for geom in (ocean, lakes) if geom is not None]
    if not geoms:
        print("警告: 缺少 Natural Earth ocean/lakes, 负高程陆地仍按水面配色.")
        return z
    water_geom = unary_union(geoms).intersection(
        box(extent[0] - 1.0, extent[2] - 1.0, extent[1] + 1.0, extent[3] + 1.0)
    )
    fixed = z.copy()
    rows, cols = np.nonzero(z < 0)
    in_water = contains_xy(water_geom, lon[cols], lat[rows])
    fixed[rows[~in_water], cols[~in_water]] = 0.5
    return fixed


def prepare_elevation(
    lon: np.ndarray, lat: np.ndarray, z: np.ndarray
) -> np.ndarray:
    """两张图共用的高程预处理: 只把真正水域留在负高程段.

    为什么只做一次: 水陆判识依赖与画框无关的 Natural Earth 面, 流域图的画框
    覆盖共和国图, 同一份修正后的高程可以直接铺进两个坐标区.
    """
    return negative_land_as_land(z, lon, lat, EXTENT_BASIN)


def add_relief(
    ax: plt.Axes,
    lon: np.ndarray,
    lat: np.ndarray,
    z: np.ndarray,
    *,
    regrid_shape: int,
) -> None:
    """把已修正海陆的高程栅格做成晕渲铺到图上.

    regrid_shape 取地图区宽度的像素量级(dpi 300 下约 3700 px), 否则 30″
    ETOPO 在 1:430 万比例尺上会被 cartopy 重采样糊掉(同 Ukraine 图).
    """
    relief, _, _ = make_relief(
        z,
        lat,
        lon,
        vmin=ELEV_VMIN,
        vmax=ELEV_VMAX,
        cmap=ELEV_CMAP,
        azimuth=HILLSHADE_AZIMUTH,
        altitude=HILLSHADE_ALTITUDE,
        vert_exag=HILLSHADE_VERT_EXAG,
        shade_strength=RELIEF_SHADE_STRENGTH,
    )
    ax.imshow(
        relief,
        origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        regrid_shape=regrid_shape,
        interpolation="nearest",
        zorder=1,
    )


def add_basin(ax: plt.Axes, basin) -> None:
    """流域面浅蓝填色 + 深蓝外轮廓.

    为什么先填色后画线: 填色只作"流域范围"的底色, 不能压住地形细节与河网;
    外轮廓是这张图的第一主题边界, 用实线而不是虚线, 并加一条白色底描边,
    让它在深色山体与半透明色块上都能连续可辨.
    """
    ax.add_geometries(
        [basin],
        crs=ccrs.PlateCarree(),
        facecolor=COLOR_BASIN_FILL,
        edgecolor="none",
        alpha=COLOR_BASIN_ALPHA,
        linewidth=0,
        zorder=1.5,
    )
    ax.add_geometries(
        [basin.boundary],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="white",
        linewidth=3.8,
        alpha=0.55,
        zorder=3.9,
    )
    ax.add_geometries(
        [basin.boundary],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=COLOR_BASIN_EDGE,
        linewidth=2.1,
        zorder=4.0,
    )


def add_water(ax: plt.Axes, extent: tuple[float, float, float, float]) -> None:
    """填画框内全部 Natural Earth 10m 湖泊与梯级水库水面.

    为什么需要填: 伏尔加—卡马梯级水库面积小、水深浅, ETOPO 30″ 下只是几
    像素宽的浅色带, 单独填色才能读出"上游窄河、下游宽水面"的沿程变化
    (与 Ukraine 图处理第聂伯河梯级水库的理由一致); 咸海的水面高出海平面
    (+29 m), 按高程配色会画成陆地, 也只能靠湖泊多边形补上.
    不填里海: 里海不在 Natural Earth lakes 图层(在 ocean 图层), 它的水深
    仍由 ETOPO 配色表达, 避免用等深浅蓝盖掉水下地形.
    """
    lakes = _ne_layer("10m", "physical", "lakes")
    if lakes is None:
        print("警告: 缺少 Natural Earth 湖泊数据, 跳过大水面填色.")
        return
    x0, x1, y0, y1 = extent
    view = box(x0, y0, x1, y1)
    selected = lakes[lakes.geometry.intersects(view)]
    geoms = [g for g in selected.geometry if g is not None and not g.is_empty]
    if not geoms:
        print("警告: 画框内没有 Natural Earth 湖泊, 跳过水面填色.")
        return
    ax.add_geometries(
        geoms,
        crs=ccrs.PlateCarree(),
        facecolor=COLOR_WATER,
        edgecolor=COLOR_WATER_EDGE,
        linewidth=0.45,
        zorder=2.75,
    )


def add_rivers(ax: plt.Axes, extent: tuple[float, float, float, float]) -> None:
    """按 scalerank 分三档画 Natural Earth 10m 河网.

    为什么分级: 河网统一同宽会把伏尔加干流淹没在支流里; 按 scalerank 分三档
    后, 干流(粗, 带白描边)-主要支流(中)-次要河流(细)的主次关系与河谷规模
    一致. 只给五条主要河流写河名, 避免整张图被文字压满.
    排除 Canal: 运河是人工线, 不属于本图要表达的天然水系.
    """
    rivers = _ne_layer("10m", "physical", "rivers_lake_centerlines")
    if rivers is None:
        print("警告: 缺少 Natural Earth 河流数据, 跳过河流图层.")
        return
    x0, x1, y0, y1 = extent
    view = box(x0, y0, x1, y1)
    selected = rivers[
        rivers.geometry.intersects(view)
        & ~rivers["featurecla"].isin(RIVER_EXCLUDE_FEATURECLA)
    ]
    if selected.empty:
        print("警告: 画框内没有 Natural Earth 河流, 跳过河流图层.")
        return
    ranks = selected["scalerank"].to_numpy()

    def draw(geoms, color: str, linewidth: float, halo: bool) -> None:
        geoms = [g for g in geoms if g is not None and not g.is_empty]
        if not geoms:
            return
        if halo:
            ax.add_geometries(
                geoms,
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor="#e8f4ff",
                linewidth=linewidth + 1.9,
                zorder=2.50,
            )
        ax.add_geometries(
            geoms,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=color,
            linewidth=linewidth,
            zorder=2.55,
        )

    geoms = list(selected.geometry)
    trunk = ranks <= RIVER_TRUNK_MAX_SCALERANK
    medium = (ranks > RIVER_TRUNK_MAX_SCALERANK) & (
        ranks <= RIVER_MEDIUM_MAX_SCALERANK
    )
    minor = ~trunk & ~medium
    draw([g for g, m in zip(geoms, minor) if m], COLOR_RIVER, 0.5, halo=False)
    draw(
        [g for g, m in zip(geoms, medium) if m],
        "#4a86b8",
        0.85,
        halo=False,
    )
    draw(
        [g for g, m in zip(geoms, trunk) if m],
        COLOR_RIVER_TRUNK,
        1.9,
        halo=True,
    )


def add_admin(ax: plt.Axes, subjects: gpd.GeoDataFrame, spec: MapSpec) -> None:
    """主体界(灰色虚线)与 spec.republics 的填色/描边.

    为什么共和国填色画在行政界线之下: 填色是面, 界线是线, 先铺面再画线,
    界线不会被半透明填色盖住. 共和国的外边界另用较粗的蓝紫线强调; 它与
    俄罗斯国界重合的段落会被后面更粗的国界线压住(国界 zorder 更高).
    流域图不画行政区(draw_admin=False), 只留国界; 共和国图的 hidden_subjects
    (科米、卡尔梅克)既不填色也不画自己的灰色界线.
    """
    if not spec.draw_admin:
        return
    republic_names = set(spec.republics)
    hidden = set(spec.hidden_subjects)
    republics = subjects[subjects["name"].isin(republic_names)]
    others = subjects[~subjects["name"].isin(republic_names | hidden)]

    # 其余联邦主体: 只画界线, 作背景参照.
    other_edges = [g.boundary for g in others.geometry if g is not None and not g.is_empty]
    if other_edges:
        ax.add_geometries(
            other_edges,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=COLOR_SUBJECT,
            linewidth=0.5,
            alpha=0.55,
            linestyle=(0, (5, 3)),
            zorder=3.0,
        )

    # 共和国: 半透明蓝紫填色 + 较粗描边.
    if not republics.empty:
        ax.add_geometries(
            [g for g in republics.geometry if g is not None and not g.is_empty],
            crs=ccrs.PlateCarree(),
            facecolor=COLOR_REPUBLIC_FILL,
            edgecolor="none",
            alpha=COLOR_REPUBLIC_ALPHA,
            linewidth=0,
            zorder=2.1,
        )
        republic_edges = [
            g.boundary for g in republics.geometry if g is not None and not g.is_empty
        ]
        ax.add_geometries(
            republic_edges,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=COLOR_REPUBLIC_EDGE,
            linewidth=1.9,
            zorder=6.3,
        )


def border_land_only(border, extent: tuple[float, float, float, float]):
    """从 GADM 俄罗斯外边界里剪掉海岸线与湖岸段, 只留国际陆地国界.

    为什么: GADM 各一级行政区的并集边界同时也是国家的外轮廓, 包含了北冰洋/
    里海/黑海海岸和拉多加湖、奥涅加湖等大湖岸线. 若整条线都按国界样式(深灰
    实线 + 白描边)画, 湖岸上会出现像"国界"的粗线, 拉多加湖西岸一个小岬角
    甚至会被看成文字/污点. 用 Natural Earth 10m 海岸线与湖泊边界做蒙版,
    把重合段剪掉, 只保留与邻国接壤的陆地国界(与 Ukraine 图剪海岸段同理).
    """
    coast = _ne_union("10m", "physical", "coastline")
    lakes = _ne_union("10m", "physical", "lakes")
    x0, x1, y0, y1 = extent
    view = box(x0 - 1.0, y0 - 1.0, x1 + 1.0, y1 + 1.0)
    overlays = []
    if coast is not None:
        overlays.append(coast.intersection(view))
    if lakes is not None:
        overlays.append(lakes.boundary.intersection(view))
    if not overlays:
        return border
    mask = overlap_mask(overlays, 0.08)
    trimmed = cut(border, mask, min_length_deg=0.03)
    return trimmed if trimmed is not None else border


def add_borders(
    ax: plt.Axes, border, extent: tuple[float, float, float, float]
) -> None:
    """俄罗斯国界(GADM 口径, 不含克里米亚)用深灰实线.

    为什么不用 Natural Earth: 与行政区同源, 国界与联邦主体界在坐标级重合,
    不会出现两套数据并行偏差; GADM RUS 的国界也不含克里米亚, 与仓库
    Ukraine 图的 1991 法理口径一致.
    """
    line = border_land_only(border, extent)
    ax.add_geometries(
        [line],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="white",
        linewidth=2.6,
        alpha=0.5,
        zorder=5.4,
    )
    ax.add_geometries(
        [line],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=COLOR_BORDER,
        linewidth=1.4,
        zorder=5.5,
    )


# ============================
# 城市点
# ============================
def add_city_markers(ax: plt.Axes, spec: MapSpec) -> None:
    """画画框内的城市点: 首都星形, 共和国首府方块, 一般城市圆点.

    只画地理符号: 国名/海名/丘陵名/河名/城名与面积注记都属于排版文字, 不在本脚本绘制.
    画框外跳过: 与改前一致, 窄画框(共和国图)不画框外的城市.
    """
    extent = spec.extent
    for lon, lat, _name, kind, _dx, _dy, _align in CITIES:
        if not in_extent(lon, lat, extent):
            continue
        if kind == "capital":
            ax.plot(
                lon,
                lat,
                marker="*",
                markersize=16,
                markerfacecolor="#ffd200",
                markeredgecolor="black",
                markeredgewidth=0.8,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )
        elif kind == "rep":
            ax.plot(
                lon,
                lat,
                marker="s",
                markersize=6.2,
                markerfacecolor="white",
                markeredgecolor="black",
                markeredgewidth=1.0,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )
        else:
            ax.plot(
                lon,
                lat,
                marker="o",
                markersize=4.2,
                markerfacecolor="white",
                markeredgecolor="black",
                markeredgewidth=0.9,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )


# ============================
# 经纬网
# ============================
def add_gridlines(ax: plt.Axes, extent: tuple[float, float, float, float]) -> None:
    """经纬网: 经度每 5°, 纬度每 2°, 只画网线, 不画刻度文字.

    线位置只取画框内 5°/2° 的整倍数, 窄画框不会把画框外的网线带出来;
    刻度文字由前端排版, 因此 draw_labels=False.
    """
    x0, x1, y0, y1 = extent

    def ticks(lo: float, hi: float, step: float) -> np.ndarray:
        return np.arange(np.ceil(lo / step) * step, hi + 1e-9, step)

    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=False,
        linewidth=0.5,
        color="gray",
        alpha=0.4,
        linestyle=":",
        zorder=4.5,
    )
    gl.xlocator = mticker.FixedLocator(ticks(x0, x1, 5))
    gl.ylocator = mticker.FixedLocator(ticks(y0, y1, 2))


# ============================
# geo.json 收集
# ============================
# 高程色标刻度: 改前色标上的整百/整千值, 前端 colorbar 直接复用.
RELIEF_TICKS = (-2000, -1000, 0, 500, 1000, 1500, 2000)

# 经纬网样式: 与 add_gridlines 画出的线同源(gray / 0.5pt / 点线 / 0.4 不透明度);
# 点线在 0.5pt 线宽下的 dash 为 (1, 1.65) x 0.5, 与旧成品抽出的 [0.5, 0.825] 一致.
GRATICULE_STYLE = {
    "stroke": "#808080",
    "width_pt": 0.5,
    "dash": [0.5, 0.825],
    "opacity": 0.4,
}


def collect_graticule(doc: GeoDoc, ax: plt.Axes, extent: tuple[float, float, float, float]) -> None:
    """把经纬刻度(值/文字/与地图框边线的交点)登记进 geo; 网线已由 add_gridlines 画好."""
    doc.add_graticule(
        ax,
        extent,
        lon_step=5.0,
        lat_step=2.0,
        lon_side="bottom",
        lat_side="left",
        style=GRATICULE_STYLE,
    )


def collect_labels(doc: GeoDoc, ax: plt.Axes, spec: MapSpec, basin_area_km2: float) -> None:
    """把旧成品上的地名整理成 geo.labels(role/位置/字号/锚点), 不画文字、不存样式.

    顺序按旧图的 zorder 升序登记(前端 scene 按 order 叠放): 国名/海名/地貌(9.0)、
    图内流域名(9.2)、共和国名(9.3)、河名(9.4)、城市(10.1). 画框外的候选跳过,
    与改前用 in_extent 过滤文字的行为一致; 颜色/斜体/描边/旋转由前端 role 表决定.
    """
    extent = spec.extent

    # 邻国名称.
    for lon, lat, text in COUNTRY_LABELS:
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(ax, lon, lat, text, role="country", font_size_pt=12.0)

    # 海域名称.
    for lon, lat, text in SEA_LABELS:
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(ax, lon, lat, text, role="sea", font_size_pt=11.0)

    # 地貌名.
    for lon, lat, text in HIGHLAND_LABELS:
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(ax, lon, lat, text, role="highland", font_size_pt=10.0)

    # 图内流域名: 只有共和国图在图上写「伏尔加河流域 / 面积」; 流域图的同一块
    # 文字在旧版是图外面板, 现在由 geo.suggestions.area_annotation 带给前端.
    if spec.area_label_in_map and in_extent(42.55, 51.95, extent):
        doc.add_label(
            ax, 42.55, 51.95,
            f"伏尔加河流域\n约 {basin_area_km2 / 1e4:.0f} 万 km²",
            role="area-basin", name="流域", font_size_pt=15.0,
        )

    # 共和国名: 字号按共和国轮廓大小分两档(小共和国 10.5, 大共和国 12.5);
    # id 前缀保留旧的 label-republic-*.
    for name in spec.republics:
        lon, lat, text = REPUBLIC_LABELS[name]
        if not in_extent(lon, lat, extent):
            continue
        size = 10.5 if name in SMALL_REPUBLICS else 12.5
        doc.add_label(
            ax, lon, lat, text,
            role="area-accent-1", id_kind="republic", name=name, font_size_pt=size,
        )

    # 河名: 同一条河标两段时 id 加 1 起算序号; 旋转由前端处理.
    river_counts: dict[str, int] = {}
    for _, _, text in RIVER_LABELS:
        river_counts[text] = river_counts.get(text, 0) + 1
    river_seen: dict[str, int] = {}
    for lon, lat, text in RIVER_LABELS:
        river_seen[text] = river_seen.get(text, 0) + 1
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(
            ax, lon, lat, text,
            role="river", name=text,
            index=river_seen[text] if river_counts[text] > 1 else None,
            font_size_pt=9.8,
        )

    # 城市: 文字跟着点位偏移; 字号按城市等级分三档.
    sizes = {"capital": 10.8, "rep": 9.3, "city": 8.8}
    for lon, lat, name, kind, dx, dy, align in CITIES:
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(
            ax, lon + dx, lat + dy, name,
            role="city", name=name, font_size_pt=sizes[kind], ha=align,
        )


def collect_legend(doc: GeoDoc, spec: MapSpec) -> None:
    """图例数据: 只列该图实际画了的线型/面, 流域图没有行政区两项(与改前图例一致)."""
    entries: list[dict] = [
        {
            "label": "伏尔加河流域",
            "shape": "rect",
            "stroke": COLOR_BASIN_EDGE,
            "width_pt": 2.0,
            "fill": COLOR_BASIN_FILL,
            "opacity": 0.45,
        }
    ]
    if spec.draw_admin:
        entries.extend(
            [
                {
                    "label": "周边联邦主体共和国",
                    "shape": "rect",
                    "stroke": COLOR_REPUBLIC_EDGE,
                    "width_pt": 1.8,
                    "fill": COLOR_REPUBLIC_FILL,
                    "opacity": 0.45,
                },
                {
                    "label": "其他联邦主体界",
                    "shape": "line",
                    "stroke": COLOR_SUBJECT,
                    "width_pt": 0.9,
                    "dash": [5.0, 3.0],
                    "opacity": 0.8,
                },
            ]
        )
    entries.extend(
        [
            {"label": "国界", "shape": "line", "stroke": COLOR_BORDER, "width_pt": 1.4},
            {"label": "干流(伏尔加河等)", "shape": "line", "stroke": COLOR_RIVER_TRUNK, "width_pt": 1.8},
            {"label": "支流", "shape": "line", "stroke": COLOR_RIVER, "width_pt": 0.8},
            {
                "label": "湖泊 / 水库水面",
                "shape": "rect",
                "stroke": COLOR_WATER_EDGE,
                "width_pt": 0.6,
                "fill": COLOR_WATER,
            },
            {
                "label": "首都",
                "shape": "point",
                "stroke": "#000000",
                "width_pt": 1.5,
                "fill": "#ffd200",
                "marker": "star",
            },
            {
                "label": "共和国首府",
                "shape": "point",
                "stroke": "#000000",
                "width_pt": 1.5,
                "fill": "#ffffff",
                "marker": "square",
            },
            {
                "label": "城市",
                "shape": "point",
                "stroke": "#000000",
                "width_pt": 1.5,
                "fill": "#ffffff",
                "marker": "circle",
            },
        ]
    )
    doc.set_legend("图例", entries)


def collect_suggestions(doc: GeoDoc, spec: MapSpec, basin_area_km2: float) -> None:
    """默认文案: 标题/副标题/右栏注/来源/图外面积注记, 只给前端预填, 不参与合成."""
    area_wan = basin_area_km2 / 1e4
    notes = [
        "注 1：流域为 HydroBASINS level 5 的伏尔加河主流域合并，",
        f"面积约 {area_wan:.0f} 万 km²（HydroSHEDS 口径，不含里海）。",
    ]
    if spec.draw_admin:
        notes += [
            "注 2：加粗填色者为流域周边的六个联邦主体共和国，科米与",
            "卡尔梅克不画；其余联邦主体只画灰色虚线界线。行政区为",
            "GADM 4.1，其俄罗斯国界口径不含克里米亚。",
        ]
    else:
        notes += [
            "注 2：本图不画联邦主体行政区界，只保留俄罗斯国界（GADM",
            "4.1 口径，不含克里米亚）。",
        ]
    notes += [
        "注 3：河网与湖库为 Natural Earth 10m；河流按 scalerank 分三级，",
        "湖泊/水库按面填色；里海不在湖泊层，其水深仍由地形配色表达。",
        "注 4：地形 ETOPO 2022（15″）；投影 Lambert Conformal Conic，",
        "中央经线 46°E，标准纬线 47°N / 57°N。",
    ]
    doc.set_suggestions(
        {
            "title": spec.title,
            "subtitle": spec.subtitle,
            "notes": notes,
            "source": (
                "地形: NOAA NCEI ETOPO 2022（15″） | 流域: HydroSHEDS HydroBASINS level 5 | "
                "行政区: GADM 4.1 | 河网·湖库: Natural Earth 10m | "
                "投影: Lambert Conformal Conic"
            ),
            "area_annotation": []
            if spec.area_label_in_map
            else ["伏尔加河流域", f"约 {area_wan:.0f} 万 km²"],
            "legend_title": "图例",
            "colorbar_title": "高程 / 水深",
        }
    )


# ============================
# 出图
# ============================
def build_map(
    spec: MapSpec,
    layout: Layout,
    subjects: gpd.GeoDataFrame,
    basin,
    border,
    lon: np.ndarray,
    lat: np.ndarray,
    z: np.ndarray,
    dpi: int,
) -> tuple[plt.Figure, plt.Axes]:
    """按规格画一张纯几何图, 返回未保存的 Figure 与地图坐标区(geo 收集要用 ax)."""
    fig = plt.figure(figsize=layout.figsize, facecolor="white")
    ax = fig.add_axes(layout.map_rect, projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(spec.extent, crs=ccrs.PlateCarree())

    # ETOPO 已覆盖全部画框; 仍先铺海陆底色, 防止边缘缺测时露出白底.
    ax.set_facecolor(BASE_OCEAN_COLOR)

    add_basin(ax, basin)
    add_admin(ax, subjects, spec)
    add_relief(
        ax,
        lon,
        lat,
        z,
        regrid_shape=max(1200, int(layout.map_width_in * dpi)),
    )
    add_rivers(ax, spec.extent)
    add_water(ax, spec.extent)
    add_borders(ax, border, spec.extent)

    add_city_markers(ax, spec)
    add_gridlines(ax, spec.extent)
    return fig, ax


# ============================
# 主流程
# ============================
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stride",
        type=int,
        default=None,
        help="使用 data/ 下对应采样步长的 ETOPO 文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="内嵌晕渲栅格的像素密度(dpi); 矢量部分与 dpi 无关, 默认 300",
    )
    parser.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    args = parser.parse_args()

    etopo_path = find_etopo(
        DATA_DIR,
        "volga",
        args.stride,
        env_path=os.environ.get("VOLGA_ETOPO_PATH"),
    )
    _require(etopo_path)
    subjects, basin, border = load_vectors(EXTENT_BASIN)

    lon, lat, z = load_elevation(etopo_path)
    z = prepare_elevation(lon, lat, z)
    area_km2 = basin_area_km2(basin)

    for spec in SPECS:
        layout = make_layout(spec)
        fig, ax = build_map(
            spec,
            layout,
            subjects,
            basin,
            border,
            lon,
            lat,
            z,
            args.dpi,
        )
        # 注意: 不用 tight_layout / bbox_inches="tight";
        # cartopy 0.25 在非矩形投影上绘制经纬网时会触发 gridliner 用未闭合
        # 顶点构造多边形的 GEOSException, 且 tight bbox 会裁掉地图边缘(项目已踩过).
        frame = figure_frame(fig, ax)
        doc = GeoDoc(frame)
        collect_labels(doc, ax, spec, area_km2)
        collect_graticule(doc, ax, spec.extent)
        doc.set_relief(
            relief_from_cmap(
                ELEV_CMAP,
                title="高程 / 水深",
                unit="m",
                vmin=ELEV_VMIN,
                vmax=ELEV_VMAX,
                ticks=RELIEF_TICKS,
            )
        )
        collect_legend(doc, spec)
        collect_suggestions(doc, spec, area_km2)
        # save_map 写裁到地图框的纯底图与同名 geo.json(miko 契约里的 base.svg + geo).
        svg_path, geo_path = save_map(fig, spec.out_svg, doc, dpi=args.dpi)
        print(f"底图与 geo 已保存: {svg_path} + {geo_path}")
        if not args.show:
            plt.close(fig)

    if args.show:
        plt.show()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
