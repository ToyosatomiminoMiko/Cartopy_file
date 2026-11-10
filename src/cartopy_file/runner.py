# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""The one rendering pipeline: figure -> basemap -> relief -> bespoke layers -> geo.json.

是什么: 所有图种脚本共用的骨架. ``render`` 负责建画布,核对数据覆盖,读高程,铺底图与
晕渲,调用图种自己的图层函数,量地图框,收集 geo.json,保存产物(地图写子项目 ``map/``,
文字信息写子项目 ``text/``); 图种脚本只剩「数据 + spec + 自己那几层」.
完整说明(流水线顺序,回调契约,为什么量地图框必须在最后)见 ``docs/reference/runner.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import matplotlib.pyplot as plt
import numpy as np

from . import layers
from . import relief as relief_helpers
from .data import configure_cartopy
from .catalog import Catalog
from .geo import GeoDoc, figure_frame, save_map
from .output import apply_svg_output
from .spec import Extent, Sheet, map_path, text_path

configure_cartopy()
apply_svg_output()

__all__ = ["RenderContext", "render"]

# 回调: draw(ctx) 画图种特有的图层; collect(doc, ctx) 登记 geo 元数据.
DrawHook = Callable[["RenderContext"], None]
CollectHook = Callable[[GeoDoc, "RenderContext"], None]


def _require_shared_layers(sheet: Sheet, catalog: Catalog) -> None:
    """出图前确认 sheet 声明用到的 Natural Earth 图层都在本地缓存里.

    为什么必须在画图前失败: ``layers.countries_frame()`` / ``relief.load_ne_layer()``
    缺层时静默返回 None, 各 draw 回调只会跳过该图层, 产物看起来"成功"但缺海陆底色/
    国界(``check_geo`` 也查不出来); 这里把缺失变成明确的 FileNotFoundError, 且失败发生
    在 save_map 之前, 不会写出半成品底图.

    只检查 ``sheet.dataset_ids`` 里声明为 ``cartopy-ne`` 的数据: 未登记却直接读共享图层的
    图种属于数据清单漏登记(另一个问题), 由数据项目 miko_gis_data 的区域 config 修复,
    不在这里猜.
    """
    missing = [
        dataset
        for dataset_id in sheet.dataset_ids
        if (dataset := catalog.get(dataset_id)).kind == "cartopy-ne"
        and not catalog.exists(dataset)
    ]
    if missing:
        lines = "\n".join(f"  {item.resolution}/{item.category}/{item.name}" for item in missing)
        raise FileNotFoundError(
            f"缺少共享 Natural Earth 图层(Sheet {sheet.id}):\n{lines}\n"
            "请先到数据项目 miko_gis_data 运行: python main.py download"
        )


@dataclass
class RenderContext:
    """回调拿到的全部上下文; 图种图层函数从这里的 ax/数据/目录取参数."""

    sheet: Sheet
    catalog: Catalog
    root: Path
    fig: plt.Figure
    ax: plt.Axes
    world: object | None
    lon: np.ndarray | None = None
    lat: np.ndarray | None = None
    z: np.ndarray | None = None
    covered: Extent | None = None
    # 地名 text 里的占位符取值(如流域面积); 有自定义 collect 时也能从 ctx 取.
    label_vars: Mapping[str, Any] | None = None


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
    catalog: Catalog,
    draw: DrawHook,
    collect: CollectHook | None = None,
    dem_path: Path | None = None,
    label_vars: Mapping[str, Any] | None = None,
    area_annotation: tuple[str, ...] | None = None,
    dpi: int | None = None,
    show: bool = False,
    close: bool = True,
) -> tuple[Path, Path]:
    """按 sheet 出一张图, 返回 (svg 路径, geo.json 路径).

    ``collect=None`` 表示用默认收集(``layers.standard_collect``): 地名/经纬刻度/色标/
    图例/文案全部来自 ``Sheet``, 图种没有额外动态数据时就不用写 collect 回调.
    回调顺序是固定的: 底图 -> 晕渲 -> ``draw`` -> 版面 -> 量地图框 -> ``collect`` -> 保存.
    为什么量地图框在最后: figure_frame 要 apply_aspect, 在版面(tight_layout)与所有
    图层都画完之后量才等于最终裁剪框; 提前量会与产物错位.
    """
    root = Path(root)
    _require_shared_layers(sheet, catalog)
    fig, ax = layers.figure_axes(sheet)
    covered = layers.covered_extent(ax)

    world = layers.countries_frame() if sheet.basemap else None
    if sheet.basemap and world is None:
        # 兜底: 声明了 basemap 但共享缓存缺 10m 国界; 不能当成"没开底图"继续出图.
        raise FileNotFoundError(
            "缺少共享 Natural Earth 底图(10m/cultural/admin_0_countries); "
            "请先到数据项目 miko_gis_data 运行: python main.py download"
        )
    if sheet.basemap:
        layers.add_base_map(ax, sheet, world)

    ctx = RenderContext(
        sheet=sheet,
        catalog=catalog,
        root=root,
        fig=fig,
        ax=ax,
        world=world,
        covered=covered,
        label_vars=label_vars,
    )

    if sheet.dem_id is not None:
        dataset = catalog.get(sheet.dem_id)
        _warn_coverage(sheet, dataset, covered)
        path = Path(dem_path) if dem_path is not None else catalog.path(dataset)
        if not path.exists():
            hint = dataset.note or "数据项目 miko_gis_data 的 download"
            raise FileNotFoundError(f"未找到高程数据: {path}\n请先准备数据({hint})")
        ctx.lon, ctx.lat, ctx.z = relief_helpers.load_elevation(path)
        if sheet.relief is None:
            raise ValueError(f"Sheet({sheet.id}) 有 dem_id 却没有 relief, 无法铺高程")
        layers.add_relief(ax, sheet, ctx.lon, ctx.lat, ctx.z)

    draw(ctx)

    if sheet.tight_layout:
        plt.tight_layout()

    doc = GeoDoc(figure_frame(fig, ax))
    if collect is None:
        layers.standard_collect(
            doc, ax, sheet, catalog, label_vars=label_vars, area_annotation=area_annotation
        )
    else:
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
