# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Layer primitives shared by every map script: figure, basemap, relief, graticule, labels.

是什么: 把各图种脚本里重复的图层代码收敛成一组函数——建画布与坐标区、铺海陆底色、
画 ETOPO 晕渲、经纬网、城市点、地名收集、色标与文案收集. 图种特有的图层(国界、行政区、
河流、流域)仍留在各自脚本里, 只是改用这里提供的原语和 spec 里的数据.
完整说明(哪些进了框架、哪些故意不进、像素级一致怎么保证)见 ``docs/reference/layers.md``.
"""

from __future__ import annotations

import math

import cartopy.crs as ccrs
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from . import relief as relief_helpers
from .data import configure_cartopy, natural_earth_paths
from .geo import GeoDoc, relief_from_cmap
from .output import apply_svg_output
from .spec import Extent, Graticule, Projection, Relief, Sheet

# 缓存目录必须在导入 matplotlib 之前设好(见 docs/reference/data.md), 各脚本已经在
# 文件顶部 setdefault; 这里再确保 cartopy 缓存落在仓库内, 重复调用无副作用.
configure_cartopy()
apply_svg_output()

__all__ = [
    "add_base_map",
    "add_cities",
    "add_gridlines",
    "add_relief",
    "build_projection",
    "collect_graticule",
    "collect_labels",
    "collect_relief",
    "countries_frame",
    "figure_axes",
    "make_relief_cmap",
    "ne_dir",
    "standard_collect",
    "suggestions",
    "tick_values",
]


def build_projection(projection: Projection) -> ccrs.Projection:
    """把纯数据的 Projection 变成 cartopy 投影对象; 参数由 cartopy 校验."""
    cls = getattr(ccrs, projection.class_name)
    return cls(**dict(projection.params))


def make_relief_cmap(relief: Relief) -> mcolors.LinearSegmentedColormap:
    """按 spec 的锚点在 0 m 处断开的双色带.

    锚点写成 (高程 m, 颜色), 归一化横轴是线性的 u=(elev-vmin)/(vmax-vmin);
    水面锚点到 -1 m、陆地锚点从 +1 m 起, 中间的空隙就是海陆跳变.
    """
    def u(elevation: float) -> float:
        return (elevation - relief.vmin) / (relief.vmax - relief.vmin)

    anchors = [(u(elev), color) for elev, color in relief.sea]
    anchors += [(u(elev), color) for elev, color in relief.land]
    return mcolors.LinearSegmentedColormap.from_list(relief.name, anchors, N=relief.stops)


def tick_values(lo: float, hi: float, step: float) -> list[float]:
    """区间 [lo, hi] 内 step 的整倍数; 与 geo.add_graticule 的取点规则完全一致."""
    if step <= 0:
        raise ValueError(f"刻度步长必须 > 0, 得到 {step!r}")
    start = math.ceil(lo / step) * step
    values: list[float] = []
    value = start
    while value <= hi + 1e-9:
        values.append(round(value, 10))
        value += step
    return values


def figure_axes(sheet: Sheet) -> tuple[plt.Figure, plt.Axes]:
    """按 spec 建画布与坐标区, 并把范围设成 sheet.extent.

    两种版式: ``axes`` 给了矩形就用 ``add_axes``(位置完全可控); 没给就用
    ``plt.subplots`` 的默认布局. 两者产物的坐标不同, 所以这是 spec 数据而不是风格选择.
    """
    projection = build_projection(sheet.projection)
    if sheet.axes is None:
        fig, ax = plt.subplots(figsize=sheet.figsize, subplot_kw={"projection": projection})
    else:
        fig = plt.figure(figsize=sheet.figsize, facecolor="white")
        ax = fig.add_axes(list(sheet.axes), projection=projection)
    # GeoAxes 用 equal aspect 保持投影等比例, 在给定矩形内居中显示.
    ax.set_anchor("C")
    ax.set_extent(sheet.extent.as_list, crs=ccrs.PlateCarree())
    return fig, ax


def covered_extent(ax: plt.Axes) -> Extent:
    """画框在经纬度上的实际覆盖范围.

    非矩形投影的矩形画框会探出 set_extent 给的经纬度矩形(圆锥投影顶边张开),
    数据必须盖住这里, 所以它才是「下载范围要多大」的唯一依据.
    """
    x0, x1, y0, y1 = ax.get_extent(crs=ccrs.PlateCarree())
    return Extent(x0, x1, y0, y1)


def ne_dir(resolution: str, category: str, name: str):
    """Natural Earth 图层所在目录(共享缓存); 缺数据时返回下载目标目录."""
    found, target = natural_earth_paths(resolution, category, name)
    return (found if found is not None else target).parent


def countries_frame(resolution: str = "10m"):
    """读 Natural Earth 国家多边形; 缺数据时返回 None(由调用方决定是否跳过底图).

    必须按「层名」定位到具体 .shp: 共享缓存里同一类别目录下有几十个图层,
    按目录取 sorted(glob("*.shp"))[0] 会读到隔壁那一层(踩过).
    """
    return relief_helpers.load_ne_layer(resolution, "cultural", "admin_0_countries")


def add_base_map(ax: plt.Axes, sheet: Sheet, world=None) -> None:
    """铺真实海陆底色(ETOPO 子集盖不到的画框角落靠它兜底), 见 relief.add_base_map."""
    relief_helpers.add_base_map(
        ax,
        countries_frame() if world is None else world,
        ocean_color=sheet.base_ocean,
        land_color=sheet.base_land,
    )


def add_relief(ax: plt.Axes, sheet: Sheet, lon, lat, z) -> None:
    """铺高程(与晕渲).

    rgba 模式: 先把高程配色与山体晕渲合成为 RGB 图; regrid_shape 用 spec 里的值
    (默认 750 对 30 弧秒数据会糊), 传 RGB 数组给 imshow 时不能再给 cmap/vmin/vmax.
    scalar 模式: 直接把高程交给 imshow, 用命名色带, 由 matplotlib 自己做 norm.
    """
    relief = sheet.relief
    if relief.mode == "scalar":
        ax.imshow(
            z,
            origin="lower",
            extent=[lon[0], lon[-1], lat[0], lat[-1]],
            transform=ccrs.PlateCarree(),
            cmap=relief.name,
            alpha=relief.alpha,
            vmin=relief.vmin,
            vmax=relief.vmax,
            interpolation="nearest",
        )
        return

    rgba, _, _ = relief_helpers.make_relief(
        z,
        lat,
        lon,
        vmin=relief.vmin,
        vmax=relief.vmax,
        cmap=make_relief_cmap(relief),
        azimuth=relief.azimuth,
        altitude=relief.altitude,
        vert_exag=relief.vert_exag,
        shade_strength=relief.shade_strength,
        shade_floor=relief.shade_floor,
    )
    kwargs: dict = {
        "origin": "lower",
        "extent": [lon[0], lon[-1], lat[0], lat[-1]],
        "transform": ccrs.PlateCarree(),
        "interpolation": "nearest",
    }
    if sheet.regrid_shape is not None:
        kwargs["regrid_shape"] = sheet.regrid_shape
    if relief.zorder is not None:
        kwargs["zorder"] = relief.zorder
    ax.imshow(rgba, **kwargs)


def add_gridlines(ax: plt.Axes, sheet: Sheet) -> None:
    """画经纬网线(不画刻度文字, 刻度由前端按 geo.graticule 排版).

    网线位置优先用 spec 里写死的取值: 各图种的起点不同(有的从画框左下整倍数起,
    有的多给一格), 多算一条线就会在 SVG 里多出一条被裁剪的路径.
    """
    graticule = sheet.graticule
    lon_values = graticule.lon_ticks or tuple(
        tick_values(sheet.extent.lon_min, sheet.extent.lon_max, graticule.lon_step)
    )
    lat_values = graticule.lat_ticks or tuple(
        tick_values(sheet.extent.lat_min, sheet.extent.lat_max, graticule.lat_step)
    )
    grid = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=False,
        linewidth=graticule.width_pt,
        color=graticule.color,
        alpha=graticule.opacity,
        linestyle="-" if graticule.dash is None else (0, tuple(graticule.dash)),
        zorder=graticule.zorder,
    )
    grid.xlocator = mticker.FixedLocator(list(lon_values))
    grid.ylocator = mticker.FixedLocator(list(lat_values))


def add_cities(ax: plt.Axes, cities, *, zorder: float = 8) -> None:
    """画城市点: 首都星形, 其余空心圆; 名称只登记到 geo.labels, 不画文字."""
    for city in cities:
        ax.plot(
            city.lon,
            city.lat,
            marker="*" if city.capital else "o",
            markersize=city.size,
            markerfacecolor=city.facecolor,
            markeredgecolor=city.edgecolor,
            markeredgewidth=city.edge_width,
            transform=ccrs.PlateCarree(),
            zorder=zorder,
        )


def collect_labels(doc: GeoDoc, ax: plt.Axes, labels) -> None:
    """把地名候选按给定顺序登记进 geo.labels(顺序即前端的叠放 order)."""
    for label in labels:
        doc.add_label(
            ax,
            label.lon + label.dx,
            label.lat + label.dy,
            label.text,
            role=label.role,
            name=label.name,
            id_kind=label.id_kind,
            font_size_pt=label.font_size_pt,
            ha=label.ha,
        )


def collect_graticule(doc: GeoDoc, ax: plt.Axes, sheet: Sheet) -> None:
    """登记经纬刻度: 值只取画框内步长的整倍数, 坐标取网线与地图框边线的交点."""
    graticule = sheet.graticule
    doc.add_graticule(
        ax,
        tuple(sheet.extent.as_list),
        lon_step=graticule.lon_step,
        lat_step=graticule.lat_step,
        lon_side=graticule.lon_side,
        lat_side=graticule.lat_side,
        style=graticule.style,
    )


def collect_relief(doc: GeoDoc, sheet: Sheet) -> None:
    """登记高程色标: 与底图同一套色带/范围, 刻度取改前成品色标上的值."""
    relief = sheet.relief
    cmap = make_relief_cmap(relief) if relief.mode == "rgba" else plt.get_cmap(relief.name)
    doc.set_relief(
        relief_from_cmap(
            cmap,
            title=relief.title,
            unit=relief.unit,
            vmin=relief.vmin,
            vmax=relief.vmax,
            ticks=relief.ticks,
        )
    )


def suggestions(sheet: Sheet, catalog) -> dict:
    """拼 geo.suggestions: 文案来自 spec, 数据来源由数据集登记自动生成.

    为什么来源不手写: 手写的「数据源」句子里混着投影参数和废话, 换一张图就要重抄一遍,
    还会漏掉许可要求的署名. 这里按 ``sheet.dataset_ids`` 查 ``DatasetSet`` 的署名,
    每个数据源只出现一次, 且一定带发布页 URL.
    """
    suggestion: dict = {
        "title": sheet.title,
        "subtitle": sheet.subtitle,
    }
    # 没有高程色标的图不写 colorbar_title: 写了会让前端初始化出一块并不存在的版面.
    if sheet.relief is not None:
        suggestion["colorbar_title"] = sheet.colorbar_title
    source_line = catalog.citation(sheet.dataset_ids) if sheet.dataset_ids else ""
    if sheet.extra_source:
        source_line = f"{source_line} · {sheet.extra_source}" if source_line else sheet.extra_source
    if source_line:
        suggestion["source"] = source_line
    if sheet.notes:
        suggestion["notes"] = list(sheet.notes)
    return suggestion


def standard_collect(doc: GeoDoc, ax: plt.Axes, sheet: Sheet, catalog) -> None:
    """默认的 geo 收集顺序: 地名 -> 经纬刻度 -> 色标 -> 文案(图种可只调其中几步)."""
    collect_labels(doc, ax, sheet.labels)
    collect_graticule(doc, ax, sheet)
    if sheet.relief is not None:
        collect_relief(doc, sheet)
    doc.set_suggestions(suggestions(sheet, catalog))
