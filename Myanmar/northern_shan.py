#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Topographic map of Shan State's special/armed-group regions.

是什么: 以掸邦为中心绘制缅甸联邦第一特区、德昂邦、佤邦、掸邦东部第四特区及
周边的地形图, 并在第一特区内标出其前身"原果敢自治区"的范围; 只绘制地理要素,
文字/图例/色标/标题/刻度文字都以数据形式写进同名 ``<产物>.geo.json``, 由前端排版.
画框/投影/色带/经纬网/地名/文案取自 ``Myanmar/config.py``; 本图的特殊图层
(特区填色与斜线、原果敢自治区、干流强调、OSM 国界)留在本脚本, 用共享原语画.
本文件是模块, 只导出 ``run()``, 由统一入口 ``python Myanmar/main.py render`` 调用.
完整说明(范围、南界取值理由、投影、果敢关系、国界处理)见
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

# ETOPO 定位与高程读取、Natural Earth 图层读取, 见 docs/reference/relief.md.
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
# 与它重合的区域边界; 图例里的线段也带同样的 alpha.
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

    先用浅色粗描边、再用深蓝细线, 与行政图里的强调方式一致; 一般河流仍是
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
    """绘制城市点: 特区首府用星形, 区域中心城市用方点, 普通城镇用小圆点.

    城名不在这里画: 名称/落点/字号属于排版文字, 只进 geo.labels(由 Sheet.labels 登记).
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
# geo.json 收集
# ============================
def collect_legend(doc) -> None:
    """把旧图手工构造的图例整理成 geo.legend(不画图例框).

    条目字段与旧图例的句柄一一对应: 区域/自治区为 rect(填充+描边)、线要素为
    line、首府为 point. label_lines 与 hatch 是契约 v2 的预留字段: 这里把旧图
    的图例文字按行给出, hatch 条目给出斜线图案, 前端将来升 v2 时不用再改数据.
    """
    entries = [
        {
            "label": "缅甸联邦第一特区(辖区)",
            "label_lines": ["缅甸联邦第一特区(辖区)"],
            "shape": "rect",
            "stroke": REGION_STYLES["sr1"]["edge"],
            "width_pt": 1.5,
            "fill": REGION_STYLES["sr1"]["fill"],
            "opacity": 0.6,
        },
        {
            "label": "原果敢自治区(2010–2023)",
            "label_lines": ["原果敢自治区(2010–2023)"],
            "shape": "rect",
            "stroke": None,
            "width_pt": 0.0,
            "fill": KOKANG_SAZ_FILL,
            "opacity": 0.8,
        },
        {
            "label": "MNDAA 实控区(大致)",
            "label_lines": ["MNDAA 实控区(大致)"],
            "shape": "rect",
            "stroke": MNDAA_HATCH_COLOR,
            "width_pt": 0.0,
            "fill": None,
            "opacity": 1.0,
            # 图例色块只有约 20 pt 宽, 图上 "///" 在这个尺寸下几乎看不出斜线,
            # 所以图例用更密的 "////"; 颜色仍与图上斜线同色.
            "hatch": "////",
        },
        {
            "label": "德昂邦(TNLA 控制)",
            "label_lines": ["德昂邦(TNLA 控制)"],
            "shape": "rect",
            "stroke": REGION_STYLES["taang"]["edge"],
            "width_pt": 1.5,
            "fill": REGION_STYLES["taang"]["fill"],
            "opacity": 0.6,
        },
        {
            "label": "佤邦",
            "label_lines": ["佤邦"],
            "shape": "rect",
            "stroke": REGION_STYLES["wa"]["edge"],
            "width_pt": 1.5,
            "fill": REGION_STYLES["wa"]["fill"],
            "opacity": 0.6,
        },
        {
            "label": "掸邦东部第四特区",
            "label_lines": ["掸邦东部第四特区"],
            "shape": "rect",
            "stroke": REGION_STYLES["sr4"]["edge"],
            "width_pt": 1.5,
            "fill": REGION_STYLES["sr4"]["fill"],
            "opacity": 0.6,
        },
        {
            "label": "国界",
            "label_lines": ["国界"],
            "shape": "line",
            "stroke": BORDER_COLOR,
            "width_pt": BORDER_WIDTH,
            "opacity": BORDER_ALPHA,
        },
        {
            "label": "省/邦界",
            "label_lines": ["省/邦界"],
            "shape": "line",
            "stroke": "#7f7f7f",
            "width_pt": 1.0,
            "dash": [6.0, 3.0],
        },
        {
            "label": "河流",
            "label_lines": ["河流"],
            "shape": "line",
            "stroke": "#1f78b4",
            "width_pt": 0.9,
        },
        {
            "label": "特区首府",
            "label_lines": ["特区首府"],
            "shape": "point",
            "stroke": "#000000",
            "width_pt": 1.0,
            "fill": "#ffd200",
            "marker": "star",
        },
    ]
    doc.set_legend("图例", entries)


def collect_suggestions(doc) -> None:
    """默认文案: 标题/副标题/注/来源只给前端预填, 不参与底图合成.

    标题/副标题/注来自 ``Sheet``; 来源由 ``DatasetSet.citation`` 按
    ``Sheet.dataset_ids`` 自动生成(带发布页 URL), 缩写表由 ``Sheet.extra_source``
    追加. 本图 7 条区域注记都在画框内(已进 geo.labels), 没有图外面积注记, 因此
    area_annotation 为空; legend_title/colorbar_title 与 collect_legend /
    collect_relief 的标题保持同一口径.
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
    regions: dict[str, list],
    border_line,
    border_zone,
) -> None:
    """按本图的叠放顺序画剩余图层: 地形 -> 省邦界 -> 国界/水系 -> 干流 -> 特区色块 -> 城市点 -> 经纬网."""
    ax = ctx.ax
    add_relief(ax, etopo_path)
    add_admin_context(ax, regions, border_zone)
    add_context(ax, border_line)
    # 两条大江压在一般河流与区域填充之上、国界/区域边界之下.
    add_main_rivers(ax)
    add_special_regions(ax, regions, border_zone)
    add_city_markers(ax)
    layers.add_gridlines(ax, SHEET)


def collect(doc, ctx: runner.RenderContext) -> None:
    """登记 geo: 地名 -> 经纬刻度 -> 色标 -> 图例 -> 文案(来源由数据集清单自动生成)."""
    layers.collect_labels(doc, ctx.ax, SHEET.labels)
    layers.collect_graticule(doc, ctx.ax, SHEET)
    layers.collect_relief(doc, SHEET)
    collect_legend(doc)
    collect_suggestions(doc)


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
            collect=collect,
            dpi=dpi,
            show=show,
        )
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python Myanmar/main.py <子命令>")
