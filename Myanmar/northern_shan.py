#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# northern_shan.py
# 以掸邦北部为中心, 绘制缅甸联邦第一特区(MNDAA 实控区)、佤邦、
# 掸邦东部第四特区及其周边直到曼德勒的地形图.
# 地形: NOAA ETOPO 2022 15 弧秒子集; 行政/控制区边界: OpenStreetMap.
# 运行前先执行:
#   python download_etopo.py --region northern_shan --stride 1
#   python download_regions.py
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Topographic map of northern Shan State's special/armed-group regions.

范围: 95.3~101.5°E, 21.0~24.75°N. 北到果敢/勐古的中缅边界, 南到曼德勒,
东到湄公河(老挝边界), 西到曼德勒省/掸邦西界.

为什么选这个范围: 用户要求"以掸邦北部为中心", 并同时包含第一特区、
佤邦、第四特区, 最南到曼德勒. 四个区域里第四特区(南板县)最南到 21.0°N,
比曼德勒还低约 1°, 所以画框南界取 21.0°N 才能完整装下第四特区;
曼德勒位于画框西南部, 作为南端的定位城市.

投影: 兰勃特等角圆锥投影(Lambert Conformal Conic), 中央经线 98.4°E,
标准纬线 21.5°N 与 24.5°N. 本区域东西约 6.2°、南北约 3.75°, 圆锥投影
在两条标准纬线之间比例误差极小, 且经线收敛方向与掸邦南北走向一致,
比等经纬度投影(高纬横向拉伸)更接近真实形状.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BOUNDARY_DIR = DATA_DIR / "ne_10m_admin_0_countries"
REGION_GEOJSON = DATA_DIR / "regions" / "shan_north_boundaries.geojson"

# 缓存目录必须在导入 matplotlib/cartopy 之前指定(与 myanmar.py 同理).
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy  # 用来把内置 Natural Earth 数据缓存改到工作区内
import cartopy.crs as ccrs  # 地图投影
import cartopy.feature as cfeature  # 海岸线/国界/河流等自然要素
import matplotlib.cm as cm  # 独立色标用的 ScalarMappable
import matplotlib.patheffects as pe  # 文字描边
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网刻度定位
import numpy as np  # 数组运算
from matplotlib.lines import Line2D  # 图例中的线要素
from matplotlib.patches import Patch  # 图例中的面要素
from shapely.geometry import shape  # GeoJSON -> Shapely
from shapely.ops import unary_union  # 合并同类边界

import map_lib  # 与本目录共用的 ETOPO/晕渲/边界工具

# cartopy 默认把下载的 shapefile 放到 ~/.local/share/cartopy, 本机该目录不可写;
# 改到工作区 data/ 下, 既绕开只读限制, 也方便清理/复现.
cartopy.config["data_dir"] = str(DATA_DIR / "cartopy")
(DATA_DIR / "cartopy").mkdir(parents=True, exist_ok=True)

# 全局字体: 项目根目录 fonts.py 统一设置. 汉字用 Noto Sans Mono CJK SC,
# 英文/数字用 JetBrains Mono Slashed Medium, 逐字符回退; 本脚本不再单独配字体.
sys.path.insert(0, str(ROOT.parent))
from fonts import apply_matplotlib_fonts

apply_matplotlib_fonts()
# 斜线填充的线宽: 默认 1.0 在 300 dpi 下偏粗, 会把特区填充压成深色块.
plt.rcParams["hatch.linewidth"] = 0.45


# ============================
# 配置
# ============================
# 画框: [min_lon, max_lon, min_lat, max_lat]; 取值理由见文件顶部说明.
EXTENT = [95.3, 101.5, 21.0, 24.75]

