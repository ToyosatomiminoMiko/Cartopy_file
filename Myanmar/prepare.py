#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""清洗/派生缅甸图种需要的数据: 行政区 GeoJSON 与 OSM 特区/国界 GeoJSON.

是什么: 读数据根里 manifest 声明的原始数据(GADM 缅甸一级行政区, Natural Earth 10m 国界,
OSM 内比都/特区/国界快照), 按本图口径裁剪,补缝,去重叠,拼装, 写到 ``Myanmar/build/``.
本文件是模块, 只导出 ``run()``; 命令行入口是 ``python Myanmar/main.py prepare``.
为什么放在渲染仓: 裁剪框,补缝阈值,特区归属都是图种口径, 数据仓只提供通用原始数据
(分工见 ``docs/data-preparation.md`` 与 ``docs/reference/prepare.md``).
完整说明见 ``docs/maps/myanmar-admin.md`` 与 ``docs/maps/northern-shan.md``.
"""

from __future__ import annotations

import json

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, mapping, shape
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

import config
from cartopy_file.catalog import catalog_for
from cartopy_file.data import configure_cartopy
from cartopy_file.geometry import geodesic_area_km2

# cartopy 的 Natural Earth 缓存必须指向数据根, 否则 manifest 里的图层会解析到旧 HOME 缓存;
# 调用要在读取图层路径之前(见 docs/reference/data.md).
configure_cartopy()

# 数据路径全部由数据清单 manifest 给出(原始数据仍在数据仓, 见 docs/reference/data.md).
CATALOG = catalog_for(config.DATA_GROUP)
GADM_JSON = CATALOG.path("gadm41-mmr")
COUNTRY_SHP = CATALOG.path("ne-countries-10m")
NPT_JSON = CATALOG.path("osm-naypyidaw")
SHAN_RAW_DIR = CATALOG.path("osm-shan-regions")
BORDER_RAW = CATALOG.path("osm-country-borders")

# 派生产物: 本子项目 build/ 下, 由本模块全量重建(目录布局见 docs/reference/spec.md).
ADMIN_OUT = config.ADMIN_GEOJSON
SHAN_OUT = config.SHAN_GEOJSON
BORDER_OUT = config.BORDER_GEOJSON

# 原始数据: (路径, 名称, 准备命令). 命令与数据仓的下载入口一致.
RAW_INPUTS = (
    (COUNTRY_SHP, "Natural Earth 10m 国界", "python main.py download --group myanmar"),
    (GADM_JSON, "GADM 4.1 缅甸一级行政区", "python main.py download --group myanmar"),
    (NPT_JSON, "OSM 内比都联邦区缓存", "python main.py download --group myanmar"),
)

# ============================
# OSM 特区/国界: 数据仓只存原始 Overpass 响应, 归属与名称在这里解释.
# ============================
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
# 注意: 这些 id 同时出现在数据仓的下载参数里(查询用), 改图时两边一起改.
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

# 原果敢自治区(2010-2023): 由老街市 + 果敢县两个relation合并还原, 不单独占一个 id.
KOKANG_SAZ_PARTS = ("老街市", "果敢县")
KOKANG_SAZ_OSM_IDS = (17632959, 17020740)

# 国界: relation id -> (英文名, 中文名). 数据仓按 bbox 只取画框附近的成员 way.
BORDER_RELATIONS: dict[int, tuple[str, str]] = {
    50371: ("Myanmar", "缅甸"),
    270056: ("China", "中国"),
    49903: ("Laos", "老挝"),
    2067731: ("Thailand", "泰国"),
}


# ============================
# 原始数据检查
# ============================
def require_raw_data() -> None:
    """检查派生所需的原始数据是否就位; 有缺失就报错并指出准备命令.

    为什么只检查不下载: 出图不联网(见 docs/data-preparation.md), 缺数据时回数据仓下载.
    """
    missing = [(path, label, hint) for path, label, hint in RAW_INPUTS if not path.exists()]
    if not missing:
        print("原始数据齐全: Natural Earth 国界, GADM 缅甸, OSM 内比都缓存.")
        return
    lines = [
        f"未找到 {label}: {path}\n请到数据项目 miko_gis_data 运行: {hint}"
        for path, label, hint in missing
    ]
    raise FileNotFoundError("\n".join(lines))


# ============================
# 行政区: GADM + OSM 内比都
# ============================
def overpass_npt_geometry() -> object:
    """从缓存的 Overpass 响应拼出内比都联邦区多边形.

    Overpass 返回的 relation 成员是一段段不闭合的 way, 首尾共享节点.
    这里把所有 way 合并后 polygonize 成外环, 再取面积最大的多边形,
    因为边界关系中偶尔会有极小的闭合碎块(例如飞地), 不应当作主体.
    """
    payload = json.loads(NPT_JSON.read_text(encoding="utf-8"))
    relation = next(el for el in payload["elements"] if el.get("type") == "relation")
    lines = [
        LineString([(point["lon"], point["lat"]) for point in member["geometry"]])
        for member in relation.get("members", [])
        if member.get("type") == "way" and member.get("geometry")
    ]
    polygons = sorted(
        polygonize(unary_union(lines)), key=lambda p: p.area, reverse=True
    )
    if not polygons:
        raise RuntimeError("OSM 内比都联邦区关系没有闭合出多边形")
    return make_valid(polygons[0])


def resolve_overlaps(units: dict[str, object]) -> None:
    """消除相邻单元之间的细长重叠.

    为什么会有重叠: GADM 相邻多边形的公共边不是同一条折线, 而是各自
    略有偏差的两条线, 相减后留下面积很小,跨度很长的楔形条带. 直接画
    会看到颜色叠深的一条边; 这里按顺序把后处理的单元减去已处理单元,
    既消除重叠又不改变总覆盖范围(重叠区域仍由先处理的单元覆盖).
    """
    done = []
    for key in list(units):
        if done:
            units[key] = make_valid(units[key].difference(unary_union(done)))
        done.append(units[key])


def fill_gaps(units: dict[str, object], country) -> None:
    """把国界内,行政区并集之外的碎块并入距离最近的单元.

    注意: 必须先做"距离最近"判断再 union, 不能按中心点判断. 边境缝隙
    往往又长又窄, 中心点可能落在另一个单元的远端.
    """
    covered = unary_union(list(units.values()))
    gap = country.difference(covered)
    gap_parts = list(gap.geoms) if gap.geom_type == "MultiPolygon" else [gap]
    for part in gap_parts:
        if part.is_empty or part.area <= 0:
            continue
        nearest_key = min(units, key=lambda key: units[key].distance(part))
        units[nearest_key] = make_valid(unary_union([units[nearest_key], part]))
    print(f"补缝: {len(gap_parts)} 个碎块, 总面积 {gap.area:.4f} 平方度")


def build_admin1() -> None:
    """重建 ``myanmar_admin1.geojson``: 15 个一级行政区(14 邦/省 + OSM 内比都)."""
    require_raw_data()
    ADMIN_OUT.parent.mkdir(parents=True, exist_ok=True)

    country_gdf = gpd.read_file(COUNTRY_SHP)
    country = make_valid(
        unary_union(country_gdf.loc[country_gdf["ADMIN"] == "Myanmar", "geometry"])
    )
    print(
        f"缅甸国界: {country.geom_type}, 面积 {country.area:.3f} 平方度, 边界框 {country.bounds}"
    )

    gadm = gpd.read_file(GADM_JSON)
    npt_geom = overpass_npt_geometry().intersection(country)
    if npt_geom.is_empty:
        raise RuntimeError("内比都联邦区与缅甸国界没有交集, 数据可能不匹配")

    units: dict[str, object] = {}
    for _, row in gadm.iterrows():
        name = row["NAME_1"]
        if name not in config.ADMIN_INFO:
            print(f"跳过未配置的 GADM 单元: {name}")
            continue
        # GADM 的内比都小块不可用, 这里跳过; 联邦区由上面的 OSM 关系提供.
        if name == "Naypyitaw":
            continue
        # 逐单元先裁到国界内, 再扣掉联邦区, 保证联邦区不会与邻省重叠.
        geom = make_valid(row.geometry).intersection(country).difference(npt_geom)
        if geom.is_empty:
            raise RuntimeError(f"{name} 与国界相交后为空")
        units[name] = geom

    if len(units) != 14:
        raise RuntimeError(f"应有 14 个邦/省, 实际 {len(units)} 个")

    # 把 OSM 联邦区加进来, 此时 15 个单元应当恰好铺满国界内的土地.
    units["Naypyitaw"] = make_valid(npt_geom)
    fill_gaps(units, country)
    resolve_overlaps(units)

    features = []
    for gadm_name, (
        key,
        name_zh,
        name_en,
        kind,
        cap_zh,
        cap_en,
        lon,
        lat,
    ) in config.ADMIN_INFO.items():
        if gadm_name not in units:
            raise RuntimeError(f"缺少 GADM 单元: {gadm_name}")
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "key": key,
                    "name_zh": name_zh,
                    "name_en": name_en,
                    "kind": kind,
                    "capital_zh": cap_zh,
                    "capital_en": cap_en,
                    "capital_lon": lon,
                    "capital_lat": lat,
                },
                "geometry": mapping(units[gadm_name]),
            }
        )

    # 拓扑自检: 并集必须等于国界(面积误差只允许浮点级别), 且单元之间不应重叠.
    total = unary_union([shape(f["geometry"]) for f in features])
    missing = country.difference(total)
    extra = total.difference(country)
    overlaps = []
    geoms = [shape(f["geometry"]) for f in features]
    for i in range(len(geoms)):
        for j in range(i + 1, len(geoms)):
            inter = geoms[i].intersection(geoms[j])
            if inter.area > 1e-9:
                overlaps.append(
                    (
                        features[i]["properties"]["key"],
                        features[j]["properties"]["key"],
                        inter.area,
                    )
                )
    print(
        f"自检: 国界内缺失 {missing.area:.8f}, 越界 {extra.area:.8f}, 重叠 {len(overlaps)} 处"
    )
    if missing.area > 1e-6 or extra.area > 1e-6 or overlaps:
        raise RuntimeError("行政区拓扑自检失败, 请检查补缝和裁剪逻辑")

    collection = {
        "type": "FeatureCollection",
        "properties": {
            "source": "GADM 4.1 + OpenStreetMap (ODbL 1.0), clipped to Natural Earth 10m",
            "units": len(features),
        },
        "features": features,
    }
    ADMIN_OUT.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"已写入: {ADMIN_OUT} ({ADMIN_OUT.stat().st_size / 1024:.0f} KiB)")


# ============================
# OSM 特区/国界: 原始响应 -> 绘图用 GeoJSON
# ============================
def load_overpass_elements(path) -> list[dict]:
    """读一份原始 Overpass 响应, 返回 elements 列表(数据仓按查询分组各存一份)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("elements", [])


