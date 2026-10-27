#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Topographic map of Shan State's special/armed-group regions.

是什么: 以掸邦为中心绘制缅甸联邦第一特区、德昂邦、佤邦、掸邦东部第四特区及
周边的地形图, 并在第一特区内标出其前身"原果敢自治区"的范围.
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

from cartopy_file.output import apply_svg_output, save_svg

# 产物统一为 SVG, 见 docs/reference/output.md.
apply_svg_output()
# 斜线填充的线宽: 默认 1.0 在成品尺寸下偏粗, 会把特区填充压成深色块.
plt.rcParams["hatch.linewidth"] = 0.45


# ============================
# 配置
# ============================
# 画框: [min_lon, max_lon, min_lat, max_lat]; 取值理由见 docs/maps/northern-shan.md.
EXTENT = [95.3, 101.5, 19.0, 24.75]

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
# 与它重合的区域边界.
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

# 城市点: (经度, 纬度, 类型).
# 类型: capital=特区首府(星形), major=区域中心城市(大方点), town=普通城镇(小圆点).
CITIES = [
    (98.764, 23.695, "capital"),
    (99.167, 22.179, "capital"),
    (100.022, 21.676, "capital"),
    (96.095, 21.960, "major"),
    (97.036, 20.784, "major"),
    (99.882, 20.447, "major"),
    (97.209, 19.674, "major"),
    (97.745, 22.942, "major"),
    (97.901, 23.998, "town"),
    (97.683, 23.835, "town"),
    (97.932, 23.458, "town"),
    (97.966, 23.304, "town"),
    (98.655, 23.418, "town"),
    (98.825, 23.477, "town"),
    (98.308, 24.101, "town"),
    (98.100, 23.580, "town"),
    (98.965, 22.971, "town"),
    (99.307, 22.009, "town"),
    (100.652, 21.395, "town"),
    (99.805, 21.851, "town"),
    (99.600, 21.290, "town"),
    (98.395, 22.494, "town"),
    (97.562, 20.925, "town"),
]

# 两条大江的强调线所对应的 Natural Earth name_en.
MAIN_RIVERS = ("Irrawaddy", "Salween")

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


def add_relief(ax: plt.Axes, etopo_path: Path) -> None:
    """读取高程并叠加晕渲地形."""
    lon, lat, z = map_lib.load_elevation(etopo_path)
    relief, _, _ = map_lib.make_relief(
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


def add_city_markers(ax: plt.Axes) -> None:
    """绘制城市点: 特区首府用星形, 区域中心城市用方点, 普通城镇用小圆点."""
    for lon, lat, kind in CITIES:
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
    add_relief(ax, etopo_path)
    add_admin_context(ax, regions, border_zone)
    add_context(ax, border_line)
    # 两条大江压在一般河流与区域填充之上、国界/区域边界之下.
    add_main_rivers(ax)
    add_special_regions(ax, regions, border_zone)

    add_city_markers(ax)

    # 经纬网: 经度每 1°、纬度每 1°, 只画网线, 不画刻度文字.
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=False,
        linewidth=0.45,
        color="gray",
        alpha=0.5,
        linestyle="-",
        zorder=7,
    )
    gl.xlocator = mticker.FixedLocator(np.arange(96, 102, 1))
    gl.ylocator = mticker.FixedLocator(np.arange(19, 25, 1))

    # 与 myanmar.py 相同: 不用 tight_layout/bbox_inches="tight":
    # cartopy 0.25 在非矩形投影上会由 gridliner 用未闭合顶点构造多边形而抛 GEOSException.
    save_svg(fig, OUT_SVG, dpi=args.dpi)
    print(f"地图已保存: {OUT_SVG}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
