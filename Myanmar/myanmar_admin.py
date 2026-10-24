#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# myanmar_admin.py
# 绘制缅甸联邦共和国省/邦级行政区划图:
#   - 七邦用冷色, 七省用暖色, 内比都联邦区用中性浅色 + 斜线;
#   - 邦/省名与行政中心均为中文 + English 双语标注;
#   - 叠加伊洛瓦底江、萨尔温江, 以及 ETOPO 2022 地形晕渲;
#   - 输出 300 dpi PNG, 适合打印与排版.
# 运行前先执行:
#   python prepare_admin_data.py
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Bilingual administrative-division map of Myanmar.

设计要点:
    1. 颜色编码: 7 个邦(State)统一用冷色系, 7 个省(Region)统一用暖色系,
       内比都联邦区既非邦也非省, 用中性浅色 + 斜线填充, 避免被误读.
    2. 投影: 缅甸南北约 19°, 东西约 9°, 用兰勃特等角圆锥投影
       (Lambert Conformal Conic), 标准纬线取 10°N / 27°N, 使全国比例误差
       最小; 等经纬度投影会把高纬的克钦邦横向拉宽, 不适合这种狭长国土.
    3. 地形: ETOPO 2022 只作为低透明度底纹, 不抢行政区颜色的视觉层级;
       河流单独加深, 让伊洛瓦底江和萨尔温江在彩色块上仍然清楚.
    4. 文字: 行政区名用大号中文 + 小号英文, 行政中心用小号中文 + 英文;
       所有文字加白色描边, 保证压在深色地形或彩色块上仍可读.

数据:
    data/myanmar_admin1.geojson  由 prepare_admin_data.py 生成
    data/ne_10m_admin_0_countries  Natural Earth 10m 国界
    data/ne_10m_rivers_lake_centerlines  Natural Earth 10m 河流
    data/ETOPO_2022_v1_15s_myanmar_stride2.nc  NOAA ETOPO 2022 地形
作者: Haojiren Galactic
时间: 2026-10-24
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# matplotlib 的缓存目录必须在导入 matplotlib 之前指定; 本机 ~/.config 不可写.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import geopandas as gpd  # 读取 Natural Earth shapefile
import matplotlib.colors as mcolors  # 颜色与色带
import matplotlib.patheffects as pe  # 文字描边
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网刻度
import numpy as np  # 数组运算
from cartopy.mpl.gridliner import LATITUDE_FORMATTER, LONGITUDE_FORMATTER
from matplotlib.patches import Rectangle  # 图例面要素
from shapely.geometry import shape  # GeoJSON -> Shapely

import map_lib  # 复用 ETOPO 读取、晕渲、海陆底色工具

# 全局字体: 项目包 cartopy_file 统一设置. 汉字用 Noto Sans Mono CJK SC,
# 英文/数字用 JetBrains Mono Slashed Medium; 中英混排由逐字符回退自动选字体,
# 所以下面的文字调用不再逐个指定 fontfamily.
from cartopy_file.fonts import apply_matplotlib_fonts

apply_matplotlib_fonts()
# 斜线填充过密会在 300 dpi 下糊成深色块, 这里保持项目里一致的细线.
plt.rcParams["hatch.linewidth"] = 0.5


# ============================
# 配置
# ============================
ADMIN_GEOJSON = DATA_DIR / "myanmar_admin1.geojson"
COUNTRY_DIR = DATA_DIR / "ne_10m_admin_0_countries"
RIVER_SHP = DATA_DIR / "ne_10m_rivers_lake_centerlines" / "ne_10m_rivers_lake_centerlines.shp"

# 画框: 缅甸本土约 92.17~101.17°E / 9.79~28.54°N, 四周留出邻国与海域.
# 西侧多留一点, 让孟加拉湾和孟加拉国进入画面; 东侧留到湄公河附近.
EXTENT = [91.0, 102.5, 8.8, 29.4]

