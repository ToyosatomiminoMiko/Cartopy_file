#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Volga basin and neighbouring federal-subject republics, topographic map.

是什么: 以 ETOPO 2022 地形晕渲为底图, 叠加 HydroSHEDS 伏尔加河流域、
GADM 4.1 俄罗斯一级行政区、Natural Earth 10m 河网与梯级水库水面, 标注
流域周边八个联邦主体共和国, 产物为单个自包含 SVG.
完整说明: 见 ``docs/maps/volga.md``(流域口径/河网分级/配色与标注避让).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import geopandas as gpd  # 读取预加工好的 GeoJSON
import matplotlib.cm as cm  # 独立色标用的 ScalarMappable
import matplotlib.colors as mcolors  # 自定义高程/水深色带
import matplotlib.patheffects as pe  # 文字白描边
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网刻度
import numpy as np  # 数组运算
from matplotlib.lines import Line2D  # 图例线段
from matplotlib.patches import Patch  # 图例色块
from shapely.geometry import box  # 湖库按画框筛选
from shapely.ops import unary_union  # 流域/行政区几何合并

# cartopy 底图缓存统一到仓库 data/cartopy, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy

configure_cartopy()

# 重合线剪枝: 国界与海岸线/湖岸重合的段落只留一种线, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# 共享的 ETOPO/晕渲/底图工具(实现见 src/cartopy_file/relief.py).
from cartopy_file.relief import find_etopo, load_elevation, load_ne_layer, make_relief

# 全局字体由 cartopy_file.fonts 统一设置, 见 docs/reference/fonts.md.
from cartopy_file.fonts import apply_matplotlib_fonts
from cartopy_file.output import apply_svg_output, save_svg

apply_matplotlib_fonts()
# 产物统一为 SVG, 见 docs/reference/output.md.
apply_svg_output()


# ============================
# 配置
# ============================
# 画框: [min_lon, max_lon, min_lat, max_lat].
# 西界留出瓦尔代丘陵(伏尔加河源头)以西约 1.7°; 东界到乌拉尔山西坡;
# 南界 44.4°N 覆盖卡尔梅克共和国全境(其最南约 44.8°N)与里海西北岸;
# 北界 62.3°N 留出科米共和国南缘与上卡马河源地的余量.
EXTENT = [30.3, 62.3, 44.4, 62.3]

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
    色标横轴仍是线性, 只是 0 m 两侧颜色不连续.
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

# 图面配色: 主题层各一个固定颜色, 图例/标注/线条共用同一套常量.
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
COLOR_HIGHLAND = "#7a6450"     # 丘陵/山地标注: 棕灰斜体
COLOR_COUNTRY = "#3a3a3a"      # 邻国名称
COLOR_SEA = "#1f4e79"          # 海域名称
COLOR_NOTE = "#333333"

# 周边八个联邦主体共和国(GADM NAME_1). 只高亮这八个: 伏尔加河流域直接
# 覆盖/紧邻的民族共和国; 高加索诸共和国离流域主体几百公里, 只画灰色界线.
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

# 共和国名称: (经度, 纬度, 文字). 放在各共和国境内的空旷处, 避开首府城点与
# 主要河湖; 小共和国用两行或略小字号, 防止文字宽度超过共和国轮廓.
REPUBLIC_LABELS = [
    (50.30, 54.85, "鞑靼斯坦\n共和国"),
    (56.60, 53.35, "巴什科尔托斯坦\n共和国"),
    (47.05, 55.28, "楚瓦什\n共和国"),
    (48.90, 57.22, "马里埃尔\n共和国"),
    (44.50, 54.85, "莫尔多瓦\n共和国"),
    (52.60, 57.55, "乌德穆尔特\n共和国"),
    (45.25, 46.78, "卡尔梅克\n共和国"),
    (54.50, 61.00, "科米\n共和国"),
]

# 城市: (经度, 纬度, 名称, 类型, 文字偏移经度, 文字偏移纬度, 水平对齐).
# 类型: capital=首都(星形), rep=共和国首府(方块), city=一般城市(圆点).
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

