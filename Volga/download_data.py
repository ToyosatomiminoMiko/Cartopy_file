#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download and unpack the raw data for the Volga basin maps.

是什么: 按 ``Volga/config.py`` 的 ``DATASETS`` 下载 ETOPO 2022 高程子集与 GADM 4.1
俄罗斯一级行政区到 ``Volga/data/raw/``, 下载并解压 HydroBASINS 5 级欧洲区到
``Volga/data/derived/``; 只做下载/解压与自检, raw -> 派生 GeoJSON 由
``Volga/main.py prepare`` 完成(实现是 ``Volga/prepare_data.py``), 绘图脚本 ``Volga/volga.py``
离线读取两者的产物.
下载地址,下载范围与落盘路径全部来自 ``config.py``, 本脚本不再另写画框; 已就位的
数据一律跳过, 不重复联网.
完整说明(数据源/两个准备子命令的分工/运行方式)见 ``docs/maps/volga.md`` 与
``docs/data-preparation.md``.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

# 数据集校验要定位 Natural Earth 共享缓存(经 cartopy), 它背后会 import matplotlib;
# 缓存目录必须在 import 之前设好, 与绘图脚本用同一份(见 docs/reference/data.md).
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import pyogrio

try:  # netCDF4 只用于校验/汇报 ETOPO 维度, 缺失时跳过维度汇报
    import netCDF4
except ImportError:  # pragma: no cover - 环境里已装 netCDF4
    netCDF4 = None

# 数据集清单与画框的唯一真源; URL/下载范围/本地路径都从这里取, 见 docs/reference/spec.md.
import config

# 下载层: .part 续传/重试/魔数校验/解压, 见 docs/reference/datasets.md.
from cartopy_file import fetch

# ============================
# 路径
# ============================
CATALOG = config.DATASETS
ETOPO_PATH = CATALOG.path("etopo-volga")
GADM_JSON = CATALOG.path("gadm41-rus")
HYBAS_ARCHIVE = CATALOG.path("hybas-eu-lev05-archive")
HYBAS_SHAPES = CATALOG.path("hybas-eu-lev05")
HYBAS_DIR = HYBAS_SHAPES.parent

# eu 区东界低于该值时伏尔加东缘(60~61°E)可能缺单元; 当前这份 eu 覆盖够, 只在
# 更低版本/别处拿到的小范围文件上告警(补 as 区属于改数据源, 要走文档评审).
HYBAS_MAX_LON_EU = 61.0


# ============================
# 下载与解压
# ============================
def is_netcdf_file(path: Path) -> bool:
    """检查文件头, 避免把 ERDDAP 的错误 HTML 当成 NetCDF 缓存下来."""
    try:
        with open(path, "rb") as fh:
            magic = fh.read(4)
    except OSError:
        return False
    return magic.startswith(b"CDF") or magic.startswith(b"\x89HDF")


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


def fetch_etopo(force: bool) -> None:
    """下载 ETOPO 2022 伏尔加区域子集(stride=2, 约 30 弧秒)."""
    dataset = CATALOG.get("etopo-volga")
    print("\n[1/3] 下载 ETOPO 2022 高程")
    print(f"  {dataset.url}")
    fetch.download(
        dataset.url,
        ETOPO_PATH,
        description=dataset.note,
        force=force,
        magic=fetch.MAGIC_NETCDF,
    )


def fetch_gadm(force: bool) -> None:
    """下载 GADM 4.1 俄罗斯一级行政区 JSON."""
    dataset = CATALOG.get("gadm41-rus")
    print("\n[2/3] 下载 GADM 4.1 俄罗斯一级行政区")
    fetch.download(
        dataset.url,
        GADM_JSON,
        description=dataset.note,
        force=force,
        magic=fetch.MAGIC_JSON,
    )


def fetch_hybas(force: bool) -> None:
    """下载并解压 HydroBASINS 5 级欧洲区; 已解压过就只做覆盖检查."""
    dataset = CATALOG.get("hybas-eu-lev05-archive")
    print("\n[3/3] 下载 HydroBASINS level 5")
    fetch.download(
        dataset.url,
        HYBAS_ARCHIVE,
        description=dataset.note,
        force=force,
        magic=fetch.MAGIC_ZIP,
    )
    if force or not CATALOG.exists("hybas-eu-lev05"):
        fetch.extract_zip(HYBAS_ARCHIVE, HYBAS_DIR, force=force)
    else:
        print(f"已存在, 跳过解压: {HYBAS_SHAPES}")
    # 解压后删掉 GDAL 不兼容的空间索引(重复调用无副作用).
    _drop_shapefile_index(HYBAS_DIR)

    info = pyogrio.read_info(HYBAS_SHAPES)
    bounds = info.get("total_bounds")
    if bounds is None:
        raise RuntimeError(f"无法读取 HydroBASINS eu 的 bbox: {HYBAS_SHAPES}")
    west, south, east, north = (float(v) for v in bounds)
    print(f"   eu lev05 bbox: {west:.2f}~{east:.2f}°E / {south:.2f}~{north:.2f}°N")
    if east < HYBAS_MAX_LON_EU:
        print(
            f"   警告: eu 区东界 {east:.2f}°E < {HYBAS_MAX_LON_EU}°E, "
            "伏尔加流域东缘可能缺单元; 需要补 as 区时先改 config.py 的 DATASETS"
        )