# 投影: 中央经线取国土中部 96.5°E, 标准纬线夹住南北端, 比例误差最小.
PROJECTION = ccrs.LambertConformal(
    central_longitude=96.5,
    central_latitude=19.5,
    standard_parallels=(10.0, 27.0),
)

# 海陆底色: 海洋浅蓝, 邻国陆地米色. 缅甸本国区域随后由行政区填色覆盖.
OCEAN_COLOR = "#d8e8f3"
LAND_COLOR = "#f7f2e6"

# 行政区颜色. 冷色 = 邦, 暖色 = 省; 色相分散, 保证相邻单元也能区分.
# 透明度在绘制时统一加, 这样底纹和地形仍能透出一点, 不至于变成纯色拼图.
STATE_COLORS = {
    "kachin": "#1e88e5",
    "kayah": "#81d4fa",
    "kayin": "#2e7d32",
    "chin": "#8e24aa",
    "mon": "#00acc1",
    "rakhine": "#00897b",
    "shan": "#5c6bc0",
}
REGION_COLORS = {
    "ayeyarwady": "#ffb74d",
    "bago": "#f9a825",
    "magway": "#d84315",
    "mandalay": "#ef6c00",
    "sagaing": "#b71c1c",
    "tanintharyi": "#e64a19",
    "yangon": "#c2185b",
}
UNION_COLOR = "#f3e5ab"
FILL_ALPHA = 0.58
BOUNDARY_COLOR = "#2f2f2f"

# 地形底纹: 从低地米白过渡到山地浅褐; 负高程(海洋)在 alpha 通道里挖掉.
RELIEF_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "myanmar_relief",
    ["#fbf8f0", "#eee5d4", "#d9c8aa", "#b7a17f"],
)
RELIEF_VMIN, RELIEF_VMAX = 0, 4200
RELIEF_ALPHA = 0.55

# 行政区名标签位置(经度, 纬度). 多数放在单元内部; 面积很小的单元
# (内比都联邦区、仰光省、孟邦)单独给 callout 锚点, 避免文字压住边界和中心点.
ADMIN_LABELS: dict[str, tuple[float, float]] = {
    "kachin": (97.05, 27.05),
    "sagaing": (94.68, 25.15),
    "chin": (93.55, 23.42),
    "shan": (98.62, 22.20),
    "mandalay": (95.95, 21.00),
    "magway": (94.30, 20.95),
    "bago": (96.35, 18.60),
    "ayeyarwady": (95.10, 17.62),
    "rakhine": (93.52, 19.00),
    "kayah": (97.45, 19.25),
    "kayin": (97.90, 18.35),
    "mon": (97.55, 15.65),
    "tanintharyi": (98.56, 12.95),
    "yangon": (96.45, 16.15),
    "npt": (96.45, 20.16),
}
# ADMIN_LABELS 中需要从标签引一条细线到实际区域的单元; 值是锚点(经度, 纬度).
ADMIN_LABEL_ANCHORS: dict[str, tuple[float, float]] = {
    "npt": (96.12, 19.74),
    "yangon": (96.35, 16.93),
    "mon": (97.78, 16.10),
}

# 行政中心标签相对标记点的偏移(单位: 磅), 以及水平对齐方式.
# ha 决定标签往哪一侧展开, 手工调整是为了避开相邻中心点、河流和边界.
CAPITAL_OFFSETS: dict[str, tuple[float, float, str]] = {
    "kachin": (7, 4, "left"),
    "kayah": (7, 4, "left"),
    "kayin": (7, 4, "left"),
    "chin": (-7, 3, "right"),
    "mon": (7, -5, "left"),
    "rakhine": (7, 3, "left"),
    "shan": (7, -5, "left"),
    "ayeyarwady": (-7, -5, "right"),
    "bago": (7, 5, "left"),
    "magway": (7, -6, "left"),
    "mandalay": (7, 5, "left"),
    "sagaing": (7, 4, "left"),
    "tanintharyi": (7, 4, "left"),
    "yangon": (-7, -7, "right"),
    "npt": (-9, 7, "right"),
}

