#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# ukraine.py
# 乌克兰全图: 以 ETOPO 2022 地形晕渲为底图, 叠加
#   1) 1991 年国际承认边界(含克里米亚);
#   2) 2014 年实际控制线(克里米亚陆上控制线 + 顿巴斯接触线)及其控制区;
#   3) 2014 年宣布的"人民共和国"(顿涅茨克/卢甘斯克实际控制区, 哈尔科夫宣称范围);
#   4) 2022 年俄方单方面宣称的赫尔松/扎波罗热/顿涅茨克/卢甘斯克四州全境边界.
# 运行前先执行: python Ukraine/download_data.py
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Ukraine overview map: 1991 / 2014 / 2022 borders over ETOPO relief.

设计要点:
    1. 投影: 兰勃特等角圆锥投影(Lambert Conformal Conic), 中央经线 31°E,
       标准纬线 45°N/52°N. 乌克兰东西约 18°、南北约 8°, 中纬度国家用圆锥
       投影比等经纬度投影更不容易把西部/东部横向拉变形; 标准纬线夹住国土
       南北缘, 全国比例误差最小.
    2. 底图: ETOPO 2022 地形 + 山体晕渲, 与项目里缅甸、苏联图一致. 地形
       信息用来提供地理参照, 不参与表达政治边界, 所以边界线都用高对比度
       颜色 + 白色描边压在晕渲上面.
    3. 边界口径(按用户确认):
       - 1991 年边界 = 苏联解体时乌克兰的国际承认边界, 含克里米亚与
         塞瓦斯托波尔(法理口径, 来自 GADM 4.1);
       - 2014 年 = 克里米亚并入俄罗斯后的陆上实际控制线(彼列科普地峡
         一带的内部行政边界) + 顿巴斯接触线. 接触线用 OCHA 2021 年
         GCA/NGCA 界线近似(明斯克协议线, 2015 年后基本稳定), 属于近似值;
       - 2022 年 = 俄方 2022-09-30 单方面宣称的赫尔松州、扎波罗热州、
         顿涅茨克人民共和国、卢甘斯克人民共和国"全境"边界; 只画法理州界,
         不把四州整体填色, 避免被误读为俄方实际控制.
    4. 分离"实际控制"与"单方面宣称": 2014 年控制区用浅蓝色填充 + 蓝色
       实线, 2022 年宣称边界用紫色点划线; 两者不混用同一种线型.

数据(由 Ukraine/download_data.py 准备, 脚本本身不联网):
    data/ETOPO_2022_v1_15s_ukraine_stride2.nc   NOAA ETOPO 2022 地形
    data/ne_10m_admin_0_countries/              Natural Earth 10m 国界(邻国)
    data/ukraine_oblasts.geojson                GADM 4.1 乌克兰一级行政区
    data/ukraine_1991.geojson                   1991 年国际承认边界
    data/crimea_2014_line.geojson               2014 年克里米亚陆上控制线
    data/occupied_2014.geojson                  2014 年顿巴斯控制区
    data/contact_line_2014.geojson              2014 年顿巴斯接触线(近似)
    data/claimed_2022.geojson                   2022 年俄方宣称四州全境
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
ELEV_CMAP = "terrain"
HILLSHADE_AZIMUTH = 315  # 西北来光, 制图惯例
HILLSHADE_ALTITUDE = 45
HILLSHADE_VERT_EXAG = 1.4  # 全国尺度上地形起伏弱, 略作夸张

# 海陆底色(只在 ETOPO 子集边缘露出来时可见).
BASE_OCEAN_COLOR = "#cfe0ee"
BASE_LAND_COLOR = "#efe9cf"