# 河名: (经度, 纬度, 文字, 旋转参考点1经度, 纬度, 参考点2经度, 纬度).
# 文字放在河道旁的陆地上, 旋转方向与河道在投影平面内的走向一致
# (不能拿经纬度差直接算 atan2, 见 projected_angle 的理由).
RIVER_LABELS = [
    (43.05, 56.10, "伏尔加河", 42.40, 56.20, 44.00, 56.10),
    (45.35, 49.90, "伏尔加河", 45.80, 50.60, 44.80, 49.10),
    (53.40, 55.35, "卡马河", 54.20, 55.30, 52.40, 55.40),
    (41.55, 54.85, "奥卡河", 40.80, 54.50, 42.40, 55.10),
    (56.30, 54.15, "别拉亚河", 56.40, 53.60, 56.10, 54.80),
    (50.20, 57.45, "维亚特卡河", 50.60, 57.70, 49.70, 57.10),
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

# 地貌名称: (经度, 纬度, 文字, 旋转角度). 旋转角度 0 表示水平.
HIGHLAND_LABELS = [
    (33.10, 57.55, "瓦尔代丘陵", 0),
    (46.90, 52.20, "伏尔加高地", 0),
    (47.40, 48.60, "里海低地", 0),
    (59.30, 56.80, "乌拉尔山", 78),
]

# 河网分级: Natural Earth 10m 河流的 scalerank(数值越小越主要)分三档.
# 画框约 1:770 万比例尺, 正好是 Natural Earth 10m 的设计尺度, 直接用缓存
# 数据即可; 不引入 HydroRIVERS 那样几十 MB 的逐段河网(本图不需要支流级细节).
RIVER_TRUNK_MAX_SCALERANK = 3   # 伏尔加干流
RIVER_MEDIUM_MAX_SCALERANK = 7  # 卡马/奥卡/维亚特卡/别拉亚等
RIVER_EXCLUDE_FEATURECLA = {"Canal"}

# 图标题与产物路径.
TITLE = (
    "伏尔加河流域与周边联邦主体共和国地形图\n"
    "ETOPO 2022 | 流域: HydroSHEDS | 行政区: GADM 4.1 | "
    "兰勃特等角圆锥投影"
)
OUT_SVG = ROOT / "volga_basin_republics_topography_etopo2022_lambert_conformal.svg"

# 文字描边: 白底 halo, 保证文字压在地形/色块/河网上仍可读.
HALO = [pe.withStroke(linewidth=3.0, foreground="white")]
HALO_WIDE = [pe.withStroke(linewidth=3.6, foreground="white")]

# 数据文件(由 Volga/download_data.py 生成).
SUBJECTS_GEOJSON = DATA_DIR / "volga_subjects.geojson"
BASIN_GEOJSON = DATA_DIR / "volga_basin.geojson"
BORDER_GEOJSON = DATA_DIR / "russia_border.geojson"


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


def load_vectors() -> tuple[gpd.GeoDataFrame, object, object]:
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
    ocean = load_ne_layer("10m", "physical", "ocean")
    if ocean is not None:
        view = box(EXTENT[0] - 1.0, EXTENT[2] - 1.0, EXTENT[1] + 1.0, EXTENT[3] + 1.0)
        land = land.difference(ocean.union_all().intersection(view))
    basin = unary_union(polygon_parts(basin.intersection(land)))
    border = unary_union(gpd.read_file(_require(BORDER_GEOJSON)).geometry)
    return subjects, basin, border


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


def projected_angle(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """求两点连线的屏幕方向角(度), 用于把文字旋转成与河道平行.

    为什么要在投影平面里算: matplotlib 的 rotation 是屏幕角, 而兰勃特等角
    圆锥投影下经线不是竖直的, 直接拿经纬度差算 atan2 会得到与屏幕不一致的
    角度, 文字会明显偏离河道走向(与 Ukraine 图同一处理).
    """
    p1 = PROJECTION.transform_point(lon1, lat1, ccrs.PlateCarree())
    p2 = PROJECTION.transform_point(lon2, lat2, ccrs.PlateCarree())
    return float(np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0])))


