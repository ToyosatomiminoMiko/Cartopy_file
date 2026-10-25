#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# ukraine.py
# 乌克兰全图: 以 ETOPO 2022 地形晕渲为底图, 叠加
#   1) 1991 年国际承认边界(含克里米亚);
#   2) 2014 年实际控制线(克里米亚陆上控制线 + 顿巴斯接触线)及其控制区;
#   3) 2014 年宣布的"人民共和国"(顿涅茨克/卢甘斯克实际控制区, 哈尔科夫宣称范围);
#   4) 2022 年俄方单方面宣称的赫尔松/扎波罗热/顿涅茨克/卢甘斯克四州全境边界.
#   5) 第聂伯河干流与梯级水库: 用 OSM 河道中心线 + 水库实际水面填色,
#      表达"河宽沿程变化"(上游窄河道 -> 五级水库的宽阔水面);
#   6) 邻国地貌/水系参照: 喀尔巴阡山、高加索山与顿河的名称标注;
#   7) 1991 年国界改用红色半透明线, 让地形与下层边界线透出来;
#   8) 2022 宣称边界与哈尔科夫界线同 1991 国界重合的段落只画 1991 红线,
#      紫/橙虚线只保留各自独有的段落.
# 运行前先执行: python Ukraine/download_data.py
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Ukraine overview map: 1991 / 2014 / 2022 borders over ETOPO relief.

设计要点:
    1. 投影: 兰勃特等角圆锥投影(Lambert Conformal Conic), 中央经线 31°E,
       标准纬线 45°N/52°N. 乌克兰东西约 18°、南北约 8°, 中纬度国家用圆锥
       投影比等经纬度投影更不容易把西部/东部横向拉变形; 标准纬线夹住国土
       南北缘, 全国比例误差最小.
    2. 底图: ETOPO 2022 高程, 海陆分开的两段色带 + 只压暗的晕渲. 为什么不能
       直接用现成的 "terrain" 色带: 一是 ±2500 m 线性归一化后, 0~300 m 的平原
       只占色带 6%, 全国低地几乎同一个颜色, 地形看不出来; 二是亚速海最深仅
       约 14 m, 在 "terrain" 上归一化值 0.497, 与 0 m 陆地的 0.500 几乎同色,
       海陆分不出来. 所以色带在 0 m 处从浅蓝(水)直接跳到浅绿(陆), 再把陆地
       颜色的锚点集中到 0~500 m 的低海拔段; 晕渲改成只压暗的乘法因子
       (见 relief.make_relief 的 shade_strength).
    3. 文字避让: 第聂伯河干流(尤其梯级水库水面)不能被标注压住, 否则水面宽度
       变化就被文字遮掉了. 河名放在克列缅丘格水库东北岸的陆地上, 顺着河道
       方向旋转; 附近的城市/州标注都留出水面, 具体偏移见 CITIES 与 add_labels.
    4. 边界口径(按用户确认):
       - 1991 年边界 = 苏联解体时乌克兰的国际承认边界, 含克里米亚与
         塞瓦斯托波尔(法理口径, 来自 GADM 4.1);
       - 2014 年 = 克里米亚并入俄罗斯后的陆上实际控制线(彼列科普地峡
         一带的内部行政边界) + 顿巴斯接触线. 接触线用 OCHA 2021 年
         GCA/NGCA 界线近似(明斯克协议线, 2015 年后基本稳定), 属于近似值;
       - 2022 年 = 俄方 2022-09-30 单方面宣称的赫尔松州、扎波罗热州、
         顿涅茨克人民共和国、卢甘斯克人民共和国"全境"边界; 只画法理州界,
         不把四州整体填色, 避免被误读为俄方实际控制.
    5. 分离"实际控制"与"单方面宣称": 2014 年控制区用浅蓝色填充 + 蓝色
       实线, 2022 年宣称边界用紫色点划线; 两者不混用同一种线型.
    6. 重合的边界只画一次: 哈尔科夫州界(橙虚线)的南段同时是 2022 年宣称
       四州外边界的北段(紫点划线). 两条线重合时, 先画的橙虚线连同白描边会
       从紫线的点划间隙里露出来, 形成"双线"错觉; 所以重合段只画紫线, 橙线
       只保留独有段落(几何处理见 draw_borders). 2022 宣称边界、哈尔科夫
       界线与 1991 国界重合时同理, 但 1991 红线是半透明(alpha=0.62)的:
       若把紫/橙线画在下面再用红线叠压, 底下颜色会透出来混成"红+紫"的
       第三种颜色, 所以重合段直接从紫/橙线里剪掉, 只画 1991 红线; 剪口
       宽度小于红线半宽, 图上看不到断口.
    7. 第聂伯河的宽度必须沿程变化: 干流在乌克兰境内是一串梯级水库, 上游
       河道只有 200~500 m 宽, 水库水面却有几公里到十几公里宽. 如果像普通
       河流那样画一条等宽细线, 在图上会明显失真(实际水面宽度差一个数量级).
       因此干流用 OSM 中心线(顶点数约为 Natural Earth 的 4 倍)画细线, 五个
       梯级水库再用 OSM 的实际水面多边形填充 —— 图上"窄河道 / 宽水库"的
       宽窄变化是真实水面, 不是线宽画出来的. 卡霍夫卡水库 2023 年被放空,
       OSM 已无水面, 这一座用 Natural Earth 溃坝前轮廓补上(见下载脚本).
    8. 邻国地貌/水系参照标注: 喀尔巴阡山、高加索山用棕色斜体、沿山脊走向
       旋转; 顿河与第聂伯河共用同一套河名旋转规则(在投影平面里求角度,
       不能拿经纬度差直接算 atan2). 顿河标在下游罗斯托夫一带的北岸陆地上:
       上游河段在图幅右上角的俄罗斯腹地, 离乌克兰主体太远, 参照意义弱;
       下游河段紧邻顿巴斯与亚速海, 读图时更容易定位.