# 图面配色: 每种边界一个固定颜色, 图例与标注共用同一套常量, 避免读图歧义.
COLOR_1991 = "#111111"       # 1991 国际承认边界: 近黑
COLOR_2014 = "#1565c0"       # 2014 实际控制线: 蓝
COLOR_2014_FILL = "#42a5f5"  # 2014 实际控制区填充
COLOR_KHARKIV = "#ef6c00"    # 2014 宣布的哈尔科夫人民共和国(未控制): 橙
COLOR_2022 = "#7b1fa2"       # 2022 俄方宣称边界: 紫
COLOR_OBLAST = "#5f6b73"     # 州界(背景参考线)
COLOR_RIVER = "#3f7fb5"      # 河流
COLOR_NEIGHBOR = "#8a8a8a"   # 邻国国界

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
# 城市标注: (经度, 纬度, 名称, 是否首都, 经度偏移, 纬度偏移, 对齐方式).
# 偏移都在 0.1~0.2°(约 10~20 km)量级, 只用于让文字离开边界线与其它标注,
# 不会把标签拖到别的国家去.
CITIES = [
    (30.523, 50.450, "基辅", True, 0.20, 0.12, "left"),
    (36.230, 49.993, "哈尔科夫", False, 0.16, 0.12, "left"),
    (30.732, 46.482, "敖德萨", False, 0.16, 0.12, "left"),
    (35.046, 48.464, "第聂伯", False, 0.16, 0.12, "left"),
    (37.802, 48.015, "顿涅茨克", False, -0.16, -0.18, "right"),
    (39.307, 48.574, "卢甘斯克", False, -0.16, 0.16, "right"),
    (35.139, 47.838, "扎波罗热", False, 0.16, 0.14, "left"),
    (32.617, 46.640, "赫尔松", False, 0.16, 0.12, "left"),
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
    casing: bool = True,
    casing_width: float = 1.6,
    casing_alpha: float = 0.7,
) -> None:
    """画一组线要素, 先画白色粗描边再画彩色细线, 保证在晕渲上仍然清楚.

    为什么不用 path_effects: ``add_geometries`` 返回的 FeatureArtist 对描边
    支持不稳定; 用"先粗白线后细彩线"两次绘制是等效且跨 cartopy 版本可靠的做法.
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
    coastline,
    neighbor_borders,
) -> None:
    """地形 + 河流 + 邻国国界 + 乌克兰州界背景线.

    乌克兰自己的海岸线不单独画: 1991 年国界(黑线)已经把它包进去; 再叠一条
    不同来源的海岸线只会露出两条线的几十米~几公里偏差. 邻国的海岸线/国界
    则照常画, 提供地理参照.
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
        # 边界外侧留下一条与黑线平行的细虚线.
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
    # 河流放在州界之下、主题边界之上; 10m 河流在国界附近可能超出画框,
    # cartopy 会按画框裁剪.
    if rivers is not None:
        ax.add_geometries(
            list(rivers.geometry),
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=COLOR_RIVER,
            linewidth=0.5,
            alpha=0.8,
            zorder=2.5,
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
    """按"先填充后线条"的顺序叠加所有主题边界."""
    # --- 2014 年实际控制区(克里米亚 + 顿巴斯 NGCA): 浅蓝填充 ---
    crimea_units = oblasts[oblasts["name"].isin(["Crimea", "Sevastopol'"])]
    ngca_units = occupied[occupied["name"].str.startswith("NGCA,", na=False)]
    add_fill_layer(ax, list(crimea_units.geometry), color=COLOR_2014_FILL, alpha=0.22, zorder=2.2)
    add_fill_layer(ax, list(ngca_units.geometry), color=COLOR_2014_FILL, alpha=0.24, zorder=2.2)

    # --- 2014 年宣布的哈尔科夫人民共和国: 只有宣称、没有实际控制, 用橙色虚线 ---
    kharkiv = oblasts[oblasts["name"] == "Kharkiv"]
    if not kharkiv.empty:
        add_line_layer(
            ax,
            list(kharkiv.geometry),
            color=COLOR_KHARKIV,
            linewidth=2.0,
            linestyle=(0, (6, 3)),
            zorder=5.0,
        )

    # --- 2022 年俄方宣称的四州全境: 四州合并后的外边界, 紫色点划线 ---
    # 先画 2022 宣称线, 再画 1991 国界与 2014 控制线: 这样在"宣称边界刚好
    # 与国界/控制线重合"的段落(顿巴斯东段、克里米亚地峡)上, 基础边界仍然
    # 清楚; 紫色线只在它独有的段落上显眼, 不会被误读成实际控制线.
    claimed_union = unary_union(list(claimed.geometry))
    add_line_layer(
        ax,
        [claimed_union.boundary],
        color=COLOR_2022,
        linewidth=2.1,
        linestyle=(0, (6, 2.0, 1.6, 2.0)),
        zorder=5.5,
        casing_width=1.0,
        casing_alpha=0.55,
    )

    # --- 1991 年国际承认边界: 最外层、最粗、实线 ---
    add_line_layer(
        ax,
        [ukraine_geom],
        color=COLOR_1991,
        linewidth=2.4,
        linestyle="-",
        zorder=6.0,
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


def add_labels(ax: plt.Axes, oblasts: gpd.GeoDataFrame) -> None:
    """国家/海域/城市标注 + 主题区域标注(2014 人民共和国与 2022 宣称州)."""
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

    # --- 2014 年宣布的"人民共和国": 卢甘斯克/顿涅茨克是实际控制区(蓝),
    #     哈尔科夫只有宣称(橙). 文字用两行, 避免横跨边界线. ---
    ax.text(
        39.45, 48.25, "卢甘斯克\n人民共和国",
        transform=ccrs.PlateCarree(),
        fontsize=8.8, color="#0d47a1",
        ha="center", va="center", linespacing=1.3, path_effects=HALO, zorder=9.5,
    )
    ax.text(
        38.15, 47.35, "顿涅茨克\n人民共和国",
        transform=ccrs.PlateCarree(),
        fontsize=8.8, color="#0d47a1",
        ha="center", va="center", linespacing=1.3, path_effects=HALO, zorder=9.5,
    )
    ax.text(
        37.15, 49.10, "哈尔科夫人民共和国\n（2014年宣布，未实际控制）",
        transform=ccrs.PlateCarree(),
        fontsize=9.4, color=COLOR_KHARKIV, style="italic",
        ha="center", va="center", linespacing=1.35, path_effects=HALO, zorder=9.5,
    )
    # --- 2022 年俄方宣称的两个州(顿/卢两州已由上面的"人民共和国"标注覆盖) ---
    ax.text(
        33.60, 46.72, "赫尔松州\n（俄宣称全境）",
        transform=ccrs.PlateCarree(),
        fontsize=9.4, color=COLOR_2022,
        ha="center", va="center", linespacing=1.35, path_effects=HALO, zorder=9.5,
    )
    ax.text(
        34.95, 47.30, "扎波罗热州\n（俄宣称全境）",
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
    """高程色标放在图例下方, 单独占一个窄坐标轴, 不抢地图的宽度."""
    cax = fig.add_axes([0.79, 0.36, 0.014, 0.17])
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
        Line2D([0], [0], color=COLOR_1991, linewidth=2.4, label="1991 年国际承认边界（含克里米亚）"),
        Line2D([0], [0], color=COLOR_2014, linewidth=2.1, label="2014 年实际控制线（克里米亚 · 顿巴斯接触线）"),
        Patch(facecolor=COLOR_2014_FILL, alpha=0.35, edgecolor="none", label="2014 年俄方实际控制区（示意填色）"),
        Line2D([0], [0], color=COLOR_KHARKIV, linewidth=2.0, linestyle=(0, (6, 3)), label="2014 年宣布的「哈尔科夫人民共和国」\n（未实际控制）"),
        Line2D([0], [0], color=COLOR_2022, linewidth=2.3, linestyle=(0, (7, 2.5, 1.6, 2.5)), label="2022 年俄方宣称四州全境边界\n（单方面宣称，非控制线）"),
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
        "实际控制范围见蓝色填充与接触线；哈尔科夫人民共和国只有\n"
        "2014 年的宣称，图中按其宣称范围(哈尔科夫州)画出，未实际控制。"
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
        "投影: Lambert Conformal Conic",
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

    # 共享缓存里的 Natural Earth 10m 图层(缺失就跳过, 不联网下载).
    rivers = None
    rivers_path = shared_layer("10m", "physical", "rivers_lake_centerlines")
    if rivers_path is not None:
        rivers = gpd.read_file(rivers_path)
        rivers = rivers[rivers["scalerank"] <= 9]
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
        coastline=coastline,
        neighbor_borders=neighbor_borders,
    )

    # 晕渲 RGB 图: imshow 比 pcolormesh 快; regrid_shape 提到 3200, 否则
    # 在 300 dpi 下 30 弧秒的 ETOPO 会被 cartopy 重采样糊掉.
    relief, norm, cmap = make_relief(
        z, lat, lon,
        vmin=ELEV_VMIN, vmax=ELEV_VMAX, cmap=ELEV_CMAP,
        azimuth=HILLSHADE_AZIMUTH, altitude=HILLSHADE_ALTITUDE,
        vert_exag=HILLSHADE_VERT_EXAG,
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