def load_shan_raw() -> dict[int, dict]:
    """把若干份原始响应里的 relation 按 id 汇总; 缺任何登记的关系就报错."""
    raw: dict[int, dict] = {}
    files = sorted(SHAN_RAW_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(
            f"未找到掸邦特区原始响应: {SHAN_RAW_DIR}\n"
            "请到数据项目 miko_gis_data 运行: python main.py download --group myanmar"
        )
    for path in files:
        for element in load_overpass_elements(path):
            if element.get("type") == "relation":
                raw[element["id"]] = element
    missing = set(RELATIONS) - set(raw)
    if missing:
        raise RuntimeError(f"以下 relation 未取到: {sorted(missing)}")
    return raw


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


def build_shan() -> None:
    """重建 ``shan_north_boundaries.geojson``: 特区/民地武控制区面要素."""
    SHAN_OUT.parent.mkdir(parents=True, exist_ok=True)
    raw = load_shan_raw()

    features = []
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

    # 原果敢自治区 = 老街市 + 果敢县; 该图层只用于显示"第一特区前身"的包含关系.
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
                "derived_from": list(KOKANG_SAZ_OSM_IDS),
                "admin_level": None,
                "population": None,
                "area_km2": round(saz_area, 1),
            },
            "geometry": mapping(saz_geom),
        }
    )
    print(f"  {'原果敢自治区':<10s} {saz_geom.geom_type:<12s} {saz_area:9.1f} km2 (派生自老街市+果敢县)")

    # 不写抓取时间: 派生文件必须可重复生成(同一份原始响应得到相同字节).
    collection = {
        "type": "FeatureCollection",
        "properties": {"source": "OpenStreetMap (ODbL 1.0)"},
        "features": features,
    }
    SHAN_OUT.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"已写入: {SHAN_OUT} ({SHAN_OUT.stat().st_size/1024:.0f} KiB)")