# 邻国、海域标注: (经度, 纬度, 中文, 英文). 只作为定位参照, 不参与颜色编码.
NEIGHBOUR_LABELS = [
    (99.85, 28.30, "中国", "CHINA"),
    (92.20, 26.40, "印度", "INDIA"),
    (91.55, 23.55, "孟加拉国", "BANGLADESH"),
    (99.45, 18.40, "泰国", "THAILAND"),
    (100.80, 20.55, "老挝", "LAOS"),
]
SEA_LABELS = [
    (91.45, 15.20, "孟加拉湾", "BAY OF BENGAL"),
    (96.45, 10.20, "安达曼海", "ANDAMAN SEA"),
]

TITLE_ZH = "缅甸联邦共和国行政区划图"
TITLE_EN = "ADMINISTRATIVE DIVISIONS OF THE REPUBLIC OF THE UNION OF MYANMAR"
SUBTITLE = (
    "七邦（冷色）· 七省（暖色）· 内比都联邦区　　"
    "7 States (cool colours) · 7 Regions (warm colours) · Naypyidaw Union Territory"
)
SOURCE = (
    "行政区划: GADM 4.1 / OpenStreetMap (ODbL)　|　"
    "国界·河流: Natural Earth 10m　|　地形: NOAA ETOPO 2022　|　"
    "投影: Lambert Conformal Conic"
)
OUT_PNG = ROOT / "myanmar_administrative_divisions_bilingual.png"


def load_admin_units():
    """读取预处理后的 15 个一级行政区, 按邦/省/联邦区分组."""
    payload = json.loads(ADMIN_GEOJSON.read_text(encoding="utf-8"))
    units = []
    for feature in payload["features"]:
        properties = feature["properties"]
        units.append(
            {
                **properties,
                "geometry": shape(feature["geometry"]),
            }
        )
    if len(units) != 15:
        raise ValueError(f"应有 15 个一级行政区, 实际 {len(units)} 个")
    return units


def add_relief(ax: plt.Axes, etopo_path: Path) -> None:
    """铺海陆底色, 再叠加只覆盖陆地的低透明度地形晕渲."""
    world = map_lib.load_countries(COUNTRY_DIR)
    map_lib.add_base_map(ax, world, ocean_color=OCEAN_COLOR, land_color=LAND_COLOR)
    if world is not None:
        # 邻国海岸线/国界用细灰线, 弱化到行政区分层之下.
        ax.add_geometries(
            world.geometry,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor="#9a9488",
            linewidth=0.45,
            zorder=1.5,
        )

    lon, lat, z = map_lib.load_elevation(etopo_path)
    relief, _, _ = map_lib.make_relief(
        z,
        lat,
        lon,
        vmin=RELIEF_VMIN,
        vmax=RELIEF_VMAX,
        cmap=RELIEF_CMAP,
        azimuth=315,  # 西北来光, 与项目内其他地形图一致
        altitude=45,
        vert_exag=1.35,
        fraction=1.0,
    )
    # 把海洋的 alpha 置 0: 海面保留纯浅蓝, 否则负高程也会被染成米色.
    relief[..., 3] = np.where(z >= 0, RELIEF_ALPHA, 0.0)
    ax.imshow(
        relief,
        origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        regrid_shape=3000,
        interpolation="bilinear",
        zorder=2,
    )


