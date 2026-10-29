#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Ukraine overview map: 1991 / 2014 / 2022 borders over ETOPO relief.

是什么: 以 ETOPO 2022 地形晕渲为底图绘制乌克兰全图, 叠加 1991/2014/2022 三种边界口径、
第聂伯河梯级水库水面与邻国地貌/水系参照; 只绘制地理要素, 不绘制任何文字/图例/色标/
标题/比例尺/指北针. 文字与版面由前端接管, 本脚本同时产出同名 geo.json, 契约见
``docs/reference/geo.md``.
完整说明: ``docs/maps/ukraine.md``(设计要点/数据来源/运行方式).
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
import matplotlib.colors as mcolors  # 自定义高程/水深色带
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网线位置定位
import numpy as np  # 数组运算
import geopandas as gpd  # 读取 GeoJSON/shapefile
from shapely.geometry import LineString, Point, box  # 图幅范围/端头延伸
from shapely.ops import unary_union  # 合并几何

# 共享的 ETOPO/晕渲/底图工具(实现见 src/cartopy_file/relief.py).
from cartopy_file.relief import add_base_map, find_etopo, load_countries, load_elevation, make_relief

# 重合边界只画一条: 剪掉低优先级线里与高优先级线重合的段落(见 docs/reference/overlap.md).
from cartopy_file.overlap import cut, overlap_mask

# cartopy 底图缓存统一到仓库 data/cartopy, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy, natural_earth_paths

configure_cartopy()

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

    返回的色带配合 Normalize(vmin, vmax) 使用(归一化横轴保持线性, 只是中点
    处色带不连续); N=2048 是为了让 0 m 处的水/陆跳变只占一个色阶宽度.
    图上不画海岸线(设计理由见 docs/maps/ukraine.md 的设计要点 9), 这条跳变本身就是岸线, 所以要够
    显眼: 水面从 -100 m 到 -1 m 逐渐变浅、变饱和, 陆地从 +1 m 起是偏黄
    的浅绿, 0 m 两侧的 L* 差约 7、色相差约 135° —— 原先那对近白色的
    #b5dcf2 / #d2e5b2 只差 3 和 119°, 没有海岸线时岸边会糊成一片.
    颜色按 (高程 m, 十六进制) 给出, 便于按数据调整.
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
    ]

    def u(elev: float) -> float:
        return (elev - vmin) / (vmax - vmin)

    anchors = [(u(e), color) for e, color in sea] + [(u(e), color) for e, color in land]
    return mcolors.LinearSegmentedColormap.from_list("ukraine_relief", anchors, N=2048)


ELEV_CMAP = make_relief_cmap(ELEV_VMIN, ELEV_VMAX)

# 海陆底色(只在 ETOPO 子集边缘露出来时可见, 与 ELEV_CMAP 两端的颜色一致).
BASE_OCEAN_COLOR = "#a2d0ee"
BASE_LAND_COLOR = "#dce4a2"

# 图面配色: 每种边界一个固定颜色, 避免读图歧义.
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
# 山系文字的深棕、境外参照文字的灰色不再作为「标注颜色」常量存在(参照点与填色的
# 几何颜色 COLOR_REFERENCE 仍保留).
COLOR_REFERENCE = "#555555"  # 境外参照(德左/罗斯托夫): 中性灰, 不参与主题配色
# 境外参照区(德左)填色透明度: 比 2014 控制区(0.22~0.24)略深, 因为它没有
# 控制线/边界线可依靠, 只有这一层填色; 但也不能更深 —— 灰色压过地形会让人
# 以为这是本图的主题图层. 0.30 在黄色低地上是明显的灰绿色, 地形晕渲仍可辨.
COLOR_REFERENCE_FILL_ALPHA = 0.30

# 1991 国界剪掉沿海段的缓冲半径(度). GADM 的国家面边界沿岸线与 Natural
# Earth 海岸线是两套数据, 偏差中位约 0.5 km、个别沙嘴可达 8 km; 0.06° 在
# 48°N 处约纬向 6.7 km / 经向 4.5 km, 覆盖绝大多数岸段. 缓冲是经纬度下的
# 圆(投影后是椭圆), 漏掉的岸段由 LAND_KEEP_DEG 那一步兜底. 剪剩的碎段
# (两条线小夹角相交的接头)按 3 km 丢掉.
COAST_CLIP_DEG = 0.06
COAST_CLIP_MIN_LEN = 0.03