数据(由 Ukraine/download_data.py 准备, 脚本本身不联网):
    data/ETOPO_2022_v1_15s_ukraine_stride2.nc   NOAA ETOPO 2022 地形
    data/ne_10m_admin_0_countries/              Natural Earth 10m 国界(邻国)
    data/ukraine_oblasts.geojson                GADM 4.1 乌克兰一级行政区
    data/ukraine_1991.geojson                   1991 年国际承认边界
    data/crimea_2014_line.geojson               2014 年克里米亚陆上控制线
    data/occupied_2014.geojson                  2014 年顿巴斯控制区
    data/contact_line_2014.geojson              2014 年顿巴斯接触线(近似)
    data/claimed_2022.geojson                   2022 年俄方宣称四州全境
    data/dnieper_river_osm.geojson              第聂伯河干流中心线(OSM)
    data/dnieper_water_osm.geojson              第聂伯河梯级水库水面(OSM + NE 卡霍夫卡)
    (河流/海岸线/邻国国界线复用仓库 data/cartopy 的 Natural Earth 10m 缓存)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# matplotlib 的缓存目录必须在导入 matplotlib 之前指定; 本机 ~/.config 不可写.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import matplotlib.cm as cm  # 色标用的 ScalarMappable
import matplotlib.colors as mcolors  # 自定义高程/水深色带
import matplotlib.patheffects as pe  # 文字描边
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网刻度
import numpy as np  # 数组运算
import geopandas as gpd  # 读取 GeoJSON/shapefile
from matplotlib.lines import Line2D  # 图例线段
from matplotlib.patches import Patch  # 图例色块
from shapely.ops import unary_union  # 合并几何

# 共享的 ETOPO/晕渲/底图工具(实现见 src/cartopy_file/relief.py).
from cartopy_file.relief import add_base_map, find_etopo, load_countries, load_elevation, make_relief

# 重合边界只画一条: 剪掉低优先级线里与高优先级线重合的段落(见 overlap.py).
from cartopy_file.overlap import cut, overlap_mask

# cartopy 的 Natural Earth 缓存统一到仓库 data/cartopy(见 cartopy_file.data).
from cartopy_file.data import configure_cartopy, natural_earth_paths

configure_cartopy()

# 全局字体: 汉字 Noto Sans Mono CJK SC, 英文/数字 JetBrains Mono Slashed Medium.
from cartopy_file.fonts import apply_matplotlib_fonts

apply_matplotlib_fonts()


# ============================
# 配置
# ============================
EXTENT = [21.0, 41.5, 43.2, 53.4]  # [min_lon, max_lon, min_lat, max_lat]

# 投影参数: 中央经线取国土中部, 标准纬线夹住南北缘, 使全国比例误差最小.
PROJECTION = ccrs.LambertConformal(
    central_longitude=31.0,
    central_latitude=48.5,
    standard_parallels=(45.0, 52.0),
)

# 地形参数: 乌克兰最高点是喀尔巴阡山的霍韦尔拉山(2061 m), 黑海最深约
# 2200 m, 所以 ±2500 m 足够; 两端都落在色带内部, 不需要 extend 三角形.
ELEV_VMIN, ELEV_VMAX = -2500, 2500
HILLSHADE_AZIMUTH = 315  # 西北来光, 制图惯例
HILLSHADE_ALTITUDE = 45
HILLSHADE_VERT_EXAG = 2.5  # 平原起伏只有几十米, 不夸张就看不出来
# 只压暗的晕渲强度(见 relief.make_relief): 1.5 在 30″ ETOPO 上能显出水系/丘陵,
# 又不至于把平原压成灰底; 与 HILLSHADE_VERT_EXAG 一起决定地形可见度.
RELIEF_SHADE_STRENGTH = 1.5


def make_relief_cmap(vmin: float, vmax: float) -> mcolors.LinearSegmentedColormap:
    """高程/水深双色带: 深蓝(深水) -> 浅蓝(0 m 水面) | 浅绿(0 m 陆地) -> 黄 -> 棕 -> 雪白.

    为什么要在 0 m 处断开:
        "terrain" 这类单段色带把 ±2500 m 线性铺开, 海平面正好在色带中点,
        0~300 m 的陆地只占 6% 的色带宽度; 而亚速海最深才 ~14 m, 归一化值
        0.497 与 0 m 陆地的 0.500 几乎重合 —— 图上浅海和陆地就是一个颜色.
        这里让水色在 0 m 处直接跳到陆色, 浅海也一眼是"水"; 陆地色带再把
        锚点密集放在 0~500 m, 平原上的高程差异才拉得开.

    返回的色带配合 Normalize(vmin, vmax) 使用(色标横轴保持线性, 只是中点
    处色带不连续); N=2048 是为了让 0 m 处的水/陆跳变只占一个色阶宽度,
    海岸线不会被渐变糊掉. 颜色按 (高程 m, 十六进制) 给出, 便于按数据调整.
    """
    sea = [
        (-2500, "#07203c"),
        (-2000, "#0f3c66"),
        (-1250, "#1b628f"),
        (-700, "#2f82b5"),
        (-300, "#5aa2cd"),
        (-100, "#82c0e2"),
        (-20, "#a6d3ec"),
        (-1, "#b5dcf2"),
    ]
    land = [
        (1, "#d2e5b2"),
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
    ]

    def u(elev: float) -> float:
        return (elev - vmin) / (vmax - vmin)

    anchors = [(u(e), color) for e, color in sea] + [(u(e), color) for e, color in land]
    return mcolors.LinearSegmentedColormap.from_list("ukraine_relief", anchors, N=2048)


ELEV_CMAP = make_relief_cmap(ELEV_VMIN, ELEV_VMAX)

# 海陆底色(只在 ETOPO 子集边缘露出来时可见, 与 ELEV_CMAP 两端的颜色一致).
BASE_OCEAN_COLOR = "#b5dcf2"
BASE_LAND_COLOR = "#d2e5b2"

# 图面配色: 每种边界一个固定颜色, 图例与标注共用同一套常量, 避免读图歧义.
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
COLOR_MOUNTAIN = "#6d4a33"   # 山系标注文字: 深棕

