#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Topographic map of Shan State's special/armed-group regions.

是什么: 以掸邦为中心绘制缅甸联邦第一特区,德昂邦,佤邦,掸邦东部第四特区及
周边的地形图, 并在第一特区内标出其前身"原果敢自治区"的范围; 只绘制地理要素,
文字/图例/色标/标题/刻度文字都以数据形式写进同名 ``<产物>.geo.json``, 由前端排版.
画框/投影/色带/经纬网/地名/文案/图例/配色全部声明在 ``Myanmar/config.py``;
本图的特殊图层(特区填色与斜线,原果敢自治区,干流强调,OSM 国界)留在本脚本,
用共享原语画; geo.json 由 runner 缺省的 ``layers.standard_collect`` 按 Sheet 收集.
本文件是模块, 只导出 ``run()``, 由统一入口 ``python Myanmar/main.py render`` 调用.
完整说明(范围,南界取值理由,投影,果敢关系,国界处理)见
``docs/maps/northern-shan.md``; 出图流程见 ``docs/reference/runner.md``,
图层原语见 ``docs/reference/layers.md``.
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
import cartopy.feature as cfeature  # 河流/湖泊等自然要素
import matplotlib.pyplot as plt  # 绘图
from shapely.geometry import shape  # GeoJSON -> Shapely
from shapely.ops import unary_union  # 合并同类边界

# 图种规格与数据集清单: 画框/投影/色带/经纬网/地名/文案都从这里取, 见 docs/reference/spec.md.
import config

# 共享图层原语(底图/经纬网/城市点/经纬刻度/色标/geo 收集), 见 docs/reference/layers.md.
from cartopy_file import layers

# 统一出图流程(建画布 -> 底图 -> 本脚本图层 -> geo 保存), 见 docs/reference/runner.md.
from cartopy_file import runner

# 区域/省界描边与国界重合时只保留国界: 用共享剪枝工具裁掉国界走廊.
from cartopy_file.overlap import cut

# ETOPO 定位与高程读取,Natural Earth 图层读取, 见 docs/reference/relief.md.
from cartopy_file.relief import find_etopo, load_elevation, load_ne_layer, make_relief

# 斜线填充的线宽: 默认 1.0 在成品尺寸下偏粗, 会把特区填充压成深色块.
plt.rcParams["hatch.linewidth"] = 0.45

SHEET = config.SHEET_NORTHERN_SHAN
DATASETS = config.DATASETS

# 缓存路径由数据集清单给出(raw/ 的约定见 docs/reference/datasets.md).
REGION_GEOJSON = DATASETS.path(config.SHAN_REGIONS)
BORDER_GEOJSON = DATASETS.path(config.OSM_COUNTRY_BORDERS)

# ============================
# 本图特有图层
# ============================
# 图面配色(区域填充/边界色,国界,果敢自治区,图例共用色)全部在 config.py,
# 图例与地图共用同一份, 改色时两边一起变; 这里只留几何参数.
# 区域边界描边在国界两侧各裁掉这么宽(度)的走廊, 让重合段只由国界线表示.
# 0.001° 约 110 m, 远小于 300 dpi 下 2.7 pt 线宽对应的大约 1.9 km, 肉眼不可见.
BORDER_ZONE_DEG = 0.001

# 两条大江的强调线所对应的 Natural Earth name_en.
# Natural Earth 10m 把两条江拆成多段(Salween 上游 Nu + 下游 Salween,
# Irrawaddy 另有三角洲段), 按 name_en 全部选出再画, 河线才从画框北缘一直连到南缘.
MAIN_RIVERS = ("Irrawaddy", "Salween")


