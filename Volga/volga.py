#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Volga basin and neighbouring republics, topographic maps (two sheets).

是什么: 以 ETOPO 2022 地形晕渲为底图, 叠加 HydroSHEDS 伏尔加河流域、GADM 4.1
俄罗斯一级行政区、Natural Earth 10m 河网与梯级水库水面, 一次生成两张自包含
SVG: 只画流域的流域图, 与画框收窄、保留六个周边共和国的共和区图; 只绘制地理
要素, 不绘制任何文字/图例/色标/标题/比例尺/指北针.
完整说明(两份画框、行政区取舍、河网分级与配色)见 ``docs/maps/volga.md``;
数据集与两张图的规格见 ``Volga/config.py``, 分层与 API 见 ``docs/reference/spec.md``
与 ``docs/reference/datasets.md``, 共享图层与出图流水线见 ``docs/reference/layers.md``
与 ``docs/reference/runner.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import geopandas as gpd  # 读取预加工好的 GeoJSON
import matplotlib.pyplot as plt  # 绘图
import numpy as np  # 数组运算
from shapely.geometry import box  # 投影画框与湖库筛选
from shapely.ops import unary_union  # 流域/行政区几何合并

# 图种规格与数据集清单: 画框/投影/色带/地名/文案都从这里取, 见 docs/reference/spec.md.
import config

# 共享图层原语(底图/晕渲/经纬网/城市点/geo 收集), 见 docs/reference/layers.md.
from cartopy_file import layers

# 统一出图流程(建画布 -> 图种图层 -> geo 保存), 见 docs/reference/runner.md.
from cartopy_file import runner

# cartopy 底图缓存统一到仓库 data/cartopy, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy

configure_cartopy()

# 重合线剪枝: 国界与海岸线/湖岸重合的段落只留一种线, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# 共享的 ETOPO/晕渲/底图工具(实现见 src/cartopy_file/relief.py).
from cartopy_file.relief import find_etopo, load_elevation, load_ne_layer


# ============================
# 数据(两张图共用, 主流程只读一次)
# ============================
@dataclass
class VolgaData:
    """两张图共用的一份数据: 矢量图层 + 修正过海陆的高程栅格 + 流域面积.

    runner 每张图只给一个 ``RenderContext``, 而两张图必须用同一份 ETOPO 与同一份
    修正后高程(见 docs/maps/volga.md 设计要点 4), 所以数据在主流程里载入一次,
    放进模块级 ``_DATA`` 由 draw/collect 取用.
    """

    subjects: gpd.GeoDataFrame
    basin: object
    border: object
    lon: np.ndarray
    lat: np.ndarray
    z: np.ndarray
    basin_area_km2: float


_DATA: VolgaData | None = None


def _data() -> VolgaData:
    """取主流程已载入的数据; 没载入说明调用顺序错了."""
    if _DATA is None:
        raise RuntimeError("数据尚未载入: 先运行 main() 的 load_data()")
    return _DATA


def _require(path: Path) -> Path:
    """检查数据文件存在, 缺失时按 raw/derived 给出对应的准备脚本."""
    if not path.exists():
        # raw/ 由下载脚本准备, derived/ 由派生脚本准备, 见 docs/maps/volga.md 运行一节.
        script = "download_data.py" if "raw" in path.parts else "prepare_data.py"
        raise FileNotFoundError(f"未找到数据: {path}\n请先运行: python Volga/{script}")
    return path


# ============================
# Natural Earth 图层缓存
# ============================
@lru_cache(maxsize=None)
def _ne_layer(resolution: str, category: str, name: str):
    """缓存一份 Natural Earth 图层: 两张图共用同一份 shapefile, 只读一次."""
    return load_ne_layer(resolution, category, name)


@lru_cache(maxsize=None)
def _ne_union(resolution: str, category: str, name: str):
    """缓存整层几何合并结果; 海洋/湖泊并集在掩版与水陆判识里要反复用."""
    layer = _ne_layer(resolution, category, name)
    return None if layer is None else layer.union_all()


