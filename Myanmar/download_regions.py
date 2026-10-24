#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# download_regions.py
# 下载掸邦北部各武装/自治区域的 OpenStreetMap 行政边界关系,
# 拼装成多边形后缓存为 GeoJSON, 供 shan_north.py 绘图使用.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""下载并缓存掸邦北部各特区/自治区域的边界 GeoJSON。

为什么用 OpenStreetMap 而不是自己手工描点:
    缅甸各特区没有官方测绘成果可下载, 但 OSM 社区已经把 2024 年以后
    缅甸联邦第一特区(1 市 4 县)、佤邦(5 县 1 特区)、掸邦东部第四特区
    (3 县)的行政边界按关系(relation)逐段绘出, 其范围与各特区自己公布的
    行政区划图基本一致. 直接取这些关系比手工描点精确得多.

为什么在本地拼装而不是直接下载现成 GeoJSON:
    Overpass API 只按 OSM 数据模型返回 relation + 成员 way, 一个多边形
    往往由几十段 way 首尾相接组成; 这里用 shapely 把所有 way 拼成线段后
    做 polygonize, 再按成员角色 outer/inner 挖洞, 得到标准 GeoJSON 多边形.

为什么把边界和绘图分开:
    渲染时不应该依赖网络. 本脚本只负责"取数 + 拼装 + 缓存",
    shan_north.py 只读本地 GeoJSON; 缓存过期时重新运行本脚本即可.

数据许可: OpenStreetMap 贡献者, ODbL 1.0.
作者: Haojiren Galactic
时间: 2026-10-24
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Geod
from shapely.geometry import LineString, mapping
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REGION_DIR = DATA_DIR / "regions"
OUT_PATH = REGION_DIR / "shan_north_boundaries.geojson"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "MyanmarMap/1.0 (cartopy map project)"
GEOD = Geod(ellps="WGS84")

# OSM relation id -> (图层, 中文名, 英文名, 上级区域).
# 图层说明:
#   sr1         缅甸联邦第一特区整体
#   sr1_county  第一特区的 1 市 4 县
#   wa          佤邦整体
#   wa_district 佤邦下辖县/特区(OSM 2026 年建制)
#   sr4         掸邦东部第四特区整体
#   sr4_county  第四特区下辖 3 县
#   context     仅作定位参考的掸邦/曼德勒省边界
RELATIONS: dict[int, tuple[str, str, str, str | None]] = {
    16991276: ("sr1", "缅甸联邦第一特区", "Special Region 1", None),
    17632959: ("sr1_county", "老街市", "Laukkaing City", "sr1"),
    17020740: ("sr1_county", "果敢县", "Kokang District", "sr1"),
    17020743: ("sr1_county", "勐古县", "Mong Ko District", "sr1"),
    17020742: ("sr1_county", "贵概县", "Kutkai District", "sr1"),
    17020741: ("sr1_county", "木邦县", "Mupang District", "sr1"),
    9399863: ("wa", "佤邦", "Wa State", None),
    14039305: ("wa_district", "邦康特区", "Pang Kham Special Township", "wa"),
    14007121: ("wa_district", "勐冒县", "Meung Mau District", "wa"),
    14039309: ("wa_district", "勐波县", "Meung Pawg District", "wa"),
    14035206: ("wa_district", "勐能县", "Mang Leen District", "wa"),
    14006889: ("wa_district", "富邦县", "Ho Pang District", "wa"),
    16742701: ("sr4", "掸邦东部第四特区", "Eastern Shan State Special Region 4", None),
    16742698: ("sr4_county", "勐拉县", "Mong La District", "sr4"),
    16742699: ("sr4_county", "色勒县", "Hsee Lu District", "sr4"),
    16742700: ("sr4_county", "南板县", "Nam Pan District", "sr4"),
    5996485: ("context", "掸邦", "Shan State", None),
    5996480: ("context", "曼德勒省", "Mandalay Region", None),
}

