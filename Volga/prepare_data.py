#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Derive the Volga basin GeoJSON files from the downloaded raw data.

是什么: 从 ``Volga/data/raw/`` 的 GADM 4.1 俄罗斯一级行政区 JSON 与
``Volga/data/derived/`` 里解压好的 HydroBASINS 5 级欧洲区 shapefile 派生出
``volga_subjects`` / ``volga_basin`` / ``russia_border`` 三个 GeoJSON 供
``Volga/volga.py`` 离线读取; 只做 raw → derived 派生, 原始数据的下载/解压由
``Volga/download_data.py`` 负责. 画框与流域核验口径来自 ``Volga/config.py``.
完整说明(数据源/输出契约/运行方式)见 ``docs/maps/volga.md`` 与
``docs/data-preparation.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 与下载/绘图脚本共用同一份 matplotlib 缓存目录: 数据集路径定位可能经 cartopy 触到
# matplotlib, 缓存必须在 import 之前指定(见 docs/reference/data.md).
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
from shapely.validation import make_valid

# 数据集清单与画框的唯一真源; 路径都从这里取, 见 docs/reference/spec.md.
import config

# ============================
# 路径与范围
# ============================
# 派生范围: 由 config 的画框外扩 0.5° 得到(shapely 顺序: min_lon, min_lat,
# max_lon, max_lat); 与下载脚本用的是同一份 Extent, 不再各写一套顺序.
ETOPO_BBOX = config.ETOPO_BBOX
BBOX = ETOPO_BBOX.as_bbox
BBOX_POLYGON = box(*BBOX)

CATALOG = config.DATASETS
GADM_JSON = CATALOG.path("gadm41-rus")
HYBAS_SHAPES = CATALOG.path("hybas-eu-lev05")

# 派生输出(绘图脚本直接读这三个文件, 字段契约不要随意改).
SUBJECTS_PATH = CATALOG.path("volga-subjects")
BASIN_PATH = CATALOG.path("volga-basin")
BORDER_PATH = CATALOG.path("russia-border")

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
# 几何工具
# ============================
def valid_geometry(geom):
    """GADM/HydroBASINS 偶有自相交, 写文件前统一修成有效几何."""
    if geom is None or geom.is_empty:
        return None
    return geom if geom.is_valid else make_valid(geom)


def extract_geometries(geom, kinds: tuple[str, ...]):
    """从 (可能嵌套的) GeometryCollection 里取出指定类型的部件."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type in kinds:
        return [geom]
    if geom.geom_type == "GeometryCollection":
        out = []
        for child in geom.geoms:
            out.extend(extract_geometries(child, kinds))
        return out
    return []


def extract_polygons(geom):
    """把任意几何裁成面(MultiPolygon 拆平再合并), 空则返回 None."""
    parts = extract_geometries(geom, ("Polygon", "MultiPolygon"))
    polys = []
    for part in parts:
        polys.extend(part.geoms if part.geom_type == "MultiPolygon" else [part])
    polys = [p for p in polys if not p.is_empty and p.area > 0]
    if not polys:
        return None
    return valid_geometry(unary_union(polys))


def extract_lines(geom):
    """把任意几何裁成线, 空则返回 None."""
    parts = extract_geometries(geom, ("LineString", "MultiLineString"))
    lines = []
    for part in parts:
        lines.extend(part.geoms if part.geom_type == "MultiLineString" else [part])
    lines = [line for line in lines if not line.is_empty and line.length > 0]
    if not lines:
        return None
    return MultiLineString(lines) if len(lines) > 1 else lines[0]


def drop_small_holes(geom, min_hole_area: float = 1e-3):
    """删掉面积小于阈值的内部环(单位: 平方度).

    为什么需要: GADM 相邻一级行政区的边界并不严格共线, union 成一个
    国家面时会在接缝处留下 215 个针状小孔(最大 1.6e-4 平方度, 但周长
    可达 0.2°, 画成国界就是一串黑色小圈, 像脏点). 真正的内部环(如
    莫斯科市被莫斯科州包住, 面积 0.15 平方度)远大于阈值, 会保留.
    """
    if geom is None or geom.is_empty:
        return geom
    if geom.geom_type == "Polygon":
        polys = [geom]
    elif geom.geom_type == "MultiPolygon":
        polys = list(geom.geoms)
    else:
        return geom
    cleaned = []
    for poly in polys:
        holes = [ring for ring in poly.interiors if Polygon(ring).area >= min_hole_area]
        cleaned.append(Polygon(poly.exterior, holes))
    return MultiPolygon(cleaned) if len(cleaned) > 1 else cleaned[0]


def write_geojson(gdf: gpd.GeoDataFrame, path: Path, *, promote_to_multi: bool = True) -> None:
    """写 EPSG:4326 GeoJSON; 坐标统一保留 5 位小数(≈1 m, 远小于出图精度).

    用 GDAL GeoJSON 驱动的 COORDINATE_PRECISION 而不是先把 shapely 坐标舍入:
    舍入可能把细长多边形压成零面积/自相交几何, 而写文件阶段做格式化不会
    改变内存中的有效几何.
    """
    gdf = gdf.to_crs("EPSG:4326").reset_index(drop=True)
    gdf.to_file(
        path,
        driver="GeoJSON",
        engine="pyogrio",
        promote_to_multi=promote_to_multi,
        layer_options={"COORDINATE_PRECISION": "5"},
    )
    print(f"写入: {path.name} ({path.stat().st_size/1048576:.2f} MiB, {len(gdf)} 要素)")


def gdf_from_records(records: list[dict], geometry_key: str = "geometry") -> gpd.GeoDataFrame:
    """把 [{'geometry':..., 'name':...}] 转成 GeoDataFrame(保持字段顺序)."""
    if not records:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
    prop_keys = [key for key in records[0] if key != geometry_key]
    data = {key: [rec[key] for rec in records] for key in prop_keys}
    data["geometry"] = [rec[geometry_key] for rec in records]
    return gpd.GeoDataFrame(data, geometry="geometry", crs="EPSG:4326")


def equal_area_km2(geom) -> float:
    """用等积投影 EPSG:6933 算面积(km²); 经纬度直接算 area 在高纬会严重偏小."""
    series = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs("EPSG:6933")
    return float(series.area.iloc[0]) / 1e6


def clean_text(value) -> str:
    """GADM 字符串字段可能有 NaN/None, 统一成空串以免写出 null."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


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
            f"缺少 {GADM_JSON}; 请先运行 python Volga/download_data.py 下载 GADM 数据"
        )
    gdf = gpd.read_file(GADM_JSON, engine="pyogrio")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")
    print(f"   GADM RUS 一级行政区: {len(gdf)} 个")

    records = []
    for _, row in gdf.iterrows():
        geom = valid_geometry(row.geometry)
        clipped = extract_polygons(geom.intersection(BBOX_POLYGON)) if geom else None
        if clipped is None:
            continue
        records.append(
            {
                "name": clean_text(row.get("NAME_1")),
                "engtype": clean_text(row.get("ENGTYPE_1")),
                "type": clean_text(row.get("TYPE_1")),
                "geometry": clipped,
            }
        )

    out = gdf_from_records(records)
    write_geojson(out, SUBJECTS_PATH)

    republics = sorted(rec["name"] for rec in records if rec["engtype"] == "Republic")
    print(f"   与画框相交的一级行政区: {len(records)} 个 (原始 {len(gdf)} 个)")
    print(f"   画框内共和国 (ENGTYPE_1=='Republic', {len(republics)} 个): {', '.join(republics)}")