# 国家标注: (经度, 纬度, 文字). 放在画面中离边界线/城市较远的位置.
COUNTRY_LABELS = [
    (37.0, 52.55, "俄罗斯"),
    (27.6, 52.9, "白俄罗斯"),
    (22.2, 51.9, "波兰"),
    (21.6, 48.8, "斯洛伐克"),
    (21.6, 47.95, "匈牙利"),
    (24.7, 45.5, "罗马尼亚"),
    (28.3, 47.6, "摩尔多瓦"),
]
SEA_LABELS = [
    (34.2, 44.25, "黑海"),
    (36.7, 46.35, "亚速海"),
]
# 山系标注: (经度, 纬度, 文字, 走向起点经度, 起点纬度, 终点经度, 终点纬度).
# 后四个数只用来求文字旋转角: 取山脊走向上两点, 在投影平面里算屏幕方向;
# 直接拿经纬度差算 atan2 会偏(兰勃特投影下经线是斜的, 1° 经度对应的
# 地面距离还随纬度变). 文字位置手工放在山体上, 不压国界/河名/城市.
MOUNTAIN_LABELS = [
    # 乌克兰喀尔巴阡山: 西北-东南走向, 文字压在乔尔诺霍拉一带的山体上.
    (24.32, 48.42, "喀尔巴阡山", 22.80, 49.15, 25.40, 47.95),
    # 大高加索山西端: 在图幅右下角(索契以东), 山脊同样是西北-东南走向.
    (40.42, 43.86, "高加索山", 38.20, 44.65, 41.30, 43.35),
]
# 河流名称: (经度, 纬度, 文字, 走向起点经度, 起点纬度, 终点经度, 终点纬度).
# 位置都放在河岸陆地上而不是水面上: 这张图要表达第聂伯河"河宽沿程变化",
# 河名压在水面上会用白色描边遮掉一段水面; 顿河同理不压河道线.
RIVER_LABELS = [
    # 第聂伯河: 克列缅丘格水库东北岸的陆地, 与水面留出几像素间隙.
    (33.30, 49.60, "第聂伯河", 31.70, 49.62, 33.05, 49.10),
    # 顿河: 下游罗斯托夫段北岸陆地. 这一段在图幅内够长, 且离顿巴斯最近.
    (40.15, 47.42, "顿河", 39.80, 47.20, 40.47, 47.45),
]
# 城市标注: (经度, 纬度, 名称, 是否首都, 经度偏移, 纬度偏移, 对齐方式).
# 偏移都在 0.1~0.3°(约 10~25 km)量级, 只用于让文字离开边界线与其它标注.
# 赫尔松城正好卡在第聂伯河(东)、第聂伯-布格河口(西南)与米科拉伊夫州界
# (西北)之间, 横向 0.6° 宽的标签放不下: 往东压河, 往西压河口; 所以放在城点
# 西北的陆地上并右对齐, 只跨过州界, 不压任何水面.
# 顿涅茨克/卢甘斯克两城的标签单独调整过: 两个"人民共和国"的名称移到其宣称
# 全境中心后, 会分别落在顿涅茨克城点与卢甘斯克城点附近, 城名必须让开;
# 同时城名原本会压住 2014 接触线(顿涅茨克)或压住共和国名称(卢甘斯克).
CITIES = [
    (30.523, 50.450, "基辅", True, 0.20, 0.12, "left"),
    (36.230, 49.993, "哈尔科夫", False, 0.16, 0.12, "left"),
    (30.732, 46.482, "敖德萨", False, 0.16, -0.12, "left"),
    (35.046, 48.464, "第聂伯罗", False, 0.16, 0.12, "left"),
    # 顿涅茨克: 城点东南侧的 NGCA 空处, 文字整体在接触线以东, 不与线相交.
    (37.802, 48.015, "顿涅茨克", False, 0.10, -0.16, "left"),
    # 卢甘斯克: 城点正南, 避开北面的共和国名称与更北的 2014 接触线.
    (39.307, 48.574, "卢甘斯克", False, 0.00, -0.19, "center"),
    (35.139, 47.838, "扎波罗热", False, 0.16, 0.14, "left"),
    (32.617, 46.640, "赫尔松", False, 0.16, -0.10, "left"),
    (37.556, 47.096, "马里乌波尔", False, -0.16, -0.06, "right"),
    (34.102, 44.952, "辛菲罗波尔", False, 0.16, 0.12, "left"),
    (33.522, 44.606, "塞瓦斯托波尔", False, -0.16, 0.10, "right"),
    (24.031, 49.842, "利沃夫", False, 0.16, 0.12, "left"),
]

# 图标题: 第一行点题, 第二行交代地形、投影与参数.
TITLE = (
    "乌克兰全图：1991 / 2014 / 2022 年边界\n"
    "NOAA ETOPO 2022 地形 | 兰勃特等角圆锥投影"
    "（中央经线 31°E，标准纬线 45°N / 52°N）"
)
OUT_PNG = ROOT / "ukraine_borders_1991_2014_2022_lambert_conformal.png"

# 输出数据文件(由 download_data.py 生成).
OBLASTS_PATH = DATA_DIR / "ukraine_oblasts.geojson"
BORDER_1991_PATH = DATA_DIR / "ukraine_1991.geojson"
CRIMEA_LINE_PATH = DATA_DIR / "crimea_2014_line.geojson"
OCCUPIED_2014_PATH = DATA_DIR / "occupied_2014.geojson"
CONTACT_2014_PATH = DATA_DIR / "contact_line_2014.geojson"
CLAIMED_2022_PATH = DATA_DIR / "claimed_2022.geojson"
DNIEPER_RIVER_PATH = DATA_DIR / "dnieper_river_osm.geojson"
DNIEPER_WATER_PATH = DATA_DIR / "dnieper_water_osm.geojson"
COUNTRY_DIR = DATA_DIR / "ne_10m_admin_0_countries"

# 文字描边: 白边保证汉字压在深色地形/彩色填充上仍可读.
HALO = [pe.withStroke(linewidth=2.8, foreground="white")]


# ============================
# 数据读取
# ============================
def _require(path: Path) -> Path:
    """缺少数据时给出明确修复命令, 而不是让后面的读取抛难懂的错."""
    if not path.exists():
        raise FileNotFoundError(f"未找到数据: {path}\n请先运行: python Ukraine/download_data.py")
    return path