def _view_box(extent, pad: float = 0.0):
    """画框外扩 pad 度的 shapely box(shapely 的顺序: min_lon, min_lat, max_lon, max_lat)."""
    return box(
        extent.lon_min - pad,
        extent.lat_min - pad,
        extent.lon_max + pad,
        extent.lat_max + pad,
    )


# ============================
# 数据读取
# ============================
def load_vectors(extent) -> tuple[gpd.GeoDataFrame, object, object]:
    """读取绘图所需的三份本地 GeoJSON, 返回 (行政区, 流域面, 国界线).

    流域取联合后的单个几何; 国界线合并成一个 MultiLineString. 河网与湖泊
    来自仓库 data/cartopy 里已缓存的 Natural Earth 10m 图层(见 add_rivers /
    add_water), 不需要各图种再下载一份.
    """
    subjects = gpd.read_file(_require(config.DATASETS.path("volga-subjects")))
    basin = unary_union(gpd.read_file(_require(config.DATASETS.path("volga-basin"))).geometry)
    # 流域面裁到俄罗斯陆地: HydroBASINS 的单元边界在里海岸边比 GADM 岸线
    # 略靠外, 不裁的话浅蓝填色会在海面上多出一圈岸线误差(约 1500 km²);
    # 行政区的陆地并集与国界同源, 裁完岸线才与国界对齐.
    land = unary_union(subjects.geometry)
    # 再减去 Natural Earth 10m 海洋面: 行政区的陆地并集在里海西岸包含部分
    # 管辖水域, 只裁陆地仍会在三角洲以南留一条伸进里海的尾巴; 海洋面把
    # 水域部分彻底去掉, 流域南界落在真实岸线上.
    ocean = _ne_union("10m", "physical", "ocean")
    if ocean is not None:
        land = land.difference(ocean.intersection(_view_box(extent, pad=1.0)))
    basin = unary_union(polygon_parts(basin.intersection(land)))
    border = unary_union(gpd.read_file(_require(config.DATASETS.path("russia-border"))).geometry)
    return subjects, basin, border


def basin_area_km2(basin) -> float:
    """流域面积(km²): 在等积投影 EPSG:6933 下计算, 与图注「约 141 万 km²」同口径."""
    # EPSG:6933 的单位是米, 面积是 m²; 先换成 km² 再返回.
    return float(
        gpd.GeoSeries([basin], crs="EPSG:4326").to_crs("EPSG:6933").area.iloc[0] / 1.0e6
    )


# ============================
# 几何工具
# ============================
def polygon_parts(geom, *, min_area_deg2: float = 1e-4):
    """把 (Multi)Polygon 拆成面部件并丢掉面积过小的缝合碎片.

    为什么需要: HydroBASINS 单元 union 后会在相邻单元接缝处留下面积为 0 的
    针状碎屑; 直接画边界会在图上出现孤立小点/毛刺(见 docs/maps/volga.md).
    """
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom] if geom.area > min_area_deg2 else []
    if geom.geom_type == "MultiPolygon":
        return [part for part in geom.geoms if part.area > min_area_deg2]
    # 面与面求交偶尔返回 GeometryCollection(夹杂线/点), 递归取其中的面.
    parts: list = []
    for child in getattr(geom, "geoms", []):
        parts.extend(polygon_parts(child, min_area_deg2=min_area_deg2))
    return parts


def in_extent(lon: float, lat: float, extent, *, pad: float = 0.0) -> bool:
    """点是否落在画框内; 用来跳过画框外的城市点, 避免符号画到地图区之外."""
    return (
        extent.lon_min - pad <= lon <= extent.lon_max + pad
        and extent.lat_min - pad <= lat <= extent.lat_max + pad
    )