def add_admin_fills(ax: plt.Axes, units) -> None:
    """按邦/省/联邦区填色, 再统一描内部边界.

    先画无边框的填充, 再单独画边界, 避免半透明填充在相邻边界处叠成
    一条颜色更深的粗线; 内比都联邦区最后画, 保证斜线填充不被覆盖.
    """
    for unit in units:
        key = unit["key"]
        if unit["kind"] == "union":
            continue
        color = STATE_COLORS[key] if unit["kind"] == "state" else REGION_COLORS[key]
        ax.add_geometries(
            [unit["geometry"]],
            crs=ccrs.PlateCarree(),
            facecolor=(*mcolors.to_rgb(color), FILL_ALPHA),
            edgecolor="none",
            zorder=4,
        )

    # 省/邦边界: 所有一级单元放在同一图层, 线宽一致, 不区分冷暖和类型.
    ax.add_geometries(
        [unit["geometry"].boundary for unit in units if unit["kind"] != "union"],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=BOUNDARY_COLOR,
        linewidth=1.05,
        zorder=5,
    )

    union = next(unit for unit in units if unit["kind"] == "union")
    ax.add_geometries(
        [union["geometry"]],
        crs=ccrs.PlateCarree(),
        facecolor=(*mcolors.to_rgb(UNION_COLOR), 0.92),
        edgecolor="#6b4e00",
        linewidth=1.15,
        hatch="////",
        zorder=6,
    )


def add_rivers(ax: plt.Axes) -> None:
    """画出伊洛瓦底江与萨尔温江, 外加浅色描边使其在彩色块上可读.

    Natural Earth 里伊洛瓦底江被拆成 Ayeyarwady + Irrawaddy Delta,
    萨尔温江被拆成 Nu + Salween 两段; 按 name_en 统一筛选再合并.
    """
    if not RIVER_SHP.exists():
        raise FileNotFoundError(
            f"未找到河流数据: {RIVER_SHP}\n请先运行: python prepare_admin_data.py"
        )
    rivers = gpd.read_file(RIVER_SHP)
    selected = rivers[rivers["name_en"].isin(["Irrawaddy", "Salween"])]
    if selected.empty:
        print("警告: 未找到伊洛瓦底江/萨尔温江, 跳过河流.")
        return
    geoms = list(selected.geometry)
    ax.add_geometries(
        geoms,
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="#e8f4ff",
        linewidth=5.4,
        zorder=7,
    )
    ax.add_geometries(
        geoms,
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="#1565c0",
        linewidth=2.25,
        zorder=8,
    )


def add_country_outline(ax: plt.Axes) -> None:
    """用白色外描边 + 黑色内线强调缅甸国界, 与内部省/邦界区分."""
    world = map_lib.load_countries(COUNTRY_DIR)
    if world is None:
        return
    myanmar = world.loc[world["ADMIN"] == "Myanmar", "geometry"]
    if myanmar.empty:
        return
    from shapely.ops import unary_union

    boundary = unary_union(myanmar)
    ax.add_geometries(
        [boundary],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="white",
        linewidth=4.6,
        zorder=9,
    )
    ax.add_geometries(
        [boundary],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="#111111",
        linewidth=2.15,
        zorder=10,
    )


def add_bilingual(
    ax: plt.Axes,
    lon: float,
    lat: float,
    zh: str,
    en: str,
    *,
    size_zh: float,
    size_en: float,
    dx: float = 0,
    dy_zh: float = 4.0,
    dy_en: float = -7.0,
    ha: str = "center",
    anchor: tuple[float, float] | None = None,
    color: str = "#171717",
    halo: float = 3.0,
    zorder: float = 12,
) -> None:
    """在指定经纬度处写中文 + 英文两行标签.

    用 offset points 而不是经纬度偏移: 标签间距应与字号相关, 不能随
    纬度变化; 投影后同样一段经度差在南北方向对应的图面距离并不相同.
    """
    transform = ccrs.PlateCarree()._as_mpl_transform(ax)
    if anchor is not None:
        ax.annotate(
            "",
            xy=anchor,
            xycoords=transform,
            xytext=(lon, lat),
            textcoords=transform,
            arrowprops=dict(
                arrowstyle="-",
                color="#3d3d3d",
                linewidth=0.75,
                shrinkA=1.5,
                shrinkB=4.0,
            ),
            zorder=zorder - 1,
        )
    halo_effects = [pe.withStroke(linewidth=halo, foreground="white")]
    ax.annotate(
        zh,
        xy=(lon, lat),
        xycoords=transform,
        xytext=(dx, dy_zh),
        textcoords="offset points",
        ha=ha,
        va="center",
        fontsize=size_zh,
        color=color,
        path_effects=halo_effects,
        zorder=zorder,
    )
    ax.annotate(
        en,
        xy=(lon, lat),
        xycoords=transform,
        xytext=(dx, dy_en),
        textcoords="offset points",
        ha=ha,
        va="center",
        fontsize=size_en,
        color="#303030",
        path_effects=[pe.withStroke(linewidth=halo * 0.8, foreground="white")],
        zorder=zorder,
    )