# ============================
# 图层
# ============================
def negative_land_as_land(z: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
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
    ocean = load_ne_layer("10m", "physical", "ocean")
    lakes = load_ne_layer("10m", "physical", "lakes")
    geoms = []
    if ocean is not None:
        geoms.append(ocean.union_all())
    if lakes is not None:
        geoms.append(lakes.union_all())
    if not geoms:
        print("警告: 缺少 Natural Earth ocean/lakes, 负高程陆地仍按水面配色.")
        return z
    water_geom = unary_union(geoms).intersection(
        box(EXTENT[0] - 1.0, EXTENT[2] - 1.0, EXTENT[1] + 1.0, EXTENT[3] + 1.0)
    )
    fixed = z.copy()
    rows, cols = np.nonzero(z < 0)
    in_water = contains_xy(water_geom, lon[cols], lat[rows])
    fixed[rows[~in_water], cols[~in_water]] = 0.5
    return fixed


def add_relief(ax: plt.Axes, etopo_path: Path):
    """读取高程并叠加晕渲地形, 返回色标用的 (norm, cmap)."""
    lon, lat, z = load_elevation(etopo_path)
    z = negative_land_as_land(z, lon, lat)
    relief, norm, cmap = make_relief(
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
    # regrid_shape 取画框宽度的像素量级(300 dpi 下约 3800 px), 否则 30″
    # ETOPO 在 1:430 万比例尺上会被 cartopy 重采样糊掉(同 Ukraine 图).
    ax.imshow(
        relief,
        origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        regrid_shape=3800,
        interpolation="nearest",
        zorder=1,
    )
    return norm, cmap


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


def add_water(ax: plt.Axes) -> None:
    """填画框内全部 Natural Earth 10m 湖泊与梯级水库水面.

    为什么需要填: 伏尔加—卡马梯级水库面积小、水深浅, ETOPO 30″ 下只是几
    像素宽的浅色带, 单独填色才能读出"上游窄河、下游宽水面"的沿程变化
    (与 Ukraine 图处理第聂伯河梯级水库的理由一致); 咸海的水面高出海平面
    (+29 m), 按高程配色会画成陆地, 也只能靠湖泊多边形补上.
    不填里海: 里海不在 Natural Earth lakes 图层(在 ocean 图层), 它的水深
    仍由 ETOPO 配色表达, 避免用等深浅蓝盖掉水下地形.
    """
    lakes = load_ne_layer("10m", "physical", "lakes")
    if lakes is None:
        print("警告: 缺少 Natural Earth 湖泊数据, 跳过大水面填色.")
        return
    x0, x1, y0, y1 = EXTENT
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


def add_rivers(ax: plt.Axes) -> None:
    """按 scalerank 分三档画 Natural Earth 10m 河网.

    为什么分级: 河网统一同宽会把伏尔加干流淹没在支流里; 按 scalerank 分三档
    后, 干流(粗, 带白描边)-主要支流(中)-次要河流(细)的主次关系与河谷规模
    一致. 只给五条主要河流写河名, 避免整张图被文字压满.
    排除 Canal: 运河是人工线, 不属于本图要表达的天然水系.
    """
    rivers = load_ne_layer("10m", "physical", "rivers_lake_centerlines")
    if rivers is None:
        print("警告: 缺少 Natural Earth 河流数据, 跳过河流图层.")
        return
    x0, x1, y0, y1 = EXTENT
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


def add_admin(ax: plt.Axes, subjects: gpd.GeoDataFrame) -> None:
    """其余联邦主体界(灰色虚线)与八个共和国的填色/描边.

    为什么共和国填色画在行政界线之下: 填色是面, 界线是线, 先铺面再画线,
    界线不会被半透明填色盖住. 共和国的外边界另用较粗的蓝紫线强调; 它与
    俄罗斯国界重合的段落会被后面更粗的国界线压住(国界 zorder 更高).
    """
    republic_names = set(REPUBLICS)
    republics = subjects[subjects["name"].isin(republic_names)]
    others = subjects[~subjects["name"].isin(republic_names)]

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

    # 八个共和国: 半透明蓝紫填色 + 较粗描边.
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


def border_land_only(border):
    """从 GADM 俄罗斯外边界里剪掉海岸线与湖岸段, 只留国际陆地国界.

    为什么: GADM 各一级行政区的并集边界同时也是国家的外轮廓, 包含了北冰洋/
    里海/黑海海岸和拉多加湖、奥涅加湖等大湖岸线. 若整条线都按国界样式(深灰
    实线 + 白描边)画, 湖岸上会出现像"国界"的粗线, 拉多加湖西岸一个小岬角
    甚至会被看成文字/污点. 用 Natural Earth 10m 海岸线与湖泊边界做蒙版,
    把重合段剪掉, 只保留与邻国接壤的陆地国界(与 Ukraine 图剪海岸段同理).
    """
    coast = load_ne_layer("10m", "physical", "coastline")
    lakes = load_ne_layer("10m", "physical", "lakes")
    x0, x1, y0, y1 = EXTENT
    view = box(x0 - 1.0, y0 - 1.0, x1 + 1.0, y1 + 1.0)
    overlays = []
    if coast is not None:
        overlays.append(coast.union_all().intersection(view))
    if lakes is not None:
        overlays.append(lakes.union_all().boundary.intersection(view))
    if not overlays:
        return border
    mask = overlap_mask(overlays, 0.08)
    trimmed = cut(border, mask, min_length_deg=0.03)
    return trimmed if trimmed is not None else border


def add_borders(ax: plt.Axes, border) -> None:
    """俄罗斯国界(GADM 口径, 不含克里米亚)用深灰实线.

    为什么不用 Natural Earth: 与行政区同源, 国界与联邦主体界在坐标级重合,
    不会出现两套数据并行偏差; GADM RUS 的国界也不含克里米亚, 与仓库
    Ukraine 图的 1991 法理口径一致.
    """
    line = border_land_only(border)
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
# 标注
# ============================
def add_text_labels(ax: plt.Axes, basin_area_km2: float) -> None:
    """流域名/共和国名/河名/城市/邻国/海域/地貌标注."""
    # 流域名: 蓝色斜体, 放在流域内偏北的开阔平原上.
    area_text = f"伏尔加河流域\n约 {basin_area_km2 / 1e4:.0f} 万 km²"
    ax.text(
        42.55,
        51.95,
        area_text,
        transform=ccrs.PlateCarree(),
        fontsize=15,
        color=COLOR_BASIN_EDGE,
        style="italic",
        ha="center",
        va="center",
        linespacing=1.35,
        path_effects=HALO_WIDE,
        zorder=9.2,
    )

    # 共和国名: 蓝紫色, 字号按共和国轮廓大小分两档(小共和国 10.5, 大共和国 12.5).
    small_republics = {"Chuvash", "Mariy-El", "Mordovia", "Kalmyk"}
    small_labels = {
        (47.05, 55.42): True,
        (48.80, 56.98): True,
        (44.45, 54.75): True,
        (45.10, 46.55): True,
    }
    for lon, lat, text in REPUBLIC_LABELS:
        size = 10.5 if small_labels.get((lon, lat)) else 12.5
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=size,
            color=COLOR_REPUBLIC_EDGE,
            ha="center",
            va="center",
            linespacing=1.15,
            path_effects=HALO,
            zorder=9.3,
        )

    # 河名: 与干流同色, 沿河道方向旋转.
    for lon, lat, text, lon1, lat1, lon2, lat2 in RIVER_LABELS:
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=9.8,
            color=COLOR_RIVER_TRUNK,
            style="italic",
            rotation=projected_angle(lon1, lat1, lon2, lat2),
            rotation_mode="anchor",
            ha="center",
            va="center",
            path_effects=HALO,
            zorder=9.4,
        )

    # 邻国与海域.
    for lon, lat, text in COUNTRY_LABELS:
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=12.0,
            color=COLOR_COUNTRY,
            ha="center",
            va="center",
            path_effects=HALO,
            zorder=9.0,
        )
    for lon, lat, text in SEA_LABELS:
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=11.0,
            color=COLOR_SEA,
            style="italic",
            ha="center",
            va="center",
            path_effects=HALO,
            zorder=9.0,
        )

    # 地貌名: 棕灰斜体; 乌拉尔山按山脊走向旋转.
    for lon, lat, text, rotation in HIGHLAND_LABELS:
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=10.0,
            color=COLOR_HIGHLAND,
            style="italic",
            rotation=rotation,
            rotation_mode="anchor",
            ha="center",
            va="center",
            path_effects=HALO,
            zorder=9.0,
        )

    # 城市: 首都星形, 共和国首府方块, 一般城市圆点.
    for lon, lat, name, kind, dx, dy, align in CITIES:
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
            fontsize = 10.8
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
            fontsize = 9.3
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
            fontsize = 8.8
        ax.text(
            lon + dx,
            lat + dy,
            name,
            transform=ccrs.PlateCarree(),
            fontsize=fontsize,
            color="black",
            ha=align,
            va="center",
            path_effects=HALO,
            zorder=10.1,
        )