# ============================
# 数据读取
# ============================
def load_regions(path: Path) -> dict[str, list]:
    """读取 download_regions.py 缓存的 GeoJSON, 按图层分组返回 Shapely 几何.

    返回 {layer: [(properties, geometry), ...]}; layer 见 download_regions.py.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"未找到区域边界: {path}\n请先运行: python Myanmar/main.py download"
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
            f"未找到国界数据: {path}\n请先运行: python Myanmar/main.py download"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return unary_union([shape(feature["geometry"]) for feature in data["features"]])


# ============================
# 本图特有图层
# ============================
def add_relief(ax: plt.Axes, etopo_path: Path) -> None:
    """读取高程并叠加晕渲地形.

    色带/范围/来光/夸张系数从 ``Sheet.relief`` 取; 色带名是 matplotlib 的
    ``terrain``, 这样底图配色与 geo.relief 用的是同一条色带, 不会出现两套 anchor.
    """
    relief = SHEET.relief
    lon, lat, z = load_elevation(etopo_path)
    rgba, _, _ = make_relief(
        z,
        lat,
        lon,
        vmin=relief.vmin,
        vmax=relief.vmax,
        cmap=relief.name,
        azimuth=relief.azimuth,
        altitude=relief.altitude,
        vert_exag=relief.vert_exag,
    )
    # regrid_shape 默认 750, 对 15 弧秒数据在 300 dpi 下会糊; 提到 3000.
    ax.imshow(
        rgba,
        origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        regrid_shape=SHEET.regrid_shape,
        interpolation="nearest",
        zorder=relief.zorder,
    )


def add_context(ax: plt.Axes, border_line) -> None:
    """绘制国界,河流与湖泊, 作为区域色块下方的地理参照.

    国界用 OSM admin_level=2 折线, 与区域边界同源: 区域边界沿国界的那一段
    与这里的国界线完全重合(坐标级), 所以不会出现 Natural Earth 那种偏移.
    """
    ax.add_geometries(
        [border_line],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=config.COLOR_BORDER,
        linewidth=config.BORDER_WIDTH,
        alpha=config.BORDER_ALPHA,
        zorder=6.2,
    )
    # 河流/湖泊放在区域填充之上, 避免半透明色块把水系盖住.
    ax.add_feature(
        cfeature.RIVERS.with_scale("10m"),
        edgecolor=config.RIVER_COLOR,
        linewidth=0.7,
        zorder=4,
    )
    ax.add_feature(
        cfeature.LAKES.with_scale("10m"),
        facecolor="#a6cee3",
        edgecolor=config.RIVER_COLOR,
        linewidth=0.4,
        zorder=4,
    )


def add_main_rivers(ax: plt.Axes) -> None:
    """把伊洛瓦底江与萨尔温江从一般河流里强调出来.

    先用浅色粗描边,再用深蓝细线, 与行政图里的强调方式一致; 一般河流仍是
    add_context 里的 0.7 pt 蓝线, 作为背景水系, 不抢这两条干流的层级.
    """
    rivers = load_ne_layer("10m", "physical", "rivers_lake_centerlines")
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
            edgecolor=config.PROVINCE_EDGE_COLOR,
            linewidth=1.0,
            linestyle=(0, (6, 3)),
            zorder=5.5,
        )


def add_special_regions(ax: plt.Axes, regions: dict[str, list], border_zone) -> None:
    """按图层绘制各区域的填充,外边界与内部县界.

    另画出第一特区内的原果敢自治区(嵌套深紫填充), 表示包含关系.

    外边界先减去 border_zone(国界走廊)再画: 与国界重合的段由 add_context
    里的国界线负责, 这样区域边界不会在国界上再压一条区域颜色的线.
    """
    # 四个区域里第一特区最后画, 压在佤邦/四特/德昂邦之上.
    draw_order = ["wa", "sr4", "taang", "sr1"]
    for layer in draw_order:
        style = config.REGION_STYLES[layer]
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
    # (压在第一特区浅紫填充之上,MNDAA 斜线之下); 不描内边界, 避免粗线
    # 把果敢境内的河流盖住.
    for _, geom in regions.get("kokang_saz", []):
        ax.add_geometries(
            [geom],
            crs=ccrs.PlateCarree(),
            facecolor=config.KOKANG_SAZ_FILL,
            edgecolor="none",
            alpha=config.KOKANG_SAZ_ALPHA,
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
        edgecolor=config.MNDAA_HATCH_COLOR,
        hatch=config.MNDAA_HATCH,
        alpha=0.35,
        linewidth=0,
        zorder=3.0,
    )

    # 内部县/特区界: 第一特区 1 市 4 县,佤邦 5 县 1 特区,四特 3 县.
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
                edgecolor=config.INTERNAL_EDGE_COLOR,
                linewidth=0.65,
                linestyle="--",
                alpha=0.85,
                zorder=6.0,
            )


def add_city_markers(ax: plt.Axes) -> None:
    """绘制城市点: 特区首府用星形, 区域中心城市用方点, 普通城镇用小圆点.

    城名不在这里画: 名称/落点属于排版文字, 只进 geo.labels(由 Sheet.labels 登记).
    """
    for city in SHEET.cities:
        if city.capital:
            marker = "*"
        elif city.name in config.NORTHERN_SHAN_MAJOR:
            marker = "s"
        else:
            marker = "o"
        ax.plot(
            city.lon,
            city.lat,
            marker=marker,
            markersize=city.size,
            markerfacecolor=city.facecolor,
            markeredgecolor=city.edgecolor,
            markeredgewidth=city.edge_width,
            transform=ccrs.PlateCarree(),
            zorder=10,
        )


# ============================
# 主流程
# ============================
def draw(
    ctx: runner.RenderContext,
    *,
    etopo_path: Path,
    regions: dict[str, list],
    border_line,
    border_zone,
) -> None:
    """按本图的叠放顺序画剩余图层: 地形 -> 省邦界 -> 国界/水系 -> 干流 -> 特区色块 -> 城市点 -> 经纬网."""
    ax = ctx.ax
    add_relief(ax, etopo_path)
    add_admin_context(ax, regions, border_zone)
    add_context(ax, border_line)
    # 两条大江压在一般河流与区域填充之上,国界/区域边界之下.
    add_main_rivers(ax)
    add_special_regions(ax, regions, border_zone)
    add_city_markers(ax)
    layers.add_gridlines(ax, SHEET)


def run(*, stride: int | None = None, dpi: int | None = None, show: bool = False) -> int:
    """渲染掸邦/特区地形图并写出同名 geo.json; 返回 0=成功, 1=数据缺失."""
    try:
        etopo_path = find_etopo(DATA_DIR / "raw", "northern_shan", stride)
        if not etopo_path.exists():
            raise FileNotFoundError(
                f"未找到高程数据: {etopo_path}\n"
                "请先运行: python Myanmar/main.py download --region northern-shan --stride 1"
            )
        regions = load_regions(REGION_GEOJSON)
        border_line = load_borders(BORDER_GEOJSON)
        # 国界走廊: 用来把区域/省界描边里与国界重合的段裁掉.
        border_zone = border_line.buffer(BORDER_ZONE_DEG, cap_style="flat", join_style="mitre")

        runner.render(
            SHEET,
            root=ROOT,
            catalog=DATASETS,
            draw=functools.partial(
                draw,
                etopo_path=etopo_path,
                regions=regions,
                border_line=border_line,
                border_zone=border_zone,
            ),
            # 没有动态数据也要显式给 area_annotation=(): 旧产物有 "area_annotation": [],
            # standard_collect 缺省不写这个键, 显式传空元组才与改前 geo.json 一致.
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