# 一次请求多个关系时, Overpass 的响应体积随成员 way 数量增长;
# 分成若干组可以避免单次请求超时.
GROUPS = [
    [16991276, 17632959, 17020740, 17020743, 17020742, 17020741],
    [9399863, 14039305, 14007121, 14039309, 14035206, 14006889],
    [16742701, 16742698, 16742699, 16742700],
    [5996485, 5996480],
]


def fetch(ids: list[int], attempts: int = 3) -> list[dict]:
    """抓取指定 relation 及其成员 way 的几何, 返回 Overpass 的 elements 列表."""
    query = f"[out:json][timeout:170];relation(id:{','.join(map(str, ids))});out geom;"
    data = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            OVERPASS_URL,
            data=data,
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=200) as response:
                return json.load(response)["elements"]
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  请求失败 ({attempt}/{attempts}): {exc}")
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)
    return []


def relation_to_geometry(rel: dict):
    """把 OSM relation 的成员 way 拼成 Shapely 多边形.

    原理: OSM 边界关系的成员是不一定闭合的 way, 首尾共享节点.
    把所有 outer way 当线段合并后 polygonize 就得到外环; 内环同理.
    最后按"内环是否落在外环内部"挖洞, 得到带洞多边形.
    """
    outers: list[LineString] = []
    inners: list[LineString] = []
    for member in rel.get("members", []):
        if member.get("type") != "way":
            continue
        geometry = member.get("geometry")
        if not geometry:
            continue
        line = LineString([(p["lon"], p["lat"]) for p in geometry])
        (inners if member.get("role") == "inner" else outers).append(line)

    if not outers:
        raise ValueError(f"relation {rel['id']} 没有外环 way")

    outer_polys = list(polygonize(unary_union(outers)))
    inner_polys = list(polygonize(unary_union(inners))) if inners else []
    pieces = []
    for poly in outer_polys:
        holes = [ip for ip in inner_polys if poly.contains(ip.representative_point())]
        if holes:
            poly = poly.difference(unary_union(holes))
        pieces.append(poly)
    return make_valid(unary_union(pieces))


def geodesic_area_km2(geom) -> float:
    """按 WGS84 椭球计算面积, 避免经纬度平方度在不同纬度不可比的问题."""
    area, _ = GEOD.geometry_area_perimeter(geom)
    return abs(area) / 1e6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 GeoJSON")
    args = parser.parse_args()

    if OUT_PATH.exists() and not args.force:
        print(f"已存在: {OUT_PATH} (加 --force 重新下载)")
        return

    REGION_DIR.mkdir(parents=True, exist_ok=True)

    # id -> relation 原始数据, 便于最后统一按 RELATIONS 顺序输出.
    raw: dict[int, dict] = {}
    for group in GROUPS:
        print(f"下载 OSM 关系: {group}")
        for element in fetch(group):
            if element.get("type") == "relation":
                raw[element["id"]] = element

    missing = set(RELATIONS) - set(raw)
    if missing:
        raise RuntimeError(f"以下 relation 未取到: {sorted(missing)}")

    features = []
    for rel_id, (layer, name_zh, name_en, parent) in RELATIONS.items():
        rel = raw[rel_id]
        geom = relation_to_geometry(rel)
        area = geodesic_area_km2(geom)
        properties = {
            "layer": layer,
            "name_zh": name_zh,
            "name_en": name_en,
            "parent": parent,
            "osm_id": rel_id,
            "admin_level": rel["tags"].get("admin_level"),
            "population": rel["tags"].get("population"),
            "area_km2": round(area, 1),
        }
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": mapping(geom),
            }
        )
        print(f"  {name_zh:<10s} {geom.geom_type:<12s} {area:9.1f} km2")

    collection = {
        "type": "FeatureCollection",
        "properties": {
            "source": "OpenStreetMap (ODbL 1.0)",
            "retrieved": time.strftime("%Y-%m-%d"),
        },
        "features": features,
    }
    OUT_PATH.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"已写入: {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.0f} KiB)")


if __name__ == "__main__":
    main()