# 1991 国界只保留"与邻国接壤"的陆上段: 边界线离任何外国陆地都超过
# LAND_KEEP_DEG 的段落, 说明它一侧是水(海岸、利曼/潟湖岸、狭长沙嘴), 剪掉.
# 这一步是给海岸线缓冲兜底的: NE 10m 海岸线没有画出的岸段(例如克里米亚
# 西部的利曼、亚速海的狭长沙嘴), 岸线缓冲剪不到, 会在图上留下孤立的红线.
# 实测真正的陆上国界离外国陆地最远约 0.07°(NE 与 GADM 在摩尔多瓦北端一带
# 的偏差), 而那些残段都在 1.4° 以上, 取 0.15° 两边都留足余量.
LAND_KEEP_DEG = 0.15
# 克里米亚半岛范围: NE 的 admin_0_countries 把克里米亚划给俄罗斯, 统计
# "外国陆地"时必须把这部分剔掉, 否则克里米亚的利曼/沙嘴岸段会被当成接壤.
CRIMEA_BOX = (32.0, 44.3, 37.0, 46.5)

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
# 山系标注: (经度, 纬度, 文字). 旧版后四个数是山脊走向参考点, 用来在投影平面里
# 求文字旋转角; 旋转改由前端处理(默认 0), 生成端不再存这些参考点.
MOUNTAIN_LABELS = [
    # 乌克兰喀尔巴阡山: 位置压在乔尔诺霍拉一带的山体上.
    (24.32, 48.42, "喀尔巴阡山"),
    # 大高加索山西端: 在图幅右下角(索契以东).
    (40.42, 43.86, "高加索山"),
]
# 河流名称: (经度, 纬度, 文字). 位置都放在河岸陆地上而不是水面上: 这张图要表达
# 第聂伯河"河宽沿程变化", 河名压在水面上会用描边遮掉一段水面; 顿河同理不压河道线.
# 旧版的河道走向参考点只服务旋转, 已随前端接管旋转而删除.
RIVER_LABELS = [
    # 第聂伯河: 克列缅丘格水库东北岸的陆地, 与水面留出几像素间隙.
    (33.30, 49.60, "第聂伯河"),
    # 顿河: 下游罗斯托夫段北岸陆地. 这一段在图幅内够长, 且离顿巴斯最近.
    (40.15, 47.42, "顿河"),
]
# 城市: (经度, 纬度, 名称, 是否首都, 经度偏移, 纬度偏移, 对齐方式).
# 偏移都在 0.1~0.3°(约 10~25 km)量级, 只用于让文字离开边界线与其它标注.
# 赫尔松城正好卡在第聂伯河(东)、第聂伯-布格河口(西南)与米科拉伊夫州界
# (西北)之间, 横向 0.6° 宽的标签放不下: 往东压河, 往西压河口; 所以放在城点
# 西北的陆地上并右对齐, 只跨过州界, 不压任何水面.
# 顿涅茨克/卢甘斯克两城的标签单独调整过: 两个"人民共和国"的名称移到其宣称
# 全境中心后, 会分别落在顿涅茨克城点与卢甘斯克城点附近, 城名必须让开;
# 同时城名原本会压住 2014 接触线(顿涅茨克)或压住共和国名称(卢甘斯克).
# 符号与城名分开: 城市点在本脚本画(见 add_place_markers), 城名只以 geo.labels
# 交给前端(见 collect_labels).
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

# 境外参照城市: 灰点 + 灰字, 与乌克兰境内城市(白底黑边 + 黑色城名)区分.
# 为什么单独列一张表: 这些城市不在乌克兰境内, 不能并进 CITIES —— 否则读图
# 会把它们当成乌克兰城市(城市样式在本图里默认"位于乌克兰").
# (经度, 纬度, 名称, 名称经度偏移, 名称纬度偏移).
# 顿河畔罗斯托夫(39.72E / 47.23N)是俄南部军区司令部驻地、顿河下游交通枢纽,
# 在顿巴斯以东约 100 km. 城点取在顿河右岸的城区, 但 NE 10m 的河道线在这个
# 纬度上几乎穿过城点, 白心灰圈的城点会压住一小段河道线 —— 城市符号盖住河道
# 是常见画法, 不影响判读. 城名放到城点东南(下、右各让一点)的空旷草原上:
# 北侧是顿河河道与已经标好的"顿河"河名, 西侧是塔甘罗格湾与顿河三角洲, 只有
# 东南方向是空白.
REFERENCE_CITIES = [
    (39.72, 47.23, "顿河畔罗斯托夫", 0.06, -0.13),
]
# 境外参照区域: 德左是摩尔多瓦境内德涅斯特河东岸的狭长地带(俄方军事存在),
# 紧邻敖德萨州; 地带宽度只有 0.1~0.5°(最窄约 10 km), 正式名称"德涅斯特河沿岸
# 摩尔达维亚共和国"共 15 字, 最长一行 8 字要 1.17° 宽, 塞不进去, 硬放会用白
# 描边把 1991 国界(红线)和德涅斯特河(蓝线)一起盖掉. 所以名称分两行放在地带
# 东侧敖德萨州的空地上(30.30E / 47.14N).
# (文字经度, 文字纬度, 文字, 字号, 指引线起点经度, 起点纬度, 终点经度, 终点纬度).
# 后四个数是旧图那条"从文字块左缘水平指回地带内部"的指引线端点: 契约 v2 的
# labels 仍没有 leader 字段, 指引线暂不画(端点保留在数据表里, 等前端支持再启用),
# 本脚本只登记名字.
# 指引线端点为什么在 29.42E: 47.14°N 处地带西缘(德涅斯特河)约 29.29E、东缘
# (国界)约 29.58E, 29.42E 离填色边界最近也有 0.13°(约 26 px), 端点小灰点不会
# 碰到填色边缘.
REFERENCE_REGIONS = [
    (30.30, 47.14, "德涅斯特河沿岸\n摩尔达维亚共和国", 7.0, 29.72, 47.14, 29.42, 47.14),
]

# 图标题: 第一行点题, 第二行交代地形、投影与参数; 前端把 title/subtitle 渲染成
# 标题块, 本脚本只登记文本(见 collect_suggestions).
TITLE = "乌克兰全图：1991 / 2014 / 2022 年边界"
SUBTITLE = "NOAA ETOPO 2022 地形 | 兰勃特等角圆锥投影（中央经线 31°E，标准纬线 45°N / 52°N）"

# 右栏口径说明: 旧图是一整块 fig.text 折行文案, 这里拆成一行一个字符串, 前端按行
# 排版; 内容(注 1~注 5)与旧图逐字一致.
NOTES = [
    "注 1：2014 年顿巴斯接触线以 OCHA 2021 年 GCA/NGCA 界线近似",
    "（明斯克协议线，2015 年后基本稳定），位置误差约 1–2 km。",
    "注 2：2022 年边界为俄方 2022-09 单方面宣称的赫尔松州、扎波罗热州、",
    "顿涅茨克人民共和国、卢甘斯克人民共和国全境，并非实际控制线。",
    "注 3：卢甘斯克、顿涅茨克两「人民共和国」于 2014 年宣布，",
    "名称标注在各自宣称全境范围内（顿涅茨克形心被城点与接触线占据，",
    "名称向北让开）；实际控制范围见蓝色填充与接触线。",
    "哈尔科夫人民共和国只有 2014 年的宣称，图中按其宣称范围",
    "(哈尔科夫州)画出，未实际控制。",
    "注 4：哈尔科夫州界（橙）南段与 2022 年宣称边界（紫）完全重合，",
    "重合段只画紫线；紫/橙线与 1991 国界重合处只画红色 1991 线。",
    "1991 国界只画陆上段；海岸线不单独画，",
    "海陆界线由地形配色在 0 m 处的跳变表达。",
    "注 5：德涅斯特河沿岸摩尔达维亚共和国（德左）位于摩尔多瓦境内",
    "德涅斯特河东岸，1990 年单方面宣布独立、未获国际承认，",
    "俄方有军事存在；灰色填色与灰字仅为位置参照，不表示乌方立场。",
]