# ============================
# 高程预处理
# ============================
def negative_land_as_land(z: np.ndarray, lon: np.ndarray, lat: np.ndarray, extent) -> np.ndarray:
    """把海平面以下、但不在海洋/湖泊多边形内的陆地像元改成 0.5 m 再配色.

    为什么需要: ETOPO 的高程是相对海平面的, 里海沿岸低地(约 -28~0 m)与里海
    水面(-28 m)都落在负值段. 若按 z<0 一刀切, 里海低地会被画成浅蓝色水面,
    在伏尔加下游/卡尔梅克一带连成一片假海. 这里用 Natural Earth 10m 的
    ocean + lakes 判定真正的水域, 只有水域保留负高程配色, 其余负高程陆地
    抬到 0.5 m(仍用陆地色, 视觉上抬升可忽略).
    """
    try:
        from shapely import contains_xy
    except ImportError:  # pragma: no cover - shapely 2.x 才有向量化谓词
        return z
    ocean = _ne_union("10m", "physical", "ocean")
    lakes = _ne_union("10m", "physical", "lakes")
    geoms = [geom for geom in (ocean, lakes) if geom is not None]
    if not geoms:
        print("警告: 缺少 Natural Earth ocean/lakes, 负高程陆地仍按水面配色.")
        return z
    water_geom = unary_union(geoms).intersection(_view_box(extent, pad=1.0))
    fixed = z.copy()
    rows, cols = np.nonzero(z < 0)
    in_water = contains_xy(water_geom, lon[cols], lat[rows])
    fixed[rows[~in_water], cols[~in_water]] = 0.5
    return fixed


def prepare_elevation(lon: np.ndarray, lat: np.ndarray, z: np.ndarray) -> np.ndarray:
    """两张图共用的高程预处理: 只把真正水域留在负高程段.

    为什么只做一次: 水陆判识依赖与画框无关的 Natural Earth 面, 流域图的画框
    覆盖共和国图, 同一份修正后的高程可以直接铺进两个坐标区.
    """
    return negative_land_as_land(z, lon, lat, config.EXTENT_BASIN)


def load_data(etopo_path: Path) -> None:
    """主流程载入一次数据: 矢量图层 + 修正后的高程 + 流域面积."""
    global _DATA
    subjects, basin, border = load_vectors(config.EXTENT_BASIN)
    lon, lat, z = load_elevation(etopo_path)
    _DATA = VolgaData(
        subjects=subjects,
        basin=basin,
        border=border,
        lon=lon,
        lat=lat,
        z=prepare_elevation(lon, lat, z),
        basin_area_km2=basin_area_km2(basin),
    )


# ============================
# 图层
# ============================
def add_basin(ax: plt.Axes, basin) -> None:
    """流域面浅蓝填色 + 深蓝外轮廓.

    为什么先填色后画线: 填色只作"流域范围"的底色, 不能压住地形细节与河网;
    外轮廓是这张图的第一主题边界, 用实线而不是虚线, 并加一条白色底描边,
    让它在深色山体与半透明色块上都能连续可辨.
    """
    ax.add_geometries(
        [basin],
        crs=ccrs.PlateCarree(),
        facecolor=config.COLOR_BASIN_FILL,
        edgecolor="none",
        alpha=config.COLOR_BASIN_ALPHA,
        linewidth=0,
        zorder=1.5,
    )
    ax.add_geometries(
        [basin.boundary],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="white",
        linewidth=3.8,
        alpha=0.55,
        zorder=3.9,
    )
    ax.add_geometries(
        [basin.boundary],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=config.COLOR_BASIN_EDGE,
        linewidth=2.1,
        zorder=4.0,
    )


