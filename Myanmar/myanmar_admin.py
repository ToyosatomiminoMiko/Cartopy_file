#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Administrative-division map of Myanmar.

是什么: 绘制缅甸省/邦级行政区划图, 七邦冷色、七省暖色、内比都联邦区中性色加
斜线, 叠加河流与 ETOPO 2022 地形晕渲, 并画出各行政区中心点;
国界用半透明红色、只画陆上段, 海岸线不单独绘制.
只绘制地理要素, 不绘制任何文字/图例/色标/标题/比例尺/指北针.
完整说明(配色、投影、数据来源、运行方式)见 ``docs/maps/myanmar-admin.md``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import geopandas as gpd  # 读取 Natural Earth shapefile
import matplotlib.colors as mcolors  # 颜色与色带
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网线位置定位
import numpy as np  # 数组运算
from shapely.geometry import LineString, shape  # GeoJSON -> Shapely / 取外环
from shapely.ops import unary_union  # 合并行政区, 得到缅甸整体轮廓

import map_lib  # 复用 ETOPO 读取、晕渲、海陆底色工具

# cartopy 底图缓存统一到仓库 data/cartopy, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy

configure_cartopy()

from cartopy_file.output import apply_svg_output, save_svg

# 国界/海岸线吻合处只画一条线: 用共享剪枝工具, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# 产物统一为 SVG, 见 docs/reference/output.md.
apply_svg_output()
# 斜线填充过密会在成品尺寸下糊成深色块, 这里保持项目里一致的细线.
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
    # 伊洛瓦底省与勃固省有很长的公共边界, 旧色 #ffb74d(浅橙) 与勃固省的
    # #f9a825(琥珀) 色相几乎相同(约 36°)、亮度也接近, 半透明叠在米色地形上
    # 几乎分不出界线; 改用 #ff8a65(deep orange 300) 把色相拉到橙红一侧,
    # 两者色差放大到约 3 倍, 同时与相邻的仰光省品红、若开邦青绿仍保持足够区分.
    "ayeyarwady": "#ff8a65",
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

# 国界配色(与 Ukraine 图一致): 红色半透明, 让地形与下层填色透出来.
COLOR_BORDER = "#c62828"
BORDER_ALPHA = 0.62
BORDER_WIDTH = 2.7
# 邻国国界: 中性灰虚线, 只作定位参照, 不与红色国界争视觉层级.
COLOR_NEIGHBOR = "#8a8a8a"

# 国界剪掉沿海段的缓冲半径(度). 本图不画海岸线, 海陆界线由底色/填色分界表达;
# 国界面本身沿海岸闭合, 整圈画出来就等于又画了一条红色海岸线, 所以只留陆上段.
# 0.06° 在 20°N 一带约 6 km, 覆盖两套折线的数字化偏差; 剪剩碎段按 3 km 丢掉.
COAST_CLIP_DEG = 0.06
COAST_CLIP_MIN_LEN = 0.03
# 邻国国界从缅甸国界两侧这么宽的走廊里剪掉, 避免红线下透出平行灰线.
NEIGHBOR_GAP_DEG = 0.06
# 省/邦界在国界、海岸走廊里剪掉的宽度(度). 这些填色单元的外缘与国界/海岸
# 完全重合, 不剪会在半透明红线下面透出一条深灰的省界线, 海岸上也会留下一圈
# 省界线 —— 都等于变相画了海岸线. 0.005° 约 550 m, 远小于图上国界线半宽.
BORDER_ZONE_DEG = 0.005

# 地形底纹: 从低地米白过渡到山地浅褐; 负高程(海洋)在 alpha 通道里挖掉.
RELIEF_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "myanmar_relief",
    ["#fbf8f0", "#eee5d4", "#d9c8aa", "#b7a17f"],
)
RELIEF_VMIN, RELIEF_VMAX = 0, 4200
RELIEF_ALPHA = 0.55

# 输出路径(脚本同目录), 见 docs/reference/output.md.
OUT_SVG = ROOT / "myanmar_administrative_divisions_bilingual.svg"


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


def country_exterior(myanmar_geom):
    """只取行政区并集的外环(真正的国界), 丢掉内部的零面积细缝.

    为什么需要: 15 个单元的相邻边来自不同折线, 逐点浮点误差会让 unary_union
    在内部边界上留下零面积的细缝(interior ring). 直接画 ``polygon.boundary``
    会把这些细缝的环也当成国界画出来 —— 半透明红线在掸邦-克钦邦、仰光省-勃固省
    这些内部边界上就会留下一串红色短段. 外环才是国界; 内部细缝既不画线, 也不
    参与省/邦界的剪枝走廊. 返回 MultiLineString, 并集为空时返回 None.
    """
    parts = getattr(myanmar_geom, "geoms", [myanmar_geom])
    rings = [
        LineString(part.exterior.coords)
        for part in parts
        if part.geom_type == "Polygon" and not part.exterior.is_empty
    ]
    if not rings:
        return None
    return unary_union(rings)


