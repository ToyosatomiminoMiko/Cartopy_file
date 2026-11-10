#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Administrative-division map of Myanmar.

是什么: 绘制缅甸省/邦级行政区划图, 七邦冷色,七省暖色,内比都联邦区中性色加斜线,
叠加河流与 ETOPO 2022 地形晕渲, 并画出各行政区中心点; 国界用半透明红色,只画陆地
上的国界段, 海岸线不单独绘制. 底图只画地理要素, 文字/图例/色标/标题/刻度文字都由
同名 ``<产物>.geo.json`` 交给前端排版; 画框/投影/色带/经纬网/双语地名/图例/配色全部
声明在 ``Myanmar/config.py`` 的 ``SHEET_ADMIN``. 本图的特殊图层(行政区填色,河网,
国界线型,自定义地形底纹)留在本脚本, 用共享原语画. 本文件是模块, 只导出 ``run()``,
由统一入口 ``python Myanmar/main.py render`` 调用.
完整说明(配色,投影,数据来源,运行方式)见 ``docs/maps/myanmar-admin.md``;
出图流程见 ``docs/reference/runner.md``, 图层原语见 ``docs/reference/layers.md``.
"""

from __future__ import annotations

import functools
import json
import os
import sys
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指到可写位置, 见 docs/reference/data.md.
from cartopy_file.data import prepare_matplotlib_env

prepare_matplotlib_env()

ROOT = Path(__file__).resolve().parent

import cartopy.crs as ccrs  # 地图投影
import geopandas as gpd  # 读取 Natural Earth shapefile
import matplotlib.colors as mcolors  # 颜色与色带
import matplotlib.pyplot as plt  # 绘图
import numpy as np  # 数组运算
from shapely.geometry import LineString, shape  # GeoJSON -> Shapely / 取外环
from shapely.ops import unary_union  # 合并行政区, 得到缅甸整体轮廓

# 图种规格与数据清单: 画框/投影/色带/经纬网/文案都从这里取, 见 docs/reference/spec.md.
import config

# 共享图层原语(底图/经纬网/城市点/geo 收集), 见 docs/reference/layers.md.
from cartopy_file.catalog import catalog_for

from cartopy_file import layers

# 统一出图流程(建画布 -> 底图 -> 本脚本图层 -> geo 保存), 见 docs/reference/runner.md.
from cartopy_file import runner

# 国界与海岸线重合时只保留国界: 用共享剪枝工具裁掉沿海段, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# ETOPO 定位与高程读取,Natural Earth 图层读取, 见 docs/reference/relief.md.
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
CATALOG = catalog_for(config.DATA_GROUP)

# 原始数据路径由数据清单 manifest 给出(目录约定见 docs/reference/data.md);
# 行政区 GeoJSON 由本仓 prepare.py 生成到 build/(见 docs/reference/spec.md).
ADMIN_GEOJSON = config.ADMIN_GEOJSON
RIVER_SHP = (
    CATALOG.path("ne-rivers-10m") / "ne_10m_rivers_lake_centerlines.shp"
)

# ============================
# 本图特有图层
# ============================
# 配色/图例/标注全部在 config.py: 行政区填色与图例共用 STATE_COLORS/REGION_COLORS,
# 国界/邻国国界用共享的 COLOR_BORDER/COLOR_NEIGHBOR, 标注落点见 ADMIN_LABEL_POSITIONS.
# 这里只留几何参数(剪枝走廊)与框架 Relief 字段表达不了的晕渲细节.

# 国界剪掉沿海段的缓冲半径(度). 本图不画海岸线, 海陆界线由底色/填色分界;
# 国界面本身沿海岸闭合, 整圈画出来就等于又画了一条红色海岸线, 所以只留陆上段.
# 0.06° 在 20°N 一带约 6 km, 覆盖两套折线的数字化偏差; 剪剩碎段按 3 km 丢掉.
COAST_CLIP_DEG = 0.06
COAST_CLIP_MIN_LEN = 0.03
# 邻国国界从缅甸国界两侧这么宽的走廊里剪掉, 避免红线下透出平行灰线.
NEIGHBOR_GAP_DEG = 0.06
# 省/邦界在国界,海岸走廊里剪掉的宽度(度). 这些填色单元的外缘与国界/海岸
# 完全重合, 不剪会在半透明红线下面透出一条深灰的省界线, 海岸上也会留下一圈
# 省界线 -- 都等于变相画了海岸线. 0.005° 约 550 m, 远小于图上国界线半宽.
BORDER_ZONE_DEG = 0.005

# 地形底纹的晕渲细节. 色带/范围/来光/夸张系数都在 Sheet.relief 里; 这里只留
# 框架 Relief 字段表达不了的两个数值: 软光混合的比例(改前成品用 1.0, 框架默认
# 1.2)与海洋像元的透明度(海面保留纯底色, 否则负高程也会被染成米色).
RELIEF_SHADE_FRACTION = 1.0
# 晕渲栅格在投影后再采样到 3000 像素宽: 默认 750 对 30 弧秒数据会糊.
RELIEF_REGRID_SHAPE = 3000
RELIEF_INTERPOLATION = "bilinear"

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
    会把这些细缝的环也当成国界画出来 -- 半透明红线在掸邦-克钦邦,仰光省-勃固省
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
        edgecolor=config.COLOR_NEIGHBOR,
        linewidth=0.45,
        linestyle=(0, (5, 3)),
        zorder=1.5,
    )


def add_relief(ax: plt.Axes, etopo_path: Path) -> None:
    """叠加只覆盖陆地的低透明度地形晕渲(海面保留底色).

    色带/高程范围/来光/夸张系数从 ``Sheet.relief`` 取; 晕渲细节(软光比例,海洋像元
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
        color = (
            config.STATE_COLORS[key]
            if unit["kind"] == "state"
            else config.REGION_COLORS[key]
        )
        ax.add_geometries(
            [unit["geometry"]],
            crs=ccrs.PlateCarree(),
            facecolor=(*mcolors.to_rgb(color), config.FILL_ALPHA),
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
            edgecolor=config.BOUNDARY_COLOR,
            linewidth=1.05,
            zorder=5,
        )

    union = next(unit for unit in units if unit["kind"] == "union")
    ax.add_geometries(
        [union["geometry"]],
        crs=ccrs.PlateCarree(),
        facecolor=(*mcolors.to_rgb(config.UNION_COLOR), 0.92),
        edgecolor=config.UNION_EDGE_COLOR,
        linewidth=1.15,
        hatch=config.UNION_HATCH,
        zorder=6,
    )


def add_rivers(ax: plt.Axes) -> None:
    """画出伊洛瓦底江与萨尔温江, 外加浅色描边使其在彩色块上可读.

    Natural Earth 里伊洛瓦底江被拆成 Ayeyarwady + Irrawaddy Delta,
    萨尔温江被拆成 Nu + Salween 两段; 按 name_en 统一筛选再合并.
    """
    if not RIVER_SHP.exists():
        raise FileNotFoundError(
            f"未找到河流数据: {RIVER_SHP}\n请先到数据项目 miko_gis_data 运行: "
            "python main.py download --group myanmar"
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
        edgecolor=config.ADMIN_RIVER_COLOR,
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
        edgecolor=config.COLOR_BORDER,
        linewidth=config.BORDER_WIDTH,
        alpha=config.BORDER_ALPHA,
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
                    config.CAPITAL_FILL,
                    config.CAPITAL_EDGE,
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
                    config.CAPITAL_EDGE,
                    0.9,
                    name=unit["capital_zh"],
                )
            )
    layers.add_cities(ax, cities, zorder=15)


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


