#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# download_data.py
# 准备乌克兰全图所需的全部本地数据:
#   1) NOAA ETOPO 2022 乌克兰区域高程子集(NetCDF);
#   2) Natural Earth 10m 国家边界(邻国底色/国界/标注用);
#   3) GADM 4.1 乌克兰一级行政区(州/克里米亚/塞瓦斯托波尔, 法理口径);
#   4) OCHA HDX 2021 HNO GCA/NGCA 分区(顿巴斯接触线与分离武装控制区);
#   5) OpenStreetMap 第聂伯河干流与梯级水库(Overpass API, 精细水系);
#   6) OpenStreetMap 南布格河/顿河下游补段(NE 10m 在河口前收笔, 见下);
# 再把它们加工成绘图脚本直接读取的 GeoJSON:
#   1991 年国际承认边界、各州边界、2014 年克里米亚陆上控制线、
#   2014 年顿巴斯控制区/接触线、2022 年俄方宣称的四州全境、
#   第聂伯河干流中心线与梯级水库水面、南布格河/顿河中心线(NE + OSM 拼接).
# 所有下载都是"文件已存在就跳过", 重复执行不会重新联网.
# 运行: python Ukraine/download_data.py
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Prepare all local data for the Ukraine overview map.

为什么用这些数据源:
    1. 地形: NOAA NCEI ETOPO 2022(15 弧秒全球地形/水深), 与项目里缅甸、
       苏联图一致; 这里向 NOAA ERDDAP 请求已经裁剪/重采样好的区域子集,
       只下一个文件, 绘图时完全离线.
    2. 1991 年国际承认边界: 用 GADM 4.1 的乌克兰一级行政区合并得到.
       选择 GADM 而不是 Natural Earth 的原因见下面 ``load_gadm`` 的注释:
       Natural Earth 的 admin_0 把克里米亚划给俄罗斯(事实控制口径), 无法
       表达"1991 年边界含克里米亚"这一法理口径; GADM 4.1 的 UKR 单元把
       克里米亚和塞瓦斯托波尔都算作乌克兰, 合并后即得法理国界.
    3. 2014 年实际控制线:
       - 克里米亚: 其与赫尔松州的行政边界就是 2014 年 3 月以后的陆上
         实际控制线(彼列科普地峡/锡瓦什湖一带);
       - 顿巴斯: OCHA/HDX 的 2021 HNO GCA/NGCA 分区给出了政府控制区
         (GCA)与非政府控制区(NGCA)两套面; 两者之间的分界线即接触线.
         这条线是明斯克协议(2015-02)之后的线, 2015-2022 基本稳定, 作为
         "2014 年接触线"的近似(项目需求明确允许大致范围).
    4. 2022 年边界: 俄方 2022-09 单方面宣称赫尔松州、扎波罗热州、顿涅茨克
       人民共和国、卢甘斯克人民共和国"全境", 实际并未全部控制; 因此这里
       只取四州完整的行政区边界(GADM 州界), 明确标注为"宣称"而非控制线.
    5. 第聂伯河: Natural Earth 10m 的河道中心线只有 ~600 个顶点, 干流在
       乌克兰境内几乎全是梯级水库, 叠在 1:330 万的图上是一条几乎看不见的
       细线, 位置也与实际河道相差中位数约 0.8 km(个别水库段可差 10 km 以上).
       改用 OSM 的 waterway=river relation: 干流在乌克兰段有上万个顶点,
       位置精度到几十米; 五个梯级水库另有独立的 natural=water 多边形, 按
       实际水面填充, 这才看得出"第聂伯河在乌克兰是一串水库".
       卡霍夫卡水库 2023-06 溃坝后被放空, OSM 已删除其水面多边形; 本图讲的
       是 2022 年, 所以这一座用 Natural Earth 10m 的溃坝前水库面补上.
    6. 南布格河/顿河下游: Natural Earth 10m 河网在这两条河入海前提前收笔 ——
       南布格河止于 (31.75, 47.26), 河口(米科拉伊夫一带的利曼)以上约 35 km;
       顿河止于 (39.38, 47.11), 还在顿河三角洲里, 离亚速海约 10 km. 图上表现
       为"河线断了": 南布格河只剩一串 ETOPO 水面像元, 顿河在三角洲里收笔.
       这两处改用 OSM waterway=river 的下游一小段补上, 并把 NE 上段与 OSM 下段
       在两条线的交点附近拼成一条连续中心线输出(做法见
       ``build_river_extension``).

