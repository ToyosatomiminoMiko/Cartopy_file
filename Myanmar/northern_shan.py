#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Topographic map of Shan State's special/armed-group regions.

是什么: 以掸邦为中心绘制缅甸联邦第一特区、德昂邦、佤邦、掸邦东部第四特区及
周边的地形图, 并在第一特区内标出其前身"原果敢自治区"的范围; 只绘制地理要素,
不绘制任何文字/图例/色标/标题/刻度文字. 文字与版面由前端接管, 本脚本同时产出
同名 <stem>.geo.json(地图框/经纬刻度/初始标注候选/色标/图例/默认文案), 字段与
口径见 ``docs/reference/geo.md``.
完整说明(范围、南界取值理由、投影、果敢关系、国界处理)见
``docs/maps/northern-shan.md``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BOUNDARY_DIR = DATA_DIR / "ne_10m_admin_0_countries"
REGION_GEOJSON = DATA_DIR / "regions" / "shan_north_boundaries.geojson"
BORDER_GEOJSON = DATA_DIR / "regions" / "osm_country_borders.geojson"

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import cartopy.feature as cfeature  # 海岸线/河流等自然要素
import matplotlib.colors as mcolors  # 高程色带类型
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网刻度定位
import numpy as np  # 数组运算
from shapely.geometry import shape  # GeoJSON -> Shapely
from shapely.ops import unary_union  # 合并同类边界

import map_lib  # 与本目录共用的 ETOPO/晕渲/边界工具

# cartopy 底图缓存统一到仓库 data/cartopy, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy

# 区域/省界描边与国界重合时只保留国界: 用共享剪枝工具裁掉国界走廊.
from cartopy_file.overlap import cut

configure_cartopy()

# 底图 + geo.json 出图: save_map 同时写裁到地图框的 SVG 与同名 geo.json,
# 见 docs/reference/geo.md.
from cartopy_file.geo import (
    GeoDoc,
    figure_frame,
    relief_from_cmap,
    save_map,
)
from cartopy_file.output import apply_svg_output

# 产物统一为 SVG, 见 docs/reference/output.md.
apply_svg_output()
# 斜线填充的线宽: 默认 1.0 在成品尺寸下偏粗, 会把特区填充压成深色块.
plt.rcParams["hatch.linewidth"] = 0.45


# ============================
# 标签
# ============================
def label_slug(text: str) -> str:
    """把图上的区域名变成标签 id 里的净名: 去掉空白与括号.

    为什么需要: 数据里的区域名带 "(南)"、"(TNLA 控制)" 之类注记, 而 id 会进布局文件
    与 DOM 选择器, 不适合带空格或括号(理由见 docs/reference/geo.md 的 id 规则).
    """
    return "".join(ch for ch in text if not ch.isspace() and ch not in "()")


# ============================
# 配置
# ============================
# 画框: (min_lon, max_lon, min_lat, max_lat); 取值理由见 docs/maps/northern-shan.md.
EXTENT = (95.3, 101.5, 19.0, 24.75)

# 投影参数: 中央经线取掸邦中部, 标准纬线夹住画框南北界.
PROJECTION = ccrs.LambertConformal(
    central_longitude=98.4,
    central_latitude=22.0,
    standard_parallels=(20.0, 24.0),
)

# 数据未覆盖区域的底色(本图 ETOPO 已覆盖全部画框, 仅作兜底).
BASE_OCEAN_COLOR = "#cfe0ee"
BASE_LAND_COLOR = "#efe9cf"

# 高程配色与晕渲参数. 本区域最低约 0 m(河谷), 最高约 3440 m(高黎贡山余脉).
# 取 -1000~3000 m: 0 m 落在色带 1/4 处的绿色, 500 m 左右黄绿, 2000 m 棕色,
# 3000 m 以上用 extend 三角形收尾; 这样河谷不会像全国图(±5000 m)那样发白.
ELEV_VMIN, ELEV_VMAX = -1000, 3000
ELEV_CMAP = "terrain"
HILLSHADE_AZIMUTH = 315  # 西北来光, 符合制图惯例
HILLSHADE_ALTITUDE = 45
HILLSHADE_VERT_EXAG = 1.6  # 15 弧秒数据在 1:100 万级地图上起伏仍偏弱, 略作夸张