# ============================
# 自检
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


def _file_ok(path: Path) -> bool:
    """文件存在且非空; ETOPO 的 nc 额外校验文件头."""
    if not path.exists() or path.stat().st_size <= 0:
        return False
    if path.suffix == ".nc" and path.name.startswith("ETOPO"):
        return is_netcdf_file(path)
    if path.suffix == ".zip":
        return zipfile.is_zipfile(path)
    return True


# 失败项按数据集 kind 分流到对应的子命令: 下载类归 download, 派生类归 prepare,
# Natural Earth 共享缓存归仓库根的 download_data.py(本子项目不下载).
_DOWNLOAD_KINDS = frozenset({"file", "zip", "script"})


def _prepare_command(dataset_id: str) -> str:
    """一项缺失数据的准备命令(kind 决定该跑哪个脚本)."""
    kind = CATALOG.get(dataset_id).kind
    if kind == "derived":
        return "python Volga/main.py prepare"
    if kind in _DOWNLOAD_KINDS:
        return "python Volga/main.py download"
    return "python download_data.py"


def check_outputs(verbose: bool = True) -> int:
    """只检查,不联网: 返回缺失/版本不符项数量(0 表示可以离线出图)."""
    lines = CATALOG.check()
    failed = 0
    commands: list[str] = []
    for line in lines:
        if line.failed:
            failed += 1
            commands.append(_prepare_command(line.dataset_id))
            if verbose:
                print(f"  [{line.state}] {line.dataset_id:<22s} {line.label:<28s} {line.detail}")
        elif verbose:
            print(f"  [已存在] {line.dataset_id:<22s} {line.label:<28s} {line.detail}")

    # 存在但文件头不对(半截/错误页)也算不可用; 数据集检查只看存在性.
    for path, label in (
        (ETOPO_PATH, "ETOPO 高程"),
        (HYBAS_ARCHIVE, "HydroBASINS 压缩包"),
    ):
        if path.exists() and not _file_ok(path):
            failed += 1
            commands.append("python Volga/main.py download")
            if verbose:
                print(f"  [损坏] {label}: {path.relative_to(ROOT)}")

    if verbose:
        if failed:
            print(f"\n共 {failed} 项缺失/损坏, 请运行:")
            for command in dict.fromkeys(commands):
                print(f"  {command}")
        else:
            print("\n全部数据已就位, 可以运行: python Volga/main.py render")
    return failed


def print_summary() -> None:
    """逐个报告原始数据文件的体积/要素数; ETOPO 额外报告维度与经纬度范围."""
    print("\n" + "=" * 60)
    print("原始数据汇总")
    print("=" * 60)
    print(f"[原始] {ETOPO_PATH.name}: {ETOPO_PATH.stat().st_size/1048576:.2f} MiB")
    try:
        dims, shape, lat_rng, lon_rng = _etopo_info(ETOPO_PATH)
        print(f"       维度={dims}, z.shape={shape}, lat={lat_rng}, lon={lon_rng}")
    except Exception as exc:  # 仅影响汇报, 不影响数据是否可用
        print(f"       (读取维度失败: {exc})")
    for path, label, kind in (
        (GADM_JSON, "GADM RUS 一级行政区", "原始"),
        (HYBAS_SHAPES, "HydroBASINS eu lev05", "解压"),
    ):
        if not path.exists():
            print(f"[缺失] {path.name}")
            continue
        size = path.stat().st_size / 1048576
        try:
            info = pyogrio.read_info(path)
            print(f"[{kind}] {path.name}: {size:.2f} MiB, {info.get('features')} 要素")
        except Exception as exc:
            print(f"[{kind}] {path.name}: {size:.2f} MiB (读取要素数失败: {exc})")


def run(*, check: bool = False, force: bool = False, skip_basin: bool = False) -> int:
    """下载入口: 只检查,下载/解压或两者都做; 返回退出码(0 表示数据齐全)."""
    if check:
        return 0 if check_outputs(verbose=True) == 0 else 1

    fetch_etopo(force=force)
    fetch_gadm(force=force)

    if skip_basin:
        print("\n--skip-basin: 跳过 HydroBASINS 下载")
    else:
        # 单独 try: HydroBASINS 源偶尔不可达时, ETOPO/GADM 仍已就位, 把缺失留给
        # --check 报告, 而不是整个脚本失败.
        try:
            fetch_hybas(force=force)
        except Exception as exc:
            print(f"\n警告: HydroBASINS 下载失败: {exc}")
            print("       可稍后重跑本子命令(原始文件会从 .part 断点续传), 或加 --skip-basin")

    print_summary()
    return 0 if check_outputs(verbose=True) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(
        "本文件是模块, 不能直接运行; 请用统一入口: python Volga/main.py download"
    )