# ============================
# 版式
# ============================
def add_gridlines(ax: plt.Axes) -> None:
    """经纬网: 经度每 5°, 纬度每 2°, 只标底边与左边.

    rotate_labels=False: 圆锥投影下经线是斜的, 默认会让底部经度标签跟着
    旋转, 数字不易读; 统一保持水平(与 Ukraine 图一致).
    """
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        x_inline=False,
        y_inline=False,
        linewidth=0.5,
        color="gray",
        alpha=0.4,
        linestyle=":",
        zorder=4.5,
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.rotate_labels = False
    gl.xlocator = mticker.FixedLocator(np.arange(30, 65, 5))
    gl.ylocator = mticker.FixedLocator(np.arange(45, 63, 2))
    gl.xlabel_style = {"size": 9.5, "color": "#444444"}
    gl.ylabel_style = {"size": 9.5, "color": "#444444"}


def add_colorbar(fig: plt.Figure, norm, cmap) -> None:
    """高程色标: 竖放在右侧面板下半部, 不抢地图宽度."""
    cax = fig.add_axes([0.800, 0.105, 0.014, 0.200])
    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])
    cbar = fig.colorbar(mappable, cax=cax)
    cbar.set_ticks([-2000, -1000, 0, 500, 1000, 1500, 2000])
    cbar.ax.tick_params(labelsize=8.5)
    cbar.ax.set_title("高程 / 水深 (m)", fontsize=8.5, pad=6)