# 区域配色: 填充色 + 边界色. 透明度让下方地形仍可读.
# 德昂邦用绿色: 第一特区(紫)、佤邦(蓝)、四特(橙)已占三色, 绿色是
# 与三者色相距离最大、且不与环境色(山体晕渲)冲突的选择.
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

# 国界: 用 OSM admin_level=2 数据(精度与区域边界一致), 红色半透明实线.
# 半透明与 Ukraine 图一致: 让下面的地形与区域填色透出来, 国界不至于压死
# 与它重合的区域边界; 图例里的线段也带同样的 alpha.
BORDER_COLOR = "#c62828"
BORDER_ALPHA = 0.62
BORDER_WIDTH = 2.7
# 区域边界描边在国界两侧各裁掉这么宽(度)的走廊, 让重合段只由国界线表示.
# 0.001° 约 110 m, 远小于 300 dpi 下 2.7 pt 线宽对应的大约 1.9 km, 肉眼不可见.
BORDER_ZONE_DEG = 0.001

# 原果敢自治区(第一特区前身): 与第一特区同色系、明显加深的填充, 用嵌套色块
# 表示"含于第一特区辖区". 只填色、不描内边界, 以免粗线压住区内的河流;
# 不加第二种底纹的原因见 docs/maps/northern-shan.md.
KOKANG_SAZ_FILL = "#54278f"
KOKANG_SAZ_ALPHA = 0.32

# 城市标注: (经度, 纬度, 名称, 类型, 文字偏移经度, 文字偏移纬度).
# 类型: capital=特区首府(星形), major=区域中心城市(大方点), town=普通城镇(小圆点).
# 偏移是旧成品文字的落点, 现在只用来产出 geo.labels 的锚点, 不再画文字.
CITIES = [
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
]

# 大区域/邻国标注: (经度, 纬度, 文字, 字号, 颜色).
# 这些是旧成品画在图内的字, 现在只登记成 geo.labels(kind=area), 不再绘制.
REGION_LABELS = [
    (98.30, 23.72, "缅甸联邦第一特区", 13.5, "#4a1486"),
    (98.25, 23.08, "MNDAA 实控区\n(大致范围)", 9.5, "#4a1486"),
    (97.00, 23.34, "德昂邦", 14, "#005a32"),
    (97.00, 23.12, "(TNLA 控制)", 9.5, "#005a32"),
    (98.60, 24.00, "原果敢自治区", 9, "#3f007d"),
    (98.99, 22.60, "佤邦", 16, "#045a8d"),
    (99.79, 21.73, "掸邦东部\n第四特区", 10.0, "#a63603"),
]
# 邻国标注必须落在该国境内. 本画框里老挝的可见部分, 是中老国界以南、
# 湄公河(缅老国界)以东的那一块(约 19.4~21.2°N, 100.6~101.5°E).
# 旧值 101.33/21.55 放错: 该经度上中老国界只到 21.19°N(OSM), 国界以南才是老挝,
# 于是"老挝"两字落进了云南勐腊境内. 现取 101.25/20.45: 距最近国界约 80 km,
# 距画框东界 0.25°(约 26 km), 2 字居中也完整落在框内.
AREA_LABELS = [
    (99.05, 24.62, "中国 云南省", 13, "#444444"),
    (101.25, 20.45, "老挝", 12, "#444444"),
    (100.60, 19.35, "泰国", 12, "#444444"),
    (96.75, 23.78, "掸邦", 13, "#666666"),
    (95.72, 22.45, "曼德勒省", 11, "#666666"),
    (97.18, 19.32, "克耶邦", 11, "#666666"),
    (99.02, 20.30, "佤邦(南)", 13, "#045a8d"),
]
# 两条大江的强调线所对应的 Natural Earth name_en, 以及河名标注位置.
# 位置都放在河道东/西侧的空地上, 离河心线约 0.3°(30~40 km), 不压河道本身;
# 也避开了城市点、特区名和邻国名(见 CITIES / REGION_LABELS / AREA_LABELS).
MAIN_RIVERS = ("Irrawaddy", "Salween")
RIVER_LABELS = [
    (95.75, 22.90, "伊洛瓦底江"),
    (98.33, 21.55, "萨尔温江"),
]

# 地名光晕: 白描边保证文字压在地形/填色/河网上仍可读; 宽度交给前端 halo 字段,
# 前端按地图缩放比换算到纸面.
HALO = {"color": "#ffffff", "width_pt": 3.0}
HALO_RIVER = {"color": "#ffffff", "width_pt": 3.2}