def load_vectors() -> tuple[gpd.GeoDataFrame, ...]:
    """读取全部派生 GeoJSON, 并统一到 EPSG:4326."""
    oblasts = gpd.read_file(_require(OBLASTS_PATH)).to_crs("EPSG:4326")
    border_1991 = gpd.read_file(_require(BORDER_1991_PATH)).to_crs("EPSG:4326")
    crimea_line = gpd.read_file(_require(CRIMEA_LINE_PATH)).to_crs("EPSG:4326")
    occupied = gpd.read_file(_require(OCCUPIED_2014_PATH)).to_crs("EPSG:4326")
    contact = gpd.read_file(_require(CONTACT_2014_PATH)).to_crs("EPSG:4326")
    claimed = gpd.read_file(_require(CLAIMED_2022_PATH)).to_crs("EPSG:4326")
    return oblasts, border_1991, crimea_line, occupied, contact, claimed


def load_dnieper() -> tuple:
    """读取第聂伯河干流中心线与梯级水库水面(由 download_data.py 从 OSM 派生).

    干流与水库分开存: 干流是线, 水库是面, 绘图时用不同样式, 且水面要盖住
    穿过水库的那段中心线(水面内不该再看到河道线).
    """
    river = gpd.read_file(_require(DNIEPER_RIVER_PATH)).to_crs("EPSG:4326")
    water = gpd.read_file(_require(DNIEPER_WATER_PATH)).to_crs("EPSG:4326")
    return river.geometry.iloc[0], water.geometry.iloc[0]


def shared_layer(resolution: str, category: str, name: str):
    """按项目缓存找 Natural Earth 图层; 缺缓存时返回 None(跳过该图层, 不联网)."""
    existing, _ = natural_earth_paths(resolution, category, name)
    if existing is None:
        print(f"警告: 缺少 Natural Earth 缓存 {resolution}/{category}/{name}, 跳过该图层")
        return None
    return existing


# ============================
# 绘图
# ============================
def add_line_layer(
    ax: plt.Axes,
    geometries,
    *,
    color: str,
    linewidth: float,
    linestyle="-",
    zorder: float,
    alpha: float = 1.0,
    casing: bool = True,
    casing_width: float = 1.6,
    casing_alpha: float = 0.7,
) -> None:
    """画一组线要素, 先画白色粗描边再画彩色细线, 保证在晕渲上仍然清楚.

    为什么不用 path_effects: ``add_geometries`` 返回的 FeatureArtist 对描边
    支持不稳定; 用"先粗白线后细彩线"两次绘制是等效且跨 cartopy 版本可靠的做法.

    ``alpha`` 是主线透明度, 只有 1991 国界线用到(红色半透明, 不加描边);
    需要"半透明主线 + 描边"时, 描边透明度仍由 ``casing_alpha`` 单独控制.
    """
    geoms = list(geometries)
    if casing:
        ax.add_geometries(
            geoms,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor="white",
            linewidth=linewidth + casing_width,
            alpha=casing_alpha,
            zorder=zorder,
        )
    ax.add_geometries(
        geoms,
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=color,
        linewidth=linewidth,
        linestyle=linestyle,
        alpha=alpha,
        zorder=zorder + 0.05,
    )


def add_fill_layer(ax: plt.Axes, geometries, *, color: str, alpha: float, zorder: float) -> None:
    """画半透明控制区填充: 只表达"谁实际控制", 不遮挡地形细节."""
    ax.add_geometries(
        list(geometries),
        crs=ccrs.PlateCarree(),
        facecolor=color,
        edgecolor="none",
        alpha=alpha,
        zorder=zorder,
    )


def draw_basemap(
    ax: plt.Axes,
    world,
    *,
    ukraine_geom,
    oblasts: gpd.GeoDataFrame,
    rivers,
    dnieper_river,
    dnieper_water,
    coastline,
    neighbor_borders,
) -> None:
    """地形 + 水系 + 邻国国界 + 乌克兰州界背景线.

    乌克兰自己的海岸线不单独画: 1991 年国界(红线)已经把它包进去; 再叠一条
    不同来源的海岸线只会露出两条线的几十米~几公里偏差. 邻国的海岸线/国界
    则照常画, 提供地理参照.

    第聂伯河单独处理: 先画中心线, 再用梯级水库的实际水面盖住穿过水库的那段
    中心线. 这样图上"上游窄河道、下游宽水库"的宽度变化是真实水面宽度, 而不是
    靠加粗同一根线来假装 —— 等宽线在这里会失真一个数量级(河道 0.2~0.5 km,
    水库 3~15 km).
    """
    add_base_map(ax, world, ocean_color=BASE_OCEAN_COLOR, land_color=BASE_LAND_COLOR)

    # 邻国与乌克兰沿海的海岸线: 裁掉乌克兰范围(含克里米亚), 避免与 1991 年
    # 边界线在海岸处出现"双线". Natural Earth 与 GADM 的海岸线偏差中位数
    # ~0.5 km、个别沙嘴可达 8 km, 所以缓冲带取 0.05°(~5 km)覆盖绝大多数.
    ua_buffer = ukraine_geom.buffer(0.05)
    if coastline is not None:
        outer_coast = coastline.difference(ua_buffer)
        ax.add_geometries(
            [outer_coast],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor="#3c3c3c",
            linewidth=0.45,
            zorder=3,
        )
    if neighbor_borders is not None:
        # 邻国国界线单独用更大的缓冲带: NE 的乌克兰国界(GADM 口径不同)会在
        # 边界外侧留下一条与红色国界线平行的细虚线.
        outer_borders = neighbor_borders.difference(ukraine_geom.buffer(0.06))
        ax.add_geometries(
            [outer_borders],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=COLOR_NEIGHBOR,
            linewidth=0.7,
            linestyle=(0, (5, 3)),
            zorder=3,
        )
    # 乌克兰州界: 只作背景参考, 用细灰线, 不与主题边界争视觉层级.
    ax.add_geometries(
        list(oblasts.geometry),
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=COLOR_OBLAST,
        linewidth=0.45,
        alpha=0.55,
        zorder=3.1,
    )
    # 一般河流放在州界之下、主题边界之上; 10m 河流在国界附近可能超出画框,
    # cartopy 会按画框裁剪. Dnieper 已从这一层剔除(改用 OSM 干流).
    if rivers is not None:
        ax.add_geometries(
            list(rivers.geometry),
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=COLOR_RIVER,
            linewidth=0.5,
            alpha=0.7,
            zorder=2.2,
        )
    # 第聂伯河干流中心线: 窄河道段就是这个线宽; 进入水库后会被下一层水面盖住.
    if dnieper_river is not None:
        ax.add_geometries(
            [dnieper_river],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=COLOR_RIVER_MAIN,
            linewidth=0.9,
            zorder=2.3,
        )
    # 梯级水库水面: 实心填充, 直接表达真实水面宽度(3~15 km).
    if dnieper_water is not None:
        ax.add_geometries(
            [dnieper_water],
            crs=ccrs.PlateCarree(),
            facecolor=COLOR_WATER,
            edgecolor=COLOR_WATER_EDGE,
            linewidth=0.45,
            zorder=2.35,
        )