def add_legend(fig: plt.Figure) -> None:
    """右侧面板: 图例 + 流域/数据口径注释.

    图例只列图上线型; 注释解释流域口径、行政区口径与数据来源, 两者分开
    写是为了让图例保持简洁, 又不会把"周边共和国"误读成"流域内全部行政区".
    """
    lax = fig.add_axes([0.757, 0.520, 0.235, 0.420])
    lax.set_axis_off()

    handles = [
        Patch(
            facecolor=COLOR_BASIN_FILL,
            edgecolor=COLOR_BASIN_EDGE,
            alpha=0.45,
            linewidth=2.0,
            label="伏尔加河流域",
        ),
        Patch(
            facecolor=COLOR_REPUBLIC_FILL,
            edgecolor=COLOR_REPUBLIC_EDGE,
            alpha=0.45,
            linewidth=1.8,
            label="周边联邦主体共和国",
        ),
        Line2D(
            [0], [0],
            color=COLOR_SUBJECT,
            linewidth=0.9,
            linestyle=(0, (5, 3)),
            alpha=0.8,
            label="其他联邦主体界",
        ),
        Line2D([0], [0], color=COLOR_BORDER, linewidth=1.4, label="国界"),
        Line2D([0], [0], color=COLOR_RIVER_TRUNK, linewidth=1.8, label="干流(伏尔加河等)"),
        Line2D([0], [0], color=COLOR_RIVER, linewidth=0.8, label="支流"),
        Patch(
            facecolor=COLOR_WATER,
            edgecolor=COLOR_WATER_EDGE,
            linewidth=0.6,
            label="湖泊 / 水库水面",
        ),
        Line2D(
            [0], [0],
            marker="*",
            color="none",
            markerfacecolor="#ffd200",
            markeredgecolor="black",
            markersize=13,
            label="首都",
        ),
        Line2D(
            [0], [0],
            marker="s",
            color="none",
            markerfacecolor="white",
            markeredgecolor="black",
            markersize=7,
            label="共和国首府",
        ),
        Line2D(
            [0], [0],
            marker="o",
            color="none",
            markerfacecolor="white",
            markeredgecolor="black",
            markersize=5.5,
            label="城市",
        ),
    ]
    legend = lax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.0, 1.0),
        frameon=True,
        framealpha=0.94,
        edgecolor="#bbbbbb",
        fontsize=9.6,
        title="图例",
        title_fontsize=12.5,
        borderpad=0.8,
        labelspacing=0.72,
        handlelength=2.4,
        handletextpad=0.9,
    )
    legend.get_title().set_color("#222222")
    legend.get_frame().set_linewidth(0.8)


