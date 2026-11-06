#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Draw a full-territory topographic map of the Republic of the Union of Myanmar.

是什么: 读取本地 NOAA ETOPO 2022 缅甸区域高程, 用兰勃特等角圆锥投影绘制全国
地形图, 叠加 Natural Earth 10m 国界(仅陆上段, 半透明红色)与邻国国界(灰虚线),
并画出主要城市点; 海岸线不单独绘制, 海陆界线由地形配色在 0 m 处的跳变表达.
文字与版面由前端接管, 本脚本同时产出同名的 geo.json: 底图只画地理要素, 地名/
色标/标题/来源只以 ``GeoDoc`` 数据形式登记, 不再画任何文字; 字段与口径见
``docs/reference/geo.md``. 本文件是模块, 只导出 ``run()``, 由统一入口
``python Myanmar/main.py render`` 调用. 画框/色带/地名/文案与国界配色全部来自
``Myanmar/config.py``; geo.json 由 runner 缺省的 ``layers.standard_collect`` 按 Sheet 收集.
完整说明(投影选择,数据来源,运行方式)见 ``docs/maps/myanmar.md``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import numpy as np  # 筛选国界要素
from shapely.ops import unary_union  # 合并多块几何, 得到缅甸整体轮廓

# 图种规格与数据集清单: 画框/投影/色带/地名/文案都从这里取, 见 docs/reference/spec.md.
import config

# 共享图层原语(底图/晕渲/经纬网/城市点/geo 收集), 见 docs/reference/layers.md.
from cartopy_file import layers

# 统一出图流程(建画布 -> 底图 -> 晕渲 -> 本脚本图层 -> geo 保存), 见 docs/reference/runner.md.
from cartopy_file import runner

# 国界与海岸线重合时只保留国界: 用共享剪枝工具裁掉沿海段, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# ETOPO 定位与 Natural Earth 图层读取, 见 docs/reference/relief.md.
from cartopy_file.relief import clip_to_axes, find_etopo, load_ne_layer

SHEET = config.SHEET_MYANMAR
DATASETS = config.DATASETS

# ============================
# 本图特有图层
# ============================
# Natural Earth 里缅甸的英文国名, 用于筛选边界.
MYANMAR_NAMES = ("Myanmar", "Burma")

# 国界/邻国国界的颜色与线型用 config.py 里三个图种共享的那一份
# (COLOR_BORDER/BORDER_ALPHA/BORDER_WIDTH/COLOR_NEIGHBOR).

# 国界剪掉沿海段的缓冲半径(度). Natural Earth 的国界面沿海岸闭合, 整圈画出来
# 会在若开/德林达依海岸与安达曼海岛屿上多出一条红色海岸线; 本图不画海岸线,
# 所以国界也只留陆上段. 0.06° 在 20°N 一带约 6 km, 覆盖国界折线与海岸线折线
# 的数字化偏差; 剪剩的碎段按 COAST_CLIP_MIN_LEN(约 3 km)丢掉.
COAST_CLIP_DEG = 0.06
COAST_CLIP_MIN_LEN = 0.03
# 邻国国界从缅甸国界两侧这么宽的走廊里剪掉, 避免在红色国界下面透出一条
# 与它平行的灰虚线.
NEIGHBOR_GAP_DEG = 0.06


def draw_borders(ax, world) -> None:
    """画缅甸陆上国界(半透明红线)与邻国国界(灰虚线), 不画海岸线.

    为什么国界只画陆上段: 本图不画海岸线, 海陆界线由地形配色在 0 m 处的
    跳变表达(见 config.py 的 MYANMAR_RELIEF). 国界面本身沿海岸闭合, 整圈画出来
    就等于又画了一条红色海岸线; 所以先按 Natural Earth 海岸线缓冲剪掉沿海段,
    红线在孟加拉湾/安达曼海岸收笔, 岸线交给颜色分界. 岛屿(安达曼海群岛等)
    的边界整圈都贴着海岸线, 会被一并剪掉, 岛上只剩地形色斑 -- 这正是
    「不画海岸线」的直接结果.
    """
    if world is None:
        return

    # Natural Earth 版本不同可能用 NAME / NAME_EN / ADMIN, 逐个兜底.
    name_columns = [c for c in ("NAME", "NAME_EN", "ADMIN") if c in world.columns]
    mask = np.zeros(len(world), dtype=bool)
    for col in name_columns:
        mask |= world[col].isin(MYANMAR_NAMES).to_numpy()

    myanmar = world[mask]
    if myanmar.empty:
        print("警告: Natural Earth 数据中未找到缅甸, 跳过国界.")
        return

    # 缅甸由大陆主体和安达曼海若干岛屿组成, 合并成一个 MultiPolygon 后再处理.
    myanmar_geom = unary_union(myanmar.geometry)

    # 国界: 红色半透明实线, 只画陆上段.
    border = myanmar_geom.boundary
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
    if border is not None:
        ax.add_geometries(
            [border],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=config.COLOR_BORDER,
            linewidth=config.BORDER_WIDTH,
            alpha=config.BORDER_ALPHA,
            zorder=6,
        )

    # 邻国国界: 细灰虚线, 只提供地理参照; 缅甸国界走廊里的段落剪掉,
    # 否则红线下面会透出一条与它平行的灰虚线.
    land_borders = load_ne_layer("10m", "cultural", "admin_0_boundary_lines_land")
    if land_borders is not None:
        others = unary_union(clip_to_axes(ax, list(land_borders.geometry)))
        others = others.difference(myanmar_geom.buffer(NEIGHBOR_GAP_DEG))
        if not others.is_empty:
            ax.add_geometries(
                [others],
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=config.COLOR_NEIGHBOR,
                linewidth=0.7,
                linestyle=(0, (5, 3)),
                zorder=3,
            )

    print(f"缅甸边界: {len(myanmar)} 个要素, 边界框 {myanmar.total_bounds.round(2)}")


def draw(ctx: runner.RenderContext) -> None:
    """按本图的叠放顺序画剩余图层: 国界 -> 城市点 -> 经纬网."""
    draw_borders(ctx.ax, ctx.world)
    layers.add_cities(ctx.ax, SHEET.cities)
    layers.add_gridlines(ctx.ax, SHEET)


def run(*, stride: int | None = None, dpi: int | None = None, show: bool = False) -> int:
    """渲染缅甸全境地形图并写出同名 geo.json; 返回 0=成功, 1=高程数据缺失."""
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
        runner.render(
            SHEET,
            root=ROOT,
            catalog=DATASETS,
            draw=draw,
            dem_path=etopo_path,
            dpi=dpi,
            show=show,
        )
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python Myanmar/main.py <子命令>")