输出(都在 ``Ukraine/data/`` 下, 已在 .gitignore 里):
    ETOPO_2022_v1_15s_ukraine_stride2.nc      ETOPO 高程
    ne_10m_admin_0_countries/                 NE 10m 国界
    gadm41_UKR/gadm41_UKR_1.json              GADM 乌克兰一级行政区
    ocha_gca_ngca/                            OCHA GCA/NGCA shapefile
    ukraine_oblasts.geojson                   27 个一级行政区(含克里米亚/塞瓦斯托波尔)
    ukraine_1991.geojson                      1991 年国际承认边界(含克里米亚)
    crimea_2014_line.geojson                  2014 年克里米亚陆上控制线
    occupied_2014.geojson                     2014 年顿巴斯分离武装控制区(顿/卢两州)
    contact_line_2014.geojson                 2014 年顿巴斯接触线(近似)
    claimed_2022.geojson                      2022 年俄方宣称的四州全境(面)
    dnieper_river_osm.geojson                 第聂伯河干流中心线(OSM)
    dnieper_water_osm.geojson                 第聂伯河梯级水库水面(OSM + NE 卡霍夫卡)
    southern_bug_river_osm.geojson            南布格河中心线(NE 上段 + OSM 下段)
    don_river_osm.geojson                     顿河中心线(NE 上段 + OSM 下段)

数据许可: OpenStreetMap 贡献者, ODbL 1.0.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
from pyproj import Geod
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import linemerge, polygonize, substring, unary_union
from shapely.validation import make_valid

# ============================
# 路径与数据源
# ============================
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

# 高程子集范围: 画框是 [21.0, 41.5]°E / [43.2, 53.4]°N, 但兰勃特等角圆锥投影
# 的矩形画框四角会向外张开, 反算到经纬度约为 18.8~43.8°E / 42.7~53.25°N.
# 这里四周再留 0.3° 余量, 避免画框四角露出没有高程数据的空白.
ETOPO_REGION = {"name": "ukraine", "stride": 2, "lon": (18.5, 44.0), "lat": (42.4, 53.5)}
ETOPO_PATH = DATA_DIR / f"ETOPO_2022_v1_15s_ukraine_stride{ETOPO_REGION['stride']}.nc"

ERDDAP_BASE = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_15s.nc"
# Natural Earth 10m 国家边界(与 Myanmar/USSR 下载的是同一份).
NE_ADMIN0_URL = (
    "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip"
)
NE_ADMIN0_DIR = DATA_DIR / "ne_10m_admin_0_countries"
NE_ADMIN0_ZIP = DATA_DIR / "ne_10m_admin_0_countries.zip"
# GADM 4.1 乌克兰一级行政区(法理口径, 含克里米亚与塞瓦斯托波尔).
GADM_DIR = DATA_DIR / "gadm41_UKR"
GADM_JSON = GADM_DIR / "gadm41_UKR_1.json"
GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_UKR_1.json"
# OCHA HDX: Ukraine - Affected areas (Donetska and Luhanska oblasts),
# 2021 HNO 的 GCA/NGCA 面. 资源 id 固定, 换版本时只需改这一行.
OCHA_DIR = DATA_DIR / "ocha_gca_ngca"
OCHA_ZIP = DATA_DIR / "2021-hno-gca_ngca.zip"
OCHA_URL = (
    "https://data.humdata.org/dataset/0a24205d-084c-4ef9-9d53-9349bacbde1e/"
    "resource/86861957-a064-4427-b93a-2277738f0caa/download/2021-hno-gca_ngca.zip"
)
USER_AGENT = "CartopyFile-UkraineMap/1.0 (cartopy map project)"

# 派生 GeoJSON 的输出路径.
OBLASTS_PATH = DATA_DIR / "ukraine_oblasts.geojson"
BORDER_1991_PATH = DATA_DIR / "ukraine_1991.geojson"
CRIMEA_LINE_PATH = DATA_DIR / "crimea_2014_line.geojson"
OCCUPIED_2014_PATH = DATA_DIR / "occupied_2014.geojson"
CONTACT_2014_PATH = DATA_DIR / "contact_line_2014.geojson"
CLAIMED_2022_PATH = DATA_DIR / "claimed_2022.geojson"

# ---- 第聂伯河: OSM 精细水系(Overpass 原始 JSON 缓存 + 派生 GeoJSON) ----
# 公共 Overpass 实例高峰期限流, 请求会排队/返回 502, 所以用"失败退避重试".
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_USER_AGENT = "CartopyFile-UkraineMap/1.0 (cartopy map project)"
# 第聂伯河干流 relation(waterway=river): 189 段 main_stream 成员 way 首尾相接.
DNIEPER_RIVER_RELATION = 2086905
# 第聂伯梯级水库(从上游到下游): OSM 里都是 natural=water 的 multipolygon
# relation. 只取 outer 成员: 水库里的岛屿(inner)在 1:330 万图上不足 1 px.
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

