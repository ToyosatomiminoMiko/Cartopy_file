#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Administrative-division map of Myanmar.

是什么: 绘制缅甸省/邦级行政区划图, 七邦冷色、七省暖色、内比都联邦区中性色加斜线,
叠加河流与 ETOPO 2022 地形晕渲, 并画出各行政区中心点; 国界用半透明红色、只画陆地
上的国界段, 海岸线不单独绘制. 底图只画地理要素, 文字/图例/色标/标题/刻度文字都由
同名 ``<产物>.geo.json`` 交给前端排版; 画框/投影/色带/经纬网/文案取自
``Myanmar/config.py``. 本图的特殊图层(行政区填色与双语图例、特区填色、河网、国界线型、
自定义地形底纹)留在本脚本, 用共享原语画. 本文件是模块, 只导出 ``run()``, 由统一入口
``python Myanmar/main.py render`` 调用.
完整说明(配色、投影、数据来源、运行方式)见 ``docs/maps/myanmar-admin.md``;
出图流程见 ``docs/reference/runner.md``, 图层原语见 ``docs/reference/layers.md``.
"""

from __future__ import annotations

import functools
import json
import os
import sys
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import geopandas as gpd  # 读取 Natural Earth shapefile
import matplotlib.colors as mcolors  # 颜色与色带
import matplotlib.pyplot as plt  # 绘图
import numpy as np  # 数组运算
from shapely.geometry import LineString, shape  # GeoJSON -> Shapely / 取外环
from shapely.ops import unary_union  # 合并行政区, 得到缅甸整体轮廓

# 图种规格与数据集清单: 画框/投影/色带/经纬网/文案都从这里取, 见 docs/reference/spec.md.
import config

# 共享图层原语(底图/经纬网/城市点/geo 收集), 见 docs/reference/layers.md.
from cartopy_file import layers

# 统一出图流程(建画布 -> 底图 -> 本脚本图层 -> geo 保存), 见 docs/reference/runner.md.
from cartopy_file import runner

# 国界与海岸线重合时只保留国界: 用共享剪枝工具裁掉沿海段, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# ETOPO 定位与高程读取、Natural Earth 图层读取, 见 docs/reference/relief.md.
from cartopy_file.relief import (
    clip_to_axes,
    find_etopo,
    load_elevation,
    load_ne_layer,
    make_relief,
)

# 城市点标记的数据类; 样式(尺寸/颜色)在本脚本按行政区类型给出.
from cartopy_file.spec import City

# 斜线填充过密会在成品尺寸下糊成深色块, 这里保持项目里一致的细线.
plt.rcParams["hatch.linewidth"] = 0.5

SHEET = config.SHEET_ADMIN
DATASETS = config.DATASETS

# 数据路径全部由数据集清单给出(raw/ 与 derived/ 的约定见 docs/reference/datasets.md).
ADMIN_GEOJSON = DATASETS.path(config.ADMIN_GEOJSON)
RIVER_SHP = (
    DATASETS.path(config.NE_RIVERS) / "ne_10m_rivers_lake_centerlines.shp"
)

# ============================
# 本图特有图层
# ============================
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

# 国界剪掉沿海段的缓冲半径(度). 本图不画海岸线, 海陆界线由底色/填色分界;
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

# 地形底纹的晕渲细节. 色带/范围/来光/夸张系数都在 Sheet.relief 里; 这里只留
# 框架 Relief 字段表达不了的两个数值: 软光混合的比例(改前成品用 1.0, 框架默认
# 1.2)与海洋像元的透明度(海面保留纯底色, 否则负高程也会被染成米色).
RELIEF_SHADE_FRACTION = 1.0
# 晕渲栅格在投影后再采样到 3000 像素宽: 默认 750 对 30 弧秒数据会糊.
RELIEF_REGRID_SHAPE = 3000
RELIEF_INTERPOLATION = "bilinear"

# ============================
# 标注数据(只登记进 geo, 底图不画文字)
# ============================
# 双语文字的中文、英文是两条独立标注(位置/字号不同); 样式统一后两者共用同一个
# role, 颜色/描边/斜体都来自前端 role 表, 生成端不再有「英文行单独配色」这回事.

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


# ============================
# 数据与几何
# ============================
def load_admin_units():
    """读取预处理后的 15 个一级行政区, 按邦/省/联邦区分组."""
    if not ADMIN_GEOJSON.exists():
        raise FileNotFoundError(
            f"未找到行政区数据: {ADMIN_GEOJSON}\n请先运行: python Myanmar/main.py prepare"
        )
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


# ============================
# 本图特有图层
# ============================
def add_land_borders(ax: plt.Axes, myanmar_geom) -> None:
    """画邻国国界参照线(细灰虚线), 从缅甸国界走廊里剪掉.

    海岸线不画: 海与陆靠底色与行政区填色分界, Natural Earth 的国家面轮廓
    会把海岸线一起描出来, 所以这里不画 ``world.geometry``, 只用
    ``admin_0_boundary_lines_land`` 画邻国国界, 免得与红色国界并行成双线.
    """
    land_borders = load_ne_layer("10m", "cultural", "admin_0_boundary_lines_land")
    if land_borders is None:
        return
    others = unary_union(clip_to_axes(ax, list(land_borders.geometry)))
    others = others.difference(myanmar_geom.buffer(NEIGHBOR_GAP_DEG))
    if others.is_empty:
        return
    ax.add_geometries(
        [others],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=COLOR_NEIGHBOR,
        linewidth=0.45,
        linestyle=(0, (5, 3)),
        zorder=1.5,
    )


def add_relief(ax: plt.Axes, etopo_path: Path) -> None:
    """叠加只覆盖陆地的低透明度地形晕渲(海面保留底色).

    色带/高程范围/来光/夸张系数从 ``Sheet.relief`` 取; 晕渲细节(软光比例、海洋像元
    透明)见本文件顶部常量. 海岸线不画, 岸线由底图与行政区填色的分界表达.
    """
    lon, lat, z = load_elevation(etopo_path)
    relief = SHEET.relief
    rgba, _, _ = make_relief(
        z,
        lat,
        lon,
        vmin=relief.vmin,
        vmax=relief.vmax,
        cmap=layers.make_relief_cmap(relief),
        azimuth=relief.azimuth,
        altitude=relief.altitude,
        vert_exag=relief.vert_exag,
        fraction=RELIEF_SHADE_FRACTION,
    )
    # 把海洋的 alpha 置 0: 海面保留纯浅蓝, 否则负高程也会被染成米色.
    rgba[..., 3] = np.where(z >= 0, relief.alpha, 0.0)
    ax.imshow(
        rgba,
        origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        regrid_shape=RELIEF_REGRID_SHAPE,
        interpolation=RELIEF_INTERPOLATION,
        zorder=relief.zorder,
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
            f"未找到河流数据: {RIVER_SHP}\n请先运行: python Myanmar/main.py prepare"
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
    coastline = load_ne_layer("10m", "physical", "coastline")
    if coastline is not None:
        coast = unary_union(clip_to_axes(ax, list(coastline.geometry)))
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
    cities = []
    for unit in units:
        if unit["kind"] == "union":
            cities.append(
                City(
                    unit["capital_lon"],
                    unit["capital_lat"],
                    15,
                    "#ffd200",
                    "#111111",
                    0.75,
                    capital=True,
                    name=unit["capital_zh"],
                )
            )
        else:
            cities.append(
                City(
                    unit["capital_lon"],
                    unit["capital_lat"],
                    5.6,
                    "white",
                    "#111111",
                    0.9,
                    name=unit["capital_zh"],
                )
            )
    layers.add_cities(ax, cities, zorder=15)


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
    doc,
    ax: plt.Axes,
    lon: float,
    lat: float,
    zh: str,
    en: str,
    *,
    role: str,
    id_kind: str,
    name: str,
    size_zh: float,
    size_en: float,
    dx: float = 0.0,
    dy_zh: float = 4.0,
    dy_en: float = -7.0,
    ha: str = "center",
) -> None:
    """登记一对中文/英文标签: 两条 add_label 共用一个 role, 只有位置/字号不同.

    为什么英文单独一条: 旧版 en 是独立文字(字号更小、位置另给、id 带 ``-en``),
    前端要能分别拖动; 样式统一后两条同 role, 颜色/描边/斜体都由前端 role 表决定.
    """
    zh_lon, zh_lat = _offset_lonlat(ax, lon, lat, dx, dy_zh)
    doc.add_label(
        ax,
        zh_lon,
        zh_lat,
        zh,
        role=role,
        id_kind=id_kind,
        name=name,
        font_size_pt=size_zh,
        ha=ha,
    )
    en_lon, en_lat = _offset_lonlat(ax, lon, lat, dx, dy_en)
    doc.add_label(
        ax,
        en_lon,
        en_lat,
        en,
        role=role,
        id_kind=id_kind,
        name=f"{name}-en",
        font_size_pt=size_en,
        ha=ha,
    )


def collect_labels(doc, ax: plt.Axes, units) -> None:
    """把旧版图上的全部地名登记成 geo.labels(38 对, 中英各一条, 共 76 条; 同 role).

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
            role="country",
            id_kind="country",
            name=zh,
            size_zh=12.0,
            size_en=8.4,
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
            role="sea",
            id_kind="sea",
            name=zh,
            size_zh=11.5,
            size_en=8.0,
            dy_zh=3.5,
            dy_en=-6.5,
        )

    # 行政区名: id 前缀保留旧版的 state/region/union(用 id_kind), role 统一记 area.
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
            role="area",
            id_kind=unit["kind"],
            name=key,
            size_zh=size_zh,
            size_en=size_en,
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
            role="city",
            id_kind="city",
            name=unit["capital_zh"],
            size_zh=8.0,
            size_en=6.5,
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
            role="river",
            id_kind="river",
            name=zh,
            size_zh=9.0,
            size_en=6.8,
            dy_zh=3.5,
            dy_en=-6.0,
        )