def add_water(ax: plt.Axes, extent) -> None:
    """填画框内全部 Natural Earth 10m 湖泊与梯级水库水面.

    为什么需要填: 伏尔加—卡马梯级水库面积小、水深浅, ETOPO 30″ 下只是几
    像素宽的浅色带, 单独填色才能读出"上游窄河、下游宽水面"的沿程变化
    (与 Ukraine 图处理第聂伯河梯级水库的理由一致); 咸海的水面高出海平面
    (+29 m), 按高程配色会画成陆地, 也只能靠湖泊多边形补上.
    不填里海: 里海不在 Natural Earth lakes 图层(在 ocean 图层), 它的水深
    仍由 ETOPO 配色表达, 避免用等深浅蓝盖掉水下地形.
    """
    lakes = _ne_layer("10m", "physical", "lakes")
    if lakes is None:
        print("警告: 缺少 Natural Earth 湖泊数据, 跳过大水面填色.")
        return
    view = box(extent.lon_min, extent.lat_min, extent.lon_max, extent.lat_max)
    selected = lakes[lakes.geometry.intersects(view)]
    geoms = [g for g in selected.geometry if g is not None and not g.is_empty]
    if not geoms:
        print("警告: 画框内没有 Natural Earth 湖泊, 跳过水面填色.")
        return
    ax.add_geometries(
        geoms,
        crs=ccrs.PlateCarree(),
        facecolor=config.COLOR_WATER,
        edgecolor=config.COLOR_WATER_EDGE,
        linewidth=0.45,
        zorder=2.75,
    )


def add_rivers(ax: plt.Axes, extent) -> None:
    """按 scalerank 分三档画 Natural Earth 10m 河网.

    为什么分级: 河网统一同宽会把伏尔加干流淹没在支流里; 按 scalerank 分三档
    后, 干流(粗, 带白描边)-主要支流(中)-次要河流(细)的主次关系与河谷规模
    一致. 只给五条主要河流写河名, 避免整张图被文字压满.
    排除 Canal: 运河是人工线, 不属于本图要表达的天然水系.
    """
    rivers = _ne_layer("10m", "physical", "rivers_lake_centerlines")
    if rivers is None:
        print("警告: 缺少 Natural Earth 河流数据, 跳过河流图层.")
        return
    view = box(extent.lon_min, extent.lat_min, extent.lon_max, extent.lat_max)
    selected = rivers[
        rivers.geometry.intersects(view)
        & ~rivers["featurecla"].isin(config.RIVER_EXCLUDE_FEATURECLA)
    ]
    if selected.empty:
        print("警告: 画框内没有 Natural Earth 河流, 跳过河流图层.")
        return
    ranks = selected["scalerank"].to_numpy()

    def draw(geoms, color: str, linewidth: float, halo: bool) -> None:
        geoms = [g for g in geoms if g is not None and not g.is_empty]
        if not geoms:
            return
        if halo:
            ax.add_geometries(
                geoms,
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=config.COLOR_RIVER_HALO,
                linewidth=linewidth + 1.9,
                zorder=2.50,
            )
        ax.add_geometries(
            geoms,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=color,
            linewidth=linewidth,
            zorder=2.55,
        )

    geoms = list(selected.geometry)
    trunk = ranks <= config.RIVER_TRUNK_MAX_SCALERANK
    medium = (ranks > config.RIVER_TRUNK_MAX_SCALERANK) & (
        ranks <= config.RIVER_MEDIUM_MAX_SCALERANK
    )
    minor = ~trunk & ~medium
    draw([g for g, m in zip(geoms, minor) if m], config.COLOR_RIVER, 0.5, halo=False)
    draw(
        [g for g, m in zip(geoms, medium) if m],
        config.COLOR_RIVER_MEDIUM,
        0.85,
        halo=False,
    )
    draw(
        [g for g, m in zip(geoms, trunk) if m],
        config.COLOR_RIVER_TRUNK,
        1.9,
        halo=True,
    )