def add_relief(ax: plt.Axes, etopo_path: Path, myanmar_geom) -> None:
    """铺海陆底色, 叠加只覆盖陆地的低透明度地形晕渲, 并画邻国国界参照.

    海岸线不画: 海与陆靠底色与行政区填色分界, Natural Earth 的国家面轮廓
    会把海岸线一起描出来, 所以这里不画 ``world.geometry``, 只用
    ``admin_0_boundary_lines_land`` 画邻国国界(细灰虚线), 并从缅甸国界走廊
    里剪掉, 免得与红色国界并行成双线.
    """
    world = map_lib.load_countries(COUNTRY_DIR)
    map_lib.add_base_map(ax, world, ocean_color=OCEAN_COLOR, land_color=LAND_COLOR)

    land_borders = map_lib.load_ne_layer("10m", "cultural", "admin_0_boundary_lines_land")
    if land_borders is not None:
        others = unary_union(map_lib.clip_to_axes(ax, list(land_borders.geometry)))
        others = others.difference(myanmar_geom.buffer(NEIGHBOR_GAP_DEG))
        if not others.is_empty:
            ax.add_geometries(
                [others],
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=COLOR_NEIGHBOR,
                linewidth=0.45,
                linestyle=(0, (5, 3)),
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


def add_admin_fills(ax: plt.Axes, units, border_zone) -> None:
    """按邦/省/联邦区填色, 再统一描内部边界.

    先画无边框的填充, 再单独画边界, 避免半透明填充在相邻边界处叠成
    一条颜色更深的粗线; 内比都联邦区最后画, 保证斜线填充不被覆盖.

    省/邦界的沿海段与国家边界段用 ``border_zone`` 剪掉: 单元面沿海岸闭合,
    不剪就会在海岸上留一圈深灰省界线, 等于变相画了海岸线; 与红色国界重合
    的那一段不剪则会从半透明红线下面透出来, 让国界发灰.
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
    # 逐个单元剪枝(而不是合并后再剪): 相邻两州的公共边界仍各画一遍, 与改前
    # 一样叠出略深的线; 只想去掉贴着国界/海岸的那一段.
    for unit in units:
        if unit["kind"] == "union":
            continue
        edge = cut(unit["geometry"].boundary, border_zone)
        if edge is None:
            continue
        ax.add_geometries(
            [edge],
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


def add_country_outline(ax: plt.Axes, border) -> None:
    """用半透明红线画缅甸陆上国界, 与内部省/邦界区分; 海岸线不画.

    国界取自 15 个行政区并集的**外环**(见 `country_exterior`), 与填色同源,
    所以红线一定压在填色边缘上; 内部零面积细缝不画, 免得在省/邦界上留下红色
    短段. 沿海段先按 Natural Earth 海岸线缓冲剪掉: 本图不画海岸线, 海陆界线
    由底色与填色分界表达, 若红线沿整圈海岸画就会变成一条红色海岸线. 剪掉的
    岸段也不补画, 岸线只留颜色分界.
    """
    coastline = map_lib.load_ne_layer("10m", "physical", "coastline")
    if coastline is not None:
        coast = unary_union(map_lib.clip_to_axes(ax, list(coastline.geometry)))
        border = cut(
            border,
            overlap_mask([coast], COAST_CLIP_DEG),
            min_length_deg=COAST_CLIP_MIN_LEN,
        )
    else:
        print("警告: 缺少海岸线数据, 国界无法剪掉沿海段, 将画出完整国界.")
    if border is None:
        return
    ax.add_geometries(
        [border],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=COLOR_BORDER,
        linewidth=BORDER_WIDTH,
        alpha=BORDER_ALPHA,
        zorder=10,
    )


def add_admin_centres(ax: plt.Axes, units) -> None:
    """画出各行政区中心: 联邦区/首都用星形, 其余用空心圆."""
    for unit in units:
        lon = unit["capital_lon"]
        lat = unit["capital_lat"]
        if unit["kind"] == "union":
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stride", type=int, default=None, help="ETOPO 采样步长; 缺省选分辨率最高的一个")
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="内嵌晕渲栅格的像素密度(dpi); 矢量部分与 dpi 无关, 默认 300",
    )
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
    # 国界与省/邦界都以 15 个行政区合并后的外环为基准: 填色与红线同源,
    # 岸上不会出现两套边界; border_zone 用来剪掉省/邦界里与国界/海岸重合的段.
    # 只取外环是为了丢掉并集内部因浮点误差产生的零面积细缝 —— 否则红线会在
    # 掸邦-克钦邦、仰光省-勃固省等内部边界上残留一串红色短段.
    myanmar_geom = unary_union([unit["geometry"] for unit in units])
    country_border = country_exterior(myanmar_geom)
    if country_border is None:
        raise ValueError("行政区并集没有外环, 无法确定国界")
    border_zone = country_border.buffer(BORDER_ZONE_DEG)
    # 画布偏竖长: 投影后缅甸国土宽高比约 0.56.
    fig = plt.figure(figsize=(13, 17), facecolor="white")
    ax = fig.add_axes([0.075, 0.045, 0.655, 0.855], projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    add_relief(ax, etopo_path, myanmar_geom)
    add_admin_fills(ax, units, border_zone)
    add_rivers(ax)
    add_country_outline(ax, country_border)
    add_admin_centres(ax, units)

    # 经纬网: 经度每 2°, 纬度每 5°, 位置由 locator 固定; 只画网线, 不画刻度文字.
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=False,
        linewidth=0.45,
        color="#6f6f6f",
        alpha=0.38,
        linestyle="-",
        zorder=3.5,
    )
    gl.xlocator = mticker.FixedLocator(np.arange(92, 103, 2))
    gl.ylocator = mticker.FixedLocator(np.arange(10, 30, 5))

    # 国界/地图边框: 线宽略粗, 让画面有明确边界.
    ax.spines["geo"].set_linewidth(0.8)
    ax.spines["geo"].set_edgecolor("#333333")

    # 注意: 不能用 tight_layout/constrained_layout/bbox_inches="tight";
    # cartopy 的 gridliner 在非矩形投影上提前绘制时会触发 GEOS 异常或裁掉画面,
    # 与项目内 myanmar.py 的处理保持一致.
    save_svg(fig, OUT_SVG, dpi=args.dpi)
    print(f"地图已保存: {OUT_SVG}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
