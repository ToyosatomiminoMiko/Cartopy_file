#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download the Myanmar ETOPO 2022 subset and Natural Earth 10m country boundaries.

是什么: 从 NOAA ERDDAP 下载 ETOPO 2022 15 弧秒缅甸区域子集, 并下载/解压
Natural Earth 10m 国家边界, 缓存到本地供绘图脚本读取.
完整说明(为什么用 ERDDAP、下载范围、--region/--stride 的含义)见
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


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

ERDDAP_BASE = (
    "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/"
    "ETOPO_2022_v1_15s.nc"
)
NE_URL = (
    "https://naturalearth.s3.amazonaws.com/"
    "10m_cultural/ne_10m_admin_0_countries.zip"
)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# 区域名 -> (经度范围, 纬度范围). 取值范围要覆盖兰勃特画框四角, 见 docs/data-preparation.md.
REGIONS = {
    "myanmar": ((85.3, 107.7), (4.9, 31.1)),
    # 掸邦放大图: 画框 95.3~101.5°E / 19.0~24.75°N, 投影后矩形在经纬度上
    # 约对应 95.17~101.63°E / 19.00~24.78°N, 所以下载范围在此基础再留
    # 约 0.2°(南) 与 0.4°(北/东西) 余量; 南界下探的理由见 docs/data-preparation.md.
    "northern_shan": ((94.6, 102.1), (18.8, 25.2)),
}


def erddap_url(stride: int, lon_range, lat_range) -> str:
    min_lon, max_lon = lon_range
    min_lat, max_lat = lat_range
    # ERDDAP 的经度是 0~360°; 本脚本用到的区域 (85~108°E 或 94~103°E)
    # 都完全落在该区间内, 直接写东经数值即可, 无需处理 -180° 到 0° 的转换.
    # 查询里的数字是坐标值 (用括号括起), stride 是索引步长, 因此步长 2 即 30 弧秒.
    query = (
        f"z%5B({min_lat}):{stride}:({max_lat})%5D"
        f"%5B({min_lon}):{stride}:({max_lon})%5D"
    )
    return f"{ERDDAP_BASE}?{query}"


def is_netcdf_file(path: Path) -> bool:
    # ERDDAP 在子集过大或参数不合法时会返回 HTML 错误页, HTTP 状态码却可能是 200,
    # 若不校验文件头就会把一段 HTML 当成 NetCDF 缓存下来, 后面 xarray 才报错.
    # NetCDF3 经典格式头是 "CDF", NetCDF4/HDF5 头是 "\x89HDF".
    with open(path, "rb") as fh:
        magic = fh.read(4)
    return magic.startswith(b"CDF") or magic.startswith(b"\x89HDF")


def download(
    url: str,
    dest: Path,
    description: str,
    force: bool,
    expect_netcdf: bool = False,
) -> None:
    # expect_netcdf 只对 ETOPO 的 .nc 打开: zip 的魔数是 "PK",
    # 若对 Natural Earth 的 .zip 也套用 CDF/HDF 魔数校验, 合法的压缩包会被删掉并报错.
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"已存在，跳过 {description}: {dest}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    if part.exists() and not force:
        print(f"发现未完成的下载，续传: {part}")
    elif part.exists():
        part.unlink()

    attempt = 0
    max_attempts = 3
    while attempt < max_attempts:
        attempt += 1
        downloaded = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"

        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                # ERDDAP 的动态子集不一定支持 Range; 若服务器忽略续传请求返回 200,
                # 说明给的是完整数据, 必须清空 .part 从头写, 否则文件会损坏.
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
                        now = time.time()
                        if now - last_report >= 3:
                            last_report = now
                            if total:
                                pct = written / (downloaded + total) * 100 if downloaded else written / total * 100
                                print(f"  {description}: {written/1024/1024:6.1f} MiB / {total/1024/1024:6.1f} MiB ({pct:5.1f}%)")
                            else:
                                print(f"  {description}: {written/1024/1024:6.1f} MiB")
            if expect_netcdf and not is_netcdf_file(part):
                part.unlink(missing_ok=True)
                raise RuntimeError(
                    f"下载内容不是 NetCDF (可能是 ERDDAP 返回的错误页): {url}"
                )
            part.replace(dest)
            print(f"完成: {dest} ({dest.stat().st_size/1024/1024:.1f} MiB)")
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  下载失败 ({attempt}/{max_attempts}): {exc}")
            if attempt < max_attempts:
                time.sleep(5 * attempt)
            else:
                raise


def extract_shapefile(zip_path: Path) -> Path:
    out_dir = DATA_DIR / "ne_10m_admin_0_countries"
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(out_dir)
    shp_files = sorted(out_dir.rglob("*.shp"))
    if not shp_files:
        raise RuntimeError(f"压缩包中没有 shapefile: {zip_path}")
    print(f"Natural Earth shapefile 已解压到: {shp_files[0]}")
    return shp_files[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stride",
        type=int,
        default=2,
        help="ERDDAP 采样步长；1=完整 15 弧秒，2=30 弧秒（默认，适合 300 dpi 出图），4=1 弧分",
    )
    parser.add_argument(
        "--region",
        choices=sorted(REGIONS),
        default="myanmar",
        help="下载区域: myanmar=缅甸全境(默认), northern_shan=掸邦北部/南部放大图",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已存在的下载文件",
    )
    args = parser.parse_args()

    if args.stride < 1:
        parser.error("--stride 必须 >= 1")

    etopo_path = DATA_DIR / f"ETOPO_2022_v1_15s_{args.region}_stride{args.stride}.nc"
    ne_zip_path = DATA_DIR / "ne_10m_admin_0_countries.zip"

    if etopo_path.exists() and not args.force:
        print("提示: 目标文件已存在; 若它是旧的区域范围, 请加 --force 重新下载.")

    lon_range, lat_range = REGIONS[args.region]
    url = erddap_url(args.stride, lon_range, lat_range)
    print(f"下载 ETOPO 2022 {args.region} 区域高程 (stride={args.stride})")
    print(url)
    started = time.time()
    download(url, etopo_path, "ETOPO 高程", args.force, expect_netcdf=True)
    print(f"ETOPO 下载耗时: {time.time() - started:.1f} 秒")

    print("\n下载 Natural Earth 10m 国家边界")
    download(NE_URL, ne_zip_path, "Natural Earth 边界", args.force)
    extract_shapefile(ne_zip_path)

    if args.region == "myanmar":
        print("\n完成。现在可运行: python myanmar.py")
    else:
        print(f"\n完成。现在可运行: python {args.region}.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断。可重新运行脚本以续传未完成的文件。")
        sys.exit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