DNIEPER_RIVER_CACHE = DATA_DIR / "osm_dnieper_river.json"
DNIEPER_WATER_CACHE = DATA_DIR / "osm_dnieper_reservoirs.json"
DNIEPER_RIVER_PATH = DATA_DIR / "dnieper_river_osm.geojson"
DNIEPER_WATER_PATH = DATA_DIR / "dnieper_water_osm.geojson"

# ---- 南布格河/顿河: NE 10m 在河口前收笔, 用 OSM 补下游段 ----
# NE 10m 缓存的收笔位置: 南布格河 (31.749, 47.259), 顿河 (39.378, 47.111).
# 两条河在图内都向南/西南入海, 所以"下游要素"= 末端纬度最低的那条
# (见 build_river_extension). Overpass 的 bbox 用 (south, west, north, east),
# 只覆盖 NE 收笔点到河口的一小段; 跨出 bbox 的 way 仍带完整几何, 足够接上.
RIVER_EXTENSIONS: tuple[dict, ...] = (
    {
        "key": "southern_bug",
        "ne_name": "Southern Bug",
        # 乌克兰段在 OSM 里是乌克兰语名; 俄语/英语名一并收, 防止个别 way
        # 用了别的语言标注而漏掉.
        "osm_names": ("Південний Буг", "Южный Буг", "Southern Bug"),
        "bbox": (46.85, 31.55, 47.40, 32.10),
        "name_zh": "南布格河下游补段",
        "cache": DATA_DIR / "osm_southern_bug_lower.json",
        "path": DATA_DIR / "southern_bug_river_osm.geojson",
    },
    {
        "key": "don",
        "ne_name": "Don",
        # 顿河下游在俄罗斯境内, OSM 用俄语名; 三角洲的汊道各有名字, 这里只要
        # 主河道 "Дон" 本身(实测三角洲里同名 way 只有一条, 直通亚速海).
        "osm_names": ("Дон",),
        "bbox": (47.00, 39.05, 47.25, 39.60),
        "name_zh": "顿河下游补段",
        "cache": DATA_DIR / "osm_don_lower.json",
        "path": DATA_DIR / "don_river_osm.geojson",
    },
)
# 接缝点选择: 在 OSM 下游链的上游段上扫描, 取"离 NE 线近 + 走向一致"的点.
# 为什么不直接首尾相接: 两套数据对同一条河的描绘相差 0.5~2 km, 且 NE 在河口
# 附近简化出了一些不自然的弯; 直接接会留下台阶或硬折角. 按距离+方向挑接缝
# 后, 实测两条河在接缝处的走向差都不到 5°, 图上就是一个普通河弯.
RIVER_JOIN_SCAN = 0.6          # 只在前 60% 弧长里找接缝, 保证下游段仍在
RIVER_JOIN_DIST_DEG = 0.01     # 距离权重: 0.01°(约 1.1 km) 记 1 个单位
RIVER_JOIN_ANGLE_DEG = 30.0    # 方向权重: 30° 记 1 个单位

GEOD = Geod(ellps="WGS84")

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
# 下载与解压
# ============================
def _erddap_url(stride: int, lon_range: tuple[float, float], lat_range: tuple[float, float]) -> str:
    """拼 ETOPO 子集请求 URL; ERDDAP 的 z[lat][lon] 顺序, 经纬度用坐标值写."""
    min_lon, max_lon = lon_range
    min_lat, max_lat = lat_range
    query = (
        f"z%5B({min_lat}):{stride}:({max_lat})%5D"
        f"%5B({min_lon}):{stride}:({max_lon})%5D"
    )
    return f"{ERDDAP_BASE}?{query}"


def is_netcdf_file(path: Path) -> bool:
    """检查文件头, 避免把 ERDDAP 的错误 HTML 当成 NetCDF 缓存下来."""
    with open(path, "rb") as fh:
        magic = fh.read(4)
    return magic.startswith(b"CDF") or magic.startswith(b"\x89HDF")


