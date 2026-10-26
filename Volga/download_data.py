#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Prepare raw and derived data for the Volga basin overview map.

是什么: 下载 ETOPO 2022 高程子集、GADM 4.1 俄罗斯一级行政区与 HydroBASINS 5 级
流域数据, 派生出 ``volga_subjects`` / ``volga_basin`` / ``russia_border`` 三个
GeoJSON 供 ``Volga/volga.py`` 离线读取; 河流/湖泊用仓库缓存的 Natural Earth 10m,
本脚本不处理.
完整说明(数据源/输出契约/运行方式)见 ``docs/add-map.md`` 第 2 节与
``docs/data-preparation.md``.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
from shapely.validation import make_valid

try:  # netCDF4 只用于校验/汇报 ETOPO 维度, 缺失时退回文件头魔数校验
    import netCDF4
except ImportError:  # pragma: no cover - 环境里已装 netCDF4
    netCDF4 = None

# ============================
# 路径与范围
# ============================
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

# 画框: (min_lon, min_lat, max_lon, max_lat). 对应绘图脚本 cartopy 的
# extent=[29.8, 62.8, 43.9, 62.8], 这里统一用 shapely box() 的参数顺序.
BBOX = (29.8, 43.9, 62.8, 62.8)
BBOX_POLYGON = box(*BBOX)

# ETOPO 子集: stride=2 即 30 弧秒; 范围由 lead 给定, 比画框略大以免投影
# 画框四角露白. ERDDAP 的 z[lat][lon] 顺序见 _erddap_url().
ERDDAP_BASE = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_15s.nc"
ETOPO_STRIDE = 2
ETOPO_LON = (29.8, 62.8)
ETOPO_LAT = (43.9, 62.8)
ETOPO_PATH = DATA_DIR / f"ETOPO_2022_v1_15s_volga_stride{ETOPO_STRIDE}.nc"

# GADM 4.1 俄罗斯一级行政区(法理口径, 不含克里米亚/塞瓦斯托波尔).
GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_RUS_1.json"
GADM_JSON = DATA_DIR / "gadm41_RUS_1.json"

# HydroBASINS 5 级: eu 区东界可能只到约 60°E, 而伏尔加流域东缘在 60~61°E;
# 若 eu 覆盖不足就补下 as 区, 两者 MAIN_BAS 是同一套 Pfafstetter 编码可合并.
HYBAS_BASE = "https://data.hydrosheds.org/file/HydroBASINS/standard"
HYBAS_MAX_LON_EU = 61.0  # eu 区东界低于该值时才需要 as 区
HYBAS_COLUMNS = ["MAIN_BAS", "UP_AREA"]
HYBAS_EU_ZIP = DATA_DIR / "hybas_eu_lev05_v1c.zip"
HYBAS_AS_ZIP = DATA_DIR / "hybas_as_lev05_v1c.zip"
HYBAS_EU_DIR = DATA_DIR / "hybas_eu_lev05_v1c"
HYBAS_AS_DIR = DATA_DIR / "hybas_as_lev05_v1c"
HYBAS_EU_SHP = HYBAS_EU_DIR / "hybas_eu_lev05_v1c.shp"
HYBAS_AS_SHP = HYBAS_AS_DIR / "hybas_as_lev05_v1c.shp"
HYBAS_EU_URL = f"{HYBAS_BASE}/hybas_eu_lev05_v1c.zip"
HYBAS_AS_URL = f"{HYBAS_BASE}/hybas_as_lev05_v1c.zip"

# 派生输出(绘图脚本直接读这三个文件, 字段契约不要随意改).
SUBJECTS_PATH = DATA_DIR / "volga_subjects.geojson"
BASIN_PATH = DATA_DIR / "volga_basin.geojson"
BORDER_PATH = DATA_DIR / "russia_border.geojson"

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

USER_AGENT = "CartopyFile-VolgaMap/1.0 (cartopy map project)"


# ============================
# 下载与解压
# ============================
def _erddap_url(stride: int, lon_range, lat_range) -> str:
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
    try:
        with open(path, "rb") as fh:
            magic = fh.read(4)
    except OSError:
        return False
    return magic.startswith(b"CDF") or magic.startswith(b"\x89HDF")


