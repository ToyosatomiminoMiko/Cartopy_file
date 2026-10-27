#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Administrative-division map of Myanmar.

是什么: 绘制缅甸省/邦级行政区划图, 七邦冷色、七省暖色、内比都联邦区中性色加
斜线, 叠加河流与 ETOPO 2022 地形晕渲, 并画出各行政区中心点;
国界用半透明红色、只画陆上段, 海岸线不单独绘制.
只绘制地理要素: 文字/图例/色标/标题/刻度文字/比例尺/指北针都不画进底图,
而是以数据形式写进同名 ``<产物>.geo.json``; 文字与版面由前端接管, 本脚本同时
产出同名 geo.json, 字段与裁剪口径见 ``docs/reference/geo.md``. 比例尺、指北针
属契约非目标, 本图不产出.
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

# 底图 + geo.json 出图: save_map 同时写裁到地图框的 SVG 与同名 geo.json,
# 见 docs/reference/geo.md.
from cartopy_file.geo import (
    GeoDoc,
    figure_frame,
    relief_from_cmap,
    save_map,
)

# 国界/海岸线吻合处只画一条线: 用共享剪枝工具, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# 产物统一为 SVG, 见 docs/reference/output.md.
from cartopy_file.output import apply_svg_output

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
# 色标刻度: 旧图没有数字色标(只在图例里示意晕渲), 这里取整千米, 供前端色标组件使用.
RELIEF_TICKS = (0, 1000, 2000, 3000, 4000)

# ============================
# 标注数据(只登记进 geo, 底图不画文字)
# ============================
# 旧版双语文字是中文、英文两条独立 annotate: 英文行统一用这个灰色且 halo 收窄,
# 不跟随中文行的配色; 这里保留同一口径, 前端的默认排版才能与旧成品一致.
EN_LABEL_COLOR = "#303030"

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
# 旧版从 ADMIN_LABELS 里给 npt/yangon/mon 引一条细线到实际区域; 契约 v2 的
# labels[].leader 尚未输出(非目标), 这里只保留锚点数据, 不画引线也不生成字段.
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
# 两条大江的名称与落点(经度, 纬度): 位置避开了主要行政区名和行政中心点.
RIVER_LABELS = [
    (95.12, 18.45, "伊洛瓦底江", "Irrawaddy River"),
    (98.55, 20.55, "萨尔温江", "Salween River"),
]

TITLE_ZH = "缅甸联邦共和国行政区划图"
TITLE_EN = "ADMINISTRATIVE DIVISIONS OF THE REPUBLIC OF THE UNION OF MYANMAR"
SUBTITLE = (
    "七邦（冷色）· 七省（暖色）· 内比都联邦区　　"
    "7 States (cool colours) · 7 Regions (warm colours) · Naypyidaw Union Territory"
)
SOURCE = (
    "行政区划: GADM 4.1 / OpenStreetMap (ODbL)　|　"
    "国界: 行政区合并轮廓(仅陆上段)　|　河流·海岸线剪枝: Natural Earth 10m　|　"
    "地形: NOAA ETOPO 2022　|　投影: Lambert Conformal Conic"
)

# 经纬网样式: 与 add_gridlines 画出的线同源(实线 0.45pt / #6f6f6f / 透明度 0.38).
GRATICULE_STYLE = {
    "stroke": "#6f6f6f",
    "width_pt": 0.45,
    "dash": None,
    "opacity": 0.38,
}

# 图例顺序按旧面板: 先 7 邦(冷色), 再 7 省(暖色), 最后联邦区; geojson 里的
# 行政区顺序不是旧面板顺序, 所以单独列一份.
LEGEND_STATE_KEYS = ("kachin", "kayah", "kayin", "chin", "mon", "rakhine", "shan")
LEGEND_REGION_KEYS = (
    "sagaing",
    "magway",
    "mandalay",
    "bago",
    "ayeyarwady",
    "yangon",
    "tanintharyi",
)

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