# 投影参数: 中央经线取掸邦北部中部, 标准纬线夹住画框南北界.
PROJECTION = ccrs.LambertConformal(
    central_longitude=98.4,
    central_latitude=23.0,
    standard_parallels=(21.5, 24.5),
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
REGION_STYLES = {
    "sr1": {
        "fill": "#8c6bb1",
        "edge": "#4a1486",
        "alpha": 0.24,
        "linewidth": 2.2,
        "label": "缅甸联邦第一特区",
    },
    "wa": {
        "fill": "#2b8cbe",
        "edge": "#045a8d",
        "alpha": 0.22,
        "linewidth": 1.9,
        "label": "佤邦",
    },
    "sr4": {
        "fill": "#f16913",
        "edge": "#a63603",
        "alpha": 0.22,
        "linewidth": 1.9,
        "label": "掸邦东部第四特区",
    },
}
# 区域内部县/特区界: 白色虚线, 在填充与地形上都看得清.
INTERNAL_EDGE_COLOR = "#ffffff"
# MNDAA 实控区斜线: 与第一特区同范围, 用斜线表示"实控", 填充色表示"辖区".
MNDAA_HATCH = "///"
MNDAA_HATCH_COLOR = "#4a1486"

# 城市标注: (经度, 纬度, 名称, 类型, 文字偏移经度, 文字偏移纬度).
# 类型: capital=特区首府(星形), major=区域中心城市(大方点), town=普通城镇(小圆点).
CITIES = [
    (98.764, 23.695, "老街", "capital", 0.0, 0.14),
    (99.167, 22.179, "邦康", "capital", 0.05, -0.10),
    (100.022, 21.676, "勐拉", "capital", 0.06, -0.06),
    (96.095, 21.960, "曼德勒", "major", 0.06, 0.0),
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
]

# 大区域/邻国标注: (经度, 纬度, 文字, 字号, 颜色).
REGION_LABELS = [
    (98.30, 23.72, "缅甸联邦第一特区", 13.5, "#4a1486"),
    (98.25, 23.08, "MNDAA 实控区\n(大致范围)", 9.5, "#4a1486"),
    (98.99, 22.60, "佤邦", 16, "#045a8d"),
    (99.79, 21.73, "掸邦东部\n第四特区", 10.0, "#a63603"),
]
AREA_LABELS = [
    (99.05, 24.62, "中国 云南省", 13, "#444444"),
    (101.33, 21.55, "老挝", 12, "#444444"),
    (96.75, 23.78, "掸邦", 13, "#666666"),
    (95.72, 22.45, "曼德勒省", 11, "#666666"),
]

# 图标题与输出路径.
TITLE = (
    "缅甸掸邦北部特区与地方武装控制区地形图（2026年10月）\n"
    "NOAA ETOPO 2022 | 边界: OpenStreetMap / Natural Earth | "
    "兰勃特等角圆锥投影(中央经线 98.4°E)"
)
OUT_PNG = ROOT / "northern_shan_topography_etopo2022_lambert_conformal.png"


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


# ============================
# 绘图
# ============================
def add_relief(ax: plt.Axes, etopo_path: Path):
    """读取高程并叠加晕渲地形, 返回色标用的 (norm, cmap)."""
    lon, lat, z = map_lib.load_elevation(etopo_path)
    relief, norm, cmap = map_lib.make_relief(
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
    return norm, cmap


def add_context(ax: plt.Axes, world) -> None:
    """绘制国界、省/邦界、河流与湖泊, 作为区域色块下方的地理参照."""
    # 国界用深红色实线突出; 注意用 edgecolor 而非 color(facecolor 被预设为 never).
    if world is not None:
        myanmar = world[world["NAME"].isin(("Myanmar", "Burma"))] if "NAME" in world else None
        if myanmar is not None and not myanmar.empty:
            ax.add_geometries(
                [unary_union(myanmar.geometry)],
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor="#8b0000",
                linewidth=2.0,
                zorder=6,
            )

    ax.add_feature(
        cfeature.BORDERS.with_scale("10m"),
        edgecolor="#555555",
        linewidth=0.6,
        linestyle="--",
        zorder=5,
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


def add_admin_context(ax: plt.Axes, regions: dict[str, list]) -> None:
    """绘制掸邦与曼德勒省边界, 让读者知道色块在掸邦内部的位置."""
    context = regions.get("context", [])
    for props, geom in context:
        ax.add_geometries(
            [geom],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor="#7f7f7f",
            linewidth=1.0,
            linestyle=(0, (6, 3)),
            zorder=5.5,
        )


def add_special_regions(ax: plt.Axes, regions: dict[str, list]) -> None:
    """按图层绘制四个区域的填充、外边界与内部县界."""
    # 先画三个区域的填充与边界(第一特区最后画, 压在佤邦/四特之上).
    draw_order = ["wa", "sr4", "sr1"]
    for layer in draw_order:
        style = REGION_STYLES[layer]
        geom = unary_union([g for _, g in regions[layer]])
        ax.add_geometries(
            [geom],
            crs=ccrs.PlateCarree(),
            facecolor=style["fill"],
            edgecolor=style["edge"],
            alpha=style["alpha"],
            linewidth=0,
            zorder=2.5,
        )
        ax.add_geometries(
            [geom],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=style["edge"],
            linewidth=style["linewidth"],
            zorder=6.5,
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
    for layer in ("sr1_county", "wa_district", "sr4_county"):
        for _, geom in regions.get(layer, []):
            ax.add_geometries(
                [geom],
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=INTERNAL_EDGE_COLOR,
                linewidth=0.65,
                linestyle="--",
                alpha=0.85,
                zorder=6.0,
            )


def add_text_labels(ax: plt.Axes) -> None:
    """标注区域名、邻国/省名与城市, 全部使用白色描边保证可读性."""
    halo = [pe.withStroke(linewidth=3.0, foreground="white")]

    for lon, lat, text, size, color in AREA_LABELS:
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=size,
            color=color,
            ha="center",
            va="center",
            path_effects=halo,
            zorder=8,
        )

    # 区域名: 第一特区/佤邦/四特名加粗效果通过字号与颜色实现
    # (本机 CJK 可变字体在 matplotlib 里只有默认实例, 不能用 fontweight="bold").
    for lon, lat, text, size, color in REGION_LABELS:
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=size,
            color=color,
            ha="center",
            va="center",
            path_effects=halo,
            zorder=9,
        )

    for lon, lat, name, kind, dx, dy in CITIES:
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
        ax.text(
            lon + dx,
            lat + dy,
            name,
            transform=ccrs.PlateCarree(),
            fontsize=9 if kind == "town" else 10.5,
            color="black",
            ha="center" if kind == "town" else "left",
            va="center",
            path_effects=halo,
            zorder=11,
        )


def add_legend(ax: plt.Axes) -> None:
    """在画框左上角的空余地形上放图例.

    用图例句柄手工构造, 而不是依赖 ax.legend 的自动识别: cartopy 的
    FeatureArtist 不会出现在句柄里, 手工构造能保证图例与图上样式一致.
    """
    handles = [
        Patch(
            facecolor=REGION_STYLES["sr1"]["fill"],
            edgecolor=REGION_STYLES["sr1"]["edge"],
            alpha=0.6,
            linewidth=1.5,
            label="缅甸联邦第一特区(辖区)",
        ),
        Patch(
            facecolor="none",
            edgecolor=MNDAA_HATCH_COLOR,
            hatch=MNDAA_HATCH,
            linewidth=0,
            label="MNDAA 实控区(大致)",
        ),
        Patch(
            facecolor=REGION_STYLES["wa"]["fill"],
            edgecolor=REGION_STYLES["wa"]["edge"],
            alpha=0.6,
            linewidth=1.5,
            label="佤邦",
        ),
        Patch(
            facecolor=REGION_STYLES["sr4"]["fill"],
            edgecolor=REGION_STYLES["sr4"]["edge"],
            alpha=0.6,
            linewidth=1.5,
            label="掸邦东部第四特区",
        ),
        Line2D([0], [0], color="#8b0000", linewidth=2.0, label="国界"),
        Line2D([0], [0], color="#7f7f7f", linewidth=1.0, linestyle="--", label="省/邦界"),
        Line2D([0], [0], color="#1f78b4", linewidth=0.9, label="河流"),
        Line2D(
            [0],
            [0],
            marker="*",
            color="none",
            markerfacecolor="#ffd200",
            markeredgecolor="black",
            markersize=12,
            label="特区首府",
        ),
    ]
    legend = ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.012, 0.988),
        fontsize=9.5,
        title="图例",
        title_fontsize=10.5,
        frameon=True,
        framealpha=0.88,
        borderpad=0.7,
        labelspacing=0.55,
        handlelength=1.8,
    )
    legend.set_zorder(20)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stride", type=int, default=None, help="指定 data/ 下的采样步长文件")
    parser.add_argument("--dpi", type=int, default=300, help="输出 PNG 分辨率, 默认 300")
    parser.add_argument("--show", action="store_true", help="保存后弹出交互窗口")
    args = parser.parse_args()

    etopo_path = map_lib.find_etopo(DATA_DIR, "northern_shan", args.stride)
    if not etopo_path.exists():
        raise FileNotFoundError(
            f"未找到高程数据: {etopo_path}\n"
            "请先运行: python download_etopo.py --region northern_shan --stride 1"
        )
    regions = load_regions(REGION_GEOJSON)

    # 画布 16x10.6, 地图轴区域比例与投影后画框比例(约 1.55)一致,
    # 避免 GeoAxes 为保持等比例而留下过大空白.
    fig = plt.figure(figsize=(16, 10.6), facecolor="white")
    ax = fig.add_axes([0.05, 0.075, 0.80, 0.785], projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    world = map_lib.load_countries(BOUNDARY_DIR)
    map_lib.add_base_map(
        ax,
        world,
        ocean_color=BASE_OCEAN_COLOR,
        land_color=BASE_LAND_COLOR,
    )
    norm, cmap = add_relief(ax, etopo_path)
    add_admin_context(ax, regions)
    add_context(ax, world)
    add_special_regions(ax, regions)

    # 色标独立占一个轴, 不抢占地图宽度.
    cax = fig.add_axes([0.868, 0.26, 0.015, 0.46])
    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])
    cbar = fig.colorbar(mappable, cax=cax, label="高程 (m)", extend="max")
    cbar.set_ticks(np.arange(0, 3001, 500))

    add_text_labels(ax)
    add_legend(ax)

    # 经纬网: 经度每 1°、纬度每 1°, 只在左侧和底部标注.
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        x_inline=False,
        y_inline=False,
        linewidth=0.45,
        color="gray",
        alpha=0.5,
        linestyle="-",
        zorder=7,
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.rotate_labels = False
    gl.xlocator = mticker.FixedLocator(np.arange(96, 102, 1))
    gl.ylocator = mticker.FixedLocator(np.arange(21, 25, 1))
    gl.xlabel_style = {"size": 9.5, "color": "#444444"}
    gl.ylabel_style = {"size": 9.5, "color": "#444444"}

    fig.suptitle(TITLE, fontsize=17, y=0.985, va="top")
    fig.text(
        0.5,
        0.021,
        "地形数据: NOAA NCEI ETOPO 2022(15 弧秒) | 边界: Natural Earth 10m / "
        "OpenStreetMap(ODbL, 2026-10) | MNDAA=缅甸民族民主同盟军",
        ha="center",
        va="bottom",
        fontsize=8.5,
        color="#666666",
    )
    fig.text(
        0.5,
        0.006,
        "注: MNDAA 实控区与第一特区辖区大体重合, 图中以斜线示意; "
        "特区与实控区范围据公开资料近似绘制, 仅供参考",
        ha="center",
        va="bottom",
        fontsize=8.5,
        color="#666666",
    )

    # 与 myanmar.py 相同: 不用 tight_layout/bbox_inches="tight".
    # 原因: cartopy 0.25 在非矩形投影上提前绘制经纬网标签会触发
    # gridliner 用未闭合顶点构造多边形的 GEOSException, 且 tight bbox 会裁掉标签.
    fig.savefig(OUT_PNG, dpi=args.dpi)
    print(f"地图已保存: {OUT_PNG}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