def draw_borders(
    ax: plt.Axes,
    *,
    ukraine_geom,
    oblasts: gpd.GeoDataFrame,
    crimea_line,
    contact,
    occupied: gpd.GeoDataFrame,
    claimed: gpd.GeoDataFrame,
) -> None:
    """按"先填充后线条"的顺序叠加所有主题边界.

    函数开头先算好 1991 国界线, 并剪掉 2022 宣称边界/哈尔科夫州界中与它
    重合的段落: 半透明红线不能靠"后画叠压"盖住下面两种虚线 —— 紫/橙会
    透过 alpha=0.62 的红线混色, 所以重合段直接从紫/橙线里剪掉, 只在剪剩
    的独有段落上画紫/橙(见 cartopy_file.overlap.cut).

    剪枝参数: tol=0.003°(约 0.3 km)只吸收同源数据的浮点误差, 断口约
    1~2 px; 1991 红线 2.7 pt 在图上约 4.3 km 宽(半宽约 2.1 km), 断口会被
    后画的红线完全盖住. min_length=0.03°(约 3 km): 两条线以小夹角相交的
    接头处(如赫尔松州界与海岸线)差集会留下 1~2 km 碎段, 比线宽还短,
    单独画出来只是孤立小点, 所以丢掉.
    """
    claimed_union = unary_union(list(claimed.geometry))
    border_1991 = ukraine_geom.boundary

    # --- 2014 年实际控制区(克里米亚 + 顿巴斯 NGCA): 浅蓝填充 ---
    crimea_units = oblasts[oblasts["name"].isin(["Crimea", "Sevastopol'"])]
    ngca_units = occupied[occupied["name"].str.startswith("NGCA,", na=False)]
    add_fill_layer(ax, list(crimea_units.geometry), color=COLOR_2014_FILL, alpha=0.22, zorder=2.2)
    add_fill_layer(ax, list(ngca_units.geometry), color=COLOR_2014_FILL, alpha=0.24, zorder=2.2)

    # --- 2014 年宣布的哈尔科夫人民共和国: 只有宣称、没有实际控制, 用橙色虚线 ---
    # 这里画的是哈尔科夫州界, 其中两段与别的线重合, 都要剪掉:
    #   - 南段 = 2022 年宣称四州的外边界(紫点划线). 两条虚线叠在一起时, 后画
    #     紫线的点划间隙里会露出橙线及其白描边, 看起来像两条线在同时表达
    #     一个口径; 所以重合段只画紫线;
    #   - 东北段 = 乌克兰与俄罗斯的 1991 国界(红色半透明线). 橙线若留在
    #     红线下面会透出橙色, 重合段变成红橙混色; 所以重合段只画 1991 红线.
    # 剪剩的是哈尔科夫州与苏梅/波尔塔瓦/第聂伯罗/卢甘斯克/顿涅茨克相邻的
    # 州内段. 差集切出的碎段由 cartopy_file.overlap.cut 拼回连续折线(否则
    # 虚线节距会乱); 若数据变化导致州界被剪空, 则直接跳过橙线图层.
    kharkiv = oblasts[oblasts["name"] == "Kharkiv"]
    if not kharkiv.empty:
        kharkiv_boundary = unary_union(list(kharkiv.geometry)).boundary
        kharkiv_only = cut(
            kharkiv_boundary,
            overlap_mask([claimed_union.boundary, border_1991], 0.003),
            min_length_deg=0.03,
        )
        if kharkiv_only is not None:
            add_line_layer(
                ax,
                [kharkiv_only],
                color=COLOR_KHARKIV,
                linewidth=2.0,
                linestyle=(0, (6, 3)),
                zorder=5.0,
            )

    # --- 2022 年俄方宣称的四州全境: 四州合并后的外边界, 紫色点划线 ---
    # 先把与 1991 国界重合的段落剪掉: 顿巴斯东缘的俄乌边界、赫尔松/扎波罗热/
    # 顿涅茨克南部的海岸线, 这几段上 2022 宣称边界与 1991 边界是同一条线,
    # 半透明红线叠在紫线上会混出红紫色, 所以只保留红线. 剪剩的紫线才是
    # 2022 口径独有的段落; 与 2014 控制线重合的克里米亚地峡一段例外, 那里
    # 紫线先画, 由后画的不透明蓝线盖住, 不存在混色问题.
    claimed_only = cut(
        claimed_union.boundary,
        overlap_mask([border_1991], 0.003),
        min_length_deg=0.03,
    )
    if claimed_only is not None:
        add_line_layer(
            ax,
            [claimed_only],
            color=COLOR_2022,
            linewidth=2.1,
            linestyle=(0, (6, 2.0, 1.6, 2.0)),
            zorder=5.5,
            casing_width=1.0,
            casing_alpha=0.55,
        )

    # --- 1991 年国际承认边界: 最外层、最粗、红色半透明实线 ---
    # 用户要求改成红色半透明: 红色 alpha 叠在地形上, 地形纹理能透出来; 不再加
    # 白色描边——白描边会把半透明红线衬成发白的"粉带", 反而看不出是半透明红.
    # 线宽保持最粗, 1991 口径仍是这张图的主线; 紫/橙线的重合段已在前面剪掉,
    # 所以红线下面不会再透出它们的颜色.
    add_line_layer(
        ax,
        [ukraine_geom],
        color=COLOR_1991,
        linewidth=2.7,
        linestyle="-",
        zorder=6.0,
        alpha=COLOR_1991_ALPHA,
        casing=False,
    )

    # --- 2014 年实际控制线: 克里米亚陆上控制线 + 顿巴斯接触线 ---
    add_line_layer(
        ax,
        [crimea_line.geometry.iloc[0], contact.geometry.iloc[0]],
        color=COLOR_2014,
        linewidth=2.1,
        linestyle="-",
        zorder=7.0,
    )