# 图标题/副标题/注/来源: 旧版是画在图外的 figure 级文字, 现在拆成 geo.suggestions
# 的默认文案, 由前端建默认排版时填入, 不参与底图合成.
TITLE = "缅甸掸邦特区与地方武装控制区地形图（2026年10月）"
SUBTITLE = (
    "NOAA ETOPO 2022 | 边界: OpenStreetMap | 底图: Natural Earth 10m | "
    "兰勃特等角圆锥投影(中央经线 98.4°E)"
)
NOTES = [
    "注: 国界与区域边界同源 OSM, 重合段按国界样式绘制",
    "原果敢自治区为第一特区前身, 以同色系加深表示其含于第一特区",
    "MNDAA 实控区与第一特区辖区大体重合, 以斜线示意",
    "范围据 OSM 公开边界绘制, 仅供参考",
]
SOURCE = (
    "地形数据: NOAA NCEI ETOPO 2022(15 弧秒) | 边界: OpenStreetMap(ODbL, 2026-10) | "
    "海陆底图·河流: Natural Earth 10m | MNDAA=缅甸民族民主同盟军, TNLA=德昂民族解放军"
)

# 高程色标: 旧色标上的整千值(0~3000 m, 每 500 m 一格), 前端 colorbar 直接复用.
RELIEF_TICKS = (0, 500, 1000, 1500, 2000, 2500, 3000)

# 经纬网样式: 与 add_gridlines 画出的线同源(gray / 0.45pt / 实线 / 0.5 不透明度).
GRATICULE_STYLE = {
    "stroke": "#808080",
    "width_pt": 0.45,
    "dash": None,
    "opacity": 0.5,
}

# 输出路径.
OUT_SVG = ROOT / "northern_shan_topography_etopo2022_lambert_conformal.svg"