def download(
    url: str,
    dest: Path,
    description: str,
    *,
    force: bool = False,
    expect_netcdf: bool = False,
) -> None:
    """带续传与失败重试的下载; 目标文件已存在且非空时直接跳过."""
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"已存在, 跳过 {description}: {dest}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    if part.exists() and not force:
        print(f"发现未完成的下载, 续传: {part}")
    elif part.exists():
        part.unlink()

    for attempt in range(1, 4):
        downloaded = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                # 服务器不支持 Range 时会返回 200 + 完整内容, 此时必须清空
                # 已有的 .part 从头写, 否则续传会得到损坏文件.
                if downloaded and response.status == 200:
                    downloaded = 0
                    part.unlink(missing_ok=True)
                mode = "ab" if downloaded else "wb"
                total = response.headers.get("Content-Length")
                total = int(total) if total else None
                last_report = time.time()
                written = downloaded
                with open(part, mode) as out:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        written += len(chunk)
                        if time.time() - last_report >= 3:
                            last_report = time.time()
                            if total:
                                pct = written / total * 100
                                print(f"  {description}: {written/1048576:6.1f} / {total/1048576:6.1f} MiB ({pct:5.1f}%)")
                            else:
                                print(f"  {description}: {written/1048576:6.1f} MiB")
            if expect_netcdf and not is_netcdf_file(part):
                part.unlink(missing_ok=True)
                raise RuntimeError(f"下载内容不是 NetCDF(可能是 ERDDAP 错误页): {url}")
            part.replace(dest)
            print(f"完成: {dest} ({dest.stat().st_size/1048576:.1f} MiB)")
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  下载失败 ({attempt}/3): {exc}")
            if attempt == 3:
                raise
            time.sleep(5 * attempt)


def extract_zip(zip_path: Path, out_dir: Path, *, skip_if_shp: bool = True) -> Path:
    """把 zip 解压到 out_dir; 已有 .shp 时不重复解压. 返回找到的 .shp."""
    shapefiles = sorted(out_dir.glob("*.shp")) if out_dir.exists() else []
    if shapefiles and skip_if_shp:
        print(f"已存在, 跳过解压: {shapefiles[0]}")
        return shapefiles[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(out_dir)
    shapefiles = sorted(out_dir.rglob("*.shp"))
    if not shapefiles:
        raise RuntimeError(f"压缩包中没有 shapefile: {zip_path}")
    print(f"已解压: {shapefiles[0]}")
    return shapefiles[0]


# ============================
# 几何工具
# ============================
def round_coords(obj, nd: int = 6):
    """递归把坐标四舍五入到 nd 位小数, 控制 GeoJSON 体积(1e-6° ≈ 0.11 m)."""
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), nd) for v in obj]
        return [round_coords(v, nd) for v in obj]
    return obj


def geod_area_km2(geom) -> float:
    """用 WGS84 椭球算测地面积(km²); 比在经纬度上直接 area 可靠."""
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    return sum(abs(GEOD.geometry_area_perimeter(p)[0]) for p in polys) / 1e6


def geod_length_km(geom) -> float:
    """测地长度(km), 用于核对接触线长度是否在合理量级.

    pyproj 的 ``Geod.geometry_length`` 返回米, 要 /1000; 这里原先误写成
    /1e6(米->千公里), 接触线长度元数据小了 1000 倍, 2026-10 修正.
    """
    lines = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
    return sum(abs(GEOD.geometry_length(line)) for line in lines) / 1000


def n_vertices(geom) -> int:
    """几何顶点数, 用于确认简化后没有丢掉细节."""
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        return sum(
            len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors) for p in polys
        )
    if geom.geom_type in ("LineString", "MultiLineString"):
        lines = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
        return sum(len(line.coords) for line in lines)
    return 0


def valid(geom):
    """GADM/OCHA 数据里偶有自相交, 统一 make_valid 后再写."""
    return geom if geom.is_valid else make_valid(geom)


def drop_small_holes(geom, min_hole_area: float = 1e-4):
    """删掉面积小于阈值的内部环(单位: 平方度).

    为什么需要: GADM 相邻州/克里米亚单元在拼接处会留下针状小孔(实测面积都
    < 2e-6 平方度, 但长度可达 0.03°, 约 3 km). 画成边界线时这些孔会变成
    地图上一串黑色小椭圆, 像脏点; 真实的内部环(基辅市被基辅州包围, 面积
    ~0.1 平方度)远大于阈值, 会保留.
    """
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


def write_fc(path: Path, features: list[dict]) -> None:
    """写 RFC 7946 GeoJSON(坐标统一 6 位小数), 方便其他脚本直接读."""
    fc = {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"写入: {path.name} ({path.stat().st_size/1024:.1f} KiB, {len(features)} 要素)")


def feat(geom, props: dict) -> dict:
    """把 shapely 几何包成 GeoJSON Feature, 坐标做定点舍入."""
    geom = drop_small_holes(valid(geom))
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {
            "type": geom.geom_type,
            "coordinates": round_coords(list(mapping(geom)["coordinates"])),
        },
    }