def projected_angle(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """求两点连线的屏幕方向角(度), 用于把文字旋转成与山脊/河道平行.

    为什么要在投影平面里算: matplotlib 的 rotation 是屏幕角, 而兰勃特等角
    圆锥投影下经线不是竖直的; 直接拿经纬度差算 atan2 会得到与屏幕不一致的
    角度(1° 经度对应的地面距离还随纬度变化), 文字会明显偏离山脊/河道走向.
    """
    p1 = PROJECTION.transform_point(lon1, lat1, ccrs.PlateCarree())
    p2 = PROJECTION.transform_point(lon2, lat2, ccrs.PlateCarree())
    return float(np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0])))


def add_labels(ax: plt.Axes, oblasts: gpd.GeoDataFrame) -> None:
    """国家/海域/山系/城市标注 + 主题区域标注(2014 人民共和国与 2022 宣称州)."""
    # --- 国家与海域 ---
    for lon, lat, text in COUNTRY_LABELS:
        ax.text(
            lon, lat, text,
            transform=ccrs.PlateCarree(),
            fontsize=12.5, color="#3a3a3a",
            ha="center", va="center", path_effects=HALO, zorder=9,
        )
    for lon, lat, text in SEA_LABELS:
        ax.text(
            lon, lat, text,
            transform=ccrs.PlateCarree(),
            fontsize=11.5, color="#1f4e79", style="italic",
            ha="center", va="center", path_effects=HALO, zorder=9,
        )
    # --- 邻国山系: 棕色斜体, 旋转到与山脊走向平行; zorder 比边界低一级,
    #     保证文字描边不会盖住国界/宣称边界这些主题线. ---
    for lon, lat, text, lon1, lat1, lon2, lat2 in MOUNTAIN_LABELS:
        ax.text(
            lon, lat, text,
            transform=ccrs.PlateCarree(),
            fontsize=11.0, color=COLOR_MOUNTAIN, style="italic",
            rotation=projected_angle(lon1, lat1, lon2, lat2),
            rotation_mode="anchor", ha="center", va="center",
            path_effects=HALO, zorder=9.2,
        )

    # --- 2014 年宣布的"人民共和国": 卢甘斯克/顿涅茨克是实际控制区(蓝),
    #     哈尔科夫只有宣称(橙). 文字用两行, 避免横跨边界线. ---
    # 名称位置按"宣称全境"取中心, 不再挤在 2014 实际控制区(蓝色填充)里:
    #   - 卢甘斯克州宣称全境(约 37.85~40.22E, 47.82~50.09N)的形心在
    #     39.03E / 48.98N, 图上是州中部的开阔地, 两行文字正好放得下;
    #     文字中心再向北 0.03° 是为了让白描边与 2014 接触线北缘的尖峰
    #     (48.78N 附近)留出间隙, 相对形心只偏 3 km, 可忽略;
    #   - 顿涅茨克州宣称全境的形心(37.67E / 48.05N)恰好落在顿涅茨克城点上,
    #     2014 接触线又绕城而过, 两行文字无论怎么摆都会压住城点或接触线;
    #     所以整体北移到接触线以北的州内空处(37.70E / 48.65N, 离顿涅茨克-
    #     卢甘斯克州界也留出一段), 仍在全境中轴线上, 只向北让开约 0.6°
    #     (约 67 km)——这是不遮接触线、不遮城点、不遮州界的最小让步.
    ax.text(
        39.03, 49.02, "卢甘斯克\n人民共和国",
        transform=ccrs.PlateCarree(),
        fontsize=8.8, color="#0d47a1",
        ha="center", va="center", linespacing=1.3, path_effects=HALO, zorder=9.5,
    )
    ax.text(
        37.70, 48.65, "顿涅茨克\n人民共和国",
        transform=ccrs.PlateCarree(),
        fontsize=8.8, color="#0d47a1",
        ha="center", va="center", linespacing=1.3, path_effects=HALO, zorder=9.5,
    )
    # 纬度比州界折角高一截: 第二行文字的白色描边原本正压在
    # 2022 宣称边界由南北向折向西南的那一段上, 把整段折线遮掉; 上移后
    # 折角完整露出, 只剩右端"国"字附近与竖直线段的一小段交叠.
    ax.text(
        36.80, 49.50, "哈尔科夫人民共和国\n（2014年宣布，未实际控制）",
        transform=ccrs.PlateCarree(),
        fontsize=9.4, color=COLOR_KHARKIV, style="italic",
        ha="center", va="center", linespacing=1.35, path_effects=HALO, zorder=9.5,
    )
    # --- 2022 年俄方宣称的两个州(顿/卢两州已由上面的"人民共和国"标注覆盖) ---
    # 位置都放在远离第聂伯河/水库水面的州内陆地: 扎波罗热州在中东部草原,
    # 赫尔松州在锡瓦什以北的左岸草原, 避免文字压住河宽变化的重点区域.
    ax.text(
        34.11, 46.52, "赫尔松州\n（俄宣称全境）",
        transform=ccrs.PlateCarree(),
        fontsize=9.4, color=COLOR_2022,
        ha="center", va="center", linespacing=1.35, path_effects=HALO, zorder=9.5,
    )
    ax.text(
        35.65, 47.08, "扎波罗热州\n（俄宣称全境）",
        transform=ccrs.PlateCarree(),
        fontsize=9.4, color=COLOR_2022,
        ha="center", va="center", linespacing=1.35, path_effects=HALO, zorder=9.5,
    )
    ax.text(
        34.55, 45.40, "克里米亚\n（2014年俄实际控制）",
        transform=ccrs.PlateCarree(),
        fontsize=9.6, color="#0d47a1",
        ha="center", va="center", linespacing=1.35, path_effects=HALO, zorder=9.5,
    )

    # --- 城市: 首都用星形, 其余用圆点; 标签偏移量在 CITIES 里逐城指定 ---
    for lon, lat, name, is_capital, dx, dy, align in CITIES:
        if is_capital:
            ax.plot(
                lon, lat, marker="*", markersize=15,
                markerfacecolor="#ffd200", markeredgecolor="black", markeredgewidth=0.8,
                transform=ccrs.PlateCarree(), zorder=9.8,
            )
        else:
            ax.plot(
                lon, lat, marker="o", markersize=4.5,
                markerfacecolor="white", markeredgecolor="black", markeredgewidth=0.9,
                transform=ccrs.PlateCarree(), zorder=9.8,
            )
        ax.text(
            lon + dx, lat + dy, name,
            transform=ccrs.PlateCarree(),
            fontsize=9.0, color="black",
            ha=align, va="center",
            path_effects=HALO, zorder=9.9,
        )


