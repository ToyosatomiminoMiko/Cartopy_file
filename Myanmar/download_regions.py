#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# download_regions.py
# 下载掸邦各武装/自治区域的 OpenStreetMap 行政边界关系以及画框附近的
# 国界(admin_level=2), 拼装成多边形/折线后缓存为 GeoJSON,
# 供 northern_shan.py 绘图使用.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""下载并缓存掸邦各特区/自治区域边界与国界 GeoJSON。

为什么用 OpenStreetMap 而不是自己手工描点:
    缅甸各特区没有官方测绘成果可下载, 但 OSM 社区已经把 2024 年以后
    缅甸联邦第一特区(1 市 4 县)、佤邦(5 县 1 特区)、掸邦东部第四特区
    (3 县)、德昂邦(德昂民族解放军控制区)的行政边界按关系(relation)
    逐段绘出, 其范围与各特区自己公布的行政区划图基本一致.
    直接取这些关系比手工描点精确得多.

为什么国界也从 OSM 取, 而不是用 Natural Earth:
    Natural Earth 10m 国界在画框内只有几百个顶点(同范围 OSM 国界约两万
    个), 与 OSM 区域边界沿国界那一段平均偏差约 1.5 km、最大约 5 km.
    若把两套数据叠在一起画, 国界和区域边界会各走各的, 同一条线画成两条.
    改用 OSM 的 admin_level=2 关系后, 国界与区域边界本来就共享同一批
    way/节点, 两者严丝合缝; 绘图时再把重合段直接按国界样式画.

为什么在本地拼装而不是直接下载现成 GeoJSON:
    Overpass API 只按 OSM 数据模型返回 relation + 成员 way, 一个多边形
    往往由几十段 way 首尾相接组成; 这里用 shapely 把所有 way 拼成线段后
    做 polygonize, 再按成员角色 outer/inner 挖洞, 得到标准 GeoJSON 多边形.
    国界不需要多边形, 按 way 直接缓存成 MultiLineString 即可.

为什么把边界和绘图分开:
    渲染时不应该依赖网络. 本脚本只负责"取数 + 拼装 + 缓存",
    northern_shan.py 只读本地 GeoJSON; 缓存过期时重新运行本脚本即可.