def add_admin(ax: plt.Axes, subjects: gpd.GeoDataFrame, theme: config.Theme) -> None:
    """主体界(灰色虚线)与 theme.republics 的填色/描边.

    为什么共和国填色画在行政界线之下: 填色是面, 界线是线, 先铺面再画线,
    界线不会被半透明填色盖住. 共和国的外边界另用较粗的蓝紫线强调; 它与
    俄罗斯国界重合的段落会被后面更粗的国界线压住(国界 zorder 更高).
    流域图不画行政区(draw_admin=False), 只留国界; 共和国图的 hidden_subjects
    (科米、卡尔梅克)既不填色也不画自己的灰色界线.
    """
    if not theme.draw_admin:
        return
    republic_names = set(theme.republics)
    hidden = set(theme.hidden_subjects)
    republics = subjects[subjects["name"].isin(republic_names)]
    others = subjects[~subjects["name"].isin(republic_names | hidden)]

    # 其余联邦主体: 只画界线, 作背景参照.
    other_edges = [g.boundary for g in others.geometry if g is not None and not g.is_empty]
    if other_edges:
        ax.add_geometries(
            other_edges,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=config.COLOR_SUBJECT,
            linewidth=0.5,
            alpha=0.55,
            linestyle=(0, (5, 3)),
            zorder=3.0,
        )

    # 共和国: 半透明蓝紫填色 + 较粗描边.
    if not republics.empty:
        ax.add_geometries(
            [g for g in republics.geometry if g is not None and not g.is_empty],
            crs=ccrs.PlateCarree(),
            facecolor=config.COLOR_REPUBLIC_FILL,
            edgecolor="none",
            alpha=config.COLOR_REPUBLIC_ALPHA,
            linewidth=0,
            zorder=2.1,
        )
        republic_edges = [
            g.boundary for g in republics.geometry if g is not None and not g.is_empty
        ]
        ax.add_geometries(
            republic_edges,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=config.COLOR_REPUBLIC_EDGE,
            linewidth=1.9,
            zorder=6.3,
        )


def border_land_only(border, extent):
    """从 GADM 俄罗斯外边界里剪掉海岸线与湖岸段, 只留国际陆地国界.

    为什么: GADM 各一级行政区的并集边界同时也是国家的外轮廓, 包含了北冰洋/
    里海/黑海海岸和拉多加湖、奥涅加湖等大湖岸线. 若整条线都按国界样式(深灰
    实线 + 白描边)画, 湖岸上会出现像"国界"的粗线, 拉多加湖西岸一个小岬角
    甚至会被看成文字/污点. 用 Natural Earth 10m 海岸线与湖泊边界做蒙版,
    把重合段剪掉, 只保留与邻国接壤的陆地国界(与 Ukraine 图剪海岸段同理).
    """
    coast = _ne_union("10m", "physical", "coastline")
    lakes = _ne_union("10m", "physical", "lakes")
    view = _view_box(extent, pad=1.0)
    overlays = []
    if coast is not None:
        overlays.append(coast.intersection(view))
    if lakes is not None:
        overlays.append(lakes.boundary.intersection(view))
    if not overlays:
        return border
    mask = overlap_mask(overlays, 0.08)
    trimmed = cut(border, mask, min_length_deg=0.03)
    return trimmed if trimmed is not None else border


def add_borders(ax: plt.Axes, border, extent) -> None:
    """俄罗斯国界(GADM 口径, 不含克里米亚)用深灰实线.

    为什么不用 Natural Earth: 与行政区同源, 国界与联邦主体界在坐标级重合,
    不会出现两套数据并行偏差; GADM RUS 的国界也不含克里米亚, 与仓库
    Ukraine 图的 1991 法理口径一致.
    """
    line = border_land_only(border, extent)
    ax.add_geometries(
        [line],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="white",
        linewidth=2.6,
        alpha=0.5,
        zorder=5.4,
    )
    ax.add_geometries(
        [line],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=config.COLOR_BORDER,
        linewidth=1.4,
        zorder=5.5,
    )