# 数据来源: 放画面底部, 只作为 suggestions.source 交给前端.
SOURCE = (
    "地形: NOAA NCEI ETOPO 2022（15″） | 边界: GADM 4.1 · OCHA/HDX 2021 HNO GCA-NGCA · "
    "Natural Earth 10m | 水系: OpenStreetMap（ODbL）· Natural Earth 10m | "
    "投影: Lambert Conformal Conic"
)

OUT_SVG = ROOT / "ukraine_borders_1991_2014_2022_lambert_conformal.svg"

# 输出数据文件(由 download_data.py 生成).
OBLASTS_PATH = DATA_DIR / "ukraine_oblasts.geojson"
BORDER_1991_PATH = DATA_DIR / "ukraine_1991.geojson"
CRIMEA_LINE_PATH = DATA_DIR / "crimea_2014_line.geojson"
OCCUPIED_2014_PATH = DATA_DIR / "occupied_2014.geojson"
CONTACT_2014_PATH = DATA_DIR / "contact_line_2014.geojson"
CLAIMED_2022_PATH = DATA_DIR / "claimed_2022.geojson"
# 德左区域面: 由 download_data.py 用 OSM 的 PMR 边界面按"德涅斯特河心线 +
# 1991 国界"裁切得到(见 build_transnistria); 只用于灰色参照填色, 不参与任何
# 边界口径. 西缘与下面 DNIESTER_RIVER_PATH 是同一条几何, 所以填色不会与河错位.
TRANSNISTRIA_PATH = DATA_DIR / "transnistria.geojson"
DNIEPER_RIVER_PATH = DATA_DIR / "dnieper_river_osm.geojson"
DNIEPER_WATER_PATH = DATA_DIR / "dnieper_water_osm.geojson"
# 德涅斯特河中心线(OSM): 用来替代 NE 10m 的同名河. NE 版本在德左一段平均
# ~1 km 一个顶点, 而德左参照面的西缘就压在这条河上, 两者必须同源同精度.
DNIESTER_RIVER_PATH = DATA_DIR / "dniester_river_osm.geojson"
# 南布格河/顿河中心线: NE 10m 在河口前收笔, download_data.py 用 OSM 补了下游段,
# 并与 NE 上段在接缝处拼成一条线(文件里含 NE + OSM 两段, 属性 replaces_ne_id
# 标出被替换的 NE 要素).
RIVER_EXTENSION_PATHS = (
    DATA_DIR / "southern_bug_river_osm.geojson",
    DATA_DIR / "don_river_osm.geojson",
)
COUNTRY_DIR = DATA_DIR / "ne_10m_admin_0_countries"


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


def load_reference_region():
    """读取德左参照区域面(OSM PMR 边界, 按德涅斯特河心线与 1991 国界裁切).

    单独一个函数而不是并进 load_vectors: 这张面不参与任何边界口径计算,
    只用来填一层灰色; 缺文件时直接报错(数据由 download_data.py 准备),
    避免悄悄少一个图层. 面的西缘与 DNIESTER_RIVER_PATH 是同一条几何,
    所以填色边缘与蓝线严格重合.
    """
    region = gpd.read_file(_require(TRANSNISTRIA_PATH)).to_crs("EPSG:4326")
    return unary_union(list(region.geometry))


def load_dnieper() -> tuple:
    """读取第聂伯河干流中心线与梯级水库水面(由 download_data.py 从 OSM 派生).

    干流与水库分开存: 干流是线, 水库是面, 绘图时用不同样式, 且水面要盖住
    穿过水库的那段中心线(水面内不该再看到河道线).
    """
    river = gpd.read_file(_require(DNIEPER_RIVER_PATH)).to_crs("EPSG:4326")
    water = gpd.read_file(_require(DNIEPER_WATER_PATH)).to_crs("EPSG:4326")
    return river.geometry.iloc[0], water.geometry.iloc[0]


def load_dniester():
    """读取德涅斯特河干流中心线(由 download_data.py 从 OSM main_stream 派生).

    单独读、单独画的原因: NE 10m 河网里那条同名河已被剔除, 否则同一条河会出现
    两条位置略有差异的线; 而德左参照面的西缘用的正是这条 OSM 线, 绘图也用同
    一条, 填色边缘与蓝线才能严格重合.
    """
    gdf = gpd.read_file(_require(DNIESTER_RIVER_PATH)).to_crs("EPSG:4326")
    return unary_union(list(gdf.geometry))


def load_river_extensions() -> tuple[list, set[int]] | None:
    """读取南布格河/顿河中心线(NE 上段 + OSM 下段拼好的整条线).

    返回 ``(线几何列表, 被替换的 NE 要素 id 集合)``. 为什么要 id: 这些文件里
    的线已经包含 NE 上段, 所以 NE 图层里对应的那条下游要素不能再画, 否则同
    一条河会出现两条位置略有差异的线(与第聂伯河从 NE 图层剔除同理).
    文件缺失时返回 None: 用旧数据仍能出图, 只是这两条河又回到"河口前断线".
    """
    lines: list = []
    replaced: set[int] = set()
    for path in RIVER_EXTENSION_PATHS:
        if not path.exists():
            print(f"警告: 缺少河流补段 {path.name}, 该河下游仍按 NE 原数据绘制")
            continue
        gdf = gpd.read_file(path).to_crs("EPSG:4326")
        lines.extend(list(gdf.geometry))
        replaced.update(int(ne_id) for ne_id in gdf["replaces_ne_id"])
    if not lines:
        return None
    return lines, replaced


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