数据许可: OpenStreetMap 贡献者, ODbL 1.0.
作者: Haojiren Galactic
时间: 2026-10-24
"""

from __future__ import annotations

import argparse
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Geod
from shapely.geometry import LineString, MultiLineString, mapping
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REGION_DIR = DATA_DIR / "regions"
OUT_PATH = REGION_DIR / "shan_north_boundaries.geojson"
# 国界单独存一个文件: 它没有"面"的属性(面积/上级区域), 与区域边界用途不同.
BORDER_PATH = REGION_DIR / "osm_country_borders.geojson"

# 公共 Overpass 实例经常满负荷(返回 502), 多个镜像轮换可以提高成功率.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
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
#   taang       德昂邦(德昂民族解放军 TNLA 控制区)
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
    17883478: ("taang", "德昂邦", "Ta'ang State", None),
    5996485: ("context", "掸邦", "Shan State", None),
    5996480: ("context", "曼德勒省", "Mandalay Region", None),
    5996477: ("context", "克耶邦", "Kayah State", None),
}

# 原果敢自治区(2010–2023): 官方自治区由老街(Laukkai)、拱掌(Konkyan)
# 两个镇区组成. 2024 年第一特区扩编为 1 市 4 县后, 这两个镇区分别对应
# 城区的"老街市"与"果敢县"; 把二者合并即还原原自治区范围(约 2000 km²).
# 本图层不再额外请求 OSM, 而是由已下载的两个子关系派生.
KOKANG_SAZ_PARTS = ("老街市", "果敢县")

# 一次请求多个关系时, Overpass 的响应体积随成员 way 数量增长;
# 分成若干组可以避免单次请求超时.
GROUPS = [
    [16991276, 17632959, 17020740, 17020743, 17020742, 17020741],
    # 佤邦整体单独一组: 它与 5 个县关系合在一起请求时响应体积过大,
    # Overpass 公共实例容易 504; 拆开后可显著降低单次请求的超时概率.
    [9399863],
    [14039305, 14007121, 14039309, 14035206, 14006889],
    [16742701, 16742698, 16742699, 16742700],
    [5996485, 5996480],
    [5996477],
    [17883478],
]

# 国界只缓存画框附近的那一段: 中国/缅甸这样的国家关系如果取全量几何会有
# 几十 MB; 用 out geom(bbox) 让 Overpass 只返回 bbox 内的成员 way 几何.
# bbox 比地图画框(95.3~101.5°E, 19.0~24.75°N)大 0.5~1.3°: 兰勃特投影的
# 矩形画框四角在经纬度上会外扩约 0.15°, 再留余量是为了避免裁剪误差和
# 画框边缘出现无国界的空白. 顺序是 (南, 西, 北, 东).
BORDER_RELATIONS: dict[int, tuple[str, str]] = {
    50371: ("Myanmar", "缅甸"),
    270056: ("China", "中国"),
    49903: ("Laos", "老挝"),
    2067731: ("Thailand", "泰国"),
}
BORDER_BBOX = (18.3, 94.0, 25.6, 102.5)


def fetch(ids: list[int], attempts: int = 6, bbox: tuple[float, ...] | None = None) -> list[dict]:
    """抓取指定 relation 及其成员 way 的几何, 返回 Overpass 的 elements 列表.

    bbox 不为空时用 out geom(bbox) 只取该范围内的成员几何; 此时 bbox 外的
    节点在返回结果里是 null(见 relation_to_lines).
    """
    out = "out geom;" if bbox is None else "out geom(%s);" % ",".join(f"{v:g}" for v in bbox)
    query = f"[out:json][timeout:170];relation(id:{','.join(map(str, ids))});{out}"
    data = urllib.parse.urlencode({"data": query}).encode()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        url = OVERPASS_URLS[(attempt - 1) % len(OVERPASS_URLS)]
        request = urllib.request.Request(
            url,
            data=data,
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                return json.load(response)["elements"]
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
            http.client.HTTPException,  # 公共实例负载高时会提前断开 chunked 响应
        ) as exc:
            # HTTPError(含 502 满负荷)是 URLError 的子类, 会被这里一并捕获.
            print(f"  请求失败 ({attempt}/{attempts}, {url.split('/')[2]}): {exc}")
            last_error = exc
            if attempt < attempts:
                time.sleep(5 * attempt)
    raise RuntimeError(f"Overpass 请求失败: {last_error}")


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


def relation_to_lines(rel: dict) -> list[LineString]:
    """把 relation 的成员 way 转成经纬度线段列表(用于国界).

    为什么不能把一条 way 的坐标直接塞进 LineString: Overpass 的
    out geom(bbox) 对落在请求 bbox 之外的节点返回 null, 一条 way 会在
    bbox 边界处断成若干段; 这里按 None 切分, 得到若干条连续 LineString.
    """
    lines: list[LineString] = []
    for member in rel.get("members", []):
        if member.get("type") != "way":
            continue
        geometry = member.get("geometry")
        if not geometry:
            continue
        run: list[tuple[float, float]] = []
        for point in geometry:
            if point is None:
                if len(run) >= 2:
                    lines.append(LineString(run))
                run = []
            else:
                run.append((point["lon"], point["lat"]))
        if len(run) >= 2:
            lines.append(LineString(run))
    return lines


def geodesic_area_km2(geom) -> float:
    """按 WGS84 椭球计算面积, 避免经纬度平方度在不同纬度不可比的问题."""
    area, _ = GEOD.geometry_area_perimeter(geom)
    return abs(area) / 1e6


def download_regions(force: bool) -> None:
    """下载区域边界并写入 OUT_PATH."""
    if OUT_PATH.exists() and not force:
        print(f"已存在: {OUT_PATH} (加 --force 重新下载)")
        return

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
    # 名称 -> 几何, 供派生图层(原果敢自治区)使用.
    geoms_by_name: dict[str, object] = {}
    for rel_id, (layer, name_zh, name_en, parent) in RELATIONS.items():
        rel = raw[rel_id]
        geom = relation_to_geometry(rel)
        geoms_by_name[name_zh] = geom
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

    # 原果敢自治区 = 老街市 + 果敢县; 该图层只用于显示"第一特区前身"的
    # 包含关系, 因此不单独占一个 OSM relation id, 只记录派生来源.
    saz_geom = unary_union([geoms_by_name[name] for name in KOKANG_SAZ_PARTS])
    saz_area = geodesic_area_km2(saz_geom)
    features.append(
        {
            "type": "Feature",
            "properties": {
                "layer": "kokang_saz",
                "name_zh": "原果敢自治区",
                "name_en": "Kokang Self-Administered Zone (former)",
                "parent": "sr1",
                "derived_from": [17632959, 17020740],
                "admin_level": None,
                "population": None,
                "area_km2": round(saz_area, 1),
            },
            "geometry": mapping(saz_geom),
        }
    )
    print(f"  {'原果敢自治区':<10s} {saz_geom.geom_type:<12s} {saz_area:9.1f} km2 (派生自老街市+果敢县)")

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


def download_borders(force: bool) -> None:
    """下载画框附近的国界并写入 BORDER_PATH.

    只缓存折线: 画国界不需要国家多边形, 而 bbox 裁剪后的成员 way 也拼不出
    完整多边形. 每个国家一条 MultiLineString(可能含 bbox 边界处的断口).
    """
    if BORDER_PATH.exists() and not force:
        print(f"已存在: {BORDER_PATH} (加 --force 重新下载)")
        return

    print(f"下载 OSM 国界(admin_level=2, bbox={BORDER_BBOX}): {sorted(BORDER_RELATIONS)}")
    raw = {
        element["id"]: element
        for element in fetch(list(BORDER_RELATIONS), bbox=BORDER_BBOX)
        if element.get("type") == "relation"
    }
    missing = set(BORDER_RELATIONS) - set(raw)
    if missing:
        raise RuntimeError(f"以下国界 relation 未取到: {sorted(missing)}")

    features = []
    for rel_id, (name_en, name_zh) in BORDER_RELATIONS.items():
        lines = relation_to_lines(raw[rel_id])
        if not lines:
            raise RuntimeError(f"国界 relation {rel_id} 没有 bbox 内的 way 几何")
        geom = MultiLineString(lines)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "layer": "border",
                    "name_en": name_en,
                    "name_zh": name_zh,
                    "osm_id": rel_id,
                },
                "geometry": mapping(geom),
            }
        )
        print(f"  {name_zh:<4s} {len(lines):4d} 段, {geom.length:7.2f} 度")

    collection = {
        "type": "FeatureCollection",
        "properties": {
            "source": "OpenStreetMap (ODbL 1.0)",
            "retrieved": time.strftime("%Y-%m-%d"),
            "bbox_s_w_n_e": BORDER_BBOX,
        },
        "features": features,
    }
    BORDER_PATH.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"已写入: {BORDER_PATH} ({BORDER_PATH.stat().st_size/1024:.0f} KiB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 GeoJSON")
    args = parser.parse_args()

    REGION_DIR.mkdir(parents=True, exist_ok=True)
    download_regions(args.force)
    download_borders(args.force)


if __name__ == "__main__":
    main()