# ============================
# geo.json 收集(文字只登记, 不画)
# ============================
def _offset_lonlat(
    ax: plt.Axes, lon: float, lat: float, dx_pt: float, dy_pt: float
) -> tuple[float, float]:
    """把「以磅为单位的文字偏移」换算成经纬度, 供 ``doc.add_label`` 使用.

    为什么需要: 旧版用 annotate 的 offset points 排双语两行(行间距应与字号相关,
    不随纬度变化), 而 geo.add_label 只接受经纬度; 先在显示坐标里加偏移, 再反投影
    回经纬度, 落点就与旧版逐点一致.
    """
    transform = ccrs.PlateCarree()._as_mpl_transform(ax)
    display_x, display_y = transform.transform((lon, lat))
    scale = ax.figure.dpi / 72.0
    projection_x, projection_y = ax.transData.inverted().transform(
        (display_x + dx_pt * scale, display_y + dy_pt * scale)
    )
    out_lon, out_lat = ccrs.PlateCarree().transform_point(
        projection_x, projection_y, ax.projection
    )
    return float(out_lon), float(out_lat)


def _add_bilingual(
    doc: GeoDoc,
    ax: plt.Axes,
    lon: float,
    lat: float,
    zh: str,
    en: str,
    *,
    kind: str,
    id_kind: str,
    name: str,
    size_zh: float,
    size_en: float,
    color_zh: str,
    halo_pt: float,
    dx: float = 0.0,
    dy_zh: float = 4.0,
    dy_en: float = -7.0,
    ha: str = "center",
) -> None:
    """登记一对中文/英文标签: 旧版两条 annotate 的落点与样式, 改成两条 add_label.

    为什么英文单独一条: 旧版 en 是独立文字(字号更小、位置另给、id 带 ``-en``),
    前端要能分别拖动/改样式; 英文行颜色与 halo 也按旧版统一收窄(见 EN_LABEL_COLOR).
    """
    zh_lon, zh_lat = _offset_lonlat(ax, lon, lat, dx, dy_zh)
    doc.add_label(
        ax,
        zh_lon,
        zh_lat,
        zh,
        kind=kind,
        id_kind=id_kind,
        name=name,
        font_size_pt=size_zh,
        color=color_zh,
        ha=ha,
        va="center",
        halo={"color": "#ffffff", "width_pt": halo_pt},
    )
    en_lon, en_lat = _offset_lonlat(ax, lon, lat, dx, dy_en)
    doc.add_label(
        ax,
        en_lon,
        en_lat,
        en,
        kind=kind,
        id_kind=id_kind,
        name=f"{name}-en",
        font_size_pt=size_en,
        color=EN_LABEL_COLOR,
        ha=ha,
        va="center",
        halo={"color": "#ffffff", "width_pt": halo_pt * 0.8},
    )


def collect_labels(doc: GeoDoc, ax: plt.Axes, units) -> None:
    """把旧版图上的全部地名登记成 geo.labels(38 对, 中英各一条, 共 76 条).

    为什么按 zorder 升序登记: 契约的 ``order`` 是原图绘制顺序(前端 scene 按它
    叠放); 旧图 zorder 依次是邻国/海域 11、行政区名 13、行政中心与河名 14,
    同一 zorder 内按插入顺序, 所以这里先国名/海名, 再行政区名, 再行政中心,
    最后河名, 与旧成品 SVG 的绘制顺序一致.
    """
    # 邻国名称.
    for lon, lat, zh, en in NEIGHBOUR_LABELS:
        _add_bilingual(
            doc,
            ax,
            lon,
            lat,
            zh,
            en,
            kind="country",
            id_kind="country",
            name=zh,
            size_zh=12.0,
            size_en=8.4,
            color_zh="#4a4a4a",
            halo_pt=3.4,
            dy_zh=4.0,
            dy_en=-7.0,
        )

    # 海域名称.
    for lon, lat, zh, en in SEA_LABELS:
        _add_bilingual(
            doc,
            ax,
            lon,
            lat,
            zh,
            en,
            kind="sea",
            id_kind="sea",
            name=zh,
            size_zh=11.5,
            size_en=8.0,
            color_zh="#1c5f8a",
            halo_pt=3.2,
            dy_zh=3.5,
            dy_en=-6.5,
        )

    # 行政区名: id 前缀保留旧版的 state/region/union(用 id_kind), 契约 kind 记 area.
    for unit in units:
        key = unit["key"]
        lon, lat = ADMIN_LABELS[key]
        is_union = unit["kind"] == "union"
        small = key in {"kayah", "mon", "yangon", "npt"}
        # 内比都的英文全名太长, 在图上压到隔壁单元; 用 U.T. 缩写,
        # 图例和标题里保留全称 Naypyidaw Union Territory.
        display_en = "Naypyidaw U.T." if is_union else unit["name_en"]
        size_zh = 8.8 if is_union else (10.3 if small else (10.8 if unit["kind"] == "state" else 10.5))
        size_en = 6.4 if is_union else (6.9 if small else 7.8)
        _add_bilingual(
            doc,
            ax,
            lon,
            lat,
            unit["name_zh"],
            display_en,
            kind="area",
            id_kind=unit["kind"],
            name=key,
            size_zh=size_zh,
            size_en=size_en,
            color_zh="#111111",
            halo_pt=3.2,
            dy_zh=4.2,
            dy_en=-7.0,
        )

    # 行政中心: 联邦区标签已经用行政区名表达, 不再重复写一次 "内比都".
    for unit in units:
        if unit["kind"] == "union":
            continue
        key = unit["key"]
        dx, dy, ha = CAPITAL_OFFSETS[key]
        _add_bilingual(
            doc,
            ax,
            unit["capital_lon"],
            unit["capital_lat"],
            unit["capital_zh"],
            unit["capital_en"],
            kind="city",
            id_kind="city",
            name=unit["capital_zh"],
            size_zh=8.0,
            size_en=6.5,
            color_zh="#111111",
            halo_pt=2.6,
            dx=dx,
            dy_zh=dy + 2.6,
            dy_en=dy - 5.0,
            ha=ha,
        )

    # 两条大江的河名.
    for lon, lat, zh, en in RIVER_LABELS:
        _add_bilingual(
            doc,
            ax,
            lon,
            lat,
            zh,
            en,
            kind="river",
            id_kind="river",
            name=zh,
            size_zh=9.0,
            size_en=6.8,
            color_zh="#0d47a1",
            halo_pt=2.8,
            dy_zh=3.5,
            dy_en=-6.0,
        )