def draw_reference_region(ax: plt.Axes, region) -> None:
    """境外参照区域(德左)填色: 中性灰、无描边, 只表示"这里是德左".

    为什么只填色、不画边界:
        德左西缘是德涅斯特河(OSM 中心线, 蓝色细线), 东缘是摩尔多瓦-乌克兰
        1991 国界(红色半透明粗线). 这两条线已经画好, 而且区域面就是按它们
        裁出来的 —— 填色边缘与蓝线/红线是同一份几何, 再描一条灰边只会与
        蓝河/红线挨在一起形成双线, 没有任何新增信息. 只填色时, 边界由已有
        线条"免费"给出, 读图者看到的是"河与国界之间这块地"被涂灰, 而不是
        一条新的边界线.
    为什么用灰色而不是主题色:
        红色是 1991 国界, 蓝色是 2014 控制, 紫/橙是宣称; 德左不属于其中
        任何一种, 上任何主题色都会被读成"俄方控制区/宣称区". 灰色与本图
        其他境外参照(灰点)同一套语汇.
    为什么 zorder 放在 2.15:
        比地形(1)高、比一般河流(2.2)/州界(3.1)/主题边界(5~7)低: 德涅斯特河
        与 1991 国界要压在填色之上, 否则河流线/红线会被灰色蒙住一截.
    """
    add_fill_layer(
        ax, [region], color=COLOR_REFERENCE, alpha=COLOR_REFERENCE_FILL_ALPHA, zorder=2.15
    )


def clip_coast_segments(line, coastline):
    """剪掉边界线里贴着海岸线的段落: 1991 国界"只画陆上段"的第一步.

    为什么必须剪: GADM 的州级面和国家面都是沿海岸线闭合的, 直接画出来会在
    黑海/亚速海岸上多出一圈灰色州界线和一条红色国界线. 图上又不画海岸线
    (设计理由见 docs/maps/ukraine.md 的设计要点 9), 所以岸边的线一律剪掉, 岸线只由地形配色在 0 m 处的
    跳变表达.

    缓冲半径 COAST_CLIP_DEG 用来吸收 GADM 岸线与 NE 海岸线的偏差(中位约
    0.5 km, 个别沙嘴可达 8 km); 剪出的碎段按 COAST_CLIP_MIN_LEN 丢掉.
    但 NE 海岸线本身会漏画一些利曼/潟湖岸和狭长沙嘴, 这些岸段这一步剪不到,
    要由 load_neighbor_land 那一步兜底(见 main). 岸线缓存缺失时原样返回,
    图不会因为少一层数据而残.
    """
    if coastline is None:
        return line
    return cut(
        line,
        overlap_mask([coastline], COAST_CLIP_DEG),
        min_length_deg=COAST_CLIP_MIN_LEN,
    )


def load_neighbor_land(world, view):
    """图幅内除乌克兰以外的陆地; NE 错划给俄罗斯的克里米亚也剔掉.

    用途: 1991 国界只画"与邻国接壤"的陆上段 —— 边界线离外国陆地足够近
    (<= LAND_KEEP_DEG)才算国界. 沿岸、利曼/潟湖岸、狭长沙嘴一侧是水, 离
    外国陆地都很远, 即使 NE 海岸线没覆盖到, 也会在 main 里被这一步剪掉.

    只取图幅附近的国家再合并: 全球国家面合并 + 缓冲很慢, 而图幅外的陆地
    对这条边界没有意义.
    """
    if world is None:
        return None
    name_col = "ADMIN" if "ADMIN" in world.columns else "NAME"
    v = view.bounds
    near = world.cx[v[0]:v[2], v[1]:v[3]]
    foreign = unary_union(
        [geom for name, geom in zip(near[name_col], near.geometry) if name != "Ukraine"]
    )
    return foreign.intersection(view).difference(box(*CRIMEA_BOX))


def extend_border_to_sea(border_land, full_boundary, lat, lon, z):
    """把剪断的陆上国界端头沿原边界一直补到海边, 国界不在离岸几公里处收笔.

    为什么需要: 剪掉沿海段后, 陆地国界的两端(顿巴斯东缘的亚速海岸、多瑙河口
    的黑海岸)停在离岸约一个 COAST_CLIP_DEG(5~7 km)的内陆, 图上看起来国界
    没画到海. 这里沿原始 GADM 边界(GADM 的乌克兰-罗马尼亚国界沿多瑙河走,
    所以多瑙河口这一段必须沿河, 不能拉直线)朝海的方向走, 走到 ETOPO 高程
    连续几个采样点都在水面以下为止, 再把这一段补回红线.

    为什么用 ETOPO 水面判断: 图上不画海岸线, 海陆界线就是配色在 0 m 处的
    跳变, "靠海"等于走到这条色界. NE 海岸线在这两处(多瑙河三角洲、亚速海
    沙嘴一带)与 GADM 岸线/ETOPO 陆海边界差得比较远, 拿它当终点会提前停下.

    sustain 的 5 个采样点(约 1.1 km)用来跳过三角洲里的窄河道: 河道也是
    z<0, 但连续 5 个点都在水里才是真正到了海.
    """
    if border_land is None or full_boundary is None:
        return border_land
    ring = full_boundary
    if ring.geom_type == "MultiLineString":
        ring = max(ring.geoms, key=lambda g: g.length)
    ring_len = ring.length
    step = 0.002  # 约 220 m
    sustain = 5
    max_steps = int(0.16 / step)  # 最远 0.16°(约 12~18 km), 防止跑飞

    def is_water(x, y):
        i = int(np.argmin(np.abs(lat - y)))
        j = int(np.argmin(np.abs(lon - x)))
        return z[i, j] < 0

    extensions = []
    for part in getattr(border_land, "geoms", [border_land]):
        if part.geom_type != "LineString" or part.is_closed:
            continue
        for end in (part.coords[0], part.coords[-1]):
            p_end = Point(end)
            t0 = ring.project(p_end)
            # 沿原始边界向剪掉的那侧走: 走 1 km 后离现存陆上国界更远的一侧,
            # 就是被剪掉(通向海)的方向.
            d_plus = ring.interpolate((t0 + 0.01) % ring_len).distance(border_land)
            d_minus = ring.interpolate((t0 - 0.01) % ring_len).distance(border_land)
            fwd = 1.0 if d_plus >= d_minus else -1.0
            samples = [p_end]
            found = False
            for k in range(1, max_steps + 1):
                samples.append(ring.interpolate((t0 + fwd * k * step) % ring_len))
                if len(samples) > sustain and all(
                    is_water(q.x, q.y) for q in samples[-sustain:]
                ):
                    found = True
                    break
            if found:
                # 只保留到连续水面的第一个采样点: 端点落进海里不到一个采样步长,
                # 不会在蓝色水面上拖出一条长红线.
                cut_at = len(samples) - sustain
                extensions.append(
                    LineString([(p.x, p.y) for p in samples[: cut_at + 1]])
                )
    if not extensions:
        return border_land
    return unary_union([border_land, *extensions])


