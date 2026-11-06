# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""The one rendering pipeline: figure -> basemap -> relief -> bespoke layers -> geo.json.

是什么: 所有图种脚本共用的骨架. ``render`` 负责建画布、核对数据覆盖、读高程、铺底图与
晕渲、调用图种自己的图层函数、量地图框、收集 geo.json、保存产物(地图写子项目 ``map/``,
文字信息写子项目 ``text/``); 图种脚本只剩「数据 + spec + 自己那几层」.
完整说明(流水线顺序、回调契约、为什么量地图框必须在最后)见 ``docs/reference/runner.md``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np

from . import layers
from . import relief as relief_helpers
from .data import configure_cartopy
from .datasets import DatasetSet
from .geo import GeoDoc, figure_frame, save_map
from .output import apply_svg_output
from .spec import Extent, Sheet, map_path, text_path

configure_cartopy()
apply_svg_output()

__all__ = ["RenderContext", "add_standard_arguments", "render", "run"]

# 回调: draw(ctx) 画图种特有的图层; collect(doc, ctx) 登记 geo 元数据.
DrawHook = Callable[["RenderContext"], None]
CollectHook = Callable[[GeoDoc, "RenderContext"], None]


@dataclass
class RenderContext:
    """回调拿到的全部上下文; 图种图层函数从这里的 ax/数据/目录取参数."""

    sheet: Sheet
    catalog: DatasetSet
    root: Path
    fig: plt.Figure
    ax: plt.Axes
    world: object | None
    lon: np.ndarray | None = None
    lat: np.ndarray | None = None
    z: np.ndarray | None = None
    covered: Extent | None = None


def add_standard_arguments(parser: argparse.ArgumentParser) -> None:
    """给脚本的 argparse 加上全项目统一的 ``--dpi`` / ``--show``."""
    parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="内嵌晕渲栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    parser.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")


def _warn_coverage(sheet: Sheet, dataset, covered: Extent) -> None:
    """数据覆盖范围盖不住画框时提示(不报错: 底图填充会兜住缺数据的角落).

    这条检查把「下载范围必须罩住投影后的画框」从注释变成可执行的断言; 以前这个数字在
    数据准备脚本和绘图脚本里各写一份, 改一边忘另一边就会露出空白.
    """
    if dataset.bbox is None or dataset.bbox.contains(covered):
        return
    # 方位投影/半球投影的矩形画框, 在经纬度上的包围盒就是整个半球(经度铺满 360°),
    # 与数据子集的范围没有可比性; 这种情况跳过, 否则每次出图都打一条无意义的警告.
    if covered.lon_max - covered.lon_min >= 359.0 or covered.lat_max - covered.lat_min >= 179.0:
        return
    print(
        f"警告: 数据集 {dataset.id} 的覆盖范围 {dataset.bbox} 盖不住画框投影后的范围 "
        f"{covered}; 画框角落会露出底图颜色. 请在子项目的 config.py 里核对 bbox."
    )


def render(
    sheet: Sheet,
    *,
    root: Path,
    catalog: DatasetSet,
    draw: DrawHook,
    collect: CollectHook,
    dem_path: Path | None = None,
    dpi: int | None = None,
    show: bool = False,
    close: bool = True,
) -> tuple[Path, Path]:
    """按 sheet 出一张图, 返回 (svg 路径, geo.json 路径).

    回调顺序是固定的: 底图 -> 晕渲 -> ``draw`` -> 版面 -> 量地图框 -> ``collect`` -> 保存.
    为什么量地图框在最后: figure_frame 要 apply_aspect, 在版面(tight_layout)与所有
    图层都画完之后量才等于最终裁剪框; 提前量会与产物错位.
    """
    root = Path(root)
    fig, ax = layers.figure_axes(sheet)
    covered = layers.covered_extent(ax)

    world = layers.countries_frame() if sheet.basemap else None
    if sheet.basemap:
        layers.add_base_map(ax, sheet, world)

    ctx = RenderContext(
        sheet=sheet, catalog=catalog, root=root, fig=fig, ax=ax, world=world, covered=covered
    )

    if sheet.dem_id is not None:
        dataset = catalog.get(sheet.dem_id)
        _warn_coverage(sheet, dataset, covered)
        path = Path(dem_path) if dem_path is not None else catalog.path(dataset)
        if not path.exists():
            hint = dataset.note or f"python {root.name}/download_data.py"
            raise FileNotFoundError(f"未找到高程数据: {path}\n请先准备数据({hint})")
        ctx.lon, ctx.lat, ctx.z = relief_helpers.load_elevation(path)
        if sheet.relief is None:
            raise ValueError(f"Sheet({sheet.id}) 有 dem_id 却没有 relief, 无法铺高程")
        layers.add_relief(ax, sheet, ctx.lon, ctx.lat, ctx.z)

    draw(ctx)

    if sheet.tight_layout:
        plt.tight_layout()

    doc = GeoDoc(figure_frame(fig, ax))
    collect(doc, ctx)
    svg_path, geo_path = save_map(
        fig,
        map_path(root, sheet.out),
        doc,
        geo_path=text_path(root, sheet.out),
        dpi=dpi or sheet.dpi,
    )
    print(f"底图与 geo 已保存: {svg_path} + {geo_path}")

    if show:
        plt.show()
    elif close:
        plt.close(fig)
    return svg_path, geo_path


def run(
    sheet: Sheet,
    *,
    root: Path,
    catalog: DatasetSet,
    draw: DrawHook,
    collect: CollectHook,
    dem_path: Path | None = None,
    argv: list[str] | None = None,
    description: str | None = None,
    close: bool = True,
) -> tuple[Path, Path]:
    """带统一命令行参数(--dpi/--show)的 ``render``; 图种要额外参数时自行 parse 后调 render."""
    parser = argparse.ArgumentParser(description=description)
    add_standard_arguments(parser)
    args = parser.parse_args(argv)
    return render(
        sheet,
        root=root,
        catalog=catalog,
        draw=draw,
        collect=collect,
        dem_path=dem_path,
        dpi=args.dpi,
        show=args.show,
        close=close,
    )
