#!/usr/bin/env python3
"""Download the ETOPO 2022 15-arc-second USSR subset and Natural Earth boundaries.

Instead of opening ~66 NOAA OPeNDAP tile URLs in xarray, this script downloads a
single regional NetCDF file from the NOAA ERDDAP endpoint and caches it locally.
The default stride is 8 (2 arc-minutes), which is still fine for the
300-dpi map output needs and keeps the download to about 0.6 GB.  Use
``--stride 1`` if you really want the full 15-arc-second grid.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
import urllib.error
import urllib.parse
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
    "110m_cultural/ne_110m_admin_0_countries.zip"
)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def erddap_url(stride: int, lon_range=(15, -165), lat_range=(20, 90)) -> str:
    min_lon, max_lon = lon_range
    min_lat, max_lat = lat_range
    # ERDDAP 的经度是 0~360°; 若用户写 [15, -165],
    # 这里把 -165 转换为 195,即从 15°E 向东到 165°W.
    if max_lon < min_lon:
        max_lon += 360
    query = (
        f"z%5B({min_lat}):{stride}:({max_lat})%5D"
        f"%5B({min_lon}):{stride}:({max_lon})%5D"
    )
    return f"{ERDDAP_BASE}?{query}"


def download(url: str, dest: Path, description: str, force: bool) -> None:
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
                # A new server may ignore Range; reset the partial file in that case.
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
    out_dir = DATA_DIR / "ne_110m_admin_0_countries"
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
        default=8,
        help="ERDDAP 采样步长；1=完整 15 弧秒，2=30 弧秒，4=1 弧分，8=2 弧分（默认，适合 300 dpi 出图）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已存在的下载文件",
    )
    args = parser.parse_args()

    if args.stride < 1:
        parser.error("--stride 必须 >= 1")

    etopo_path = DATA_DIR / f"ETOPO_2022_v1_15s_ussr_stride{args.stride}.nc"
    ne_zip_path = DATA_DIR / "ne_110m_admin_0_countries.zip"

    if etopo_path.exists() and not args.force:
        print("提示: 目标文件已存在; 若它是旧的 15~170°E 范围,请加 --force 重新下载.")

    url = erddap_url(args.stride)
    print(f"下载 ETOPO 2022 区域高程 (stride={args.stride})")
    print(url)
    download(url, etopo_path, "ETOPO 高程", args.force)

    print("\n下载 Natural Earth 110m 国家边界")
    download(NE_URL, ne_zip_path, "Natural Earth 边界", args.force)
    extract_shapefile(ne_zip_path)

    print("\n完成。现在可运行: python ussr.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断。可重新运行脚本以续传未完成的文件。")
        sys.exit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