def add_river_labels(ax: plt.Axes) -> None:
    """在河岸陆地上标注干流名称(第聂伯河/顿河), 文字沿河道方向旋转.

    为什么把字放在岸上而不是水面上: 这张图要表达"河宽沿程变化", 河名压在
    梯级水库水面上会用白色描边遮掉一段水面, 正好挡住要看的宽度变化; 所以
    文字放在水库/河道旁的陆地上, 与水面留出几像素间隙, 旋转方向仍与河道
    一致. 顿河同理放在下游北岸, 不压河道线. 位置与旋转参考点见 RIVER_LABELS.
    """
    for lon, lat, text, lon1, lat1, lon2, lat2 in RIVER_LABELS:
        ax.text(
            lon, lat, text,
            transform=ccrs.PlateCarree(),
            fontsize=10.5, color=COLOR_RIVER_MAIN, style="italic",
            rotation=projected_angle(lon1, lat1, lon2, lat2),
            rotation_mode="anchor", ha="center", va="center",
            path_effects=HALO, zorder=9.4,
        )


def add_gridlines(ax: plt.Axes) -> None:
    """经纬网: 只保留底边经度与左边纬度标签, 减少画面边缘拥挤.

    rotate_labels=False: 圆锥投影下经线是斜的, 默认会让底部经度标签跟着
    旋转, 旋转后的数字不易读; 统一保持水平.
    """
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        x_inline=False,
        y_inline=False,
        linewidth=0.5,
        color="gray",
        alpha=0.45,
        linestyle=":",
        zorder=4,
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.rotate_labels = False
    gl.xlocator = mticker.FixedLocator(np.arange(20, 45, 5))
    gl.ylocator = mticker.FixedLocator(np.arange(45, 55, 5))
    gl.xlabel_style = {"size": 9.5, "color": "#444444"}
    gl.ylabel_style = {"size": 9.5, "color": "#444444"}


def add_colorbar(fig: plt.Figure, norm, cmap) -> None:
    """高程色标放在图例下方, 单独占一个窄坐标轴, 不抢地图的宽度.

    纵向位置要压到 0.33: 右侧口径说明(注 3/注 4)文字块较高, 色标标题从
    0.53 再往上一段, 若色标起始位置抬高, 标题就会压住注 4 的最后一行.
    """
    cax = fig.add_axes([0.79, 0.33, 0.014, 0.17])
    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])
    cbar = fig.colorbar(mappable, cax=cax)
    cbar.ax.tick_params(labelsize=8.5)
    # 用标题而不是旋转 ylabel: 竖排汉字在窄色标旁边容易与刻度和图例挤在一起.
    cbar.ax.set_title("高程 / 水深 (m)", fontsize=8.5, pad=6)


def add_legend(fig: plt.Figure) -> None:
    """右下角图例 + 三条口径说明.

    图例只列"图上线型", 说明文字解释数据口径与近似程度; 两者分开写是为了
    让图例本身保持简洁, 又不会把"宣称边界"误读成"实际控制线".
    """
    lax = fig.add_axes([0.785, 0.60, 0.205, 0.34])
    lax.set_axis_off()

    handles = [
        Line2D([0], [0], color=COLOR_1991, linewidth=2.7, alpha=COLOR_1991_ALPHA, label="1991 年国际承认边界（含克里米亚）"),
        Line2D([0], [0], color=COLOR_2014, linewidth=2.1, label="2014 年实际控制线（克里米亚 · 顿巴斯接触线）"),
        Patch(facecolor=COLOR_2014_FILL, alpha=0.24, edgecolor="none", label="2014 年俄方实际控制区（示意填色）"),
        Line2D([0], [0], color=COLOR_KHARKIV, linewidth=2.0, linestyle=(0, (6, 3)), label="2014 年宣布的「哈尔科夫人民共和国」\n（未实际控制）"),
        Line2D([0], [0], color=COLOR_2022, linewidth=2.1, linestyle=(0, (6, 2.0, 1.6, 2.0)), label="2022 年俄方宣称四州全境边界\n（单方面宣称，非控制线）"),
    ]
    legend = lax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.0, 1.0),
        frameon=True,
        framealpha=0.94,
        edgecolor="#bbbbbb",
        fontsize=9.6,
        title="图 例",
        title_fontsize=12.5,
        borderpad=0.8,
        labelspacing=1.05,
        handlelength=2.8,
        handletextpad=0.9,
    )
    legend.get_title().set_color("#222222")
    legend.get_frame().set_linewidth(0.8)

    # 口径说明: 用 fig.text 而不是 legend 的 footer, 便于控制换行与字号.
    notes = (
        "注 1：2014 年顿巴斯接触线以 OCHA 2021 年 GCA/NGCA 界线近似\n"
        "（明斯克协议线，2015 年后基本稳定），位置误差约 1–2 km。\n"
        "注 2：2022 年边界为俄方 2022-09 单方面宣称的赫尔松州、扎波罗热州、\n"
        "顿涅茨克人民共和国、卢甘斯克人民共和国全境，并非实际控制线。\n"
        "注 3：卢甘斯克、顿涅茨克两「人民共和国」于 2014 年宣布，\n"
        "名称标注在各自宣称全境范围内（顿涅茨克形心被城点与接触线占据，\n"
        "名称向北让开）；实际控制范围见蓝色填充与接触线。\n"
        "哈尔科夫人民共和国只有 2014 年的宣称，图中按其宣称范围\n"
        "(哈尔科夫州)画出，未实际控制。\n"
        "注 4：哈尔科夫州界（橙）南段与 2022 年宣称边界（紫）完全重合，\n"
        "重合段只画紫线；紫/橙线与 1991 国界重合处只画红色 1991 线\n"
        "（顿巴斯东缘、南部海岸、哈尔科夫州东北的俄乌边界）。"
    )
    fig.text(
        0.785, 0.735, notes,
        ha="left", va="top", fontsize=8.2, color="#333333", linespacing=1.45,
    )