def load_gadm() -> gpd.GeoDataFrame:
    """读 GADM 乌克兰一级行政区.

    为什么用 GADM 4.1: Natural Earth 的 admin_0 把克里米亚划给俄罗斯
    (事实控制口径). 本图要画"1991 年国际承认边界", 必须让克里米亚和
    塞瓦斯托波尔留在乌克兰内, 因此用 GADM 的法理口径(UKR 下含 Crimea
    与 Sevastopol' 两个单元), 与 Myanmar/prepare_admin_data.py 的数据源一致.
    GADM 有一行 NAME_1 为 "?" 的约 170 km² 碎块(基辅东郊), 不参与州界
    展示, 但保留在 1991 年国界合并里, 保证国界无缺口.
    """
    gdf = gpd.read_file(GADM_JSON)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs("EPSG:4326")


# ============================
# 1. 下载原始数据
# ============================
def fetch_etopo(force: bool) -> None:
    url = _erddap_url(ETOPO_REGION["stride"], ETOPO_REGION["lon"], ETOPO_REGION["lat"])
    print(f"下载 ETOPO 2022 乌克兰区域高程 (stride={ETOPO_REGION['stride']}, 约 30 弧秒)")
    print(f"  {url}")
    download(url, ETOPO_PATH, "ETOPO 高程", force=force, expect_netcdf=True)


def fetch_admin0(force: bool) -> None:
    print("下载 Natural Earth 10m 国家边界(邻国底色/国界)")
    # 仓库里可能已经有解压好的 shapefile(例如从 USSR/data 复制过来的);
    # 只要 .shp 在就跳过, 不必为了缺少 zip 再下一次 9 MB.
    if not force and sorted(NE_ADMIN0_DIR.glob("*.shp")):
        print(f"已存在, 跳过: {sorted(NE_ADMIN0_DIR.glob('*.shp'))[0]}")
        return
    download(NE_ADMIN0_URL, NE_ADMIN0_ZIP, "Natural Earth 国界", force=force)
    extract_zip(NE_ADMIN0_ZIP, NE_ADMIN0_DIR)


def fetch_gadm(force: bool) -> None:
    print("下载 GADM 4.1 乌克兰一级行政区")
    if not force and GADM_JSON.exists() and GADM_JSON.stat().st_size > 0:
        print(f"已存在, 跳过: {GADM_JSON}")
        return
    download(GADM_URL, GADM_JSON, "GADM 乌克兰一级行政区", force=force)


def fetch_ocha(force: bool) -> None:
    print("下载 OCHA/HDX 2021 HNO 顿巴斯 GCA/NGCA 分区")
    download(OCHA_URL, OCHA_ZIP, "OCHA GCA/NGCA", force=force)
    extract_zip(OCHA_ZIP, OCHA_DIR)