def add_notes(fig: plt.Figure, basin_area_km2: float) -> None:
    """右侧面板: 流域/行政区/河网口径与数据来源注释."""
    area_wan = basin_area_km2 / 1e4
    notes = (
        f"注 1：流域为 HydroBASINS level 5 的伏尔加河主流域合并，\n"
        f"面积约 {area_wan:.0f} 万 km²（HydroSHEDS 口径，不含里海）。\n"
        "注 2：加粗填色者为流域周边的八个联邦主体共和国；其余联邦\n"
        "主体只画灰色虚线界线。行政区为 GADM 4.1，其俄罗斯国界\n"
        "口径不含克里米亚。\n"
        "注 3：河网与湖库为 Natural Earth 10m；河流按 scalerank 分三级，\n"
        "湖泊/水库按面填色；里海不在湖泊层，其水深仍由地形配色表达。\n"
        "注 4：地形 ETOPO 2022（15″）；投影 Lambert Conformal Conic，\n"
        "中央经线 46°E，标准纬线 47°N / 57°N。"
    )
    fig.text(
        0.757,
        0.505,
        notes,
        ha="left",
        va="top",
        fontsize=8.0,
        color=COLOR_NOTE,
        linespacing=1.5,
    )


def add_source_note(fig: plt.Figure) -> None:
    """数据来源与许可放画面底部, 不遮挡地图主体."""
    fig.text(
        0.5,
        0.009,
        "地形: NOAA NCEI ETOPO 2022（15″） | 流域: HydroSHEDS HydroBASINS level 5 | "
        "行政区: GADM 4.1 | 河网·湖库: Natural Earth 10m | "
        "投影: Lambert Conformal Conic",
        ha="center",
        va="bottom",
        fontsize=8.5,
        color="#666666",
    )


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
    subjects, basin, border = load_vectors()
    # 面积按绘图实际使用的流域面重算(已裁掉海洋岸线误差), 不用 GeoJSON 里的
    # 原始值, 保证图注面积与画面几何一致.
    basin_area_km2 = float(
        gpd.GeoSeries([basin], crs="EPSG:4326").to_crs("EPSG:6933").area.iloc[0]
        / 1.0e6
    )

    # 画布比例按投影后画框宽高比(约 1.30)定制, 避免地图上下留大片空白;
    # 地图区占左侧 0.715, 右侧 0.235 留给图例/色标/注释(与 Ukraine 图同一布局).
    fig = plt.figure(figsize=(18.0, 12.2), facecolor="white")
    ax = fig.add_axes([0.030, 0.072, 0.715, 0.811], projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    # ETOPO 已覆盖全部画框; 仍先铺海陆底色, 防止边缘缺测时露出白底.
    ax.set_facecolor(BASE_OCEAN_COLOR)

    add_basin(ax, basin)
    add_admin(ax, subjects)
    norm, cmap = add_relief(ax, etopo_path)
    add_rivers(ax)
    add_water(ax)
    add_borders(ax, border)

    add_text_labels(ax, basin_area_km2)
    add_gridlines(ax)

    # 标题用 figure 级: GeoAxes 在有经纬网标签时会重算标题位置, 多行标题
    # 容易被移出画布(与 Ukraine/northern_shan 的原因相同).
    fig.suptitle(TITLE, fontsize=16.5, y=0.986, va="top")
    add_legend(fig)
    add_colorbar(fig, norm, cmap)
    add_notes(fig, basin_area_km2)
    add_source_note(fig)

    # 注意: 不用 tight_layout / bbox_inches="tight";
    # cartopy 0.25 在非矩形投影上绘制经纬网标签时会触发 gridliner 用未闭合
    # 顶点构造多边形的 GEOSException, 且 tight bbox 会裁掉标签(项目已踩过).
    save_svg(fig, OUT_SVG, dpi=args.dpi)
    print(f"地图已保存: {OUT_SVG}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