def add_source_note(fig: plt.Figure) -> None:
    """数据来源放画面底部, 不遮挡地图主体."""
    fig.text(
        0.5, 0.008,
        "地形: NOAA NCEI ETOPO 2022（15″） | 边界: GADM 4.1 · OCHA/HDX 2021 HNO GCA-NGCA · Natural Earth 10m | "
        "水系: OpenStreetMap（ODbL）· Natural Earth 10m | 投影: Lambert Conformal Conic",
        ha="center", va="bottom", fontsize=8.5, color="#666666",
    )


# ============================
# 主流程
# ============================
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stride", type=int, default=None,
        help="使用 data/ 下对应采样步长的 ETOPO 文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    parser.add_argument("--dpi", type=int, default=300, help="输出 PNG 分辨率, 默认 300")
    parser.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    args = parser.parse_args()

    etopo_path = find_etopo(
        DATA_DIR, "ukraine", args.stride, env_path=os.environ.get("UKRAINE_ETOPO_PATH")
    )
    _require(etopo_path)
    lon, lat, z = load_elevation(etopo_path)

    oblasts, border_1991, crimea_line, occupied, contact, claimed = load_vectors()
    ukraine_geom = border_1991.geometry.iloc[0]
    print(f"1991 年边界: 要素 {len(border_1991)}, 范围 {np.round(ukraine_geom.bounds, 2)}")
    print(f"州级单元: {len(oblasts)} 个; 2014 控制区: {len(occupied)} 个要素; "
          f"2022 宣称四州: {len(claimed)} 个要素")

    world = load_countries(COUNTRY_DIR)
    dnieper_river, dnieper_water = load_dnieper()
    print(f"第聂伯河: 干流顶点 {len(dnieper_river.coords) if dnieper_river.geom_type == 'LineString' else '?'}, "
          f"水库水面 {dnieper_water.geom_type}")

    # 共享缓存里的 Natural Earth 10m 图层(缺失就跳过, 不联网下载).
    rivers = None
    rivers_path = shared_layer("10m", "physical", "rivers_lake_centerlines")
    if rivers_path is not None:
        rivers = gpd.read_file(rivers_path)
        rivers = rivers[rivers["scalerank"] <= 9]
        # 第聂伯河改由 OSM 干流 + 水库水面绘制, 从 NE 图层里剔除, 避免同一条
        # 河出现两条位置略有差异的线(NE 与 OSM 中位数偏差约 0.8 km).
        rivers = rivers[rivers["name_en"].fillna("") != "Dnieper"]
        bbox = (EXTENT[0] - 1, EXTENT[2] - 1, EXTENT[1] + 1, EXTENT[3] + 1)
        rivers = rivers.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    coastline = None
    coast_path = shared_layer("10m", "physical", "coastline")
    if coast_path is not None:
        coastline = unary_union(list(gpd.read_file(coast_path).geometry))
    neighbor_borders = None
    borders_path = shared_layer("10m", "cultural", "admin_0_boundary_lines_land")
    if borders_path is not None:
        neighbor_borders = unary_union(list(gpd.read_file(borders_path).geometry))

    # 画布比例按投影后画框的宽高比(约 1.41)定制, 避免地图上下留大片空白.
    fig = plt.figure(figsize=(20, 12.5), facecolor="white")
    ax = fig.add_axes([0.035, 0.045, 0.735, 0.90], projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    draw_basemap(
        ax, world,
        ukraine_geom=ukraine_geom,
        oblasts=oblasts,
        rivers=rivers,
        dnieper_river=dnieper_river,
        dnieper_water=dnieper_water,
        coastline=coastline,
        neighbor_borders=neighbor_borders,
    )

    # 晕渲 RGB 图: imshow 比 pcolormesh 快; regrid_shape 提到 3200, 否则
    # 在 300 dpi 下 30 弧秒的 ETOPO 会被 cartopy 重采样糊掉.
    relief, norm, cmap = make_relief(
        z, lat, lon,
        vmin=ELEV_VMIN, vmax=ELEV_VMAX, cmap=ELEV_CMAP,
        azimuth=HILLSHADE_AZIMUTH, altitude=HILLSHADE_ALTITUDE,
        vert_exag=HILLSHADE_VERT_EXAG, shade_strength=RELIEF_SHADE_STRENGTH,
    )
    ax.imshow(
        relief, origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        regrid_shape=3200,
        interpolation="nearest",
        zorder=1,
    )

    draw_borders(
        ax,
        ukraine_geom=ukraine_geom,
        oblasts=oblasts,
        crimea_line=crimea_line,
        contact=contact,
        occupied=occupied,
        claimed=claimed,
    )
    add_labels(ax, oblasts)
    add_river_labels(ax)
    add_gridlines(ax)

    # 标题用 figure 级: GeoAxes 在有经纬网标签时重算标题位置, 多行标题
    # 容易被移出画布(与 myanmar.py 的原因相同).
    fig.suptitle(TITLE, fontsize=17, y=0.982, va="top")
    add_legend(fig)
    add_colorbar(fig, norm, cmap)
    add_source_note(fig)

    # 注意: 不用 tight_layout / bbox_inches="tight".
    # 原因: cartopy 0.25 在非矩形投影上绘制经纬网标签时, 布局引擎触发的提前
    # 绘制会让 gridliner 抛 shapely GEOSException; bbox_inches="tight" 还会把
    # 标签包围盒算错, 导致图片被裁掉一截(项目里 myanmar.py 已踩过这个坑).
    fig.savefig(OUT_PNG, dpi=args.dpi)
    print(f"地图已保存: {OUT_PNG}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