def add_admin_labels(ax: plt.Axes, units) -> None:
    """标注 15 个行政区名(中文 + English)与 15 个行政中心."""
    for unit in units:
        key = unit["key"]
        lon, lat = ADMIN_LABELS[key]
        is_union = unit["kind"] == "union"
        small = key in {"kayah", "mon", "yangon", "npt"}
        # 内比都的英文全名太长, 在图上压到隔壁单元; 用 U.T. 缩写,
        # 图例和标题里保留全称 Naypyidaw Union Territory.
        display_en = "Naypyidaw U.T." if is_union else unit["name_en"]
        add_bilingual(
            ax,
            lon,
            lat,
            unit["name_zh"],
            display_en,
            size_zh=8.8 if is_union else (10.3 if small else (10.8 if unit["kind"] == "state" else 10.5)),
            size_en=6.4 if is_union else (6.9 if small else 7.8),
            dy_zh=4.2,
            dy_en=-7.0,
            anchor=ADMIN_LABEL_ANCHORS.get(key),
            color="#111111",
            halo=3.2,
            zorder=13,
        )

    # 行政中心: 普通省/邦中心用空心圆, 联邦区/首都用星形.
    for unit in units:
        key = unit["key"]
        lon = unit["capital_lon"]
        lat = unit["capital_lat"]
        is_union = unit["kind"] == "union"
        if is_union:
            ax.plot(
                lon,
                lat,
                marker="*",
                markersize=15,
                markerfacecolor="#ffd200",
                markeredgecolor="#111111",
                markeredgewidth=0.75,
                transform=ccrs.PlateCarree(),
                zorder=15,
            )
        else:
            ax.plot(
                lon,
                lat,
                marker="o",
                markersize=5.6,
                markerfacecolor="white",
                markeredgecolor="#111111",
                markeredgewidth=0.9,
                transform=ccrs.PlateCarree(),
                zorder=15,
            )

        dx, dy, ha = CAPITAL_OFFSETS[key]
        # 联邦区标签已经用行政区名表达, 不再重复写一次 "内比都" 破坏小区域.
        if is_union:
            continue
        add_bilingual(
            ax,
            lon,
            lat,
            unit["capital_zh"],
            unit["capital_en"],
            size_zh=8.0,
            size_en=6.5,
            dx=dx,
            dy_zh=dy + 2.6,
            dy_en=dy - 5.0,
            ha=ha,
            color="#111111",
            halo=2.6,
            zorder=14,
        )


def add_place_labels(ax: plt.Axes) -> None:
    """标注邻国、海域和两条大江, 提供地图定位参照."""
    for lon, lat, zh, en in NEIGHBOUR_LABELS:
        add_bilingual(
            ax,
            lon,
            lat,
            zh,
            en,
            size_zh=12.0,
            size_en=8.4,
            dy_zh=4.0,
            dy_en=-7.0,
            color="#4a4a4a",
            halo=3.4,
            zorder=11,
        )
    for lon, lat, zh, en in SEA_LABELS:
        add_bilingual(
            ax,
            lon,
            lat,
            zh,
            en,
            size_zh=11.5,
            size_en=8.0,
            dy_zh=3.5,
            dy_en=-6.5,
            color="#1c5f8a",
            halo=3.2,
            zorder=11,
        )

    # 两条大江的标签; 位置避开了主要行政区名和行政中心点.
    add_bilingual(
        ax,
        95.12,
        18.45,
        "伊洛瓦底江",
        "Irrawaddy River",
        size_zh=9.0,
        size_en=6.8,
        dy_zh=3.5,
        dy_en=-6.0,
        color="#0d47a1",
        halo=2.8,
        zorder=14,
    )
    add_bilingual(
        ax,
        98.55,
        20.55,
        "萨尔温江",
        "Salween River",
        size_zh=9.0,
        size_en=6.8,
        dy_zh=3.5,
        dy_en=-6.0,
        color="#0d47a1",
        halo=2.8,
        zorder=14,
    )