def is_zip_file(path: Path) -> bool:
    """zip 必须能读到中央目录; 半截文件(下载中断)会返回 False."""
    try:
        return zipfile.is_zipfile(path)
    except OSError:
        return False


def _download_once(url: str, part: Path, description: str, timeout: float = 60.0) -> None:
    """从 url 下载到 part, 已有内容用 Range 续传(服务器忽略 Range 则从头写).

    为什么用 timeout=60 且失败后无限重试: data.hydrosheds.org 对本机极慢,
    经常"连接建立后长时间不出字节", 长超时只会白等; 短超时 + .part 续传能
    在每次中断后从断点继续, 最终拉完 9 MB 的 HydroBASINS.
    注: Python urllib 只讲 HTTP/1.1; 用 curl 手工续传时要加 ``--http1.1``,
    curl 默认的 HTTP/2 到该源会卡住不出字节.
    """
    downloaded = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if downloaded:
        headers["Range"] = f"bytes={downloaded}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        # 服务器不支持 Range 时会返回 200 + 完整内容; 此时必须清空 .part
        # 从头写, 否则续传得到的是"旧前缀 + 完整文件"的损坏结果.
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
                if time.time() - last_report >= 5:
                    last_report = time.time()
                    if total:
                        pct = written / (downloaded + total) * 100
                        print(
                            f"  {description}: {written/1048576:6.1f} / "
                            f"{(downloaded+total)/1048576:6.1f} MiB ({pct:5.1f}%)",
                            flush=True,
                        )
                    else:
                        print(f"  {description}: {written/1048576:6.1f} MiB", flush=True)