# ============================
# 城市点
# ============================
def add_city_markers(ax: plt.Axes, extent) -> None:
    """画画框内的城市点: 首都星形, 共和国首府方块, 一般城市圆点.

    只画地理符号: 国名/海名/丘陵名/河名/城名与面积注记都属于排版文字, 不在本脚本绘制.
    画框外跳过: 与改前一致, 窄画框(共和国图)不画框外的城市.
    """
    for lon, lat, _name, kind, _dx, _dy, _align in config.CITIES:
        if not in_extent(lon, lat, extent):
            continue
        if kind == "capital":
            ax.plot(
                lon,
                lat,
                marker="*",
                markersize=16,
                markerfacecolor="#ffd200",
                markeredgecolor="black",
                markeredgewidth=0.8,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )
        elif kind == "rep":
            ax.plot(
                lon,
                lat,
                marker="s",
                markersize=6.2,
                markerfacecolor="white",
                markeredgecolor="black",
                markeredgewidth=1.0,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )
        else:
            ax.plot(
                lon,
                lat,
                marker="o",
                markersize=4.2,
                markerfacecolor="white",
                markeredgecolor="black",
                markeredgewidth=0.9,
                transform=ccrs.PlateCarree(),
                zorder=10,
            )


# ============================
# 经纬网
# ============================

# ============================
# geo.json 收集
# ============================
LEGEND_TITLE = "图例"


def collect_labels(doc, ax, sheet: config.Sheet, area_km2: float) -> None:
    """把旧成品上的地名整理成 geo.labels(role/位置/字号/锚点), 不画文字、不存样式.

    顺序按旧图的 zorder 升序登记(前端 scene 按 order 叠放): 国名/海名/地貌(9.0)、
    图内流域名(9.2)、共和国名(9.3)、河名(9.4)、城市(10.1). 画框外的候选跳过,
    与改前用 in_extent 过滤文字的行为一致; 颜色/斜体/描边/旋转由前端 role 表决定.
    """
    extent = sheet.extent
    theme = config.THEMES[sheet.id]

    # 邻国名称.
    for lon, lat, text in config.COUNTRY_LABELS:
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(ax, lon, lat, text, role="country", font_size_pt=12.0)

    # 海域名称.
    for lon, lat, text in config.SEA_LABELS:
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(ax, lon, lat, text, role="sea", font_size_pt=11.0)

    # 地貌名.
    for lon, lat, text in config.HIGHLAND_LABELS:
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(ax, lon, lat, text, role="highland", font_size_pt=10.0)

    # 图内流域名: 只有共和国图在图上写「伏尔加河流域 / 面积」; 流域图的同一块
    # 文字在旧版是图外面板, 现在由 geo.suggestions.area_annotation 带给前端.
    if theme.area_label_in_map and in_extent(42.55, 51.95, extent):
        doc.add_label(
            ax, 42.55, 51.95,
            f"伏尔加河流域\n约 {area_km2 / 1e4:.0f} 万 km²",
            role="area-basin", name="流域", font_size_pt=15.0,
        )

    # 共和国名: 字号按共和国轮廓大小分两档(小共和国 10.5, 大共和国 12.5);
    # id 前缀保留旧的 label-republic-*.
    for name in theme.republics:
        lon, lat, text = config.REPUBLIC_LABELS[name]
        if not in_extent(lon, lat, extent):
            continue
        size = 10.5 if name in config.SMALL_REPUBLICS else 12.5
        doc.add_label(
            ax, lon, lat, text,
            role="area-accent-1", id_kind="republic", name=name, font_size_pt=size,
        )

    # 河名: 同一条河标两段时 id 加 1 起算序号; 旋转由前端处理.
    river_counts: dict[str, int] = {}
    for _, _, text in config.RIVER_LABELS:
        river_counts[text] = river_counts.get(text, 0) + 1
    river_seen: dict[str, int] = {}
    for lon, lat, text in config.RIVER_LABELS:
        river_seen[text] = river_seen.get(text, 0) + 1
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(
            ax, lon, lat, text,
            role="river", name=text,
            index=river_seen[text] if river_counts[text] > 1 else None,
            font_size_pt=9.8,
        )

    # 城市: 文字跟着点位偏移; 字号按城市等级分三档.
    sizes = {"capital": 10.8, "rep": 9.3, "city": 8.8}
    for lon, lat, name, kind, dx, dy, align in config.CITIES:
        if not in_extent(lon, lat, extent):
            continue
        doc.add_label(
            ax, lon + dx, lat + dy, name,
            role="city", name=name, font_size_pt=sizes[kind], ha=align,
        )