def draw_basemap(
    ax: plt.Axes,
    world,
    *,
    ukraine_geom,
    oblast_lines,
    rivers,
    river_extensions,
    dniester_river,
    dnieper_river,
    dnieper_water,
    neighbor_borders,
) -> None:
    """地形 + 水系 + 邻国国界 + 乌克兰州界背景线.

    海岸线不画: 海陆界线由 ETOPO 配色在 0 m 处的跳变表达(见
    make_relief_cmap), 岸边一条线都没有. 1991 国界与州界同样只画陆上段
    (国界见 draw_borders, 州界在 main 里用海岸蒙版剪好), 所以黑海/亚速海
    岸上、以及 NE 海岸线漏画的利曼/沙嘴岸边, 都不会出现国界线或州界线.

    第聂伯河单独处理: 先画中心线, 再用梯级水库的实际水面盖住穿过水库的那段
    中心线. 这样图上"上游窄河道、下游宽水库"的宽度变化是真实水面宽度, 而不是
    靠加粗同一根线来假装 —— 等宽线在这里会失真一个数量级(河道 0.2~0.5 km,
    水库 3~15 km).

    ``river_extensions`` 是南布格河/顿河的整条中心线(NE 上段 + OSM 下段拼好,
    见 download_data.py): 与一般河流同一图层、同一线型画, 这两条河的下游
    才不会在河口前断掉.

    ``dniester_river`` 是 OSM 的德涅斯特河中心线, 也并入一般河流图层画: NE 的
    同名要素已在 main 里剔除. 它与德左参照面共用同一条几何(填色西缘就压在这
    条线上), 所以蓝线与灰区边缘不会出现"两条平行线"或"灰区偏到河里/河外".
    """
    add_base_map(ax, world, ocean_color=BASE_OCEAN_COLOR, land_color=BASE_LAND_COLOR)

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
    # 乌克兰州界: 沿海段已在 main 里剪掉, 这里只画陆上段; 仍逐个州画
    # (相邻两州的公共边界会被画两遍, 叠出比单画更深的灰线, 效果与改前一致),
    # 只作背景参考, 不与主题边界争视觉层级.
    if oblast_lines:
        ax.add_geometries(
            oblast_lines,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=COLOR_OBLAST,
            linewidth=0.45,
            alpha=0.55,
            zorder=3.1,
        )
    # 一般河流放在州界之下、主题边界之上; 10m 河流在国界附近可能超出画框,
    # cartopy 会按画框裁剪. Dnieper/Dniester 已从这一层剔除(改用 OSM 干流);
    # 南布格河与顿河的补段(NE 上段 + OSM 下段)、德涅斯特河 OSM 线都与一般
    # 河流同色同宽一起画.
    river_geoms = list(rivers.geometry) if rivers is not None else []
    if river_extensions:
        river_geoms.extend(river_extensions)
    if dniester_river is not None:
        river_geoms.append(dniester_river)
    if river_geoms:
        ax.add_geometries(
            river_geoms,
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
    border_land,
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

    ``border_land`` 是已经剪掉沿海段的 1991 国界线(在 main 里先按海岸线
    缓冲带剪, 再剪掉离外国陆地太远的利曼/沙嘴残段): 红线只画陆上段, 沿海段
    一律不画 —— 海岸线图层也整个去掉了, 海陆界线由地形配色在 0 m 处的跳变
    表达(见 make_relief_cmap). 而上面两处"重合段"仍以完整的
    ``ukraine_geom.boundary`` 为参考 —— 紫/橙线的沿海段与完整国界重合,
    必须一并剪掉, 否则会沿黑海/亚速海岸画出一条紫色/橙色国界线, 正好是
    这张图要避免的.

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
    # 哈尔科夫州界的南段/东北段分别与 2022 宣称边界、1991 国界重合, 只画优先级更高的
    # 那条; 差集碎段由 overlap.cut 拼回连续折线, 剪空时跳过图层(理由见
    # docs/maps/ukraine.md 设计要点 6).
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
    # 2022 宣称四州的外边界: 与 1991 国界/海岸线重合的段落按优先级剪掉, 只保留紫线
    # 独有的段落; 与 2014 控制线重合的克里米亚地峡段先画紫线, 由后画的不透明蓝线盖住
    # (理由见 docs/maps/ukraine.md 设计要点 6).
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
    # 1991 年边界: 最外层、最粗、红色半透明实线, 不加白描边; 只画陆上段, 海陆界线
    # 由地形配色表达, border_land 为空时退回完整国界(理由见 docs/maps/ukraine.md
    # 设计要点 5 与 9).
    if border_land is not None:
        add_line_layer(
            ax,
            [border_land],
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


def add_place_markers(ax: plt.Axes) -> None:
    """城市点符号: 首都星形, 其余白心圆点; 境外参照点用灰圈白心.

    只画地理符号: 城名、境外狭长区域的名称与指引线都属于排版文字, 不在本脚本绘制,
    城名的落点/样式以 geo.labels 登记(见 collect_labels).
    """
    for lon, lat, _name, is_capital, _dx, _dy, _align in CITIES:
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
    for lon, lat, _name, _dx, _dy in REFERENCE_CITIES:
        ax.plot(
            lon, lat, marker="o", markersize=3.6,
            markerfacecolor="white", markeredgecolor=COLOR_REFERENCE, markeredgewidth=1.0,
            transform=ccrs.PlateCarree(), zorder=9.8,
        )


def add_gridlines(ax: plt.Axes) -> None:
    """经纬网: 只画网线, 不画刻度文字.

    线位置由 locator 固定; 刻度文字由前端排版, 因此 draw_labels=False,
    也不再设置 top/right/rotate 与刻度字号颜色.
    """
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=False,
        linewidth=0.5,
        color="gray",
        alpha=0.45,
        linestyle=":",
        zorder=4,
    )
    gl.xlocator = mticker.FixedLocator(np.arange(20, 45, 5))
    gl.ylocator = mticker.FixedLocator(np.arange(45, 55, 5))


# ============================
# geo.json 收集
# ============================
# 色标刻度: 旧图色标没设固定刻度, matplotlib 默认刻度落在 -2500~2500 范围内的
# 就是整千的这五个(超出范围的 ±3000 不显示).
RELIEF_TICKS = (-2000, -1000, 0, 1000, 2000)

# 经纬网样式: 与 add_gridlines 画出的线同源(gray=#808080 / 0.5 pt / 点线 /
# alpha 0.45); 点线在 0.5 pt 线宽下的 dash 为 0.5 pt 实 + 0.825 pt 虚
# (matplotlib (1, 1.65) x 线宽).
GRATICULE_STYLE = {
    "stroke": "#808080",
    "width_pt": 0.5,
    "dash": [0.5, 0.825],
    "opacity": 0.45,
}


def collect_labels(doc: GeoDoc, ax: plt.Axes) -> None:
    """把旧成品上的 33 条地名整理成 geo.labels(role/位置/字号/锚点), 不画文字、不存样式.

    顺序按旧图 zorder 升序登记(前端 scene 按 order 叠放): 国名/海名(9.0)、
    山系(9.2)、河名(9.4)、主题区域名与境外参照(9.5)、城市(9.9). 颜色/斜体/描边/
    旋转都改由前端 role 表决定, 这里只给落点、字号与语义角色.
    """
    # 邻国名称.
    for lon, lat, text in COUNTRY_LABELS:
        doc.add_label(ax, lon, lat, text, role="country", font_size_pt=12.5)

    # 海域名称.
    for lon, lat, text in SEA_LABELS:
        doc.add_label(ax, lon, lat, text, role="sea", font_size_pt=11.5)

    # 邻国山系.
    for lon, lat, text in MOUNTAIN_LABELS:
        doc.add_label(ax, lon, lat, text, role="highland", font_size_pt=11.0)

    # 干流名称: 位置在岸上, 不压水面(理由见 RIVER_LABELS).
    for lon, lat, text in RIVER_LABELS:
        doc.add_label(ax, lon, lat, text, role="river", name=text, font_size_pt=10.5)

    # 2014 年宣布的"人民共和国": 卢甘斯克/顿涅茨克是实际控制区(蓝), 哈尔科夫只有
    # 宣称(橙), 两者的强调色由 role 区分(accent-3 / accent-4). 文字用两行, 避免
    # 横跨边界线. 落点按"宣称全境"取中心, 不再挤在 2014 实际控制区(蓝色填充)里:
    #   - 卢甘斯克州宣称全境(约 37.85~40.22E, 47.82~50.09N)的形心在 39.03E/48.98N,
    #     图上是州中部的开阔地; 再向北 0.03° 是为了让文字描边与 2014 接触线北缘的
    #     尖峰(48.78N 附近)留出间隙, 相对形心只偏 3 km, 可忽略;
    #   - 顿涅茨克州宣称全境的形心(37.67E/48.05N)恰好落在顿涅茨克城点上, 2014
    #     接触线又绕城而过, 所以整体北移到接触线以北的州内空处(37.70E/48.65N),
    #     仍在全境中轴线上, 只向北让开约 0.6°(约 67 km) —— 这是不遮接触线、不遮
    #     城点、不遮州界的最小让步.
    doc.add_label(
        ax, 39.03, 49.02, "卢甘斯克\n人民共和国",
        role="area-accent-3", id_kind="republic", name="卢甘斯克人民共和国",
        font_size_pt=8.8,
    )
    doc.add_label(
        ax, 37.70, 48.65, "顿涅茨克\n人民共和国",
        role="area-accent-3", id_kind="republic", name="顿涅茨克人民共和国",
        font_size_pt=8.8,
    )
    # 哈尔科夫: 纬度比州界折角高一截 —— 第二行的文字描边原本正压在 2022 宣称边界
    # 由南北向折向西南的那一段上, 上移后折角完整露出.
    doc.add_label(
        ax, 36.80, 49.50, "哈尔科夫人民共和国",
        role="area-accent-4", id_kind="republic", name="哈尔科夫人民共和国",
        font_size_pt=9.4,
    )

    # 2022 年俄方宣称的两个州(顿/卢两州已由上面的"人民共和国"标注覆盖): 位置都
    # 放在远离第聂伯河/水库水面的州内陆地 —— 扎波罗热州在中东部草原, 赫尔松州在
    # 锡瓦什以北的左岸草原, 避免文字压住河宽变化的重点区域.
    doc.add_label(
        ax, 34.11, 46.52, "赫尔松州\n（俄宣称全境）",
        role="area-accent-1", id_kind="region", name="赫尔松州",
        font_size_pt=9.4,
    )
    doc.add_label(
        ax, 35.65, 47.08, "扎波罗热州\n（俄宣称全境）",
        role="area-accent-1", id_kind="region", name="扎波罗热州",
        font_size_pt=9.4,
    )
    doc.add_label(
        ax, 34.55, 45.40, "克里米亚\n（2014年俄实际控制）",
        role="area-accent-3", id_kind="region", name="克里米亚",
        font_size_pt=9.6,
    )

    # 境外参照城市: 字号比境内城市(9.0)小一档, 只作定位参照(role=city-reference).
    for lon, lat, name, dx, dy in REFERENCE_CITIES:
        doc.add_label(
            ax, lon + dx, lat + dy, name,
            role="city-reference", name=name, font_size_pt=8.4, ha="left",
        )

    # 境外狭长区域名: 旧图用一条细指引线从文字块左缘指回德左地带; 契约 v2 的
    # labels 仍没有 leader 字段, 指引线暂不画(端点坐标留在 REFERENCE_REGIONS),
    # 只登记名字; 样式由 role=area-muted 决定.
    for lon, lat, text, size, _x1, _y1, _x2, _y2 in REFERENCE_REGIONS:
        doc.add_label(
            ax, lon, lat, text,
            role="area-muted", id_kind="region", name="".join(text.split()),
            font_size_pt=size,
        )

    # 城市: 文字跟着点位偏移; 首都与一般城市同字号, 只靠符号区分.
    for lon, lat, name, _is_capital, dx, dy, align in CITIES:
        doc.add_label(
            ax, lon + dx, lat + dy, name,
            role="city", name=name, font_size_pt=9.0, ha=align,
        )


def collect_graticule(doc: GeoDoc, ax: plt.Axes) -> None:
    """把经纬刻度(值/文字/与地图框边线的交点)登记进 geo; 网线已由 add_gridlines 画好.

    步长与 add_gridlines 的 FixedLocator 同源(经度 5°、纬度 5°), 旧图只标底边经度
    与左边纬度; 画框内落在整倍数上的刻度由 GeoDoc 反查边线交点.
    """
    doc.add_graticule(
        ax,
        tuple(EXTENT),
        lon_step=5.0,
        lat_step=5.0,
        lon_side="bottom",
        lat_side="left",
        style=GRATICULE_STYLE,
    )


def collect_legend(doc: GeoDoc) -> None:
    """图例数据: 5 条, 文案与线型/填色沿用旧图.

    多行标签的兼容写法: 图例条目的 label 约定是单行字符串, 这里把第二行直接并在
    label 末尾(括号串), 完整分行数组放 label_lines(图例条目的扩展字段, 前端不
    识别时忽略), 第二行不丢.
    2022 边界旧图是点划线(6, 2.0, 1.6, 2.0), legend.dash 只有 [实, 虚] 两项,
    这里简化成 [6, 2](点划的"点"留给前端样式表).
    """
    entries = [
        {
            "label": "1991 年国际承认边界（含克里米亚，仅陆上段）",
            "shape": "line",
            "stroke": COLOR_1991,
            "width_pt": 2.7,
            "opacity": COLOR_1991_ALPHA,
        },
        {
            "label": "2014 年实际控制线（克里米亚 · 顿巴斯接触线）",
            "shape": "line",
            "stroke": COLOR_2014,
            "width_pt": 2.1,
        },
        {
            # 旧图是 Patch(edgecolor="none"): 只填色、不描边.
            "label": "2014 年俄方实际控制区（示意填色）",
            "shape": "rect",
            "stroke": None,
            "width_pt": 0.0,
            "fill": COLOR_2014_FILL,
            "opacity": 0.24,
        },
        {
            "label": "2014 年宣布的「哈尔科夫人民共和国」（未实际控制）",
            "label_lines": ["2014 年宣布的「哈尔科夫人民共和国」", "（未实际控制）"],
            "shape": "line",
            "stroke": COLOR_KHARKIV,
            "width_pt": 2.0,
            "dash": [6.0, 3.0],
        },
        {
            "label": "2022 年俄方宣称四州全境边界（单方面宣称，非控制线）",
            "label_lines": ["2022 年俄方宣称四州全境边界", "（单方面宣称，非控制线）"],
            "shape": "line",
            "stroke": COLOR_2022,
            "width_pt": 2.1,
            "dash": [6.0, 2.0],
        },
    ]
    doc.set_legend("图 例", entries)


def collect_suggestions(doc: GeoDoc) -> None:
    """默认文案: 标题/副标题/右栏注/来源, 只给前端预填, 不参与底图合成."""
    doc.set_suggestions(
        {
            "title": TITLE,
            "subtitle": SUBTITLE,
            "notes": NOTES,
            "source": SOURCE,
            "legend_title": "图 例",
            "colorbar_title": "高程 / 水深",
        }
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
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="内嵌晕渲栅格的像素密度(dpi); 矢量部分与 dpi 无关, 默认 300",
    )
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
    transnistria = load_reference_region()
    print(f"德左参照区域: {transnistria.geom_type}, 范围 {np.round(transnistria.bounds, 2)}")
    dnieper_river, dnieper_water = load_dnieper()
    print(f"第聂伯河: 干流顶点 {len(dnieper_river.coords) if dnieper_river.geom_type == 'LineString' else '?'}, "
          f"水库水面 {dnieper_water.geom_type}")
    dniester_river = load_dniester()
    print(f"德涅斯特河: {dniester_river.geom_type}, "
          f"顶点 {sum(len(g.coords) for g in (dniester_river.geoms if hasattr(dniester_river, 'geoms') else [dniester_river]))}")
    river_extensions = load_river_extensions()
    extension_lines = river_extensions[0] if river_extensions is not None else None

    # 共享缓存里的 Natural Earth 10m 图层(缺失就跳过, 不联网下载).
    # 图幅外扩 1°: 画框边缘的要素不能被裁断, 裁剪图层时要把那一圈也带上.
    bbox = (EXTENT[0] - 1, EXTENT[2] - 1, EXTENT[1] + 1, EXTENT[3] + 1)
    view = box(*bbox)
    rivers = None
    rivers_path = shared_layer("10m", "physical", "rivers_lake_centerlines")
    if rivers_path is not None:
        rivers = gpd.read_file(rivers_path)
        rivers = rivers[rivers["scalerank"] <= 9]
        # 第聂伯河改由 OSM 干流 + 水库水面绘制, 德涅斯特河改由 OSM 干流绘制,
        # 两条河都从 NE 图层里剔除, 避免同一条河出现两条位置略有差异的线
        # (NE 与 OSM 中位数偏差: 第聂伯河约 0.8 km, 德涅斯特河约 0.3 km).
        # 德涅斯特河这条还关系到德左参照面的西缘: 填色边缘用的就是 OSM 线.
        rivers = rivers[~rivers["name_en"].fillna("").isin(["Dnieper", "Dniester"])]
        if river_extensions is not None:
            # 南布格河/顿河的下游补段文件里已经含 NE 上段, 对应 NE 要素同理剔除.
            rivers = rivers[~rivers["ne_id"].isin(river_extensions[1])]
        rivers = rivers.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    coastline = None
    coast_path = shared_layer("10m", "physical", "coastline")
    if coast_path is not None:
        # 岸线本身不画(海陆界线由配色表达), 这里只取图幅附近的一小段几何,
        # 用来给 1991 国界剪掉沿海段; 全球岸线整体缓冲既慢又没意义.
        coast = gpd.read_file(coast_path)
        coast = coast.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
        coastline = unary_union(list(coast.geometry)).intersection(view)
    neighbor_borders = None
    borders_path = shared_layer("10m", "cultural", "admin_0_boundary_lines_land")
    if borders_path is not None:
        neighbor_borders = unary_union(list(gpd.read_file(borders_path).geometry))

    # 1991 国界只画陆上段, 分两步剪:
    #   1) clip_coast_segments: 剪掉贴着海岸线的段落;
    #   2) 离外国陆地太远的残段: NE 海岸线没画出来的利曼/潟湖岸、狭长沙嘴
    #      第 1 步剪不到, 它们一侧是水, 离外国陆地都在 1.4° 以上, 这里清掉.
    # 剪完再把顿巴斯/多瑙河口这两个端头沿原边界补到海边(见 extend_border_to_sea),
    # 否则陆地国界会在离岸 5~7 km 的内陆收笔, 看起来没画到海.
    border_land = clip_coast_segments(ukraine_geom.boundary, coastline)
    neighbor_land = load_neighbor_land(world, view)
    if border_land is not None and neighbor_land is not None:
        border_land = cut(
            border_land,
            view.difference(neighbor_land.buffer(LAND_KEEP_DEG)),
            min_length_deg=COAST_CLIP_MIN_LEN,
        )
    border_land = extend_border_to_sea(border_land, ukraine_geom.boundary, lat, lon, z)

    # 州界: 沿海段与国界完全重合(同一个 GADM 源, 州级面溶解成国家面), 所以
    # 直接拿"国界被剪掉的那部分"当蒙版剪州界 —— 第 2 步清掉的利曼/沙嘴残段
    # 也不会在州界图层里留下灰色线. 仍按州逐个剪、逐个画, 相邻两州公共边界
    # 照旧叠两遍, 灰度与改前一致.
    if border_land is not None:
        coast_zone = overlap_mask([ukraine_geom.boundary.difference(border_land)], 0.003)
        oblast_lines = [
            line
            for line in (
                cut(g.boundary, coast_zone, min_length_deg=COAST_CLIP_MIN_LEN)
                for g in oblasts.geometry
            )
            if line is not None
        ]
    else:
        oblast_lines = [g.boundary for g in oblasts.geometry]

    # 画布比例按投影后画框的宽高比(约 1.41)定制, 避免地图上下留大片空白.
    fig = plt.figure(figsize=(20, 12.5), facecolor="white")
    ax = fig.add_axes([0.035, 0.045, 0.735, 0.90], projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    draw_basemap(
        ax, world,
        ukraine_geom=ukraine_geom,
        oblast_lines=oblast_lines,
        rivers=rivers,
        river_extensions=extension_lines,
        dniester_river=dniester_river,
        dnieper_river=dnieper_river,
        dnieper_water=dnieper_water,
        neighbor_borders=neighbor_borders,
    )

    # 晕渲 RGB 图: imshow 比 pcolormesh 快; regrid_shape 提到 3200, 否则
    # 在 300 dpi 下 30 弧秒的 ETOPO 会被 cartopy 重采样糊掉.
    relief, _, _ = make_relief(
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

    # 德左参照区域填色: zorder 2.15 在河流(2.2)与主题边界之下, 河流/国界保持
    # 在填色之上; 先画填色再画边界不影响层级, 但放在这里与其它图层顺序一致.
    draw_reference_region(ax, transnistria)

    draw_borders(
        ax,
        ukraine_geom=ukraine_geom,
        border_land=border_land,
        oblasts=oblasts,
        crimea_line=crimea_line,
        contact=contact,
        occupied=occupied,
        claimed=claimed,
    )
    add_place_markers(ax)
    add_gridlines(ax)

    # 注意: 不用 tight_layout / bbox_inches="tight".
    # 原因: 地图框的位置/尺寸由 figure_frame 量出并写进 geo.base, 底图只改根标签
    # 的 viewBox 来裁到地图框; tight_layout 会重排坐标区(底图与 geo 对不上),
    # bbox_inches="tight" 会引入第二套坐标系、把地图包围盒算错(项目里踩过这个坑).
    frame = figure_frame(fig, ax)
    doc = GeoDoc(frame)
    collect_labels(doc, ax)
    collect_graticule(doc, ax)
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
    collect_legend(doc)
    collect_suggestions(doc)
    # save_map 写裁到地图框的纯底图与同名 geo.json(miko 契约里的 base.svg + geo).
    svg_path, geo_path = save_map(fig, OUT_SVG, doc, dpi=args.dpi)
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