def build_border() -> None:
    """GADM 全部一级行政区 union 的 boundary, 即 GADM 口径俄罗斯国界.

    为什么不用 Natural Earth: 与行政区同源, 国界与州界严丝合缝; 且 GADM
    RUS 不含克里米亚, 与仓库 Ukraine 图的法理口径一致.
    """
    print("\n派生 russia_border.geojson (GADM 口径俄罗斯国界)")
    if not GADM_JSON.exists():
        raise RuntimeError(
            f"缺少 {GADM_JSON}; 请先运行 python Volga/download_data.py 下载 GADM 数据"
        )
    gdf = gpd.read_file(GADM_JSON, engine="pyogrio")
    gdf = gdf.to_crs("EPSG:4326")
    geoms = [valid_geometry(geom) for geom in gdf.geometry]
    geoms = [geom for geom in geoms if geom is not None]
    country = valid_geometry(unary_union(geoms))
    # 相邻州边界不共线, union 后接缝处有 215 个针状小孔; 不去掉会画成一串
    # 黑色小圈. 阈值远离真实内部环(莫斯科市 0.15 平方度)的量级.
    country = drop_small_holes(country, min_hole_area=1e-3)
    border = extract_lines(country.boundary.intersection(BBOX_POLYGON))
    if border is None:
        raise RuntimeError("GADM 俄罗斯国界与画框求交后为空")
    out = gpd.GeoDataFrame({"name": ["俄罗斯国界(GADM)"]}, geometry=[border], crs="EPSG:4326")
    write_geojson(out, BORDER_PATH, promote_to_multi=True)
    minx, miny, maxx, maxy = border.bounds
    print(f"   国界 bbox: {minx:.2f}~{maxx:.2f}°E / {miny:.2f}~{maxy:.2f}°N")


def _hybas_files() -> list[Path]:
    """当前可用的 HydroBASINS shp 列表(当前只登记欧洲区)."""
    if not HYBAS_SHAPES.exists():
        raise RuntimeError(
            f"缺少 HydroBASINS shapefile: {HYBAS_SHAPES}; "
            "请先运行 python Volga/download_data.py 下载并解压"
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

    area_km2 = equal_area_km2(basin)
    minx, miny, maxx, maxy = basin.bounds
    print(f"   流域面积(EPSG:6933 等积): {area_km2:,.0f} km²")
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

    out = gpd.GeoDataFrame(
        {"area_km2": [round(area_km2, 2)]},
        geometry=[basin],
        crs="EPSG:4326",
    )
    write_geojson(out, BASIN_PATH, promote_to_multi=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-basin",
        action="store_true",
        help="跳过流域派生(只重建行政区与国界, 缺 HydroBASINS 数据时用)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("派生 GeoJSON(每次运行都重建; 不依赖 HydroBASINS 的先做)")
    print("=" * 60)
    build_subjects()
    build_border()

    if args.skip_basin:
        print("\n--skip-basin: 跳过流域派生")
    else:
        build_basin()

    missing = [
        path for path in (SUBJECTS_PATH, BASIN_PATH, BORDER_PATH) if not path.exists()
    ]
    if missing:
        print("\n缺少派生文件: " + ", ".join(path.name for path in missing))
        print("       先运行 python Volga/download_data.py 检查原始数据, 再重跑本脚本")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断; 重新运行会从头重建派生文件.")
        sys.exit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