def collect_graticule(doc: GeoDoc, ax: plt.Axes) -> None:
    """登记经纬刻度(值/文字/与地图框边线的交点), 网线已由 main 画好."""
    doc.add_graticule(
        ax,
        EXTENT,
        lon_step=2.0,
        lat_step=5.0,
        lon_side="bottom",
        lat_side="left",
        style=GRATICULE_STYLE,
    )


def collect_relief(doc: GeoDoc) -> None:
    """登记地形色标: 与 add_relief 的晕渲同一条色带(0~4200 m), 刻度取整千米."""
    doc.set_relief(
        relief_from_cmap(
            RELIEF_CMAP,
            title="高程",
            unit="m",
            vmin=RELIEF_VMIN,
            vmax=RELIEF_VMAX,
            ticks=RELIEF_TICKS,
        )
    )


def collect_legend(doc: GeoDoc, units) -> None:
    """把旧版自绘的 7 邦/7 省色块面板改成 geo.legend.entries(按旧面板顺序平铺).

    为什么分组不单独出条目: 图例条目只能表达「一条符号」, 旧面板的「邦 / 省 /
    联邦区」分组标题和三行图例文字无法在 v1 里表达; 这里把分组语义留在
    suggestions.notes(七邦冷色/七省暖色), 条目按旧面板顺序逐个列出行政区并保留
    中英名, 色块沿用旧面板的不透明填充与白色描边, 联邦区保留斜线(hatch 是契约
    v2 预留字段, v1 前端会忽略).
    """
    units_by_key = {unit["key"]: unit for unit in units}
    entries: list[dict] = []
    for keys, colors in (
        (LEGEND_STATE_KEYS, STATE_COLORS),
        (LEGEND_REGION_KEYS, REGION_COLORS),
    ):
        for key in keys:
            unit = units_by_key[key]
            entries.append(
                {
                    "label": f"{unit['name_zh']} {unit['name_en']}",
                    "label_lines": [unit["name_zh"], unit["name_en"]],
                    "shape": "rect",
                    "stroke": "#ffffff",
                    "width_pt": 0.6,
                    "fill": colors[key],
                    "opacity": 1.0,
                }
            )

    union = next(unit for unit in units if unit["kind"] == "union")
    entries.append(
        {
            "label": f"{union['name_zh']} {union['name_en']}",
            "label_lines": ["联邦区 Union Territory", union["name_zh"], union["name_en"]],
            "shape": "rect",
            "stroke": "#6b4e00",
            "width_pt": 1.0,
            "fill": UNION_COLOR,
            "opacity": 1.0,
            "hatch": "////",
        }
    )

    # 旧面板下半部分的符号与线型, 顺序与图例面板一致; 说明文字放在条目标签里.
    entries.extend(
        [
            {
                "label": "联邦首都 Union capital",
                "label_lines": ["联邦首都", "Union capital"],
                "shape": "point",
                "stroke": "#111111",
                "width_pt": 0.7,
                "fill": "#ffd200",
                "marker": "star",
            },
            {
                "label": "行政中心 Administrative centre",
                "label_lines": ["行政中心", "Administrative centre"],
                "shape": "point",
                "stroke": "#111111",
                "width_pt": 0.9,
                "fill": "#ffffff",
                "marker": "circle",
            },
            {
                "label": "河流 River",
                "label_lines": ["河流", "River"],
                "shape": "line",
                "stroke": "#1565c0",
                "width_pt": 2.25,
            },
            {
                "label": "邦/省界 State & region boundary",
                "label_lines": ["邦/省界", "State & region boundary"],
                "shape": "line",
                "stroke": BOUNDARY_COLOR,
                "width_pt": 1.05,
            },
            {
                "label": "国界 International boundary",
                "label_lines": ["国界", "International boundary"],
                "shape": "line",
                "stroke": COLOR_BORDER,
                "width_pt": BORDER_WIDTH,
                "opacity": BORDER_ALPHA,
            },
            {
                "label": "邻国国界 Neighbour boundary",
                "label_lines": ["邻国国界", "Neighbour boundary"],
                "shape": "line",
                "stroke": COLOR_NEIGHBOR,
                "width_pt": 0.45,
                "dash": [5.0, 3.0],
            },
        ]
    )
    doc.set_legend("图例", entries)


