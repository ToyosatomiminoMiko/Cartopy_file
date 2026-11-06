#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Derive the Volga basin GeoJSON files from the downloaded raw data.

是什么: 从 ``Volga/data/raw/`` 的 GADM 4.1 俄罗斯一级行政区 JSON 与
``Volga/data/derived/`` 里解压好的 HydroBASINS 5 级欧洲区 shapefile 派生出
``volga_subjects`` / ``volga_basin`` / ``russia_border`` 三个 GeoJSON 供
``Volga/volga.py`` 离线读取; 只做 raw → derived 派生, 原始数据的下载/解压由
``Volga/download_data.py``(经 ``python Volga/main.py download``)负责. 几何修复/写
GeoJSON/量面积等通用操作走 ``cartopy_file.geometry``, 本文件只保留本图种的路径、
阈值与派生流程.
完整说明(数据源/输出契约/运行方式)见 ``docs/maps/volga.md``.
"""

from __future__ import annotations

import os
from pathlib import Path

# 与下载/绘图脚本共用同一份 matplotlib 缓存目录: 数据集路径定位可能经 cartopy 触到
# matplotlib, 缓存必须在 import 之前指定(见 docs/reference/data.md).
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import Point, box
from shapely.ops import unary_union

# 共享几何与 GeoJSON 工具: 修几何/拆面线/删小孔/写确定性 GeoJSON/椭球面积,
# 见 docs/reference/geometry.md.
from cartopy_file.geometry import (
    clean_text,
    drop_small_holes,
    extract_lines,
    extract_polygons,
    feature,
    geodesic_area_km2,
    valid_geometry,
    write_geojson,
)

# 数据集清单与画框的唯一真源; 路径都从这里取, 见 docs/reference/spec.md.
import config

# ============================
# 路径与范围
# ============================
# 派生范围: 由 config 的画框外扩 0.5° 得到(shapely 顺序: min_lon, min_lat,
# max_lon, max_lat); 与下载脚本用的是同一份 Extent, 不再各写一套顺序.
BBOX = config.ETOPO_BBOX.as_bbox
BBOX_POLYGON = box(*BBOX)

CATALOG = config.DATASETS
GADM_JSON = CATALOG.path("gadm41-rus")
HYBAS_SHAPES = CATALOG.path("hybas-eu-lev05")

# 派生输出(绘图脚本直接读这三个文件, 字段契约不要随意改).
SUBJECTS_PATH = CATALOG.path("volga-subjects")
BASIN_PATH = CATALOG.path("volga-basin")
BORDER_PATH = CATALOG.path("russia-border")

# 坐标精度: 1e-5° ≈ 1.1 m, 远小于本图 1:770 万的出图精度; 与改前产物一致, 不随框架
# 默认的 6 位(见 docs/reference/geometry.md 注意事项).
COORD_PRECISION = 5
# 对应 1e-5° 的坐标网格. 旧产物由 GDAL 按 COORDINATE_PRECISION=5 写出, 它在坐标舍入会
# 产生重合顶点时用 GEOS 精度模型压网格(顺带删点、重排环起点); 直接用 feature() 的 Python
# 舍入会保留那些顶点, 顶点序列一变出图产物就不再与基线逐字节一致. 本图要求产物不动,
# 所以流域面先用 set_precision 复现同一份网格几何(见 docs/maps/volga.md 注意事项).
COORD_GRID_DEG = 10 ** -COORD_PRECISION
# GADM 相邻州边界 union 后接缝处针孔的面积上限(平方度); 阈值出处见
# docs/reference/geometry.md 与 drop_small_holes 的说明.
MIN_HOLE_AREA_DEG = 1e-3

# 伏尔加入海口/三角洲一带: 在 HydroBASINS 里找 UP_AREA 最大的单元, 其
# MAIN_BAS 即整个伏尔加流域. 用小窗口而非单点, 避免点落在里海水面或
# 单元缝隙里找不到下游单元.
ESTUARY_BBOX = (47.0, 44.8, 50.2, 47.2)
ESTUARY_DELTA_BOX = box(47.8, 45.85, 49.2, 46.35)

# 流域核验点: 流域内(干流/支流)与相邻流域各取几个, 选错 MAIN_BAS 能立刻暴露.
BASIN_INSIDE_POINTS = {
    "卡马河": (51.0, 55.5),   # (lon, lat)
    "奥卡河": (36.0, 54.8),
    "伏尔加中游": (44.5, 48.7),
}
BASIN_OUTSIDE_POINTS = {
    "顿河": (40.5, 48.5),
    "乌拉尔河": (51.5, 51.0),
    "北德维纳河": (41.5, 63.0),
}
BASIN_AREA_RANGE_KM2 = (1.2e6, 1.5e6)  # HydroBASINS 口径伏尔加流域约 1.35e6 km²

HYBAS_COLUMNS = ["MAIN_BAS", "UP_AREA"]


# ============================
# 派生 GeoJSON(不依赖 HydroBASINS 的两项可单独重建)
# ============================
def build_subjects() -> None:
    """GADM 全部 83 个一级行政区用完整几何裁到画框.

    为什么读完整的 83 行再用完整几何求交: 若先用 ``cx`` 粗筛, 跨越画框的
    州(如秋明/阿尔汉格尔斯克)会因代表性点选不中而丢失或只剩一小块; 正确
    做法是逐要素做"完整几何 ∩ BBOX", 完全在画框外的州不产要素.
    """
    print("\n派生 volga_subjects.geojson (GADM 一级行政区)")
    if not GADM_JSON.exists():
        raise RuntimeError(
            f"缺少 {GADM_JSON}; 请先运行 python Volga/main.py download 下载 GADM 数据"
        )
    gdf = gpd.read_file(GADM_JSON, engine="pyogrio")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")
    print(f"   GADM RUS 一级行政区: {len(gdf)} 个")

    features = []
    for _, row in gdf.iterrows():
        geom = valid_geometry(row.geometry)
        clipped = extract_polygons(geom.intersection(BBOX_POLYGON)) if geom else None
        if clipped is None:
            continue
        features.append(
            feature(
                clipped,
                {
                    "name": clean_text(row.get("NAME_1")),
                    "engtype": clean_text(row.get("ENGTYPE_1")),
                    "type": clean_text(row.get("TYPE_1")),
                },
                precision=COORD_PRECISION,
            )
        )
    write_geojson(SUBJECTS_PATH, features)

    republics = sorted(
        item["properties"]["name"]
        for item in features
        if item["properties"]["engtype"] == "Republic"
    )
    print(f"   与画框相交的一级行政区: {len(features)} 个 (原始 {len(gdf)} 个)")
    print(f"   画框内共和国 (ENGTYPE_1=='Republic', {len(republics)} 个): {', '.join(republics)}")


def build_border() -> None:
    """GADM 全部一级行政区 union 的 boundary, 即 GADM 口径俄罗斯国界.

    为什么不用 Natural Earth: 与行政区同源, 国界与州界严丝合缝; 且 GADM
    RUS 不含克里米亚, 与仓库 Ukraine 图的法理口径一致.
    """
    print("\n派生 russia_border.geojson (GADM 口径俄罗斯国界)")
    if not GADM_JSON.exists():
        raise RuntimeError(
            f"缺少 {GADM_JSON}; 请先运行 python Volga/main.py download 下载 GADM 数据"
        )
    gdf = gpd.read_file(GADM_JSON, engine="pyogrio")
    gdf = gdf.to_crs("EPSG:4326")
    geoms = [valid_geometry(geom) for geom in gdf.geometry]
    geoms = [geom for geom in geoms if geom is not None]
    country = valid_geometry(unary_union(geoms))
    # 相邻州边界不共线, union 后接缝处有 215 个针状小孔; 不去掉会画成一串
    # 黑色小圈. 阈值远离真实内部环(莫斯科市 0.15 平方度)的量级.
    country = drop_small_holes(country, min_hole_area=MIN_HOLE_AREA_DEG)
    border = extract_lines(country.boundary.intersection(BBOX_POLYGON))
    if border is None:
        raise RuntimeError("GADM 俄罗斯国界与画框求交后为空")
    write_geojson(
        BORDER_PATH,
        [feature(border, {"name": "俄罗斯国界(GADM)"}, precision=COORD_PRECISION)],
    )
    minx, miny, maxx, maxy = border.bounds
    print(f"   国界 bbox: {minx:.2f}~{maxx:.2f}°E / {miny:.2f}~{maxy:.2f}°N")


def _hybas_files() -> list[Path]:
    """当前可用的 HydroBASINS shp 列表(当前只登记欧洲区)."""
    if not HYBAS_SHAPES.exists():
        raise RuntimeError(
            f"缺少 HydroBASINS shapefile: {HYBAS_SHAPES}; "
            "请先运行 python Volga/main.py download 下载并解压"
        )
    return [HYBAS_SHAPES]


def _read_hybas(files: list[Path], bbox, columns=None) -> gpd.GeoDataFrame:
    """用 pyogrio 的 bbox 过滤读 HydroBASINS, 只取需要的属性列."""
    parts = []
    for shp in files:
        part = gpd.read_file(
            shp,
            bbox=bbox,
            columns=columns or HYBAS_COLUMNS,
            engine="pyogrio",
        )
        if len(part):
            parts.append(part)
    if not parts:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs="EPSG:4326")
    return gdf.to_crs("EPSG:4326")


def _read_main_bas(files: list[Path], main_bas: int) -> gpd.GeoDataFrame:
    """读出 MAIN_BAS 等于给定值的全部单元(用比画框大的 bbox 读入再属性过滤)."""
    read_bbox = (BBOX[0] - 3.0, BBOX[1] - 3.0, BBOX[2] + 3.0, BBOX[3] + 3.0)
    gdf = _read_hybas(files, bbox=read_bbox)
    if gdf.empty:
        raise RuntimeError(f"读不到 HydroBASINS 单元, 检查文件: {files}")
    selected = gdf[gdf["MAIN_BAS"].astype("int64") == main_bas]
    if selected.empty:
        raise RuntimeError(f"HydroBASINS 中找不到 MAIN_BAS={main_bas} 的单元")
    return selected


def build_basin() -> None:
    """在 HydroBASINS lev05 里取与伏尔加入海口同一 MAIN_BAS 的全部单元并合并.

    识别方法: 伏尔加三角洲窗口内 UP_AREA 最大的单元就是下游出口单元, 它的
    MAIN_BAS 覆盖整个流域(伏尔加、卡马、奥卡等支流都归同一主流域编码).
    不依赖"与某条河流相交"之类的脆弱条件, 换数据版本也稳定.
    """
    print("\n派生 volga_basin.geojson (HydroBASINS 伏尔加流域)")
    files = _hybas_files()

    estuary = _read_hybas(files, bbox=ESTUARY_BBOX)
    if estuary.empty:
        raise RuntimeError(
            f"在入海口窗口 {ESTUARY_BBOX} 内找不到单元; 检查 eu 文件是否覆盖里海西北岸"
        )
    estuary = estuary.assign(_up_area=pd.to_numeric(estuary["UP_AREA"], errors="coerce"))
    outlet = estuary.loc[estuary["_up_area"].idxmax()]
    main_bas = int(outlet["MAIN_BAS"])
    print(
        f"   入海口出口单元: MAIN_BAS={main_bas}, UP_AREA={outlet['_up_area']:.0f} km²"
    )

    units = _read_main_bas(files, main_bas)
    print(f"   同一 MAIN_BAS 的 lev05 单元: {len(units)} 个")
    geoms = [valid_geometry(geom) for geom in units.geometry]
    geoms = [geom for geom in geoms if geom is not None]
    basin = valid_geometry(unary_union(geoms))
    if basin is None or basin.is_empty:
        raise RuntimeError(f"MAIN_BAS={main_bas} 的单元合并后为空")

    # 先压到 1e-5° 网格再量面积/写文件, 让写出的几何与旧产物逐字节一致.
    basin = shapely.set_precision(basin, COORD_GRID_DEG)
    area_km2 = geodesic_area_km2(basin)
    minx, miny, maxx, maxy = basin.bounds
    print(f"   流域面积(WGS84 椭球): {area_km2:,.0f} km²")
    print(f"   流域 bbox: {minx:.2f}~{maxx:.2f}°E / {miny:.2f}~{maxy:.2f}°N")

    # 核验 (a): 面积在 HydroBASINS 口径的合理范围内, 且包含伏尔加三角洲.
    low, high = BASIN_AREA_RANGE_KM2
    if not low <= area_km2 <= high:
        raise RuntimeError(
            f"流域面积 {area_km2:,.0f} km² 不在预期 {low:,.0f}~{high:,.0f} km² 内; "
            f"MAIN_BAS={main_bas} 可能选错或 HydroBASINS 区域不全"
        )
    if not basin.intersects(ESTUARY_DELTA_BOX):
        raise RuntimeError("流域面与伏尔加三角洲窗口不相交, MAIN_BAS 可能选错")
    for name, (lon, lat) in BASIN_INSIDE_POINTS.items():
        if not basin.contains(Point(lon, lat)):
            raise RuntimeError(
                f"流域面不包含{name}参照点 ({lon}, {lat}); MAIN_BAS 可能选错或单元缺失"
            )

    # 核验 (b): 不能把顿河/乌拉尔河/北德维纳河等相邻流域并进来.
    for name, (lon, lat) in BASIN_OUTSIDE_POINTS.items():
        if basin.contains(Point(lon, lat)):
            raise RuntimeError(f"流域面包含了相邻的{name} ({lon}, {lat}); MAIN_BAS 可能选错")

    write_geojson(
        BASIN_PATH,
        [feature(basin, {"area_km2": round(area_km2, 2)}, precision=COORD_PRECISION)],
    )


def run(*, skip_basin: bool = False) -> int:
    """派生入口: 重建三个派生 GeoJSON; 返回退出码(0 成功)."""
    print("\n" + "=" * 60)
    print("派生 GeoJSON(每次运行都重建; 不依赖 HydroBASINS 的先做)")
    print("=" * 60)
    build_subjects()
    build_border()

    if skip_basin:
        print("\n--skip-basin: 跳过流域派生")
    else:
        build_basin()

    missing = [
        path for path in (SUBJECTS_PATH, BASIN_PATH, BORDER_PATH) if not path.exists()
    ]
    if missing:
        print("\n缺少派生文件: " + ", ".join(path.name for path in missing))
        print("       先运行 python Volga/main.py download 检查原始数据, 再重跑本子命令")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(
        "本文件是模块, 不能直接运行; 请用统一入口: python Volga/main.py prepare"
    )