# ============================
# 数据读取
# ============================
def load_regions(path: Path) -> dict[str, list]:
    """读取 download_regions.py 缓存的 GeoJSON, 按图层分组返回 Shapely 几何.

    返回 {layer: [(properties, geometry), ...]}; layer 见 download_regions.py.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"未找到区域边界: {path}\n请先运行: python download_regions.py"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, list] = {}
    for feature in data["features"]:
        props = feature["properties"]
        grouped.setdefault(props["layer"], []).append(
            (props, shape(feature["geometry"]))
        )
    return grouped


def load_borders(path: Path):
    """读取 download_regions.py 缓存的国界折线, 合并成一个 MultiLineString."""
    if not path.exists():
        raise FileNotFoundError(
            f"未找到国界数据: {path}\n请先运行: python download_regions.py"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return unary_union([shape(feature["geometry"]) for feature in data["features"]])


def add_relief(ax: plt.Axes, etopo_path: Path) -> mcolors.Colormap:
    """读取高程并叠加晕渲地形, 返回高程色带(供 geo.relief 采样).

    色带是字符串 ELEV_CMAP 经 make_relief 解析出的同一个对象, 这样底图配色与
    前端色标用的是同一条色带, 不会出现两套 anchor.
    """
    lon, lat, z = map_lib.load_elevation(etopo_path)
    relief, _, cmap = map_lib.make_relief(
        z,
        lat,
        lon,
        vmin=ELEV_VMIN,
        vmax=ELEV_VMAX,
        cmap=ELEV_CMAP,
        azimuth=HILLSHADE_AZIMUTH,
        altitude=HILLSHADE_ALTITUDE,
        vert_exag=HILLSHADE_VERT_EXAG,
    )
    # regrid_shape 默认 750, 对 15 弧秒数据在 300 dpi 下会糊; 提到 3000.
    ax.imshow(
        relief,
        origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        regrid_shape=3000,
        interpolation="nearest",
        zorder=1,
    )
    return cmap


def add_context(ax: plt.Axes, border_line) -> None:
    """绘制国界、河流与湖泊, 作为区域色块下方的地理参照.

    国界用 OSM admin_level=2 折线, 与区域边界同源: 区域边界沿国界的那一段
    与这里的国界线完全重合(坐标级), 所以不会出现 Natural Earth 那种偏移.
    """
    ax.add_geometries(
        [border_line],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=BORDER_COLOR,
        linewidth=BORDER_WIDTH,
        alpha=BORDER_ALPHA,
        zorder=6.2,
    )
    # 河流/湖泊放在区域填充之上, 避免半透明色块把水系盖住.
    ax.add_feature(
        cfeature.RIVERS.with_scale("10m"),
        edgecolor="#1f78b4",
        linewidth=0.7,
        zorder=4,
    )
    ax.add_feature(
        cfeature.LAKES.with_scale("10m"),
        facecolor="#a6cee3",
        edgecolor="#1f78b4",
        linewidth=0.4,
        zorder=4,
    )


def add_main_rivers(ax: plt.Axes) -> None:
    """把伊洛瓦底江与萨尔温江从一般河流里强调出来.

    河流数据里这两条已经被拆成几段(NE 10m: Irrawaddy 干流 + Irrawaddy Delta,
    Salween 上游 Nu + 下游 Salween); 按 name_en 全部选出再画, 河线才从画框
    北缘一直连到南缘, 不会在 20.95°N 的分段点断掉. 先用浅色粗描边、再用深蓝
    细线, 与行政图里的强调方式一致; 一般河流仍是上面那条 0.7 pt 蓝线, 作为
    背景水系, 不抢这两条干流的层级.
    """
    rivers = map_lib.load_ne_layer("10m", "physical", "rivers_lake_centerlines")
    if rivers is None:
        print("警告: 缺少 Natural Earth 河流数据, 跳过干流强调.")
        return
    selected = rivers[rivers["name_en"].isin(MAIN_RIVERS)]
    if selected.empty:
        print("警告: 未找到伊洛瓦底江/萨尔温江, 跳过干流强调.")
        return
    geoms = [geom for geom in selected.geometry if geom is not None and not geom.is_empty]
    ax.add_geometries(
        geoms,
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="#e8f4ff",
        linewidth=4.2,
        zorder=4.2,
    )
    ax.add_geometries(
        geoms,
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="#1565c0",
        linewidth=1.9,
        zorder=4.3,
    )


def add_admin_context(ax: plt.Axes, regions: dict[str, list], border_zone) -> None:
    """绘制掸邦/曼德勒省/克耶邦边界, 让读者知道色块在行政区的哪个位置.

    这些省/邦界沿国界的那一段也要裁掉, 否则灰色虚线会叠在深红国界线上.
    """
    for _, geom in regions.get("context", []):
        edge = cut(geom.boundary, border_zone)
        if edge is None:
            continue
        ax.add_geometries(
            [edge],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor="#7f7f7f",
            linewidth=1.0,
            linestyle=(0, (6, 3)),
            zorder=5.5,
        )


def add_special_regions(ax: plt.Axes, regions: dict[str, list], border_zone) -> None:
    """按图层绘制各区域的填充、外边界与内部县界.

    另画出第一特区内的原果敢自治区(嵌套深紫填充), 表示包含关系.

    外边界先减去 border_zone(国界走廊)再画: 与国界重合的段由 add_context
    里的国界线负责, 这样区域边界不会在国界上再压一条区域颜色的线.
    """
    # 四个区域里第一特区最后画, 压在佤邦/四特/德昂邦之上.
    draw_order = ["wa", "sr4", "taang", "sr1"]
    for layer in draw_order:
        style = REGION_STYLES[layer]
        geom = unary_union([g for _, g in regions[layer]])
        ax.add_geometries(
            [geom],
            crs=ccrs.PlateCarree(),
            facecolor=style["fill"],
            edgecolor="none",
            alpha=style["alpha"],
            linewidth=0,
            zorder=2.5,
        )
        edge = cut(geom.boundary, border_zone)
        if edge is None:
            continue
        ax.add_geometries(
            [edge],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=style["edge"],
            linewidth=style["linewidth"],
            zorder=6.5,
        )

    # 原果敢自治区: 第一特区的前身, 范围含于第一特区. 只铺一层深紫填充
    # (压在第一特区浅紫填充之上、MNDAA 斜线之下); 不描内边界, 避免粗线
    # 把果敢境内的河流盖住.
    for _, geom in regions.get("kokang_saz", []):
        ax.add_geometries(
            [geom],
            crs=ccrs.PlateCarree(),
            facecolor=KOKANG_SAZ_FILL,
            edgecolor="none",
            alpha=KOKANG_SAZ_ALPHA,
            linewidth=0,
            zorder=2.7,
        )

    # MNDAA 实控区: 与第一特区辖区大体重合, 用斜线叠加表示"实际控制".
    # 说明: 2026 年公开报道与 OSM 边界显示实控区已基本覆盖特区辖区;
    # 若将来边界变化, 重跑 download_regions.py 即可.
    sr1_geom = unary_union([g for _, g in regions["sr1"]])
    ax.add_geometries(
        [sr1_geom],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=MNDAA_HATCH_COLOR,
        hatch=MNDAA_HATCH,
        alpha=0.35,
        linewidth=0,
        zorder=3.0,
    )

    # 内部县/特区界: 第一特区 1 市 4 县、佤邦 5 县 1 特区、四特 3 县.
    # 同样裁掉国界走廊, 避免白色虚线与深红国界线重叠.
    for layer in ("sr1_county", "wa_district", "sr4_county"):
        for _, geom in regions.get(layer, []):
            edge = cut(geom.boundary, border_zone)
            if edge is None:
                continue
            ax.add_geometries(
                [edge],
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=INTERNAL_EDGE_COLOR,
                linewidth=0.65,
                linestyle="--",
                alpha=0.85,
                zorder=6.0,
            )


# ============================
# 城市点
# ============================
def add_city_markers(ax: plt.Axes) -> None:
    """绘制城市点: 特区首府用星形, 区域中心城市用方点, 普通城镇用小圆点.

    城名不在这里画: 名称/落点/字号属于排版文字, 只进 geo.labels(见 collect_labels).
    """
    for lon, lat, _name, kind, _dx, _dy in CITIES:
        if kind == "capital":
            ax.plot(
                lon,
                lat,
                marker="*",
                markersize=14,
                markerfacecolor="#ffd200",
                markeredgecolor="black",
                markeredgewidth=0.8,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )
        elif kind == "major":
            ax.plot(
                lon,
                lat,
                marker="s",
                markersize=6,
                markerfacecolor="#ffd200",
                markeredgecolor="black",
                markeredgewidth=0.9,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )
        else:
            ax.plot(
                lon,
                lat,
                marker="o",
                markersize=3.8,
                markerfacecolor="white",
                markeredgecolor="black",
                markeredgewidth=0.8,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )


# ============================
# 经纬网
# ============================
def add_gridlines(ax: plt.Axes) -> None:
    """经纬网: 经度每 1°、纬度每 1°, 只画网线, 不画刻度文字.

    线位置只取画框内 1° 的整倍数(与 collect_graticule 的取点同源); 刻度文字
    由前端排版, 因此 draw_labels=False.
    """
    x0, x1, y0, y1 = EXTENT

    def ticks(lo: float, hi: float, step: float) -> np.ndarray:
        return np.arange(np.ceil(lo / step) * step, hi + 1e-9, step)

    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=False,
        linewidth=GRATICULE_STYLE["width_pt"],
        color=GRATICULE_STYLE["stroke"],
        alpha=GRATICULE_STYLE["opacity"],
        linestyle="-",
        zorder=7,
    )
    gl.xlocator = mticker.FixedLocator(ticks(x0, x1, 1))
    gl.ylocator = mticker.FixedLocator(ticks(y0, y1, 1))


# ============================
# geo.json 收集
# ============================
def collect_labels(doc: GeoDoc, ax: plt.Axes) -> None:
    """把旧成品图内的文字整理成 geo.labels(位置/字号/颜色/锚点/halo), 不画文字.

    顺序按旧图 zorder 升序登记(前端 scene 按 order 叠放): 邻国/省邦注记(8) →
    特区/区域名(9) → 河名(9.5) → 城市(11). id 沿用旧前缀: 邻国类用 area、
    特区/区域名用 region、河名 river、城名 city, 便于旧布局文件迁移.
    """
    # 邻国/省邦注: 旧图 label-area-<slug>.
    for lon, lat, text, size, color in AREA_LABELS:
        doc.add_label(
            ax, lon, lat, text,
            kind="area", id_kind="area", name=label_slug(text),
            font_size_pt=size, color=color, ha="center", va="center", halo=HALO,
        )

    # 特区/区域名: 旧图 label-region-<slug>; 契约 kind 枚举里没有 region, 归到 area.
    for lon, lat, text, size, color in REGION_LABELS:
        doc.add_label(
            ax, lon, lat, text,
            kind="area", id_kind="region", name=label_slug(text),
            font_size_pt=size, color=color, ha="center", va="center", halo=HALO,
        )

    # 两条大江的河名: 与干流同色, 用稍大的白描边, 压在彩色区域上也能读.
    for lon, lat, text in RIVER_LABELS:
        doc.add_label(
            ax, lon, lat, text,
            kind="river", name=text, font_size_pt=10.5, color="#1565c0",
            ha="center", va="center", halo=HALO_RIVER,
        )

    # 城市名: 位置跟着点位偏移; 字号按城市等级分两档, 普通城镇居中对齐.
    for lon, lat, name, kind, dx, dy in CITIES:
        doc.add_label(
            ax, lon + dx, lat + dy, name,
            kind="city", name=name,
            font_size_pt=9.0 if kind == "town" else 10.5, color="#000000",
            ha="center" if kind == "town" else "left", va="center", halo=HALO,
        )


def collect_graticule(doc: GeoDoc, ax: plt.Axes) -> None:
    """把经纬刻度(值/文字/与地图框边线的交点)登记进 geo; 网线已由 add_gridlines 画好."""
    doc.add_graticule(
        ax,
        EXTENT,
        lon_step=1.0,
        lat_step=1.0,
        lon_side="bottom",
        lat_side="left",
        style=GRATICULE_STYLE,
    )


def collect_relief(doc: GeoDoc, cmap: mcolors.Colormap) -> None:
    """登记高程色标: 与底图同一色带, 等距采 21 个 stop, 刻度取旧色标的整千值."""
    doc.set_relief(
        relief_from_cmap(
            cmap,
            title="高程",
            unit="m",
            vmin=ELEV_VMIN,
            vmax=ELEV_VMAX,
            ticks=RELIEF_TICKS,
        )
    )


def collect_legend(doc: GeoDoc) -> None:
    """把旧图手工构造的图例整理成 geo.legend(不画图例框).

    条目字段与旧图例的句柄一一对应: 区域/自治区为 rect(填充+描边)、线要素为
    line、首府为 point. label_lines 与 hatch 是契约 v2 的预留字段: 这里把旧图
    的图例文字按行给出, hatch 条目给出斜线图案, 前端将来升 v2 时不用再改数据.
    """
    entries = [
        {
            "label": "缅甸联邦第一特区(辖区)",
            "label_lines": ["缅甸联邦第一特区(辖区)"],
            "shape": "rect",
            "stroke": REGION_STYLES["sr1"]["edge"],
            "width_pt": 1.5,
            "fill": REGION_STYLES["sr1"]["fill"],
            "opacity": 0.6,
        },
        {
            "label": "原果敢自治区(2010–2023)",
            "label_lines": ["原果敢自治区(2010–2023)"],
            "shape": "rect",
            "stroke": None,
            "width_pt": 0.0,
            "fill": KOKANG_SAZ_FILL,
            "opacity": 0.8,
        },
        {
            "label": "MNDAA 实控区(大致)",
            "label_lines": ["MNDAA 实控区(大致)"],
            "shape": "rect",
            "stroke": MNDAA_HATCH_COLOR,
            "width_pt": 0.0,
            "fill": None,
            "opacity": 1.0,
            # 图例色块只有约 20 pt 宽, 图上 "///" 在这个尺寸下几乎看不出斜线,
            # 所以图例用更密的 "////"; 颜色仍与图上斜线同色.
            "hatch": "////",
        },
        {
            "label": "德昂邦(TNLA 控制)",
            "label_lines": ["德昂邦(TNLA 控制)"],
            "shape": "rect",
            "stroke": REGION_STYLES["taang"]["edge"],
            "width_pt": 1.5,
            "fill": REGION_STYLES["taang"]["fill"],
            "opacity": 0.6,
        },
        {
            "label": "佤邦",
            "label_lines": ["佤邦"],
            "shape": "rect",
            "stroke": REGION_STYLES["wa"]["edge"],
            "width_pt": 1.5,
            "fill": REGION_STYLES["wa"]["fill"],
            "opacity": 0.6,
        },
        {
            "label": "掸邦东部第四特区",
            "label_lines": ["掸邦东部第四特区"],
            "shape": "rect",
            "stroke": REGION_STYLES["sr4"]["edge"],
            "width_pt": 1.5,
            "fill": REGION_STYLES["sr4"]["fill"],
            "opacity": 0.6,
        },
        {
            "label": "国界",
            "label_lines": ["国界"],
            "shape": "line",
            "stroke": BORDER_COLOR,
            "width_pt": BORDER_WIDTH,
            "opacity": BORDER_ALPHA,
        },
        {
            "label": "省/邦界",
            "label_lines": ["省/邦界"],
            "shape": "line",
            "stroke": "#7f7f7f",
            "width_pt": 1.0,
            "dash": [6.0, 3.0],
        },
        {
            "label": "河流",
            "label_lines": ["河流"],
            "shape": "line",
            "stroke": "#1f78b4",
            "width_pt": 0.9,
        },
        {
            "label": "特区首府",
            "label_lines": ["特区首府"],
            "shape": "point",
            "stroke": "#000000",
            "width_pt": 1.0,
            "fill": "#ffd200",
            "marker": "star",
        },
    ]
    doc.set_legend("图例", entries)


def collect_suggestions(doc: GeoDoc) -> None:
    """默认文案: 标题/副标题/注/来源只给前端预填, 不参与底图合成.

    本图 7 条区域注记都在画框内(已进 geo.labels), 没有图外面积注记, 因此
    area_annotation 为空; legend_title/colorbar_title 与 collect_legend /
    collect_relief 的标题保持同一口径.
    """
    doc.set_suggestions(
        {
            "title": TITLE,
            "subtitle": SUBTITLE,
            "notes": list(NOTES),
            "source": SOURCE,
            "area_annotation": [],
            "legend_title": "图例",
            "colorbar_title": "高程",
        }
    )


# ============================
# 主流程
# ============================
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stride", type=int, default=None, help="指定 data/ 下的采样步长文件")
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="内嵌晕渲栅格的像素密度(dpi); 矢量部分与 dpi 无关, 默认 300",
    )
    parser.add_argument("--show", action="store_true", help="保存后弹出交互窗口")
    args = parser.parse_args()

    etopo_path = map_lib.find_etopo(DATA_DIR, "northern_shan", args.stride)
    if not etopo_path.exists():
        raise FileNotFoundError(
            f"未找到高程数据: {etopo_path}\n"
            "请先运行: python download_etopo.py --region northern_shan --stride 1"
        )
    regions = load_regions(REGION_GEOJSON)
    border_line = load_borders(BORDER_GEOJSON)
    # 国界走廊: 用来把区域/省界描边里与国界重合的段裁掉.
    border_zone = border_line.buffer(BORDER_ZONE_DEG, cap_style="flat", join_style="mitre")

    # 画布 16x15: 投影后画框约 653x636 km(宽高比 1.026), 轴区域与之匹配,
    # 避免 GeoAxes 为保持等比例而留下过大空白. 高度比旧图大, 因为南界下探了 2°.
    fig = plt.figure(figsize=(16, 15), facecolor="white")
    ax = fig.add_axes([0.045, 0.062, 0.80, 0.831], projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    # Natural Earth 数据只用来铺海陆底色; 国界改由 OSM 数据绘制.
    world = map_lib.load_countries(BOUNDARY_DIR)
    map_lib.add_base_map(
        ax,
        world,
        ocean_color=BASE_OCEAN_COLOR,
        land_color=BASE_LAND_COLOR,
    )
    cmap = add_relief(ax, etopo_path)
    add_admin_context(ax, regions, border_zone)
    add_context(ax, border_line)
    # 两条大江压在一般河流与区域填充之上、国界/区域边界之下.
    add_main_rivers(ax)
    add_special_regions(ax, regions, border_zone)

    add_city_markers(ax)
    add_gridlines(ax)

    # 地图框量在 set_extent/aspect 修正之后; 底图裁剪、geo.base 与经纬刻度共用它.
    frame = figure_frame(fig, ax)
    doc = GeoDoc(frame)
    collect_labels(doc, ax)
    collect_graticule(doc, ax)
    collect_relief(doc, cmap)
    collect_legend(doc)
    collect_suggestions(doc)

    # 与 myanmar.py 相同: 不用 tight_layout/bbox_inches="tight":
    # cartopy 0.25 在非矩形投影上会由 gridliner 用未闭合顶点构造多边形而抛 GEOSException.
    # save_map 写裁到地图框的纯底图与同名 geo.json(miko 契约里的 base.svg + geo).
    svg_path, geo_path = save_map(fig, OUT_SVG, doc, dpi=args.dpi)
    print(f"底图与 geo 已保存: {svg_path} + {geo_path}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