def overpass_query(query: str, dest: Path, description: str, *, force: bool = False) -> None:
    """执行一条 Overpass QL 查询, 把原始 JSON 缓存到 dest(已存在则跳过).

    为什么不在绘图时联网: 渲染应该只读本地文件; 这里下载一次, 之后
    build_dnieper_* 每次都从这份 JSON 重建派生 GeoJSON.
    为什么要退避重试: 公共实例按请求排队, 高峰时会直接 502 或长时间排队;
    同一条查询换时间重试比让整个脚本失败更省事(实测一次成功约 30~60 s).
    """
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"已存在, 跳过 {description}: {dest.name}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    body = urllib.parse.urlencode({"data": query}).encode()
    last_error: Exception | None = None
    for attempt in range(1, 6):
        request = urllib.request.Request(
            OVERPASS_URL, data=body, headers={"User-Agent": OVERPASS_USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                payload = response.read()
            data = json.loads(payload)
            if "elements" not in data:
                raise RuntimeError(f"Overpass 返回异常: {payload[:200]!r}")
            part = dest.with_name(dest.name + ".part")
            part.write_bytes(payload)
            part.replace(dest)
            print(f"完成: {dest.name} ({dest.stat().st_size/1048576:.1f} MiB, {len(data['elements'])} 元素)")
            return
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            last_error = exc
            print(f"  Overpass 失败 ({attempt}/5): {exc}")
            time.sleep(10 * attempt)
    raise RuntimeError(f"Overpass 下载失败: {description}: {last_error}")


def fetch_dnieper_osm(force: bool) -> None:
    """下载第聂伯河干流 relation 与五个梯级水库的外环 way."""
    print("下载 OpenStreetMap 第聂伯河干流与梯级水库 (Overpass)")
    overpass_query(
        f"[out:json][timeout:300];rel({DNIEPER_RIVER_RELATION});out geom;",
        DNIEPER_RIVER_CACHE,
        "第聂伯河干流",
        force=force,
    )
    # 只取 outer 成员: inner 是水库里的岛, 数量(基辅水库 520 个 inner way)
    # 和体积都远大于 outer, 在 1:330 万图上却看不见, 没必要下载.
    rel_ids = ",".join(str(rel_id) for rel_id in DNIEPER_RESERVOIRS)
    overpass_query(
        f'[out:json][timeout:300];rel(id:{rel_ids})->.rels;way(r.rels:"outer");out geom;',
        DNIEPER_WATER_CACHE,
        "第聂伯河梯级水库",
        force=force,
    )


def fetch_river_extensions(force: bool) -> None:
    """下载南布格河/顿河下游的 OSM waterway=river way(Overpass, 小 bbox).

    只取下游一小块: 上段已经由 NE 10m 画, 这里只补 NE 提前收笔的那一段.
    不按河名过滤(在 Python 里按 ``osm_names`` 过滤): 同一段河在 OSM 里可能
    用不同语言/拼写标注, bbox 又很小, 整块下载只多几百 KB, 换来的鲁棒性比
    省那点流量值.
    """
    print("下载 OpenStreetMap 南布格河/顿河下游 (Overpass)")
    for spec in RIVER_EXTENSIONS:
        south, west, north, east = spec["bbox"]
        overpass_query(
            f'[out:json][timeout:120];way["waterway"="river"]'
            f"({south},{west},{north},{east});out geom;",
            spec["cache"],
            spec["name_zh"],
            force=force,
        )


# ============================
# 2. 派生边界数据
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
        geom = valid(row.geometry)
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
    write_fc(OBLASTS_PATH, feats)

    # 1991 年边界 = 全部 GADM 一级单元(含 '?' 碎块)合并; 保留克里米亚与
    # 塞瓦斯托波尔, 因为 GADM 是法理口径.
    border_1991 = unary_union([valid(g) for g in gdf.geometry])
    write_fc(
        BORDER_1991_PATH,
        [
            feat(
                border_1991,
                {
                    "name": "Ukraine 1991 border (internationally recognised)",
                    "name_zh": "1991 年乌克兰国际承认边界(含克里米亚)",
                    "note": "苏联解体时乌克兰的国界; 含克里米亚自治共和国与塞瓦斯托波尔.",
                    "source": "GADM 4.1 gadm41_UKR_1.json dissolved (de jure)",
                    "area_km2_geodesic": round(geod_area_km2(border_1991), 1),
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
        [valid(g) for g in gdf[gdf["NAME_1"].isin(["Crimea", "Sevastopol'"])].geometry]
    )
    kherson = valid(gdf[gdf["NAME_1"] == "Kherson"].geometry.iloc[0])
    shared = crimea.boundary.intersection(kherson.buffer(0.005))
    line = linemerge(shared) if shared.geom_type != "LineString" else shared
    parts = [p for p in (line.geoms if hasattr(line, "geoms") else [line]) if p.geom_type == "LineString"]
    # 0.001° ≈ 110 m, 去掉数字化噪音; 共享边界本身不长, 保留全部主要段.
    parts = [p.simplify(0.001, preserve_topology=False) for p in parts if p.length > 0.005]
    line = unary_union(parts)
    write_fc(
        CRIMEA_LINE_PATH,
        [
            feat(
                line,
                {
                    "name": "Crimea de facto control line (land, 2014-)",
                    "name_zh": "2014 年克里米亚陆上实际控制线",
                    "note": "克里米亚与赫尔松州的行政边界; 海上部分未画.",
                    "source": "GADM 4.1 Crimea + Sevastopol' vs Kherson shared boundary",
                    "length_km_geodesic": round(geod_length_km(line), 1),
                },
            )
        ],
    )


def build_donbas_2014() -> None:
    """2014 年顿巴斯控制区与接触线, 基于 OCHA GCA/NGCA 分区(2021 HNO).

    处理步骤:
      1. 读 GCA/NGCA 四个面(顿涅茨克/卢甘斯克各一个 GCA、一个 NGCA);
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
    gca_ngca = gpd.read_file(next(OCHA_DIR.glob("*.shp"))).to_crs("EPSG:4326")
    status_col = "GCA or NGC"  # 注意 HDX 原始字段名就是这个拼写
    ngca = gca_ngca[gca_ngca[status_col] == "NGCA"]
    gca = gca_ngca[gca_ngca[status_col] == "GCA"]

    # 3.1 控制区: 按州分别输出, 图上可以分别标注"顿涅茨克人民共和国/
    # 卢甘斯克人民共和国"的实际控制范围.
    occ_feats = []
    for _, row in ngca.iterrows():
        geom = valid(row.geometry).simplify(0.0003, preserve_topology=True)
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
                    "area_km2_geodesic": round(geod_area_km2(geom), 1),
                },
            )
        )
    occupied = unary_union([valid(r.geometry) for _, r in ngca.iterrows()])
    occ_feats.append(
        feat(
            occupied,
            {
                "name": "NGCA union, Donetsk + Luhansk",
                "name_zh": "顿巴斯分离武装控制区合计",
                "approx": True,
                "area_km2_geodesic": round(geod_area_km2(occupied), 1),
            },
        )
    )
    write_fc(OCCUPIED_2014_PATH, occ_feats)

    # 3.2 接触线.
    band = unary_union([valid(g) for g in gca.geometry]).buffer(0.0012)
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
    write_fc(
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
                    "length_km_geodesic": round(geod_length_km(contact), 1),
                    "uncertainty": "positional error ~1-2 km; stands in for end-2014 contact line",
                },
            )
        ],
    )


def build_claimed_2022(gdf: gpd.GeoDataFrame) -> None:
    """2022 年俄方宣称的四州全境: 取四州完整州界(面), 面本身不填色, 只画边界.

    为什么要强调"宣称": 俄方 2022-09-30 单方面宣称并入赫尔松州、扎波罗热州、
    顿涅茨克人民共和国、卢甘斯克人民共和国全境, 但其中相当一部分(如赫尔松市、
    扎波罗热市)从未被俄军控制; 所以本图不把四州整个涂色, 只用紫色点划线
    画其法理州界, 并在图例/注记里写明"单方面宣称, 非实际控制线".
    """
    feats = []
    for gadm_name, name_zh in CLAIMED_2022_UNITS:
        row = gdf[gdf["NAME_1"] == gadm_name].iloc[0]
        geom = valid(row.geometry)
        feats.append(
            feat(
                geom,
                {
                    "name": f"{gadm_name} oblast (claimed in full)",
                    "name_zh": name_zh,
                    "claim": "Russia, 2022-09-30, full oblast territory",
                    "approx_claim": True,
                    "source": "GADM 4.1 admin-1 boundary (full oblast, de jure)",
                    "area_km2_geodesic": round(geod_area_km2(geom), 1),
                },
            )
        )
    write_fc(CLAIMED_2022_PATH, feats)


# ============================
# 3. 第聂伯河: 从 OSM 原始 JSON 派生绘图用 GeoJSON
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
    relation = payload["elements"][0]
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
    write_fc(
        DNIEPER_RIVER_PATH,
        [
            feat(
                line,
                {
                    "name": "Dnieper main stream (OSM)",
                    "name_zh": "第聂伯河干流中心线",
                    "source": f"OpenStreetMap relation {DNIEPER_RIVER_RELATION} "
                    "(waterway=river, main_stream members); ODbL 1.0",
                    "note": "仅取 main_stream; 三角洲 side_stream 与水库内的中心线不单独画.",
                    "length_km_geodesic": round(geod_length_km(line), 1),
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
    try:
        from cartopy_file.data import configure_cartopy, natural_earth_paths
    except ImportError:
        print("警告: 无法导入 cartopy_file, 卡霍夫卡水库将不画(其他四座仍画)")
        return None
    configure_cartopy()
    path, _ = natural_earth_paths("10m", "physical", "lakes")
    if path is None:
        print("警告: 缺少 Natural Earth 10m 湖泊缓存, 卡霍夫卡水库将不画")
        return None
    lakes = gpd.read_file(path)
    row = lakes[lakes["name_en"] == KAKHOVKA_NE_NAME]
    if row.empty:
        print(f"警告: NE 10m 湖泊里没有 {KAKHOVKA_NE_NAME}, 卡霍夫卡水库将不画")
        return None
    return valid(row.geometry.iloc[0])


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
        polygons.append(valid(kakhovka).simplify(WATER_SIMPLIFY_DEG, preserve_topology=True))
        sources.append("Natural Earth 10m lakes (Kakhovka Reservoir, pre-2023)")

    water = unary_union(polygons).intersection(box(*DNIEPER_CLIP))
    write_fc(
        DNIEPER_WATER_PATH,
        [
            feat(
                water,
                {
                    "name": "Dnieper cascade reservoirs (OSM)",
                    "name_zh": "第聂伯河梯级水库水面",
                    "source": "; ".join(sources) + "; ODbL 1.0",
                    "note": "只取 outer 环; 水库岛屿(inner)在图上小于 1 px, 未画.",
                    "area_km2_geodesic": round(geod_area_km2(water), 1),
                    "vertices": n_vertices(water),
                    "simplify_deg": WATER_SIMPLIFY_DEG,
                },
            )
        ],
    )


# ============================
# 3b. 南布格河/顿河: NE 上段 + OSM 下游段拼成一条连续中心线
# ============================
def load_ne_rivers() -> gpd.GeoDataFrame:
    """读共享缓存里的 Natural Earth 10m 河网(只读, 不联网)."""
    try:
        from cartopy_file.data import configure_cartopy, natural_earth_paths
    except ImportError as exc:
        raise RuntimeError("无法导入 cartopy_file, 请先 `uv pip install -e .`") from exc
    configure_cartopy()
    path, _ = natural_earth_paths("10m", "physical", "rivers_lake_centerlines")
    if path is None:
        raise RuntimeError("缺少 Natural Earth 10m 河网缓存, 请先运行: python download_data.py")
    return gpd.read_file(path)


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
    """在 OSM 链上游段上挑接缝: 离 NE 线近、且两条线走向一致的点.

    返回 ``(OSM 弧长比例, NE 上对应的点, 两条线的距离(度), 走向差(度))``.
    代价函数把距离和方向差归一化后平方相加; 实测两条河的最优点距离
    100~350 m、方向差 <5°, 接缝在图上就是一个普通河弯.
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
      1. NE 侧: 取该河"末端纬度最低"的线要素 —— 两条河在图内都往南/西南
         入海, 纬度最低的末端就是下游干流(其余要素更靠上游).
      2. OSM 侧: 从下游 bbox 的 waterway=river way 里按河名挑出主河道,
         合并(linemerge)后取最长的一段; 出现多段说明有三角洲汊道, 图上只要
         主道.
      3. 摆正方向: 把 OSM 链摆成上游 -> 下游(见 ``_orient_to_sea``).
      4. 挑接缝: 在 OSM 链上游 60% 里找"离 NE 线近 + 走向一致"的点(见
         ``_choose_seam``); 接缝以上用 NE、以下用 OSM —— 两套数据本来就
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

    payload = json.loads(spec["cache"].read_text(encoding="utf-8"))
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

    write_fc(
        spec["path"],
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
                    "length_km_geodesic": round(geod_length_km(line), 1),
                    "vertices": n_vertices(line),
                    "simplify_deg": RIVER_SIMPLIFY_DEG,
                },
            )
        ],
    )
    print(
        f"  接缝: OSM 上游 {frac:.0%} 处, 距 NE 线 {dist * 111000:.0f} m, "
        f"走向差 {angle:.1f}°; 合并后 {len(line.coords)} 顶点, "
        f"{geod_length_km(line):.0f} km"
    )


# ============================
# 4. 检查与主流程
# ============================
def check_outputs(verbose: bool = True) -> int:
    """只检查、不联网: 返回缺失项数量(0 表示可以离线出图)."""
    required = [
        ETOPO_PATH,
        NE_ADMIN0_DIR / "ne_10m_admin_0_countries.shp",
        GADM_JSON,
        OCHA_DIR / "2021 HNO GCA_NGCA.shp",
        OBLASTS_PATH,
        BORDER_1991_PATH,
        CRIMEA_LINE_PATH,
        OCCUPIED_2014_PATH,
        CONTACT_2014_PATH,
        CLAIMED_2022_PATH,
        DNIEPER_RIVER_PATH,
        DNIEPER_WATER_PATH,
        *[spec["path"] for spec in RIVER_EXTENSIONS],
    ]
    missing = 0
    for path in required:
        if path.exists():
            if verbose:
                print(f"  [已存在] {path.relative_to(ROOT)}")
        else:
            missing += 1
            if verbose:
                print(f"  [缺失]   {path.relative_to(ROOT)}")
    if verbose:
        if missing:
            print(f"\n共 {missing} 项缺失, 请运行: python Ukraine/download_data.py")
        else:
            print("\n全部数据已就位, 可以运行: python Ukraine/ukraine.py")
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只检查数据是否齐全, 不联网")
    parser.add_argument("--force", action="store_true", help="强制重新下载原始数据(派生文件总是重建)")
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check_outputs(verbose=True) == 0 else 1)

    fetch_etopo(force=args.force)
    fetch_admin0(force=args.force)
    fetch_gadm(force=args.force)
    fetch_ocha(force=args.force)
    fetch_dnieper_osm(force=args.force)
    fetch_river_extensions(force=args.force)

    print("\n加工行政区与 1991 年边界")
    gdf, border_1991 = build_oblasts(load_gadm())
    print("\n加工 2014 年克里米亚控制线")
    build_crimea_line(gdf)
    print("\n加工 2014 年顿巴斯控制区与接触线")
    build_donbas_2014()
    print("\n加工 2022 年俄方宣称四州边界")
    build_claimed_2022(gdf)
    print("\n加工第聂伯河干流中心线")
    build_dnieper_river()
    print("\n加工第聂伯河梯级水库水面")
    build_dnieper_water()
    for spec in RIVER_EXTENSIONS:
        print(f"\n加工{spec['name_zh']}")
        build_river_extension(spec)

    print("\n数据自检")
    check_outputs(verbose=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断; 重新运行可继续下载未完成的文件.")
        sys.exit(130)
