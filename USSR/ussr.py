#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""USSR topography map: ETOPO 2022 relief with merged ex-USSR borders.

是什么: 从本地 ETOPO 2022 NetCDF 读取苏联区域高程, 用兰勃特等面积方位投影绘制地形图,
叠加 Natural Earth 110m 海岸线与 15 个前苏联加盟共和国合并出的红色外轮廓.
文字与版面由前端接管, 本脚本同时产出同名的 geo.json: 底图只画地理要素, 色标/标题/
副标题只以 ``GeoDoc`` 数据形式登记; 字段与口径见 ``docs/reference/geo.md``.
画框/投影/色带/经纬网/文案全部来自 ``USSR/specs.py``; 完整说明(投影选择、图幅内容、
数据来源、运行方式)见 ``docs/maps/ussr.md``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import cartopy.feature as cfeature  # 海岸线(固定 110m)
import numpy as np  # 筛选国界要素
from shapely.ops import unary_union  # 合并多个面为苏联整体轮廓

# 图种规格与数据集清单: 画框/投影/色带/经纬网/文案都从这里取, 见 docs/reference/spec.md.
import specs

# 共享图层原语(经纬网/色标/geo 收集), 见 docs/reference/layers.md.
from cartopy_file import layers

# 统一出图流程(建画布 -> 高程 -> 本脚本图层 -> geo 保存), 见 docs/reference/runner.md.
from cartopy_file import runner

# ETOPO 定位, 见 docs/reference/relief.md.
from cartopy_file.relief import find_etopo

SHEET = specs.SHEET_USSR
DATASETS = specs.DATASETS

# ============================
# 本图特有图层
# ============================
# 前苏联 15 个加盟共和国的 Natural Earth 英文国名.
USSR_REPUBLICS = (
    "Russia",
    "Ukraine",
    "Belarus",
    "Moldova",
    "Georgia",
    "Armenia",
    "Azerbaijan",
    "Kazakhstan",
    "Uzbekistan",
    "Turkmenistan",
    "Kyrgyzstan",
    "Tajikistan",
    "Lithuania",
    "Latvia",
    "Estonia",
)

# 国界样式: 改前成品的口径——纯红实线、只画线不填充, 免得盖住地形.
BORDER_COLOR = "red"
BORDER_WIDTH = 1.8
# 海岸线样式: 黑色细线, 与底图叠在一起看地形与海岸的对应关系.
COASTLINE_WIDTH = 0.6
COASTLINE_COLOR = "black"


def draw_ussr_border(ax, world) -> None:
    """把 15 个加盟共和国合并成苏联外轮廓, 只画红色轮廓线.

    为什么只画线不填充: 苏联不是一个真实存在的国家面, 填充会盖住地形;
    轮廓与红星色是改前成品的口径.
    """
    if world is None:
        return

    # Natural Earth 字段因版本不同可能是 NAME/NAME_EN/ADMIN, 只保留实际存在的字段.
    name_columns = [c for c in ("NAME", "NAME_EN", "ADMIN") if c in world.columns]
    if not name_columns:
        raise RuntimeError("无法识别 Natural Earth 国名字段,请检查 shapefile.")

    # 优先使用第一个可用国名字段筛选出前苏联国家.
    name_column = name_columns[0]
    ussr_countries = world[world[name_column].isin(USSR_REPUBLICS)]
    if ussr_countries.empty:
        # 某些版本使用 sovereign 字段更准确,退化到所有字段模糊匹配.
        mask = np.zeros(len(world), dtype=bool)
        for col in name_columns:
            mask |= world[col].isin(USSR_REPUBLICS).to_numpy()
        ussr_countries = world[mask]

    if ussr_countries.empty:
        print("警告: 未在 Natural Earth 数据中找到目标国家,跳过红色边界.")
        return

    # 将多个加盟共和国几何合并成一个整体,得到苏联外轮廓.
    ussr_boundary = unary_union(ussr_countries.geometry)
    ax.add_geometries(
        [ussr_boundary],
        crs=ccrs.PlateCarree(),
        edgecolor=BORDER_COLOR,
        facecolor="none",
        linewidth=BORDER_WIDTH,
    )


def draw(ctx: runner.RenderContext) -> None:
    """按本图的叠放顺序画剩余图层: 海岸线 -> 苏联轮廓 -> 经纬网.

    为什么海岸线钉死 110m: ``cfeature`` 默认按视野自动选分辨率, 缩放重绘时可能换到
    没预取的 50m/10m 并触发下载, 违背「出图不联网」; 110m 是改前成品的实际分辨率,
    也由根目录 ``download_data.py`` 按 specs.py 的 cartopy-ne 声明预取.
    为什么自己读国界: ``Sheet.basemap=False`` 时 runner 不加载共享底图, 苏联轮廓要的
    是 10m 国界(与 110m 海岸线同尺度才不会折线); 这份图层全项目共用 data/cartopy 缓存.
    """
    ctx.ax.add_feature(
        cfeature.COASTLINE.with_scale("110m"),
        linewidth=COASTLINE_WIDTH,
        color=COASTLINE_COLOR,
    )
    world = layers.countries_frame()
    draw_ussr_border(ctx.ax, world)
    layers.add_gridlines(ctx.ax, SHEET)


def collect(doc, ctx: runner.RenderContext) -> None:
    """登记 geo: 经纬网线型 -> 色标 -> 文案(来源由数据集清单自动生成).

    为什么不调 ``layers.standard_collect``: 改前成品没有经纬刻度文字, 旧脚本只用
    ``set_graticule_style`` 写线型、把 lon/lat 留空; 换成 ``collect_graticule`` 会
    给前端补出一圈旧图没有的刻度文字.
    """
    graticule = SHEET.graticule
    doc.set_graticule_style(
        stroke=graticule.stroke,
        width_pt=graticule.width_pt,
        dash=graticule.dash,
        opacity=graticule.opacity,
    )
    layers.collect_relief(doc, SHEET)
    doc.set_suggestions(layers.suggestions(SHEET, DATASETS))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stride",
        type=int,
        default=None,
        help="使用 data/raw 下对应采样步长的高程文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    runner.add_standard_arguments(parser)
    args = parser.parse_args()

    etopo_path = find_etopo(
        DATA_DIR / "raw",
        "ussr",
        args.stride,
        env_path=os.environ.get("ETOPO_PATH"),
    )
    runner.render(
        SHEET,
        root=ROOT,
        catalog=DATASETS,
        draw=draw,
        collect=collect,
        dem_path=etopo_path,
        dpi=args.dpi,
        show=args.show,
    )


if __name__ == "__main__":
    main()