def collect_suggestions(doc: GeoDoc) -> None:
    """默认文案: 旧版标题/副标题/注/来源, 只作前端预填, 不参与合成.

    旧版图例面板里的分组标题与说明(七邦冷色/七省暖色、双语说明、7 邦·7 省·1
    联邦区)无法作为图例条目表达, 一并放进 notes 交给前端排版.
    """
    doc.set_suggestions(
        {
            "title": TITLE_ZH,
            "subtitle": TITLE_EN,
            "notes": [
                SUBTITLE,
                "地名均为中文 + English 双语（All place names are bilingual）",
                "7 邦 · 7 省 · 1 联邦区",
            ],
            "source": SOURCE,
            "area_annotation": [],
            "legend_title": "图例",
            "colorbar_title": "高程",
        }
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

    # 画布偏竖长: 投影后缅甸国土宽高比约 0.56. 地图区位置与旧版相同(右侧原来
    # 放图例面板的那一条留白保留); save_map 只按地图框裁根标签, 留白不进底图.
    fig = plt.figure(figsize=(13, 17), facecolor="white")
    ax = fig.add_axes([0.075, 0.045, 0.655, 0.855], projection=PROJECTION)
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    add_relief(ax, etopo_path, myanmar_geom)
    add_admin_fills(ax, units, border_zone)
    add_rivers(ax)
    add_country_outline(ax, country_border)
    add_admin_centres(ax, units)

    # 经纬网: 经度每 2°, 纬度每 5°, 位置由 locator 固定; 只画网线, 不画刻度文字
    # (刻度数值与文字由前端按 geo.graticule 排版).
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

    # 地图框必须在 set_extent 之后量: figure_frame 会先 apply_aspect,
    # 否则拿到的是 aspect 修正前的矩形, 裁剪框会与地图错位.
    frame = figure_frame(fig, ax)
    doc = GeoDoc(frame)
    collect_labels(doc, ax, units)
    collect_graticule(doc, ax)
    collect_relief(doc)
    collect_legend(doc, units)
    collect_suggestions(doc)

    # 注意: 不能用 tight_layout/constrained_layout/bbox_inches="tight";
    # cartopy 的 gridliner 在非矩形投影上提前绘制时会触发 GEOS 异常或裁掉画面,
    # 与项目内 myanmar.py 的处理保持一致.
    svg_path, geo_path = save_map(fig, OUT_SVG, doc, dpi=args.dpi)
    print(f"底图与 geo 已保存: {svg_path} + {geo_path}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