def collect_legend(doc, sheet: config.Sheet) -> None:
    """图例数据: 只列该图实际画了的线型/面, 流域图没有行政区两项(与改前图例一致)."""
    theme = config.THEMES[sheet.id]
    entries: list[dict] = [
        {
            "label": "伏尔加河流域",
            "shape": "rect",
            "stroke": config.COLOR_BASIN_EDGE,
            "width_pt": 2.0,
            "fill": config.COLOR_BASIN_FILL,
            "opacity": 0.45,
        }
    ]
    if theme.draw_admin:
        entries.extend(
            [
                {
                    "label": "周边联邦主体共和国",
                    "shape": "rect",
                    "stroke": config.COLOR_REPUBLIC_EDGE,
                    "width_pt": 1.8,
                    "fill": config.COLOR_REPUBLIC_FILL,
                    "opacity": 0.45,
                },
                {
                    "label": "其他联邦主体界",
                    "shape": "line",
                    "stroke": config.COLOR_SUBJECT,
                    "width_pt": 0.9,
                    "dash": [5.0, 3.0],
                    "opacity": 0.8,
                },
            ]
        )
    entries.extend(
        [
            {"label": "国界", "shape": "line", "stroke": config.COLOR_BORDER, "width_pt": 1.4},
            {"label": "干流(伏尔加河等)", "shape": "line", "stroke": config.COLOR_RIVER_TRUNK, "width_pt": 1.8},
            {"label": "支流", "shape": "line", "stroke": config.COLOR_RIVER, "width_pt": 0.8},
            {
                "label": "湖泊 / 水库水面",
                "shape": "rect",
                "stroke": config.COLOR_WATER_EDGE,
                "width_pt": 0.6,
                "fill": config.COLOR_WATER,
            },
            {
                "label": "首都",
                "shape": "point",
                "stroke": "#000000",
                "width_pt": 1.5,
                "fill": "#ffd200",
                "marker": "star",
            },
            {
                "label": "共和国首府",
                "shape": "point",
                "stroke": "#000000",
                "width_pt": 1.5,
                "fill": "#ffffff",
                "marker": "square",
            },
            {
                "label": "城市",
                "shape": "point",
                "stroke": "#000000",
                "width_pt": 1.5,
                "fill": "#ffffff",
                "marker": "circle",
            },
        ]
    )
    doc.set_legend(LEGEND_TITLE, entries)


def collect_suggestions(doc, sheet: config.Sheet, area_km2: float) -> None:
    """默认文案: 标题/副标题/右栏注/来源/图外面积注记, 只给前端预填, 不参与合成.

    数据来源由 ``layers.suggestions`` 按 ``sheet.dataset_ids`` 从 DatasetSet 的署名
    自动生成(每条带发布页 URL); 面积注记与图例标题是图种特有字段, 在这里补进 dict,
    并保持改前 geo.json 的键顺序(title -> colorbar_title -> notes -> source ->
    area_annotation -> legend_title).
    """
    area_wan = area_km2 / 1e4
    suggestion = layers.suggestions(sheet, config.DATASETS)
    theme = config.THEMES[sheet.id]
    ordered = {
        "title": suggestion["title"],
        "subtitle": suggestion["subtitle"],
        "notes": [line.format(area_wan=area_wan) for line in sheet.notes],
        "source": suggestion.get("source", ""),
        "area_annotation": []
        if theme.area_label_in_map
        else ["伏尔加河流域", f"约 {area_wan:.0f} 万 km²"],
        "legend_title": LEGEND_TITLE,
        "colorbar_title": suggestion["colorbar_title"],
    }
    doc.set_suggestions(ordered)