def add_scale_bar(ax: plt.Axes) -> None:
    """在西南海域画 200 km 直线比例尺.

    投影坐标单位是米, 在标准纬线 10°N 附近比例因子接近 1, 所以直接按
    投影平面长度画 200 km; 这不是全图统一比例尺(兰勃特投影比例随纬度
    变化), 但在该参考位置足够准确, 且不会误导到 5% 以上.
    """
    x0, y0 = PROJECTION.transform_point(91.35, 10.15, ccrs.PlateCarree())
    length_m = 200_000.0
    ax.plot(
        [x0, x0 + length_m],
        [y0, y0],
        color="#222222",
        linewidth=3.0,
        solid_capstyle="butt",
        zorder=16,
    )
    ax.plot(
        [x0, x0 + length_m],
        [y0, y0],
        color="white",
        linewidth=1.2,
        solid_capstyle="butt",
        zorder=17,
    )
    for frac in (0.0, 0.5, 1.0):
        x = x0 + length_m * frac
        ax.plot(
            [x, x],
            [y0 - 3500, y0 + 3500],
            color="#222222",
            linewidth=1.0,
            zorder=17,
        )
    for frac, label in ((0.0, "0"), (0.5, "100"), (1.0, "200 km")):
        ax.text(
            x0 + length_m * frac,
            y0 + 7000,
            label,
            ha="center",
            va="bottom",
            fontsize=7.0,
            color="#222222",
            zorder=18,
        )



def add_north_arrow(ax: plt.Axes) -> None:
    """在右上角空白处画一个简洁的指北针."""
    ax.annotate(
        "",
        xy=(0.965, 0.965),
        xytext=(0.965, 0.905),
        xycoords="axes fraction",
        arrowprops=dict(arrowstyle="-|>", color="#222222", linewidth=1.2),
        zorder=20,
    )
    ax.text(
        0.965,
        0.972,
        "N",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=11,
        color="#222222",
        zorder=20,
    )