def run(*, stride: int | None = None, dpi: int | None = None, show: bool = False) -> int:
    """渲染行政区划图并写出同名 geo.json; 返回 0=成功, 1=数据缺失."""
    try:
        etopo_path = find_etopo(
            CATALOG.raw_dir,
            "myanmar",
            stride,
            env_path=os.environ.get("MYANMAR_ETOPO_PATH"),
        )
        if not etopo_path.exists():
            raise FileNotFoundError(
                f"未找到高程数据: {etopo_path}\n"
                "请先到数据项目 miko_gis_data 运行: python main.py download --group myanmar"
            )

        units = load_admin_units()
        # 国界与省/邦界都以 15 个行政区合并后的外环为基准: 填色与红线同源,
        # 岸上不会出现两套边界; border_zone 用来剪掉省/邦界里与国界/海岸重合的段.
        # 只取外环是为了丢掉并集内部因浮点误差产生的零面积细缝 -- 否则红线会在
        # 掸邦-克钦邦,仰光省-勃固省等内部边界上残留一串红色短段.
        myanmar_geom = unary_union([unit["geometry"] for unit in units])
        country_border = country_exterior(myanmar_geom)
        if country_border is None:
            raise ValueError("行政区并集没有外环, 无法确定国界")
        border_zone = country_border.buffer(BORDER_ZONE_DEG)

        # 画布/坐标区/范围/底图由 runner 按 Sheet 建好; 本图的特有图层按叠放顺序在 draw 里画.
        runner.render(
            SHEET,
            root=ROOT,
            catalog=CATALOG,
            draw=functools.partial(
                draw,
                etopo_path=etopo_path,
                units=units,
                myanmar_geom=myanmar_geom,
                border_zone=border_zone,
                country_border=country_border,
            ),
            # 旧产物有 "area_annotation": [], standard_collect 缺省不写这个键;
            # 显式传空元组才与改前 geo.json 一致.
            area_annotation=(),
            dpi=dpi,
            show=show,
        )
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python Myanmar/main.py <子命令>")