# ============================
# 出图回调
# ============================
def draw(ctx: runner.RenderContext) -> None:
    """按改前的叠放顺序画图种特有的全部图层(底图与晕渲由 runner 之外的步骤控制).

    为什么高程不走 runner 的 dem_id: 本图的 ETOPO 栅格要先做「负高程陆地抬升」修正
    (见 docs/maps/volga.md 设计要点 4), 而 runner 在调用本回调之前就会铺好高程;
    所以高程在 main 里读取/修正一次, 这里用 ``layers.add_relief`` 原语铺上同一份.
    """
    data = _data()
    ax = ctx.ax
    sheet = ctx.sheet

    # ETOPO 已覆盖全部画框; 仍先铺海陆底色, 防止边缘缺测时露出白底.
    ax.set_facecolor(sheet.base_ocean)

    add_basin(ax, data.basin)
    add_admin(ax, data.subjects, config.THEMES[sheet.id])
    layers.add_relief(ax, sheet, data.lon, data.lat, data.z)
    add_rivers(ax, sheet.extent)
    add_water(ax, sheet.extent)
    add_borders(ax, data.border, sheet.extent)

    add_city_markers(ax, sheet.extent)
    layers.add_gridlines(ax, sheet)


def collect(doc, ctx: runner.RenderContext) -> None:
    """登记 geo: 地名 -> 经纬刻度 -> 色标 -> 图例 -> 文案(来源由数据集清单自动生成).

    顺序与改前一致; 地名/图例/文案是图种特有的动态数据, 所以不用 standard_collect.
    """
    data = _data()
    sheet = ctx.sheet
    collect_labels(doc, ctx.ax, sheet, data.basin_area_km2)
    layers.collect_graticule(doc, ctx.ax, sheet)
    layers.collect_relief(doc, sheet)
    collect_legend(doc, sheet)
    collect_suggestions(doc, sheet, data.basin_area_km2)


# ============================
# 主流程
# ============================
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stride",
        type=int,
        default=None,
        help="使用 data/raw 下对应采样步长的 ETOPO 文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    parser.add_argument(
        "--map",
        choices=("all", "basin", "republics"),
        default="all",
        help="只出其中一张图; 缺省两张都出(产物与改前一致)",
    )
    runner.add_standard_arguments(parser)
    args = parser.parse_args()

    etopo_path = find_etopo(
        DATA_DIR / "raw",
        "volga",
        args.stride,
        env_path=os.environ.get("VOLGA_ETOPO_PATH"),
    )
    _require(etopo_path)
    load_data(etopo_path)

    # 晕渲栅格密度按地图区宽度与 dpi 算(与原实现一致); --dpi 只影响这张内嵌栅格.
    dpi = args.dpi or config.SHEET_BASIN.dpi
    selected = (
        config.SHEETS
        if args.map == "all"
        else tuple(sheet for sheet in config.SHEETS if sheet.id == args.map)
    )
    for sheet in selected:
        layout = config.LAYOUTS[sheet.id]
        sheet = replace(sheet, regrid_shape=max(1200, int(layout.map_width_in * dpi)))
        # 注意: 不用 tight_layout / bbox_inches="tight";
        # cartopy 在非矩形投影上绘制经纬网时会触发 gridliner 用未闭合顶点构造
        # 多边形的 GEOSException, 且 tight bbox 会裁掉地图边缘(项目已踩过).
        runner.render(
            sheet,
            root=ROOT,
            catalog=config.DATASETS,
            draw=draw,
            collect=collect,
            dpi=args.dpi,
            show=False,
            close=not args.show,
        )

    if args.show:
        plt.show()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