def collect_legend(doc, units) -> None:
    """把旧版自绘的 7 邦/7 省色块面板改成 geo.legend.entries(按旧面板顺序平铺).

    为什么分组不单独出条目: 图例条目只能表达「一条符号」, 旧面板的「邦 / 省 /
    联邦区」分组标题和三行图例文字无法在图例条目里表达; 这里把分组语义留在
    suggestions.notes(七邦冷色/七省暖色), 条目按旧面板顺序逐个列出行政区并保留
    中英名, 色块沿用旧面板的不透明填充与白色描边, 联邦区保留斜线(hatch 是图例
    条目的扩展字段, 前端不识别时忽略).
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


def collect_suggestions(doc) -> None:
    """默认文案: 标题/副标题/注/来源, 只作前端预填, 不参与合成.

    标题/副标题/注来自 ``Sheet``; 来源由 ``DatasetSet.citation`` 按
    ``Sheet.dataset_ids`` 自动生成(带发布页 URL), 不再手写.
    旧版图例面板里的分组标题与说明(七邦冷色/七省暖色、双语说明、7 邦·7 省·1
    联邦区)无法作为图例条目表达, 一并放进 notes 交给前端排版.
    """
    suggestion = layers.suggestions(SHEET, DATASETS)
    doc.set_suggestions(
        {
            "title": suggestion["title"],
            "subtitle": suggestion["subtitle"],
            "notes": suggestion["notes"],
            "source": suggestion["source"],
            "area_annotation": [],
            "legend_title": "图例",
            "colorbar_title": suggestion["colorbar_title"],
        }
    )


# ============================
# 主流程
# ============================
def draw(
    ctx: runner.RenderContext,
    *,
    etopo_path: Path,
    units,
    myanmar_geom,
    border_zone,
    country_border,
) -> None:
    """按本图的叠放顺序画剩余图层: 邻国国界 -> 地形 -> 行政区 -> 河流 -> 国界 -> 中心点 -> 经纬网."""
    ax = ctx.ax
    add_land_borders(ax, myanmar_geom)
    add_relief(ax, etopo_path)
    add_admin_fills(ax, units, border_zone)
    add_rivers(ax)
    add_country_outline(ax, country_border)
    add_admin_centres(ax, units)
    layers.add_gridlines(ax, SHEET)
    # 国界/地图边框: 线宽略粗, 让画面有明确边界.
    ax.spines["geo"].set_linewidth(0.8)
    ax.spines["geo"].set_edgecolor("#333333")


def collect(doc, ctx: runner.RenderContext, *, units) -> None:
    """登记 geo: 地名 -> 经纬刻度 -> 色标 -> 图例 -> 文案(来源由数据集清单自动生成)."""
    collect_labels(doc, ctx.ax, units)
    layers.collect_graticule(doc, ctx.ax, SHEET)
    layers.collect_relief(doc, SHEET)
    collect_legend(doc, units)
    collect_suggestions(doc)


def run(*, stride: int | None = None, dpi: int | None = None, show: bool = False) -> int:
    """渲染行政区划图并写出同名 geo.json; 返回 0=成功, 1=数据缺失."""
    try:
        etopo_path = find_etopo(
            DATA_DIR / "raw",
            "myanmar",
            stride,
            env_path=os.environ.get("MYANMAR_ETOPO_PATH"),
        )
        if not etopo_path.exists():
            raise FileNotFoundError(
                f"未找到高程数据: {etopo_path}\n"
                "请先运行: python Myanmar/main.py download --region myanmar"
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

        # 画布/坐标区/范围/底图由 runner 按 Sheet 建好; 本图的特有图层按叠放顺序在 draw 里画.
        runner.render(
            SHEET,
            root=ROOT,
            catalog=DATASETS,
            draw=functools.partial(
                draw,
                etopo_path=etopo_path,
                units=units,
                myanmar_geom=myanmar_geom,
                border_zone=border_zone,
                country_border=country_border,
            ),
            collect=functools.partial(collect, units=units),
            dpi=dpi,
            show=show,
        )
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python Myanmar/main.py <子命令>")
