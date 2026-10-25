#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Temporary script: download the Myanmar stride-1 ETOPO subset in 8 bands and merge it.

是什么: 分 8 个纬度带并行下载 ERDDAP 子集, 用 xarray 沿纬度拼接成单个 NetCDF, 并做自检.
完整说明(为什么分块、用法与自检内容)见 ``docs/data-preparation.md``.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "Myanmar" / "data"
BAND_DIR = DATA_DIR / "_stride1_bands"
OUT_PATH = DATA_DIR / "ETOPO_2022_v1_15s_myanmar_stride1.nc"

BASE_URL = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_15s.nc"
LON_RANGE = (85.3, 107.7)
USER_AGENT = "Cartopy_file/1.0 (offline map project)"

# 边界都落在 15 弧秒网格上(1/240 度): 4.9/8.175/.../31.1 乘 240 均为整数.
LAT_BANDS = [
    (4.9, 8.175),
    (8.175, 11.45),
    (11.45, 14.725),
    (14.725, 18.0),
    (18.0, 21.275),
    (21.275, 24.55),
    (24.55, 27.825),
    (27.825, 31.1),
]

MAX_WORKERS = 4      # 并发太多时 ERDDAP 反而有请求 0 字节挂住
ATTEMPTS = 5
TIMEOUT = 900        # 单块约 16 MB, 20 KiB/s 时也需要 13 分钟


def band_url(min_lat: float, max_lat: float) -> str:
    min_lon, max_lon = LON_RANGE
    query = (
        f"z%5B({min_lat}):1:({max_lat})%5D"
        f"%5B({min_lon}):1:({max_lon})%5D"
    )
    return f"{BASE_URL}?{query}"


def is_netcdf_file(path: Path) -> bool:
    with open(path, "rb") as fh:
        magic = fh.read(4)
    return magic.startswith(b"CDF") or magic.startswith(b"\x89HDF")


def download_band(index: int, min_lat: float, max_lat: float) -> Path:
    dest = BAND_DIR / f"band{index:02d}_{min_lat:.3f}_{max_lat:.3f}.nc"
    if dest.exists() and dest.stat().st_size > 0 and is_netcdf_file(dest):
        print(f"[band{index}] 已存在, 跳过 ({dest.stat().st_size/1024/1024:.1f} MiB)")
        return dest

    url = band_url(min_lat, max_lat)
    part = dest.with_suffix(".part")
    for attempt in range(1, ATTEMPTS + 1):
        started = time.time()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                written = 0
                with open(part, "wb") as out:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        written += len(chunk)
            if not is_netcdf_file(part):
                raise RuntimeError("响应不是 NetCDF(可能是 ERDDAP 错误页)")
            part.replace(dest)
            print(
                f"[band{index}] 完成 {dest.stat().st_size/1024/1024:.1f} MiB, "
                f"耗时 {time.time()-started:.0f}s"
            )
            return dest
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            part.unlink(missing_ok=True)
            print(f"[band{index}] 失败 ({attempt}/{ATTEMPTS}): {exc}")
            if attempt < ATTEMPTS:
                time.sleep(10 * attempt)
    raise RuntimeError(f"band{index} 下载失败: {min_lat}~{max_lat}")


def merge_bands(paths: list[Path]) -> None:
    import xarray as xr

    datasets = [xr.open_dataset(p, decode_times=False, engine="netcdf4")
                for p in paths]
    try:
        # 相邻纬度带在边界上共享一行纬度; 后续块去掉第一行再拼, 避免重复.
        parts = [datasets[0]]
        for ds in datasets[1:]:
            parts.append(ds.isel(latitude=slice(1, None)))
        merged = xr.concat(parts, dim="latitude")
        merged = merged.sortby("latitude")
        n_nan = int(merged["z"].isnull().sum())
        print(f"合并后形状: {tuple(merged['z'].shape)}, NaN 数: {n_nan}")
        if n_nan:
            raise RuntimeError("合并结果含 NaN, 分块边界可能没对齐")
        merged.to_netcdf(OUT_PATH, engine="netcdf4")
        print(f"已写入: {OUT_PATH} ({OUT_PATH.stat().st_size/1024/1024:.1f} MiB)")
    finally:
        for ds in datasets:
            ds.close()


def self_check() -> None:
    """检查最终文件的范围/形状, 并按几个采样点与 stride2 文件对比高程."""
    import xarray as xr

    ds1 = xr.open_dataset(OUT_PATH, decode_times=False, engine="netcdf4")
    z1 = ds1["z"].isel(time=0) if "time" in ds1["z"].dims else ds1["z"]
    lon1 = z1["longitude"].to_numpy()
    lat1 = z1["latitude"].to_numpy()
    print(
        f"stride1: 形状 {z1.shape}, 经度 {lon1[0]:.2f}~{lon1[-1]:.2f}, "
        f"纬度 {lat1[0]:.2f}~{lat1[-1]:.2f}"
    )
    assert abs(lon1[0] - 85.3) < 1e-6 and abs(lon1[-1] - 107.7) < 1e-6
    assert abs(lat1[0] - 4.9) < 1e-6 and abs(lat1[-1] - 31.1) < 1e-6
    assert z1.shape == (6289, 5377), f"形状异常: {z1.shape}"

    ds2 = xr.open_dataset(
        DATA_DIR / "ETOPO_2022_v1_15s_myanmar_stride2.nc",
        decode_times=False, engine="netcdf4",
    )
    z2 = ds2["z"].isel(time=0) if "time" in ds2["z"].dims else ds2["z"]
    # 缅甸境内几个点: 曼德勒附近平原、克钦山区、安达曼海(负值=水深).
    for lat, lon in [(21.97, 96.08), (25.4, 97.5), (14.0, 96.5)]:
        v1 = float(z1.sel(latitude=lat, longitude=lon, method="nearest"))
        v2 = float(z2.sel(latitude=lat, longitude=lon, method="nearest"))
        print(f"  ({lat}N,{lon}E): stride1={v1:8.1f} m, stride2={v2:8.1f} m")
    ds1.close()
    ds2.close()


def main() -> None:
    BAND_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists():
        print(f"最终文件已存在, 只做自检: {OUT_PATH}")
        self_check()
        return

    print(f"分块下载 stride=1, 共 {len(LAT_BANDS)} 块, 并发 {MAX_WORKERS}")
    started = time.time()
    results: dict[int, Path] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(download_band, i, lo, hi): i
            for i, (lo, hi) in enumerate(LAT_BANDS)
        }
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()

    paths = [results[i] for i in range(len(LAT_BANDS))]
    print(f"全部下载完成, 总耗时 {time.time()-started:.0f}s, 开始合并")
    merge_bands(paths)
    self_check()
    print(f"总耗时 {time.time()-started:.0f}s")


if __name__ == "__main__":
    main()
