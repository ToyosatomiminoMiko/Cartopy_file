#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download the ETOPO 2022 15-arc-second USSR subset.

是什么: 从 NOAA ERDDAP 下载苏联区域 ETOPO 高程子集(默认 stride=8, 约 45 MB); URL 与
下载范围来自 ``cartopy_file.sources`` 与 ``USSR/specs.py``, 文件已就位时跳过、不重复下载.
Natural Earth 国界/海岸线由根目录 ``download_data.py`` 预取到共享缓存, 这里不再下载.
完整说明(数据来源、下载范围、断点续传与退出码)见 ``docs/maps/ussr.md`` 与
``docs/data-preparation.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 子项目配置(数据集清单 + 画框)与下载层, 见 docs/reference/datasets.md.
import specs
from cartopy_file import fetch
from cartopy_file.sources import erddap_url


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

    datasets = specs.DATASETS

    # ETOPO 子集: 文件名带 stride, 不同步长的文件可以共存(drawing 侧按步长挑).
    # 下载范围来自 specs.py 的 ETOPO_BBOX_USSR, 与「这份数据覆盖多大」是同一个对象.
    bbox = specs.ETOPO_BBOX_USSR
    etopo_path = datasets.raw_dir / f"ETOPO_2022_v1_15s_ussr_stride{args.stride}.nc"
    url = erddap_url(
        "etopo-2022",
        stride=args.stride,
        lon_range=(bbox.lon_min, bbox.lon_max),
        lat_range=(bbox.lat_min, bbox.lat_max),
    )
    print(f"下载 ETOPO 2022 苏联区域高程 (stride={args.stride})")
    print(url)
    fetch.download(
        url,
        etopo_path,
        description="ETOPO 高程",
        force=args.force,
        magic=fetch.MAGIC_NETCDF,
    )

    print("\n完成。现在可运行: python USSR/ussr.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断。可重新运行脚本以续传未完成的文件。")
        sys.exit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(1)