def build_borders() -> None:
    """重建 ``osm_country_borders.geojson``: 画框附近国界折线.

    只缓存折线: 画国界不需要国家多边形, 而 bbox 裁剪后的成员 way 也拼不出完整多边形.
    每个国家一条 MultiLineString(可能含 bbox 边界处的断口).
    """
    BORDER_OUT.parent.mkdir(parents=True, exist_ok=True)
    if not BORDER_RAW.exists():
        raise FileNotFoundError(
            f"未找到 OSM 国界原始响应: {BORDER_RAW}\n"
            "请到数据项目 miko_gis_data 运行: python main.py download --group myanmar"
        )
    raw = {
        element["id"]: element
        for element in load_overpass_elements(BORDER_RAW)
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
        "properties": {"source": "OpenStreetMap (ODbL 1.0)"},
        "features": features,
    }
    BORDER_OUT.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"已写入: {BORDER_OUT} ({BORDER_OUT.stat().st_size/1024:.0f} KiB)")


def run() -> int:
    """全量重建三份派生 GeoJSON; 返回 0=成功(原始数据缺失或拓扑自检失败会抛异常)."""
    print("\n" + "=" * 60)
    print("派生缅甸图种数据(每次运行都全量重建; 原始数据来自数据仓 miko_gis_data)")
    print("=" * 60)
    print("\n[1/3] 行政区 GeoJSON")
    build_admin1()
    print("\n[2/3] 掸邦特区/民地武控制区")
    build_shan()
    print("\n[3/3] 画框附近国界")
    build_borders()
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python Myanmar/main.py prepare")
