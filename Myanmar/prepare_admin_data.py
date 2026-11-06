#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Prepare the 15 first-order administrative units of Myanmar for mapping.

是什么: 读取 GADM 4.1 缅甸一级行政区原始 JSON, 从 OpenStreetMap 取内比都联邦区边界,
经过裁剪、补缝、拓扑检查后输出 ``Myanmar/data/derived/myanmar_admin1.geojson`` 供绘图
读取. 原始数据与派生文件的位置全部来自 ``Myanmar/config.py`` 的 ``DATASETS``; 缺失的
原始数据用共享下载层补齐, 已就位时只做跳过、不联网.
完整说明(为什么混用 GADM/OSM、为什么补缝)见 ``docs/maps/myanmar-admin.md``;
数据集层见 ``docs/reference/datasets.md``.
"""

from __future__ import annotations

import json
import urllib.parse

import geopandas as gpd
from shapely.geometry import LineString, mapping, shape
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

# 数据集清单与数据源登记: 路径/URL 都不在脚本里另写一份.
import config
from cartopy_file.fetch import (
    MAGIC_JSON,
    MAGIC_ZIP,
    download,
    extract_zip,
    post,
)
from cartopy_file.sources import gadm_url, overpass_endpoints

# 数据路径全部由数据集清单给出(raw/ 与 derived/ 的约定见 docs/reference/datasets.md).
ADMIN_JSON = config.DATASETS.path(config.GADM_MMR_RAW)
ADMIN_DIR = ADMIN_JSON.parent
COUNTRY_SHP = config.DATASETS.path(config.NE_COUNTRIES)
RIVER_DIR = config.DATASETS.path(config.NE_RIVERS)
RIVER_SHP = RIVER_DIR / "ne_10m_rivers_lake_centerlines.shp"
NPT_JSON = config.DATASETS.path(config.NAYPYIDAW_CACHE)
OUT_PATH = config.DATASETS.path(config.ADMIN_GEOJSON)
NPT_RELATION_ID = 5996482

# GADM 名称 -> (键名, 中文名, 英文名, 类型, 行政中心中文, 行政中心英文, 中心经度, 中心纬度).
# 行政中心坐标来自 Natural Earth 10m populated places, 实皆省的行政中心
# 按现行建制改用蒙育瓦(Monywa), 不用 Natural Earth 里过时的实皆(Sagaing).
# 类型: state=邦, region=省, union=联邦区.
ADMIN_INFO: dict[str, tuple[str, str, str, str, str, str, float, float]] = {
    "Kachin": (
        "kachin",
        "克钦邦",
        "Kachin State",
        "state",
        "密支那",
        "Myitkyina",
        97.392753,
        25.359627,
    ),
    "Kayah": (
        "kayah",
        "克耶邦",
        "Kayah State",
        "state",
        "垒固",
        "Loikaw",
        97.206004,
        19.665000,
    ),
    "Kayin": (
        "kayin",
        "克伦邦",
        "Kayin State",
        "state",
        "帕安",
        "Hpa-an",
        97.616701,
        16.849998,
    ),
    "Chin": (
        "chin",
        "钦邦",
        "Chin State",
        "state",
        "哈卡",
        "Hakha",
        93.616705,
        22.650003,
    ),
    "Mon": (
        "mon",
        "孟邦",
        "Mon State",
        "state",
        "毛淡棉",
        "Mawlamyine",
        97.670048,
        16.500426,
    ),
    "Rakhine": (
        "rakhine",
        "若开邦",
        "Rakhine State",
        "state",
        "实兑",
        "Sittwe",
        92.880005,
        20.139997,
    ),
    "Shan": (
        "shan",
        "掸邦",
        "Shan State",
        "state",
        "东枝",
        "Taunggyi",
        97.038001,
        20.781999,
    ),
    "Ayeyarwady": (
        "ayeyarwady",
        "伊洛瓦底省",
        "Ayeyarwady Region",
        "region",
        "勃生",
        "Pathein",
        94.749968,
        16.770409,
    ),
    "Bago": (
        "bago",
        "勃固省",
        "Bago Region",
        "region",
        "勃固",
        "Bago",
        96.514977,
        17.320014,
    ),
    "Magway": (
        "magway",
        "马圭省",
        "Magway Region",
        "region",
        "马圭",
        "Magway",
        94.919570,
        20.144544,
    ),
    "Mandalay": (
        "mandalay",
        "曼德勒省",
        "Mandalay Region",
        "region",
        "曼德勒",
        "Mandalay",
        96.083083,
        21.971934,
    ),
    "Sagaing": (
        "sagaing",
        "实皆省",
        "Sagaing Region",
        "region",
        "蒙育瓦",
        "Monywa",
        95.149996,
        22.104993,
    ),
    "Tanintharyi": (
        "tanintharyi",
        "德林达依省",
        "Tanintharyi Region",
        "region",
        "土瓦",
        "Dawei",
        98.194978,
        14.097963,
    ),
    "Yangon": (
        "yangon",
        "仰光省",
        "Yangon Region",
        "region",
        "仰光",
        "Yangon",
        96.164732,
        16.785300,
    ),
    # 键名里的 npt 是 Naypyitaw/Naypyidaw 的缩写; 联邦区不是邦也不是省,
    # 绘图时单独使用中性色, 避免被误读为暖色的省.
    "Naypyitaw": (
        "npt",
        "内比都联邦区",
        "Naypyidaw Union Territory",
        "union",
        "内比都",
        "Naypyidaw",
        96.116673,
        19.768503,
    ),
}


def ensure_country_data() -> None:
    """确保共享缓存里的 Natural Earth 10m 国界可用(由根目录 download_data.py 预取)."""
    if COUNTRY_SHP.is_file():
        print(f"已存在, 跳过 Natural Earth 10m 国界: {COUNTRY_SHP}")
        return
    raise FileNotFoundError(
        f"未找到 Natural Earth 10m 国界: {COUNTRY_SHP}\n"
        "请先运行根目录的 python download_data.py 预取共享底图缓存."
    )


def ensure_river_data() -> None:
    """确保 Natural Earth 10m 河流(5.0.0 旧副本)可用; 已存在时绝不重下."""
    if RIVER_SHP.is_file():
        print(f"已存在, 跳过 Natural Earth 10m 河流: {RIVER_DIR}")
        return
    dataset = config.NE_RIVERS
    archive = RIVER_DIR.with_suffix(".zip")
    download(
        dataset.url,
        archive,
        description="Natural Earth 10m 河流压缩包",
        magic=MAGIC_ZIP,
    )
    extract_zip(archive, RIVER_DIR)
    # 这份数据钉在旧版本 5.0.0(河网几何参与成品); S3 地址不带版本号, 重下可能拿到
    # 新版, 这里显式提示, 版本对不上时按 docs/reference/datasets.md 的流程复核.
    found = config.DATASETS.version_of(dataset)
    if found and dataset.version and found != dataset.version:
        print(
            f"警告: 河流数据版本是 {found}, 期望 {dataset.version}; "
            "换版会改变河网几何, 请复核产物."
        )


def ensure_gadm_data() -> None:
    """确保 GADM 4.1 缅甸一级行政区 JSON 可用; 已存在时跳过."""
    download(
        gadm_url("MMR"),
        ADMIN_JSON,
        description="GADM 4.1 缅甸一级行政区",
        magic=MAGIC_JSON,
    )


def ensure_npt_cache() -> None:
    """确保 OSM 内比都联邦区 relation 的原始响应已缓存; 已存在时跳过."""
    if NPT_JSON.is_file():
        print(f"已存在, 跳过 OSM 内比都联邦区缓存: {NPT_JSON}")
        return
    query = f"[out:json][timeout:90];rel({NPT_RELATION_ID});out geom;"
    body = urllib.parse.urlencode({"data": query}).encode()
    # Overpass 主实例偶尔返回 502; 换镜像并重试, 避免整个数据准备流程中断.
    last_error: Exception | None = None
    for url in overpass_endpoints():
        try:
            post(
                url,
                body,
                NPT_JSON,
                description="OSM 内比都联邦区",
                retries=2,
                timeout=180,
            )
            return
        except RuntimeError as exc:  # fetch.post 重试用尽后的统一异常
            last_error = exc
            print(f"  Overpass 请求失败 ({url}): {exc}")
    raise RuntimeError(f"无法从 Overpass 获取内比都联邦区边界: {last_error}")


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
    略有偏差的两条线, 相减后留下面积很小、跨度很长的楔形条带. 直接画
    会看到颜色叠深的一条边; 这里按顺序把后处理的单元减去已处理单元,
    既消除重叠又不改变总覆盖范围(重叠区域仍由先处理的单元覆盖).
    """
    done = []
    for key in list(units):
        if done:
            units[key] = make_valid(units[key].difference(unary_union(done)))
        done.append(units[key])


def fill_gaps(units: dict[str, object], country) -> None:
    """把国界内、行政区并集之外的碎块并入距离最近的单元.

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


def main() -> None:
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)
    ensure_country_data()
    ensure_river_data()
    ensure_gadm_data()
    ensure_npt_cache()

    country_gdf = gpd.read_file(COUNTRY_SHP)
    country = make_valid(
        unary_union(country_gdf.loc[country_gdf["ADMIN"] == "Myanmar", "geometry"])
    )
    print(
        f"缅甸国界: {country.geom_type}, 面积 {country.area:.3f} 平方度, 边界框 {country.bounds}"
    )

    gadm = gpd.read_file(ADMIN_JSON)
    npt_geom = overpass_npt_geometry().intersection(country)
    if npt_geom.is_empty:
        raise RuntimeError("内比都联邦区与缅甸国界没有交集, 数据可能不匹配")

    units: dict[str, object] = {}
    for _, row in gadm.iterrows():
        name = row["NAME_1"]
        if name not in ADMIN_INFO:
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
    ) in ADMIN_INFO.items():
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
    OUT_PATH.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"已写入: {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
