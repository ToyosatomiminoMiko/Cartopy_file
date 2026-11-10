#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Build the derived GeoJSON layers for the Ukraine overview map.

是什么: 读数据仓的原始数据(GADM 乌克兰一级行政区, OCHA GCA/NGCA 压缩包, Natural Earth
10m 河网/湖泊, 6 份 OSM Overpass 快照), 按本图口径派生出 1991/2014/2022 边界, 德左参照面,
河流/水库等 12 份 GeoJSON 到 ``Ukraine/build/``, 供渲染模块离线读取; 每次运行全量重建.
本文件是模块, 只导出 ``run()``; 命令行入口是 ``python Ukraine/main.py prepare``.
为什么放在渲染仓: 法理口径,裁剪边缘,简化阈值都是图种需求; 数据仓只提供原始数据
(分工见 ``docs/data-preparation.md`` 与 ``docs/reference/prepare.md``).
完整说明(数据源选择,输出文件,运行方式)见 ``docs/maps/ukraine.md``;
几何工具口径见 ``docs/reference/geometry.md``.
"""

from __future__ import annotations

import functools
import json
import math
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, box
from shapely.ops import linemerge, polygonize, substring, unary_union

# 目录布局与派生路径(本仓子项目 build/, 见 docs/reference/spec.md).
import config
from cartopy_file.catalog import catalog_for
from cartopy_file.data import configure_cartopy

# cartopy 的 Natural Earth 缓存必须指向数据根, 否则 manifest 里的图层会解析到旧 HOME 缓存;
# 调用要在读取图层路径之前(见 docs/reference/data.md).
configure_cartopy()

# 共享几何工具(与图种无关), 口径见 docs/reference/geometry.md.
from cartopy_file.geometry import (
    feature,
    geodesic_area_km2,
    geodesic_length_km,
    n_vertices,
    valid_geometry,
    write_geojson,
)

# ============================
# 1. 路径与数据来源(原始数据仍由数据仓 manifest 定位)
# ============================
CATALOG = catalog_for(config.DATA_GROUP)

# 原始数据(raw/, 由数据仓 download 准备).
GADM_JSON = CATALOG.path("gadm41-ukr")
# OCHA 解压目录(数据仓 download 解压, dest 是目录).
OCHA_DIR = CATALOG.path("ocha-gca-ngca")
DNIEPER_RIVER_CACHE = CATALOG.path("osm-dnieper-river")
DNIEPER_WATER_CACHE = CATALOG.path("osm-dnieper-reservoirs")
DNIESTER_RIVER_CACHE = CATALOG.path("osm-dniester-river")
TRANSNISTRIA_BOUNDARY_CACHE = CATALOG.path("osm-transnistria-boundary")

# 派生 GeoJSON 的输出路径(文件名在 config.py 里登记).
OBLASTS_PATH = config.OBLASTS_GEOJSON
BORDER_1991_PATH = config.BORDER_1991_GEOJSON
CRIMEA_LINE_PATH = config.CRIMEA_LINE_GEOJSON
OCCUPIED_2014_PATH = config.OCCUPIED_2014_GEOJSON
CONTACT_2014_PATH = config.CONTACT_2014_GEOJSON
CLAIMED_2022_PATH = config.CLAIMED_2022_GEOJSON
TRANSNISTRIA_PATH = config.TRANSNISTRIA_GEOJSON
DNIEPER_RIVER_PATH = config.DNIEPER_RIVER_GEOJSON
DNIEPER_WATER_PATH = config.DNIEPER_WATER_GEOJSON
DNIESTER_RIVER_PATH = config.DNIESTER_RIVER_GEOJSON

# ---- 绘图所需参数 ----
# 第聂伯河梯级水库(从上游到下游): OSM 里都是 natural=water 的 multipolygon relation.
# 只取 outer 成员: 水库里的岛屿(inner)在 1:330 万图上不足 1 px.
# 注意: 这组 id 也出现在数据仓的下载查询里, 改图时两边一起改.
DNIEPER_RESERVOIRS: dict[int, str] = {
    1605938: "Київське водосховище",       # 基辅水库
    3173129: "Канівське водосховище",       # 卡尼夫水库
    2289192: "Кременчуцьке водосховище",    # 克列缅丘格水库
    287177: "Кам'янське водосховище",       # 卡缅斯克水库
    21217234: "Дніпровське водосховище",    # 第聂伯水库
}
# 卡霍夫卡水库: 2023-06 大坝被毁后放空, OSM 已删除其水面; 本图是 2022 年口径,
# 用 Natural Earth 10m 湖泊层里溃坝前的水库面补上.
KAKHOVKA_NE_NAME = "Kakhovka"
RIVER_SIMPLIFY_DEG = 0.0003   # ≈33 m, 小于图上 1 px(≈270 m), 肉眼无损
WATER_SIMPLIFY_DEG = 0.0003
WATER_MIN_AREA_DEG2 = 0.001   # 约 8 km², 滤掉 polygonize 留下的碎片
# 画框 [21.0, 41.5]E / [43.2, 53.4]N 投影后四角外张, 这里比画框多留 ~1°.
DNIEPER_CLIP = (29.0, 44.5, 38.0, 54.0)  # (min_lon, min_lat, max_lon, max_lat)

# ---- 德涅斯特河(OSM) 与德左参照面 ----
# 德左面裁切用的局部 bbox (min_lon, min_lat, max_lon, max_lat); 只在这里求
# "河心线东侧"与"1991 国界以内", 不必把整条河/整个乌克兰都参与运算.
TRANSNISTRIA_CLIP = (28.2, 46.3, 30.4, 48.5)
# 主流程按 main_stream 合并时允许直连的最大断口: OSM 里个别河段被水库/坝
# 断开(实测最大断口 ~1.6 km, 在摩尔多瓦北部), 不接上就会在图上留一个小断口.
DNIESTER_BRIDGE_DEG = 0.02
# 裁切交集留下的小碎片(实测最大 1.3 km²)比图上 1 px 还小, 丢掉.
TRANSNISTRIA_MIN_AREA_KM2 = 2.0

# ---- 南布格河/顿河: NE 10m 在河口前收笔, 用 OSM 补下游段 ----
# cache 是数据仓的 OSM 原始响应数据集 id; name_zh/输出文件名只在本图用.
RIVER_EXTENSIONS: tuple[dict, ...] = (
    {
        "key": "southern_bug",
        "ne_name": "Southern Bug",
        "osm_names": ("Південний Буг", "Южний Буг", "Southern Bug"),
        "name_zh": "南布格河下游补段",
        "cache_id": "osm-southern-bug",
        "out_path": config.SOUTHERN_BUG_GEOJSON,
    },
    {
        "key": "don",
        "ne_name": "Don",
        # 顿河下游在俄罗斯境内, OSM 用俄语名; 三角洲的汊道各有名字, 只要主河道.
        "osm_names": ("Дон",),
        "name_zh": "顿河下游补段",
        "cache_id": "osm-don",
        "out_path": config.DON_GEOJSON,
    },
)
# 接缝点选择: 在 OSM 下游链的上游段上扫描, 取"离 NE 线近 + 走向一致"的点.
# 为什么不直接首尾相接: 两套数据对同一条河的描绘相差 0.5~2 km, 且 NE 在河口
# 附近简化出了一些不自然的弯; 直接接会留下台阶或硬折角. 按距离+方向挑接缝
# 后, 实测两条河在接缝处的走向差都不到 5°, 图上就是一个普通河弯.
RIVER_JOIN_SCAN = 0.6          # 只在前 60% 弧长里找接缝, 保证下游段仍在
RIVER_JOIN_DIST_DEG = 0.01     # 距离权重: 0.01°(约 1.1 km) 记 1 个单位
RIVER_JOIN_ANGLE_DEG = 30.0    # 方向权重: 30° 记 1 个单位

# GADM 英文名 -> (中文名, 显示用英文名). 只用于图面标注与属性, 不影响几何.
# 名字带撇号是 GADM 的原文(如 Donets'k), 显示时统一成通行英文拼写.
UNIT_NAMES: dict[str, tuple[str, str]] = {
    "Cherkasy": ("切尔卡瑟州", "Cherkasy"),
    "Chernihiv": ("切尔尼戈夫州", "Chernihiv"),
    "Chernivtsi": ("切尔诺夫策州", "Chernivtsi"),
    "Crimea": ("克里米亚", "Crimea"),
    "Dnipropetrovs'k": ("第聂伯罗彼得罗夫斯克州", "Dnipropetrovsk"),
    "Donets'k": ("顿涅茨克州", "Donetsk"),
    "Ivano-Frankivs'k": ("伊万诺-弗兰科夫斯克州", "Ivano-Frankivsk"),
    "Kharkiv": ("哈尔科夫州", "Kharkiv"),
    "Kherson": ("赫尔松州", "Kherson"),
    "Khmel'nyts'kyy": ("赫梅利尼茨基州", "Khmelnytskyi"),
    "Kiev": ("基辅州", "Kyiv Oblast"),
    "KievCity": ("基辅市", "Kyiv City"),
    "Kirovohrad": ("基洛沃格勒州", "Kirovohrad"),
    "L'viv": ("利沃夫州", "Lviv"),
    "Luhans'k": ("卢甘斯克州", "Luhansk"),
    "Mykolayiv": ("尼古拉耶夫州", "Mykolaiv"),
    "Odessa": ("敖德萨州", "Odesa"),
    "Poltava": ("波尔塔瓦州", "Poltava"),
    "Rivne": ("里夫内州", "Rivne"),
    "Sevastopol'": ("塞瓦斯托波尔", "Sevastopol"),
    "Sumy": ("苏梅州", "Sumy"),
    "Ternopil'": ("捷尔诺波尔州", "Ternopil"),
    "Vinnytsya": ("文尼察州", "Vinnytsia"),
    "Volyn": ("沃伦州", "Volyn"),
    "Zakarpattia": ("外喀尔巴阡州", "Zakarpattia"),
    "Zaporizhia": ("扎波罗热州", "Zaporizhzhia"),
    "Zhytomyr": ("日托米尔州", "Zhytomyr"),
}

# 2022 年俄方单方面宣称"全境"的四个地区(GADM 英文名, 中文名).
CLAIMED_2022_UNITS = [
    ("Kherson", "赫尔松州"),
    ("Zaporizhia", "扎波罗热州"),
    ("Donets'k", "顿涅茨克人民共和国"),
    ("Luhans'k", "卢甘斯克人民共和国"),
]


# ============================
# 2. 几何工具与 GADM 读取
# ============================
# 几何修整/GeoJSON 写出/面积长度量算已上移到通用几何模块(cartopy_file.geometry).
# 这里只留本图幅的小孔阈值; 阈值与图幅尺度有关, 不能做成全局常数
# (见 docs/reference/geometry.md).
MIN_HOLE_AREA_DEG = 1e-4
# feat() 调用点保持旧写法: 用 partial 把本图幅的阈值固定进去(坐标精度用模块缺省的 6 位).
feat = functools.partial(feature, min_hole_area=MIN_HOLE_AREA_DEG)


def _read_ne_layer(dataset_id: str):
    """读共享缓存里的 Natural Earth 图层; 缺文件时返回 None(不联网)."""
    path = CATALOG.path(dataset_id)
    if not Path(path).is_file():
        return None
    return gpd.read_file(path)


def _single_relation(payload: dict) -> dict:
    """从一份专用 Overpass 快照里取唯一的关系.

    为什么不再按 id 找: 数据仓现在每个数据集对应一次查询,一份原始响应, 文件里只有
    该查询返回的关系; 若文件里没有或有多个, 说明缓存来源不对, 直接报错.
    """
    relations = [
        element for element in payload.get("elements", []) if element.get("type") == "relation"
    ]
    if len(relations) != 1:
        raise RuntimeError(f"Overpass 快照里应有 1 个 relation, 实际 {len(relations)} 个")
    return relations[0]


def load_gadm() -> gpd.GeoDataFrame:
    """读 GADM 乌克兰一级行政区.

    为什么用 GADM 4.1: Natural Earth 的 admin_0 把克里米亚划给俄罗斯
    (事实控制口径). 本图要画"1991 年国际承认边界", 必须让克里米亚和
    塞瓦斯托波尔留在乌克兰内, 因此用 GADM 的法理口径(UKR 下含 Crimea
    与 Sevastopol' 两个单元), 与缅甸行政图的取数口径一致.
    GADM 有一行 NAME_1 为 "?" 的约 170 km² 碎块(基辅东郊), 不参与州界
    展示, 但保留在 1991 年国界合并里, 保证国界无缺口.
    """
    gdf = gpd.read_file(GADM_JSON)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs("EPSG:4326")


# ============================
# 3. 派生边界数据
# ============================
def build_oblasts(gdf: gpd.GeoDataFrame):
    """输出 27 个一级行政区(不含 GADM 的 '?' 碎块), 并合并出 1991 年国界."""
    feats = []
    for _, row in gdf.iterrows():
        name = row["NAME_1"]
        if name not in UNIT_NAMES:
            # 跳过 "?" 行; 若 GADM 升级后出现新的单元, 打印出来提醒补映射.
            if name != "?":
                print(f"警告: 未登记的一级行政区 {name!r}, 已跳过")
            continue
        name_zh, name_en = UNIT_NAMES[name]
        geom = valid_geometry(row.geometry)
        feats.append(
            feat(
                geom,
                {
                    "gid": row["GID_1"],
                    "name": name,
                    "name_en": name_en,
                    "name_zh": name_zh,
                    "type": row.get("ENGTYPE_1", ""),
                    "source": "GADM 4.1 gadm41_UKR_1.json",
                    "dejure_country": "Ukraine",
                },
            )
        )
    write_geojson(OBLASTS_PATH, feats)

    # 1991 年边界 = 全部 GADM 一级单元(含 '?' 碎块)合并; 保留克里米亚与
    # 塞瓦斯托波尔, 因为 GADM 是法理口径.
    border_1991 = unary_union([valid_geometry(g) for g in gdf.geometry])
    write_geojson(
        BORDER_1991_PATH,
        [
            feat(
                border_1991,
                {
                    "name": "Ukraine 1991 border (internationally recognised)",
                    "name_zh": "1991 年乌克兰国际承认边界(含克里米亚)",
                    "note": "苏联解体时乌克兰的国界; 含克里米亚自治共和国与塞瓦斯托波尔.",
                    "source": "GADM 4.1 gadm41_UKR_1.json dissolved (de jure)",
                    "area_km2_geodesic": round(geodesic_area_km2(border_1991), 1),
                    "contains_crimea": True,
                },
            )
        ],
    )
    return gdf, border_1991


def build_crimea_line(gdf: gpd.GeoDataFrame) -> None:
    """2014 年克里米亚陆上控制线 = 克里米亚与赫尔松州的共享行政边界.

    为什么不是克里米亚的整个外轮廓: 外轮廓的其余部分都是海岸线, 1991 年
    国际承认边界(黑线)已经画过; 2014 年真正改变的是半岛与乌克兰本土之间
    的这条内部行政边界(彼列科普地峡 + 锡瓦什湖一带). 用"两边界的交集"取
    共享段, 比手工裁切稳定.
    """
    crimea = unary_union(
        [valid_geometry(g) for g in gdf[gdf["NAME_1"].isin(["Crimea", "Sevastopol'"])].geometry]
    )
    kherson = valid_geometry(gdf[gdf["NAME_1"] == "Kherson"].geometry.iloc[0])
    shared = crimea.boundary.intersection(kherson.buffer(0.005))
    line = linemerge(shared) if shared.geom_type != "LineString" else shared
    parts = [p for p in (line.geoms if hasattr(line, "geoms") else [line]) if p.geom_type == "LineString"]
    # 0.001° ≈ 110 m, 去掉数字化噪音; 共享边界本身不长, 保留全部主要段.
    parts = [p.simplify(0.001, preserve_topology=False) for p in parts if p.length > 0.005]
    line = unary_union(parts)
    write_geojson(
        CRIMEA_LINE_PATH,
        [
            feat(
                line,
                {
                    "name": "Crimea de facto control line (land, 2014-)",
                    "name_zh": "2014 年克里米亚陆上实际控制线",
                    "note": "克里米亚与赫尔松州的行政边界; 海上部分未画.",
                    "source": "GADM 4.1 Crimea + Sevastopol' vs Kherson shared boundary",
                    "length_km_geodesic": round(geodesic_length_km(line), 1),
                },
            )
        ],
    )


def build_donbas_2014() -> None:
    """2014 年顿巴斯控制区与接触线, 基于 OCHA GCA/NGCA 分区(2021 HNO).

    处理步骤:
      1. 读 GCA/NGCA 四个面(顿涅茨克/卢甘斯克各一个 GCA,一个 NGCA);
      2. NGCA 按州分别输出为"分离武装控制区"(填色用);
      3. 接触线 = NGCA 边界 ∩ GCA 外扩 130 m 的缓冲带. 用缓冲带而不是直接
         求交集, 是因为两套面在数字化时会有几十米的缝/叠; 这样能稳定地挑出
         "紧贴政府控制区"的那段边界, 自动排除俄罗斯国界与亚速海岸线.
    误差说明: 这条线是 2015 年明斯克协议后的线(2018-08 数字化), 2015-2022
    基本稳定; 用于近似 2014 年底的接触线, 主要差异在杰巴利采韦(2015-02 才
    易手)与斯维特洛达尔斯克一带. 项目需求允许"大致范围".
    交叉验证: 与 OCHA 2017-04 接触线相比, 平均偏差约 0.04 km, 90 分位
    ~0.1 km, 最大 0.5 km; 反向局部最大 6.9 km 出现在南顿涅茨克与佐洛特
    (Zolote)两处, 属于 2018 面数据的泛化误差.
    """
    gca_ngca = gpd.read_file(next(Path(OCHA_DIR).glob("*.shp"))).to_crs("EPSG:4326")
    status_col = "GCA or NGC"  # 注意 HDX 原始字段名就是这个拼写
    ngca = gca_ngca[gca_ngca[status_col] == "NGCA"]
    gca = gca_ngca[gca_ngca[status_col] == "GCA"]

    # 3.1 控制区: 按州分别输出, 图上可以分别标注"顿涅茨克人民共和国/
    # 卢甘斯克人民共和国"的实际控制范围.
    occ_feats = []
    for _, row in ngca.iterrows():
        geom = valid_geometry(row.geometry).simplify(0.0003, preserve_topology=True)
        name_en = row["adm1NameEN"]
        occ_feats.append(
            feat(
                geom,
                {
                    "name": f"NGCA, {name_en} oblast",
                    "name_zh": f"{name_en}州非政府控制区(分离武装控制)",
                    "period": "2014-2022 (proxy: Minsk line)",
                    "control": "Russian-backed separatist forces",
                    "approx": True,
                    "source": "OCHA/HDX 2021 HNO GCA_NGCA (dataset 0a24205d)",
                    "area_km2_geodesic": round(geodesic_area_km2(geom), 1),
                },
            )
        )
    occupied = unary_union([valid_geometry(r.geometry) for _, r in ngca.iterrows()])
    occ_feats.append(
        feat(
            occupied,
            {
                "name": "NGCA union, Donetsk + Luhansk",
                "name_zh": "顿巴斯分离武装控制区合计",
                "approx": True,
                "area_km2_geodesic": round(geodesic_area_km2(occupied), 1),
            },
        )
    )
    write_geojson(OCCUPIED_2014_PATH, occ_feats)

    # 3.2 接触线.
    band = unary_union([valid_geometry(g) for g in gca.geometry]).buffer(0.0012)
    raw = occupied.boundary.intersection(band)
    merged = linemerge(raw) if raw.geom_type != "LineString" else raw
    segments = [s for s in (merged.geoms if hasattr(merged, "geoms") else [merged]) if s.geom_type == "LineString" and s.length > 0.005]
    # 逐级简化, 顶点数控制在 4500 以内(300 dpi 下这个密度已经足够).
    tol = 0.0002
    simplified = [s.simplify(tol, preserve_topology=False) for s in segments]
    while sum(len(s.coords) for s in simplified) > 4500:
        tol = min(tol * 1.5, 0.005)
        simplified = [s.simplify(tol, preserve_topology=False) for s in segments]
    contact = unary_union(simplified)
    write_geojson(
        CONTACT_2014_PATH,
        [
            feat(
                contact,
                {
                    "name": "Donbas contact line (approx. 2014-2015 Minsk line)",
                    "name_zh": "顿巴斯接触线(近似: 明斯克协议线)",
                    "period": "2014-2015 (proxy: Minsk line, 2018-08 digitised)",
                    "approx": True,
                    "source": "derived from OCHA/HDX 2021 HNO GCA_NGCA shared boundary",
                    "length_km_geodesic": round(geodesic_length_km(contact), 1),
                    "uncertainty": "positional error ~1-2 km; stands in for end-2014 contact line",
                },
            )
        ],
    )


def build_claimed_2022(gdf: gpd.GeoDataFrame) -> None:
    """2022 年俄方宣称的四州全境: 取四州完整州界(面), 面本身不填色, 只画边界.

    为什么要强调"宣称": 俄方 2022-09-30 单方面宣称并入赫尔松州,扎波罗热州,
    顿涅茨克人民共和国,卢甘斯克人民共和国全境, 但其中相当一部分(如赫尔松市,
    扎波罗热市)从未被俄军控制; 所以本图不把四州整个涂色, 只用紫色点划线
    画其法理州界, 并在图例/注记里写明"单方面宣称, 非实际控制线".
    """
    feats = []
    for gadm_name, name_zh in CLAIMED_2022_UNITS:
        row = gdf[gdf["NAME_1"] == gadm_name].iloc[0]
        geom = valid_geometry(row.geometry)
        feats.append(
            feat(
                geom,
                {
                    "name": f"{gadm_name} oblast (claimed in full)",
                    "name_zh": name_zh,
                    "claim": "Russia, 2022-09-30, full oblast territory",
                    "approx_claim": True,
                    "source": "GADM 4.1 admin-1 boundary (full oblast, de jure)",
                    "area_km2_geodesic": round(geodesic_area_km2(geom), 1),
                },
            )
        )
    write_geojson(CLAIMED_2022_PATH, feats)


# ============================
# 4. 第聂伯河: 从 OSM 原始快照派生绘图用 GeoJSON
# ============================
def _osm_way_geometry(element: dict) -> LineString | None:
    """把 Overpass ``out geom`` 的 way 元素转成 LineString; 顶点不足 2 个时返回 None."""
    coords = [(p["lon"], p["lat"]) for p in element.get("geometry", [])]
    return LineString(coords) if len(coords) >= 2 else None


def build_dnieper_river() -> None:
    """第聂伯河干流: 合并 relation 的 main_stream 成员 way, 裁剪后输出中心线.

    为什么只取 main_stream: relation 里还有 73 段 side_stream(三角洲汊道与
    废弃老河道), 在 1:330 万图上会把干流弄脏; 干流本身是一条首尾相接的
    连续线, linemerge 后只得到一个 LineString, 不需要自己排序.
    """
    payload = json.loads(DNIEPER_RIVER_CACHE.read_text(encoding="utf-8"))
    relation = _single_relation(payload)
    ways = [
        geom
        for member in relation["members"]
        if member.get("type") == "way" and member.get("role") == "main_stream"
        and (geom := _osm_way_geometry(member)) is not None
    ]
    if not ways:
        raise RuntimeError("OSM 第聂伯河 relation 中没有 main_stream 成员")

    merged = linemerge(ways)
    clipped = merged.intersection(box(*DNIEPER_CLIP))
    lines = (
        [clipped]
        if clipped.geom_type == "LineString"
        else [g for g in getattr(clipped, "geoms", []) if g.geom_type == "LineString"]
    )
    lines = [g.simplify(RIVER_SIMPLIFY_DEG, preserve_topology=False) for g in lines]
    line = lines[0] if len(lines) == 1 else unary_union(lines)
    write_geojson(
        DNIEPER_RIVER_PATH,
        [
            feat(
                line,
                {
                    "name": "Dnieper main stream (OSM)",
                    "name_zh": "第聂伯河干流中心线",
                    "source": f"OpenStreetMap relation {relation['id']} "
                    "(waterway=river, main_stream members); ODbL 1.0",
                    "note": "仅取 main_stream; 三角洲 side_stream 与水库内的中心线不单独画.",
                    "length_km_geodesic": round(geodesic_length_km(line), 1),
                    "vertices": n_vertices(line),
                    "simplify_deg": RIVER_SIMPLIFY_DEG,
                },
            )
        ],
    )


def load_kakhovka_from_ne():
    """从共享的 Natural Earth 10m 湖泊缓存取卡霍夫卡水库(溃坝前水面).

    为什么不用 OSM: 2023-06 新卡霍夫卡大坝被毁后水库放空, OSM 已删掉这片
    水面; 本图表达 2022 年, 所以用 Natural Earth(2022 年前编制)的轮廓.
    缓存缺失时返回 None(调用方跳过, 不联网).
    """
    lakes = _read_ne_layer("ne-lakes-10m")
    if lakes is None:
        print("警告: 缺少 Natural Earth 10m 湖泊缓存, 卡霍夫卡水库将不画")
        return None
    row = lakes[lakes["name_en"] == KAKHOVKA_NE_NAME]
    if row.empty:
        print(f"警告: NE 10m 湖泊里没有 {KAKHOVKA_NE_NAME}, 卡霍夫卡水库将不画")
        return None
    return valid_geometry(row.geometry.iloc[0])


def build_dnieper_water() -> None:
    """第聂伯河梯级水库水面: 五个 OSM multipolygon 的 outer 环 + NE 卡霍夫卡.

    处理步骤:
      1. 把全部 outer way 拼成线段, polygonize 成闭合多边形;
      2. 丢掉面积 < WATER_MIN_AREA_DEG2 的碎片(polygonize 偶尔会留下小面);
      3. 简化到 0.0003°(≈33 m), 顶点从 13.9 万降到约 1.2 万, 肉眼无损;
      4. 并入 NE 的卡霍夫卡水库面, 裁剪到画框外 1°.
    忽略 inner(岛屿): 基辅水库一个 relation 就有 520 个 inner way, 而图上
    这些岛都小于 1 px; 不下载它们能把 Overpass 响应从 ~13 MB 降到 ~9 MB.
    """
    payload = json.loads(DNIEPER_WATER_CACHE.read_text(encoding="utf-8"))
    ways = [geom for element in payload["elements"] if (geom := _osm_way_geometry(element))]
    if not ways:
        raise RuntimeError("OSM 水库缓存里没有 way 几何")

    polygons = [p for p in polygonize(unary_union(ways)) if p.area >= WATER_MIN_AREA_DEG2]
    print(f"  水库多边形: {len(polygons)} 个(已有 5 个梯级水库应全部闭合)")
    polygons = [p.simplify(WATER_SIMPLIFY_DEG, preserve_topology=True) for p in polygons]
    sources = [f"OSM relation {rel_id} ({name})" for rel_id, name in DNIEPER_RESERVOIRS.items()]

    kakhovka = load_kakhovka_from_ne()
    if kakhovka is not None:
        polygons.append(valid_geometry(kakhovka).simplify(WATER_SIMPLIFY_DEG, preserve_topology=True))
        sources.append("Natural Earth 10m lakes (Kakhovka Reservoir, pre-2023)")

    water = unary_union(polygons).intersection(box(*DNIEPER_CLIP))
    write_geojson(
        DNIEPER_WATER_PATH,
        [
            feat(
                water,
                {
                    "name": "Dnieper cascade reservoirs (OSM)",
                    "name_zh": "第聂伯河梯级水库水面",
                    "source": "; ".join(sources) + "; ODbL 1.0",
                    "note": "只取 outer 环; 水库岛屿(inner)在图上小于 1 px, 未画.",
                    "area_km2_geodesic": round(geodesic_area_km2(water), 1),
                    "vertices": n_vertices(water),
                    "simplify_deg": WATER_SIMPLIFY_DEG,
                },
            )
        ],
    )


# ============================
# 5. 德涅斯特河干流与德左参照面(OSM)
# ============================
def _relation_way_geometries(relation: dict, roles: tuple[str, ...]) -> list[LineString]:
    """取 Overpass relation 成员 way 的几何, 只保留指定 role.

    为什么要按 role 过滤: 德涅斯特河 relation 里 main_stream 是干流,
    side_stream/tributary 是三角洲汊道与支流; 德左边界 relation 里
    outer 是地带外缘, inner 是飞地内环. 混在一起会把线/面画脏.
    """
    return [
        geom
        for member in relation["members"]
        if member.get("type") == "way"
        and member.get("role") in roles
        and (geom := _osm_way_geometry(member)) is not None
    ]


def _bridge_line_parts(parts: list[LineString], tol: float) -> LineString:
    """把若干线段按"最近端点"贪心拼成一条线; 断口 <= tol 时用直线接上.

    为什么需要: OSM relation 的 main_stream 成员在个别水库/坝处端点不重合
    (实测德涅斯特河最大断口约 1.6 km, 在摩尔多瓦北部), linemerge 后会留下
    多段. 画图时它们必须是一条连续线, 否则河上会留小断口; 只接 tol 以内的
    断口, 不会把相距很远的支流误连成一条.
    """
    parts = [part for part in parts if part.length > 0]
    if not parts:
        raise RuntimeError("没有可拼接的线段")
    parts.sort(key=lambda part: part.length, reverse=True)
    coords = list(parts.pop(0).coords)
    while parts:
        best: tuple[float, str, int] | None = None
        for index, part in enumerate(parts):
            candidates = (
                (Point(coords[0]).distance(Point(part.coords[0])), "head-head", index),
                (Point(coords[0]).distance(Point(part.coords[-1])), "head-tail", index),
                (Point(coords[-1]).distance(Point(part.coords[0])), "tail-head", index),
                (Point(coords[-1]).distance(Point(part.coords[-1])), "tail-tail", index),
            )
            dist, kind, idx = min(candidates)
            if dist <= tol and (best is None or dist < best[0]):
                best = (dist, kind, idx)
        if best is None:
            break
        _, kind, idx = best
        part = list(parts.pop(idx).coords)
        if kind == "head-head":
            coords = part[::-1] + coords[1:]
        elif kind == "head-tail":
            coords = part + coords[1:]
        elif kind == "tail-head":
            coords = coords + part[1:]
        else:
            coords = coords + part[::-1][1:]
    return LineString(coords)


def _east_of_river(line: LineString) -> Polygon:
    """把一条自西北向东南流的河线闭合成"河心线东侧"的多边形.

    做法: 河两端各接一条到远东的短线, 再沿远东经线闭合, 用 polygonize 取
    包含远东探测点的那块面. 为什么不直接 Polygon(河线 + 闭合线): 河线上有
    河曲/牛轭, 直接闭合可能自相交; polygonize 会把线图切成面, 取东侧那块
    面不受河曲影响.
    """
    x0, y0 = line.coords[0]
    x1, y1 = line.coords[-1]
    far = line.bounds[2] + 5.0
    closure = [
        LineString([(x1, y1), (far, y1)]),
        LineString([(far, y1), (far, y0)]),
        LineString([(far, y0), (x0, y0)]),
    ]
    faces = [p for p in polygonize(unary_union([line, *closure])) if p.area >= 1e-3]
    probe = Point(far - 1.0, (y0 + y1) / 2.0)
    east = [p for p in faces if p.contains(probe)]
    if not east:
        raise RuntimeError("德涅斯特河河心线东侧多边形构造失败")
    return max(east, key=lambda p: p.area)


def build_dniester_river() -> tuple[LineString, int]:
    """德涅斯特河干流: main_stream 成员合并成一条中心线, 供绘图与德左裁切共用.

    为什么要换掉 Natural Earth: NE 10m 的德涅斯特河在德左一段只有 ~200 个
    顶点(平均约 1 km 一个), 与"沿河"的德左西缘放在一起会差出 0.3~1.3 km;
    填色的西缘必须与画出来的河是同一条几何, 否则又会回到"灰区和河流对不上".
    OSM 的 main_stream 有 1.1 万个顶点, 与第聂伯河同一口径.

    返回值直接交给 ``build_transnistria``: 德左面用这条线裁切, 绘制也用同一条
    线, 从数据源头保证两者重合, 而不是靠事后"填色不描边"来掩盖偏差.
    第二个返回值是关系 id, 写进派生属性里的来源句.
    """
    payload = json.loads(DNIESTER_RIVER_CACHE.read_text(encoding="utf-8"))
    relation = _single_relation(payload)
    ways = _relation_way_geometries(relation, ("main_stream",))
    if not ways:
        raise RuntimeError("OSM 德涅斯特河 relation 中没有 main_stream 成员")
    merged = linemerge(ways)
    parts = (
        [merged]
        if merged.geom_type == "LineString"
        else [g for g in getattr(merged, "geoms", []) if g.geom_type == "LineString"]
    )
    line = _bridge_line_parts(parts, DNIESTER_BRIDGE_DEG)
    line = line.simplify(RIVER_SIMPLIFY_DEG, preserve_topology=False)
    if not DNIESTER_RIVER_PATH.parent.exists():
        DNIESTER_RIVER_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_geojson(
        DNIESTER_RIVER_PATH,
        [
            feat(
                line,
                {
                    "name": "Dniester main stream (OSM)",
                    "name_zh": "德涅斯特河干流中心线",
                    "source": f"OpenStreetMap relation {relation['id']} "
                    "(waterway=river, main_stream members); ODbL 1.0",
                    "note": "仅取 main_stream; 三角洲 side_stream 不画. "
                    "德左参照面的西缘用的就是这条线.",
                    "length_km_geodesic": round(geodesic_length_km(line), 1),
                    "vertices": n_vertices(line),
                    "simplify_deg": RIVER_SIMPLIFY_DEG,
                },
            )
        ],
    )
    print(f"  德涅斯特河干流: {n_vertices(line)} 顶点, 范围 {[round(v, 2) for v in line.bounds]}")
    return line, relation["id"]


def build_transnistria(dniester_line: LineString, border_1991, dniester_rel_id: int) -> None:
    """输出德涅斯特河沿岸摩尔达维亚共和国(德左)的参照区域面.

    几何口径: OSM 的 PMR 边界面, 再按两条"图上已经画出来的线"裁切:
        - 西缘 = 德涅斯特河中心线(``dniester_line``, 与绘图共用一条几何);
        - 东缘 = 1991 年乌克兰国界(``border_1991``, 即图上红色那条线的面).
    这样填色边界就是蓝线 + 红线, 不会再与河流错位. 改前用 GADM 4.1 摩尔多瓦
    一级单元, 其西缘与河心线中位差 5.6 km,最远约 30 km, 大锯齿肉眼可见.

    为什么要裁掉河右岸: PMR 面包含 Bender(宾杰里, 河右岸)与部分右岸村庄, 直接
    填会让灰色跨过德涅斯特河; 本图只表达"河东岸那条地带". 用河心线裁切后,
    西缘就落在蓝线上.

    为什么还要与 1991 国界求差: PMR 面的东缘是 OSM 的摩尔多瓦-乌克兰国界, 与
    图上红线所用的 GADM 国界不是同一套数字化(实测中位差 ~0.35 km, 个别处
    ~0.6 km); 不求差时北端与河口的小尖角会戳出红线约 1~2 px.

    为什么把 PMR 关系里的内环一起填上: 该内环是摩尔多瓦控制的左岸村庄(杜伯萨里
    区飞地, 约 62 km²). 本图灰区只是位置参照,不区分实际控制, 改前的 GADM 单元
    同样没有挖掉它, 所以保持一条连续地带; 若以后要表达实际控制, 应保留内环.

    碎片: 交集/求差会留下小于 2 km² 的小块(实测最大 1.3 km²), 比 1 px 还小,
    丢掉; 主面约 3385 km².
    """
    payload = json.loads(TRANSNISTRIA_BOUNDARY_CACHE.read_text(encoding="utf-8"))
    relation = _single_relation(payload)
    ways = _relation_way_geometries(relation, ("outer", "inner"))
    if not ways:
        raise RuntimeError("OSM 德左边界 relation 里没有 outer/inner 成员几何")
    # polygonize 得到各闭合面再合并 = 外环面(内环被一并填满, 理由见上).
    faces = [p for p in polygonize(unary_union(ways)) if p.area >= 1e-4]
    if not faces:
        raise RuntimeError("OSM 德左边界 relation 无法闭合成面")
    region = unary_union(faces).intersection(_east_of_river(dniester_line))
    region = region.difference(border_1991).intersection(box(*TRANSNISTRIA_CLIP))
    region = unary_union(
        [
            part
            for part in (
                region.geoms if region.geom_type == "MultiPolygon" else [region]
            )
            if geodesic_area_km2(part) >= TRANSNISTRIA_MIN_AREA_KM2
        ]
    )
    write_geojson(
        TRANSNISTRIA_PATH,
        [
            feat(
                region,
                {
                    "name": "Transnistria (OSM PMR boundary, clipped to river/border)",
                    "name_zh": "德涅斯特河沿岸摩尔达维亚共和国",
                    "name_en": "Pridnestrovian Moldavian Republic",
                    "alias_zh": "德涅斯特河左岸(德左)",
                    "dejure_country": "Moldova",
                    "status": "unrecognised breakaway state; Russian military presence",
                    "source": f"OpenStreetMap relation {relation['id']} "
                    "(boundary=administrative, admin_level=3, ODbL 1.0), clipped by "
                    f"OSM Dniester main stream (relation {dniester_rel_id}) "
                    "and GADM 4.1 Ukraine 1991 border",
                    "note": "只保留德涅斯特河东岸,1991 国界以西南的地带: 西缘=OSM 河心线, "
                    "东缘=1991 国界, 因此与图上蓝河/红线严格重合. Bender(河右岸)已裁掉; "
                    "PMR 关系里的杜伯萨里区飞地内环按改前 GADM 口径一并填上, 不区分实际控制.",
                    "area_km2_geodesic": round(geodesic_area_km2(region), 1),
                    "vertices": n_vertices(region),
                },
            )
        ],
    )
    print(
        f"  德左参照面: {n_vertices(region)} 顶点, 面积 {geodesic_area_km2(region):.0f} km², "
        f"范围 {[round(v, 2) for v in region.bounds]}"
    )


# ============================
# 6. 南布格河/顿河: NE 上段 + OSM 下游段拼成一条连续中心线
# ============================
def load_ne_rivers() -> gpd.GeoDataFrame:
    """读共享缓存里的 Natural Earth 10m 河网(只读, 不联网)."""
    rivers = _read_ne_layer("ne-rivers-10m")
    if rivers is None:
        raise RuntimeError(
            "缺少 Natural Earth 10m 河网缓存, 请到数据项目 miko_gis_data 运行: "
            "python main.py download --group ukraine"
        )
    return rivers


def _ne_river_features(rivers: gpd.GeoDataFrame, name: str) -> list[tuple[int, LineString]]:
    """取某条河的全部 NE 线要素(MultiLineString 展开), 返回 (ne_id, 单条线)."""
    features: list[tuple[int, LineString]] = []
    for _, row in rivers[rivers["name_en"] == name].iterrows():
        geom = row.geometry
        parts = [geom] if geom.geom_type == "LineString" else list(getattr(geom, "geoms", []))
        for part in parts:
            if part.geom_type == "LineString" and len(part.coords) >= 2:
                features.append((int(row["ne_id"]), part))
    return features


def _unit_direction(line: LineString, t: float, window: float = 0.004) -> tuple[float, float]:
    """求线上弧长 t 处"沿距离增大方向"的单位向量; window 是取样窗口(度).

    window 取 0.004°(约 450 m): 太短会被单个顶点带偏, 太长又会把河弯平均掉;
    接缝选择只关心几公里尺度的走向, 这个窗口足够稳.
    """
    a = line.interpolate(max(0.0, t - window))
    b = line.interpolate(min(line.length, t + window))
    dx, dy = b.x - a.x, b.y - a.y
    norm = (dx * dx + dy * dy) ** 0.5
    return (dx / norm, dy / norm) if norm else (0.0, 0.0)


def _orient_to_sea(chain: LineString, ne_line: LineString) -> LineString:
    """把 OSM 下游链摆成"上游 -> 下游"方向.

    依据: 下游端伸进利曼/亚速海, 离只画到河口附近的 NE 线远; 上游端与 NE 线
    是同一条河, 距离近. OSM way 本身按水流方向画(起点在上游), 两端距离相近
    时保持原方向.
    """
    head = Point(chain.coords[0]).distance(ne_line)
    tail = Point(chain.coords[-1]).distance(ne_line)
    if tail < head:
        return LineString(list(chain.coords)[::-1])
    return chain


def _choose_seam(ne_line: LineString, osm_line: LineString):
    """在 OSM 链上游段上挑接缝: 离 NE 线近,且两条线走向一致的点.

    返回 ``(OSM 弧长比例, NE 上对应的点, 两条线的距离(度), 走向差(度))``.
    代价函数把距离和方向差归一化后平方相加; 实测两条河的最优点距离
    100~350 m,方向差 <5°, 接缝在图上就是一个普通河弯.
    """
    best = None
    for i in range(121):
        frac = RIVER_JOIN_SCAN * i / 120
        t_osm = frac * osm_line.length
        point = osm_line.interpolate(t_osm)
        t_ne = ne_line.project(point)
        near = ne_line.interpolate(t_ne)
        dist = point.distance(near)
        a = _unit_direction(ne_line, t_ne)
        b = _unit_direction(osm_line, t_osm)
        cos = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
        angle = math.degrees(math.acos(cos))
        cost = (dist / RIVER_JOIN_DIST_DEG) ** 2 + (angle / RIVER_JOIN_ANGLE_DEG) ** 2
        if best is None or cost < best[0]:
            best = (cost, frac, near, dist, angle)
    return best[1:]


def build_river_extension(spec: dict) -> None:
    """南布格河/顿河: NE 上段与 OSM 下游段在接缝处拼成一条连续中心线.

    步骤:
      1. NE 侧: 取该河"末端纬度最低"的线要素 -- 两条河在图内都往南/西南
         入海, 纬度最低的末端就是下游干流(其余要素更靠上游).
      2. OSM 侧: 从下游 bbox 的 waterway=river way 里按河名挑出主河道,
         合并(linemerge)后取最长的一段; 出现多段说明有三角洲汊道, 图上只要
         主道.
      3. 摆正方向: 把 OSM 链摆成上游 -> 下游(见 ``_orient_to_sea``).
      4. 挑接缝: 在 OSM 链上游 60% 里找"离 NE 线近 + 走向一致"的点(见
         ``_choose_seam``); 接缝以上用 NE,以下用 OSM -- 两套数据本来就
         在这附近重合, 所以看不出是拼的.
      5. 拼成一条 LineString, 简化到 ``RIVER_SIMPLIFY_DEG`` 后写 GeoJSON.
         属性里带 ``replaces_ne_id``: 绘图时据此把 NE 图层里被替换的那条
         下游要素剔除, 避免同一条河出现两条位置略有差异的线.
    """
    rivers = load_ne_rivers()
    features = _ne_river_features(rivers, spec["ne_name"])
    if not features:
        raise RuntimeError(f"NE 10m 河网里没有 {spec['ne_name']}, 无法补下游段")
    ne_id, ne_line = min(features, key=lambda item: item[1].coords[-1][1])

    cache = CATALOG.path(spec["cache_id"])
    payload = json.loads(cache.read_text(encoding="utf-8"))
    ways = []
    for element in payload["elements"]:
        if element.get("tags", {}).get("name") not in spec["osm_names"]:
            continue
        geom = _osm_way_geometry(element)
        if geom is not None:
            ways.append(geom)
    if not ways:
        raise RuntimeError(f"{spec['name_zh']}: OSM 缓存里没有同名 waterway=river")

    union = unary_union(ways)
    if union.geom_type == "LineString":
        osm_line = union
    else:
        merged = linemerge(union)
        parts = (
            [merged]
            if merged.geom_type == "LineString"
            else [g for g in getattr(merged, "geoms", []) if g.geom_type == "LineString"]
        )
        if not parts:
            raise RuntimeError(f"{spec['name_zh']}: OSM 河段无法合并")
        osm_line = max(parts, key=lambda g: g.length)
    osm_line = _orient_to_sea(osm_line, ne_line)

    frac, seam, dist, angle = _choose_seam(ne_line, osm_line)
    head = substring(ne_line, 0.0, ne_line.project(seam))
    tail = substring(osm_line, frac * osm_line.length, osm_line.length)
    coords = list(head.coords)
    if Point(coords[-1]).distance(Point(tail.coords[0])) > 1e-9:
        coords.append(tuple(tail.coords[0]))
    coords.extend(list(tail.coords)[1:])
    line = LineString(coords).simplify(RIVER_SIMPLIFY_DEG, preserve_topology=False)

    write_geojson(
        spec["out_path"],
        [
            feat(
                line,
                {
                    "name": f"{spec['ne_name']} lower reach (Natural Earth + OSM)",
                    "name_zh": spec["name_zh"],
                    "source": "Natural Earth 10m rivers_lake_centerlines (upstream, "
                    "public domain) + OpenStreetMap waterway=river (downstream, ODbL 1.0)",
                    "note": "NE 10m 在河口前收笔; 接缝以上用 NE, 以下用 OSM, "
                    "接缝点按距离/走向自动挑选.",
                    "replaces_ne_id": ne_id,
                    "length_km_geodesic": round(geodesic_length_km(line), 1),
                    "vertices": n_vertices(line),
                    "simplify_deg": RIVER_SIMPLIFY_DEG,
                },
            )
        ],
    )
    print(
        f"  接缝: OSM 上游 {frac:.0%} 处, 距 NE 线 {dist * 111000:.0f} m, "
        f"走向差 {angle:.1f}°; 合并后 {len(line.coords)} 顶点, "
        f"{geodesic_length_km(line):.0f} km"
    )


# ============================
# 7. 主流程
# ============================
# 派生需要的原始数据(config 里的数据集 id). 只列硬依赖: NE 湖泊缺失时
# build_dnieper_water 只少卡霍夫卡水库并打印警告, 不阻塞派生, 因此不在此列.
RAW_INPUT_IDS = (
    "gadm41-ukr",
    "ocha-gca-ngca",
    "ne-rivers-10m",
    "osm-dnieper-river",
    "osm-dnieper-reservoirs",
    "osm-dniester-river",
    "osm-transnistria-boundary",
    "osm-southern-bug",
    "osm-don",
)


def check_raw_inputs() -> bool:
    """派生所需的原始数据是否就位(不联网); 缺失时打印准备命令并返回 False."""
    missing = [item for item in RAW_INPUT_IDS if not CATALOG.exists(item)]
    if not missing:
        return True
    for dataset_id in missing:
        print(f"  缺失: {dataset_id}")
    print("\n原始数据不全, 请先到数据项目 miko_gis_data 运行(已存在的会自动跳过):")
    print("  python main.py download --group ukraine")
    return False


def print_summary() -> None:
    """逐个报告派生 GeoJSON 的体积/要素数: 汇总是本次全量重建的结果清单."""
    print("\n" + "=" * 60)
    print("派生文件汇总(每次运行全量重建)")
    print("=" * 60)
    for path in DERIVED_PATHS:
        if not path.is_file():
            print(f"[缺失] {path.name}")
            continue
        features = json.loads(path.read_text(encoding="utf-8")).get("features", [])
        print(
            f"[派生] {path.name}: {path.stat().st_size / 1024:.1f} KiB, {len(features)} 要素"
        )


# 本模块产出的全部派生文件(汇总与检查用).
DERIVED_PATHS = (
    OBLASTS_PATH,
    BORDER_1991_PATH,
    CRIMEA_LINE_PATH,
    OCCUPIED_2014_PATH,
    CONTACT_2014_PATH,
    CLAIMED_2022_PATH,
    TRANSNISTRIA_PATH,
    DNIEPER_RIVER_PATH,
    DNIEPER_WATER_PATH,
    DNIESTER_RIVER_PATH,
    config.SOUTHERN_BUG_GEOJSON,
    config.DON_GEOJSON,
)


def run() -> int:
    """全量重建派生 GeoJSON 并打印汇总; 返回 0=成功, 1=原始数据不全."""
    if not check_raw_inputs():
        return 1
    OBLASTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("\n" + "=" * 60)
    print("派生乌克兰图种数据(每次运行都全量重建; 原始数据来自数据仓 miko_gis_data)")
    print("=" * 60)

    print("\n加工行政区与 1991 年边界")
    gdf, border_1991 = build_oblasts(load_gadm())
    print("\n加工 2014 年克里米亚控制线")
    build_crimea_line(gdf)
    print("\n加工 2014 年顿巴斯控制区与接触线")
    build_donbas_2014()
    print("\n加工 2022 年俄方宣称四州边界")
    build_claimed_2022(gdf)
    print("\n加工德涅斯特河干流中心线")
    dniester_line, dniester_rel_id = build_dniester_river()
    print("\n加工德左参照区域面")
    build_transnistria(dniester_line, border_1991, dniester_rel_id)
    print("\n加工第聂伯河干流中心线")
    build_dnieper_river()
    print("\n加工第聂伯河梯级水库水面")
    build_dnieper_water()
    for extension in RIVER_EXTENSIONS:
        print(f"\n加工{extension['name_zh']}")
        build_river_extension(extension)

    print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python Ukraine/main.py prepare")
