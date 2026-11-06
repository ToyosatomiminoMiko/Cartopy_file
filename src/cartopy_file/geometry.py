#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Shared geometry and GeoJSON helpers for the data-preparation scripts.

是什么: 把「几何修到能画」「按确定性格式写 GeoJSON」「量面积/长度/顶点」这三类与图种无关的
操作收在一处, 供各子项目的 prepare_*.py 与下载脚本共用.
为什么: 这些函数原先在 Ukraine/Volga 各复制一份并已经开始漂移(坐标精度,面积算法,写文件
方式不一致); 放在这里只有一份实现, 数值阈值(小孔面积等)仍由各子项目按自己的图传参.
只依赖 shapely/pyproj/pandas, 不 import matplotlib/cartopy, 所以数据准备脚本与工具都能用.
完整说明(阈值怎么定,为什么统一写 GeoJSON,精度怎么选)见 ``docs/reference/geometry.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # clean_text 判 NaN
from pyproj import Geod  # 椭球面积/长度
from shapely.geometry import MultiLineString, MultiPolygon, Polygon, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

__all__ = [
    "valid_geometry",
    "extract_geometries",
    "extract_polygons",
    "extract_lines",
    "drop_small_holes",
    "round_coords",
    "feature",
    "write_geojson",
    "geodesic_area_km2",
    "geodesic_length_km",
    "n_vertices",
    "clean_text",
]

GEOD = Geod(ellps="WGS84")


# ============================
# 几何修复与拆解
# ============================
def valid_geometry(geom):
    """把自相交/失效几何修成合法几何; None 与空几何返回 None."""
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
    """把任意几何裁成面(MultiPolygon 拆平再合并), 没有面积则返回 None."""
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
    """删掉面积小于阈值的内部环(单位: 平方度); 阈值由各子项目按图幅决定.

    为什么需要: 相邻行政区边界不严格共线, union 成一个面时接缝处会留下针状小孔
    (实测面积 < 2e-6 平方度, 但周长可达 0.2°), 画成边界线就是一串黑点; 真正的内部环
    (如被包围的直辖市, 面积 0.1 平方度量级)远大于阈值, 会保留.
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


# ============================
# 写 GeoJSON
# ============================
def round_coords(obj, nd: int = 6):
    """递归把坐标四舍五入到 nd 位小数, 控制 GeoJSON 体积(1e-6° ≈ 0.11 m)."""
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), nd) for v in obj]
        return [round_coords(v, nd) for v in obj]
    return obj


def feature(geom, props: dict, *, precision: int = 6, min_hole_area: float | None = None) -> dict:
    """把 shapely 几何包成 GeoJSON Feature, 坐标按 precision 位小数舍入.

    min_hole_area 给定时先删小孔(阈值见各子项目); 不给则保留原始内部环.
    不支持 GeometryCollection: 调用前先用 extract_polygons/extract_lines 拆成面或线.
    """
    geom = valid_geometry(geom)
    if min_hole_area is not None:
        geom = drop_small_holes(geom, min_hole_area)
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {
            "type": geom.geom_type,
            "coordinates": round_coords(list(mapping(geom)["coordinates"]), precision),
        },
    }


def write_geojson(path: Path, features: list[dict], *, name: str | None = None) -> None:
    """写确定性的 RFC 7946 GeoJSON(紧凑分隔符, 键序固定, 不写时间戳).

    为什么不用 GIS 库写: 同一份数据必须每次逐字节一致(项目确定性契约), 而库的写出顺序与
    浮点格式化会随版本变; 这里由本仓控制格式, 内容只来自调用方给的 Feature 列表.
    """
    collection = {
        "type": "FeatureCollection",
        "name": name or path.stem,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(collection, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"写入: {path.name} ({path.stat().st_size/1024:.1f} KiB, {len(features)} 要素)")


# ============================
# 量算
# ============================
def geodesic_area_km2(geom) -> float:
    """按 WGS84 椭球算面积(km²); 经纬度上直接算 area 在高纬会严重偏小."""
    if geom is None or geom.is_empty:
        return 0.0
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        return 0.0
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    return sum(abs(GEOD.geometry_area_perimeter(p)[0]) for p in polys) / 1e6


def geodesic_length_km(geom) -> float:
    """按 WGS84 椭球算线长度(km); pyproj 返回米, 要 /1000."""
    if geom is None or geom.is_empty:
        return 0.0
    if geom.geom_type not in ("LineString", "MultiLineString"):
        return 0.0
    lines = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
    return sum(abs(GEOD.geometry_length(line)) for line in lines) / 1000


def n_vertices(geom) -> int:
    """几何顶点数, 用于核对简化后没有丢掉细节."""
    if geom is None or geom.is_empty:
        return 0
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        return sum(
            len(p.exterior.coords) + sum(len(ring.coords) for ring in p.interiors)
            for p in polys
        )
    if geom.geom_type in ("LineString", "MultiLineString"):
        lines = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
        return sum(len(line.coords) for line in lines)
    return 0


def clean_text(value) -> str:
    """把 GADM 等数据里的 NaN/None 属性统一成空串, 以免写出 null."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)