def add_legend(fig: plt.Figure) -> None:
    """右侧独立图例面板: 颜色分组、符号、线型与数据说明."""
    lax = fig.add_axes([0.765, 0.19, 0.215, 0.66])
    lax.set_xlim(0, 1)
    lax.set_ylim(0, 1)
    lax.axis("off")

    lax.text(
        0.0,
        0.98,
        "图例",
        ha="left",
        va="top",
        fontsize=17,
        color="#111111",
    )
    lax.text(
        0.22,
        0.978,
        "LEGEND",
        ha="left",
        va="top",
        fontsize=10,
        color="#555555",
    )

    # --- 邦: 冷色 ---
    lax.text(
        0.0,
        0.915,
        "邦 / STATE（7）",
        ha="left",
        va="top",
        fontsize=10.2,
        color="#111111",
    )
    lax.text(
        0.0,
        0.880,
        "冷色 · cool colours",
        ha="left",
        va="top",
        fontsize=7.6,
        color="#555555",
    )
    state_keys = ["kachin", "kayah", "kayin", "chin", "mon", "rakhine", "shan"]
    for i, key in enumerate(state_keys):
        lax.add_patch(
            Rectangle(
                (0.02 + i * 0.137, 0.825),
                0.115,
                0.035,
                facecolor=STATE_COLORS[key],
                edgecolor="#ffffff",
                linewidth=0.6,
            )
        )

    # --- 省: 暖色 ---
    lax.text(
        0.0,
        0.775,
        "省 / REGION（7）",
        ha="left",
        va="top",
        fontsize=10.2,
        color="#111111",
    )
    lax.text(
        0.0,
        0.740,
        "暖色 · warm colours",
        ha="left",
        va="top",
        fontsize=7.6,
        color="#555555",
    )
    region_keys = ["sagaing", "magway", "mandalay", "bago", "ayeyarwady", "yangon", "tanintharyi"]
    for i, key in enumerate(region_keys):
        lax.add_patch(
            Rectangle(
                (0.02 + i * 0.137, 0.685),
                0.115,
                0.035,
                facecolor=REGION_COLORS[key],
                edgecolor="#ffffff",
                linewidth=0.6,
            )
        )

    # --- 联邦区 ---
    lax.add_patch(
        Rectangle(
            (0.02, 0.600),
            0.115,
            0.040,
            facecolor=UNION_COLOR,
            edgecolor="#6b4e00",
            linewidth=1.0,
            hatch="////",
        )
    )
    lax.text(
        0.18,
        0.628,
        "联邦区  Union Territory",
        ha="left",
        va="center",
        fontsize=9.2,
        color="#111111",
    )
    lax.text(
        0.18,
        0.598,
        "内比都联邦区",
        ha="left",
        va="center",
        fontsize=7.6,
        color="#333333",
    )
    lax.text(
        0.18,
        0.568,
        "Naypyidaw Union Territory",
        ha="left",
        va="center",
        fontsize=6.9,
        color="#555555",
    )

    # --- 点符号 ---
    lax.plot(
        [0.045],
        [0.535],
        marker="*",
        markersize=13,
        markerfacecolor="#ffd200",
        markeredgecolor="#111111",
        markeredgewidth=0.7,
        linestyle="none",
    )
    lax.text(
        0.18,
        0.535,
        "联邦首都 / Union capital",
        ha="left",
        va="center",
        fontsize=8.4,
        color="#111111",
    )
    lax.plot(
        [0.045],
        [0.485],
        marker="o",
        markersize=6.5,
        markerfacecolor="white",
        markeredgecolor="#111111",
        markeredgewidth=0.9,
        linestyle="none",
    )
    lax.text(
        0.18,
        0.485,
        "行政中心 / Administrative centre",
        ha="left",
        va="center",
        fontsize=8.4,
        color="#111111",
    )

    # --- 线状要素 ---
    lax.plot(
        [0.02, 0.11],
        [0.425, 0.425],
        color="#1565c0",
        linewidth=3.0,
        solid_capstyle="round",
    )
    lax.text(
        0.18,
        0.425,
        "河流 / River",
        ha="left",
        va="center",
        fontsize=8.4,
        color="#111111",
    )
    lax.plot(
        [0.02, 0.11],
        [0.380, 0.380],
        color=BOUNDARY_COLOR,
        linewidth=1.2,
    )
    lax.text(
        0.18,
        0.380,
        "邦/省界 / State & region boundary",
        ha="left",
        va="center",
        fontsize=7.9,
        color="#111111",
    )
    lax.plot(
        [0.02, 0.11],
        [0.335, 0.335],
        color="#111111",
        linewidth=2.2,
    )
    lax.text(
        0.18,
        0.335,
        "国界 / International boundary",
        ha="left",
        va="center",
        fontsize=7.9,
        color="#111111",
    )

    # --- 地形晕渲示意 ---
    for i in range(40):
        frac = i / 39
        color = RELIEF_CMAP(frac)
        lax.add_patch(
            Rectangle(
                (0.02 + i * 0.0027, 0.265),
                0.0028,
                0.032,
                facecolor=color,
                edgecolor="none",
            )
        )
    lax.text(
        0.18,
        0.281,
        "地形晕渲 / Relief shading",
        ha="left",
        va="center",
        fontsize=7.9,
        color="#111111",
    )

    # --- 文字说明 ---
    lax.add_patch(
        Rectangle(
            (0.0, 0.09),
            1.0,
            0.115,
            facecolor="#f4f1e8",
            edgecolor="#d0c8b6",
            linewidth=0.6,
        )
    )
    lax.text(
        0.04,
        0.178,
        "地名均为中文 + English 双语",
        ha="left",
        va="center",
        fontsize=8.3,
        color="#333333",
    )
    lax.text(
        0.04,
        0.128,
        "All place names are bilingual (Chinese + English).",
        ha="left",
        va="center",
        fontsize=7.0,
        color="#555555",
    )

    lax.text(
        0.0,
        0.025,
        "7 邦 · 7 省 · 1 联邦区",
        ha="left",
        va="bottom",
        fontsize=10.2,
        color="#111111",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stride", type=int, default=None, help="ETOPO 采样步长; 缺省选分辨率最高的一个")
    parser.add_argument("--dpi", type=int, default=300, help="输出 PNG 分辨率, 默认 300")
    parser.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    args = parser.parse_args()

    etopo_path = map_lib.find_etopo(
        DATA_DIR,
        "myanmar",
        args.stride,
        env_path=os.environ.get("MYANMAR_ETOPO_PATH"),
    )
    if not etopo_path.exists():
        raise FileNotFoundError(
            f"未找到高程数据: {etopo_path}\n"
            "请先运行: python download_etopo.py"
        )

    if not ADMIN_GEOJSON.exists():
        raise FileNotFoundError(
            f"未找到行政区数据: {ADMIN_GEOJSON}\n请先运行: python prepare_admin_data.py"
        )
    units = load_admin_units()
    # 画布偏竖长: 投影后缅甸国土宽高比约 0.56, 右侧留 2.9 英寸给图例.
    fig = plt.figure(figsize=(13, 17), facecolor="white")
    ax = fig.add_axes([0.075, 0.045, 0.655, 0.855], projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    add_relief(ax, etopo_path)
    add_admin_fills(ax, units)
    add_rivers(ax)
    add_country_outline(ax)
    add_admin_labels(ax, units)
    add_place_labels(ax)
    add_scale_bar(ax)
    add_north_arrow(ax)

    # 经纬网: 经度每 2°, 纬度每 5°, 只留左侧和底部标签; 标签保持水平,
    # 因为圆锥投影下经线是斜的, 旋转后的数字不适合中文地图阅读习惯.
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        x_inline=False,
        y_inline=False,
        linewidth=0.45,
        color="#6f6f6f",
        alpha=0.38,
        linestyle="-",
        zorder=3.5,
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.rotate_labels = False
    gl.xlocator = mticker.FixedLocator(np.arange(92, 103, 2))
    gl.ylocator = mticker.FixedLocator(np.arange(10, 30, 5))
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER
    gl.xlabel_style = {"size": 8.5, "color": "#333333"}
    gl.ylabel_style = {"size": 8.5, "color": "#333333"}

    # 国界/地图边框: 线宽略粗, 让画面有明确边界.
    ax.spines["geo"].set_linewidth(0.8)
    ax.spines["geo"].set_edgecolor("#333333")

    # 标题与副标题用 figure 级文本, 避开 GeoAxes 的自动布局.
    fig.text(
        0.5,
        0.988,
        TITLE_ZH,
        ha="center",
        va="top",
        fontsize=25,
        color="#111111",
    )
    fig.text(
        0.5,
        0.955,
        TITLE_EN,
        ha="center",
        va="top",
        fontsize=12.8,
        color="#333333",
    )
    fig.text(
        0.5,
        0.933,
        SUBTITLE,
        ha="center",
        va="top",
        fontsize=9.4,
        color="#555555",
    )
    fig.text(
        0.5,
        0.012,
        SOURCE,
        ha="center",
        va="bottom",
        fontsize=7.6,
        color="#666666",
    )

    add_legend(fig)

    # 注意: 不能用 tight_layout/constrained_layout/bbox_inches="tight";
    # cartopy 的 gridliner 在非矩形投影上提前绘制时会触发 GEOS 异常或裁掉标签,
    # 与项目内 myanmar.py 的处理保持一致.
    fig.savefig(OUT_PNG, dpi=args.dpi)
    print(f"地图已保存: {OUT_PNG}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