def download(
    url: str,
    dest: Path,
    description: str,
    *,
    force: bool = False,
    expect_netcdf: bool = False,
    expect_zip: bool = False,
    max_attempts: int | None = 6,
) -> None:
    """带 .part 续传/重试的下载; 已存在且通过魔数校验时跳过.

    为什么先写 ``.part``: 中断后重跑能用 Range 从断点续传, 也不会让派生
    脚本把半截文件当完整数据.
    为什么"已存在但魔数不对"也要重下: 其他进程直接写目标文件名、上次下载
    中断或服务器返回错误页都会留下"非空但损坏"的文件, 只看大小会误跳过,
    后面 xarray/GDAL 才报错.
    ``max_attempts=None`` 表示无限重试(用于极慢/易断的 HydroBASINS 源).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size > 0 and not force:
        if expect_netcdf and not is_netcdf_file(dest):
            print(f"  已存在但文件头不是 NetCDF, 重新下载: {dest}")
        elif expect_zip and not is_zip_file(dest):
            print(f"  已存在但不是完整 zip(可能正在下载/上次中断), 重新下载: {dest}")
        else:
            print(f"已存在, 跳过 {description}: {dest}")
            return

    part = dest.with_name(dest.name + ".part")
    if part.exists() and force:
        part.unlink()
    elif part.exists():
        print(f"发现未完成的下载, 续传: {part}")

    attempt = 0
    while max_attempts is None or attempt < max_attempts:
        attempt += 1
        try:
            _download_once(url, part, description)
            if expect_netcdf and not is_netcdf_file(part):
                part.unlink(missing_ok=True)
                raise RuntimeError(
                    f"下载内容不是 NetCDF(可能是 ERDDAP 返回的错误页): {url}"
                )
            if expect_zip and not is_zip_file(part):
                part.unlink(missing_ok=True)
                raise RuntimeError(
                    f"下载内容不是完整 zip(服务器返回错误页或数据被截断): {url}"
                )
            part.replace(dest)
            print(f"完成: {dest} ({dest.stat().st_size/1048576:.1f} MiB)", flush=True)
            return
        except urllib.error.HTTPError as exc:
            # 4xx(限流 429 除外)是永久错误, 无限重试没有意义.
            if 400 <= exc.code < 500 and exc.code != 429:
                raise
            print(f"  下载失败 (第 {attempt} 次): {exc}", flush=True)
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            print(f"  下载失败 (第 {attempt} 次): {exc}", flush=True)
        if max_attempts is not None and attempt >= max_attempts:
            raise RuntimeError(f"{description} 下载失败, 已重试 {attempt} 次: {url}")
        time.sleep(min(5 * attempt, 30))


def _drop_shapefile_index(out_dir: Path) -> None:
    """删掉 shp 附带的 .sbn/.sbx 空间索引.

    HydroBASINS 官方 v1c zip 里的 .sbn 与 GDAL 的 shapefile 驱动不兼容,
    带 bbox 过滤读取时会报 ``Invalid node descriptor size in .sbn``; .sbn
    只是可选的空间索引, 删掉后 GDAL 用 .shx 或自己的索引照样能读, 不影响
    几何与属性.
    """
    for pattern in ("*.sbn", "*.sbx"):
        for path in out_dir.glob(pattern):
            path.unlink(missing_ok=True)


def extract_zip(zip_path: Path, out_dir: Path, shp_name: str, *, force: bool = False) -> Path:
    """解压到 out_dir 并返回其中的 shp; 目标 shp 已存在时跳过解压."""
    shp_path = out_dir / shp_name
    if shp_path.exists() and shp_path.stat().st_size > 0 and not force:
        _drop_shapefile_index(out_dir)
        print(f"已存在, 跳过解压: {shp_path}")
        return shp_path
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            # 只接受相对路径, 防止压缩包内出现 ../ 或绝对路径.
            if Path(member).is_absolute() or ".." in Path(member).parts:
                raise RuntimeError(f"压缩包内路径非法: {member} (来自 {zip_path})")
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"压缩包 CRC 校验失败: {bad} (来自 {zip_path})")
        archive.extractall(out_dir)
    _drop_shapefile_index(out_dir)
    if not shp_path.exists():
        found = sorted(out_dir.rglob("*.shp"))
        raise RuntimeError(
            f"压缩包里没有期望的 {shp_name}; 实际找到: {[p.name for p in found] or '无'}"
        )
    print(f"已解压: {shp_path}")
    return shp_path


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
# 1. 下载原始数据
# ============================
def fetch_etopo(force: bool) -> None:
    """下载 ETOPO 2022 伏尔加区域子集(stride=2, 约 30 弧秒)."""
    url = _erddap_url(ETOPO_STRIDE, ETOPO_LON, ETOPO_LAT)
    print(f"\n[1/3] 下载 ETOPO 2022 高程 (stride={ETOPO_STRIDE})")
    print(f"  {url}")
    download(url, ETOPO_PATH, "ETOPO 高程", force=force, expect_netcdf=True)


def fetch_gadm(force: bool) -> None:
    """下载 GADM 4.1 俄罗斯一级行政区 JSON."""
    print("\n[2/3] 下载 GADM 4.1 俄罗斯一级行政区")
    download(GADM_URL, GADM_JSON, "GADM 俄罗斯一级行政区", force=force)


def fetch_hybas(force: bool) -> None:
    """下载并解压 HydroBASINS 5 级; eu 区覆盖不到 ~61°E 时补下 as 区."""
    print("\n[3/3] 下载 HydroBASINS level 5")
    # 该源很慢且会长时间不出字节, 用无限重试 + 续传; 下载完的 zip 会缓存,
    # 后续重跑直接跳过.
    download(
        HYBAS_EU_URL,
        HYBAS_EU_ZIP,
        "HydroBASINS eu lev05",
        force=force,
        expect_zip=True,
        max_attempts=None,
    )
    extract_zip(HYBAS_EU_ZIP, HYBAS_EU_DIR, HYBAS_EU_SHP.name, force=force)

    info = pyogrio.read_info(HYBAS_EU_SHP)
    bounds = info.get("total_bounds")
    if bounds is None:
        raise RuntimeError(f"无法读取 HydroBASINS eu 的 bbox: {HYBAS_EU_SHP}")
    west, south, east, north = (float(v) for v in bounds)
    print(f"   eu lev05 bbox: {west:.2f}~{east:.2f}°E / {south:.2f}~{north:.2f}°N")
    # 伏尔加流域东缘约 60~61°E; eu 区东界不够就补 as 区, 否则东段单元缺失.
    if east < HYBAS_MAX_LON_EU:
        print(f"   eu 区东界 {east:.2f}°E < {HYBAS_MAX_LON_EU}°E, 补下 as 区并合并")
        download(
            HYBAS_AS_URL,
            HYBAS_AS_ZIP,
            "HydroBASINS as lev05",
            force=force,
            expect_zip=True,
            max_attempts=None,
        )
        extract_zip(HYBAS_AS_ZIP, HYBAS_AS_DIR, HYBAS_AS_SHP.name, force=force)
    else:
        print(f"   eu 区已覆盖到 {east:.2f}°E, 不需要 as 区")


# ============================
# 2. 派生 GeoJSON(不依赖 HydroBASINS 的两项可单独重建)
# ============================
def build_subjects() -> None:
    """GADM 全部 83 个一级行政区用完整几何裁到画框.

    为什么读完整的 83 行再用完整几何求交: 若先用 ``cx`` 粗筛, 跨越画框的
    州(如秋明/阿尔汉格尔斯克)会因代表性点选不中而丢失或只剩一小块; 正确
    做法是逐要素做"完整几何 ∩ BBOX", 完全在画框外的州不产要素.
    """
    print("\n派生 volga_subjects.geojson (GADM 一级行政区)")
    if not GADM_JSON.exists():
        raise RuntimeError(f"缺少 {GADM_JSON}; 请先运行本脚本下载 GADM 数据")
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
        raise RuntimeError(f"缺少 {GADM_JSON}; 请先运行本脚本下载 GADM 数据")
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
    """当前可用的 HydroBASINS shp 列表(eu 必有; as 视覆盖情况可选)."""
    files = [HYBAS_EU_SHP]
    if HYBAS_AS_SHP.exists():
        files.append(HYBAS_AS_SHP)
    for path in files:
        if not path.exists():
            raise RuntimeError(f"缺少 HydroBASINS shapefile: {path}; 请先下载并解压")
    return files


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
            f"在入海口窗口 {ESTUARY_BBOX} 内找不到单元; 检查 eu/as 文件是否覆盖里海西北岸"
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
            f"MAIN_BAS={main_bas} 可能选错或 HydroBASINS 区域不全(检查是否需要 as 区)"
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


# ============================
# 3. 自检
# ============================
def _etopo_info(path: Path):
    """返回 (维度 dict, z shape, lat 范围, lon 范围); 打不开则抛异常.

    ERDDAP 导出的坐标变量名可能是 lat/lon, 也可能是 latitude/longitude,
    两种都接受, 否则汇报里会误显示"读不到范围".
    """
    if netCDF4 is None:
        raise RuntimeError("未安装 netCDF4, 无法读取 NetCDF 维度")
    with netCDF4.Dataset(path, "r") as ds:
        if "z" not in ds.variables:
            raise RuntimeError(f"NetCDF 里没有变量 z: {path}")
        var = ds.variables["z"]
        dims = {name: len(dim) for name, dim in ds.dimensions.items()}
        lat_var = ds.variables.get("lat", ds.variables.get("latitude"))
        lon_var = ds.variables.get("lon", ds.variables.get("longitude"))
        lat_rng = (float(lat_var[:].min()), float(lat_var[:].max())) if lat_var is not None else None
        lon_rng = (float(lon_var[:].min()), float(lon_var[:].max())) if lon_var is not None else None
        return dims, var.shape, lat_rng, lon_rng


def check_outputs(verbose: bool = True) -> int:
    """只检查、不联网: 返回缺失/损坏项数量(0 表示可以离线出图)."""
    required = [
        (ETOPO_PATH, "ETOPO 高程"),
        (GADM_JSON, "GADM 俄罗斯一级行政区"),
        (HYBAS_EU_SHP, "HydroBASINS eu lev05"),
        (SUBJECTS_PATH, "派生: 一级行政区"),
        (BASIN_PATH, "派生: 伏尔加流域"),
        (BORDER_PATH, "派生: 俄罗斯国界"),
    ]
    missing = 0
    for path, label in required:
        ok = path.exists() and path.stat().st_size > 0
        reason = ""
        if ok and path.suffix == ".nc":
            ok = is_netcdf_file(path)
            reason = "" if ok else "文件头不是 NetCDF"
        elif ok and path.suffix == ".zip":
            ok = is_zip_file(path)
            reason = "" if ok else "不是完整 zip"
        if not ok:
            missing += 1
            if verbose:
                print(f"  [缺失/损坏] {label}: {path.relative_to(ROOT)} {reason}".rstrip())
        elif verbose:
            print(f"  [已存在] {label}: {path.relative_to(ROOT)} ({path.stat().st_size/1048576:.2f} MiB)")

    if verbose:
        if missing:
            print(f"\n共 {missing} 项缺失/损坏, 请运行: python Volga/download_data.py")
        else:
            print("\n全部数据已就位, 可以运行: python Volga/volga.py")
    return missing


def print_summary() -> None:
    """逐个报告数据文件的体积/要素数; ETOPO 额外报告维度与经纬度范围."""
    print("\n" + "=" * 60)
    print("数据文件汇总")
    print("=" * 60)
    print(f"[原始] {ETOPO_PATH.name}: {ETOPO_PATH.stat().st_size/1048576:.2f} MiB")
    try:
        dims, shape, lat_rng, lon_rng = _etopo_info(ETOPO_PATH)
        print(f"       维度={dims}, z.shape={shape}, lat={lat_rng}, lon={lon_rng}")
    except Exception as exc:  # 仅影响汇报, 不影响数据是否可用
        print(f"       (读取维度失败: {exc})")
    for path, label in [
        (GADM_JSON, "GADM RUS 一级行政区"),
        (HYBAS_EU_SHP, "HydroBASINS eu lev05"),
        (SUBJECTS_PATH, "volga_subjects"),
        (BASIN_PATH, "volga_basin"),
        (BORDER_PATH, "russia_border"),
    ]:
        if not path.exists():
            print(f"[缺失] {path.name}")
            continue
        size = path.stat().st_size / 1048576
        try:
            info = pyogrio.read_info(path)
            print(f"[{'派生' if path.suffix == '.geojson' else '原始'}] {path.name}: {size:.2f} MiB, {info.get('features')} 要素")
        except Exception as exc:
            print(f"[原始] {path.name}: {size:.2f} MiB (读取要素数失败: {exc})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只检查数据是否齐全, 不联网")
    parser.add_argument("--force", action="store_true", help="强制重新下载/解压原始数据(派生文件总是重建)")
    parser.add_argument(
        "--skip-basin",
        action="store_true",
        help="跳过 HydroBASINS 下载/流域派生(只重建行政区与国界, 缺该数据时用)",
    )
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check_outputs(verbose=True) == 0 else 1)

    fetch_etopo(force=args.force)
    fetch_gadm(force=args.force)

    print("\n" + "=" * 60)
    print("派生 GeoJSON(每次运行都重建; 不依赖 HydroBASINS 的先做)")
    print("=" * 60)
    build_subjects()
    build_border()

    if args.skip_basin:
        print("\n--skip-basin: 跳过 HydroBASINS 下载与流域派生")
    else:
        # 单独 try: HydroBASINS 源偶尔不可达时, 已生成的两个文件仍有效,
        # 并把缺失留给 --check 报告, 而不是整个脚本失败.
        try:
            fetch_hybas(force=args.force)
            build_basin()
        except Exception as exc:
            print(f"\n警告: HydroBASINS 下载/流域派生失败, volga_basin.geojson 未生成: {exc}")
            print("       可稍后重跑本脚本(原始文件会从 .part 断点续传), 或加 --skip-basin")

    print_summary()
    missing = check_outputs(verbose=True)
    sys.exit(0 if missing == 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断; 重新运行可继续下载未完成的文件.")
        sys.exit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
