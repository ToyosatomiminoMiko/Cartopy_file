#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download the ETOPO 2022 subsets declared in the Myanmar dataset inventory.

是什么: 按 ``Myanmar/specs.py`` 里登记的 ETOPO 数据集(URL、下载范围、dest 命名约定)
从 NOAA ERDDAP 下载区域高程子集; 目标文件已存在时跳过, 中断过可续传.
Natural Earth 10m 国界不再由本脚本下载: 它由根目录 ``download_data.py`` 预取到全项目
共享缓存 ``data/cartopy/``, 绘图脚本通过 cartopy 的缓存路径直接读取.
完整说明(为什么用 ERDDAP、下载范围、--region/--stride 的含义)见
``docs/data-preparation.md`` 的 ETOPO 一节; 数据集层见 ``docs/reference/datasets.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 图种规格与数据集清单: ETOPO 的 URL/范围/dest 只写在那里, 见 docs/reference/datasets.md.
import specs
from cartopy_file.fetch import MAGIC_NETCDF, download
from cartopy_file.sources import erddap_url

# --region -> specs 里对应的 ETOPO 数据集 id; 下载范围与默认步长都在数据集里声明.
REGIONS = {
    "myanmar": "etopo-myanmar",
    "northern_shan": "etopo-northern-shan",
}

# dest 命名的模板必须与 cartopy_file.relief.find_etopo 的约定一致, 否则出图脚本
# 找不到刚下载的文件. 数据集里登记的 dest 只是默认步长的那一份, 其它步长按模板拼.
DEST_TEMPLATE = "raw/ETOPO_2022_v1_15s_{region}_stride{stride}.nc"


def resolve_target(region: str, stride: int | None) -> tuple[str, str, Path]:
    """把 (region, stride) 解析成 (url, 数据集 id, 本地路径).

    stride 缺省时用数据集自己登记的步长; 与登记值不同时按同一套 URL 生成规则
    重新拼查询串, 并把 dest 换成对应步长的文件名.
    """
    dataset = specs.DATASETS.get(REGIONS[region])
    actual_stride = dataset.stride if stride is None else stride
    if actual_stride is None:
        raise ValueError(f"数据集 {dataset.id} 没有登记 stride, 请用 --stride 指定")
    if actual_stride < 1:
        raise ValueError(f"--stride 必须 >= 1, 得到 {actual_stride}")
    if actual_stride == dataset.stride:
        return dataset.url, dataset.id, specs.DATASETS.path(dataset)

    bbox = dataset.bbox
    if bbox is None:
        raise ValueError(f"数据集 {dataset.id} 没有登记 bbox, 无法换算下载范围")
    url = erddap_url(
        dataset.source_id,
        stride=actual_stride,
        lon_range=(bbox.lon_min, bbox.lon_max),
        lat_range=(bbox.lat_min, bbox.lat_max),
    )
    dest = specs.DATASETS.root / DEST_TEMPLATE.format(
        region=region, stride=actual_stride
    )
    return url, dataset.id, dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stride",
        type=int,
        default=None,
        help="ERDDAP 采样步长; 缺省用数据集登记的步长(缅甸 stride=2, 掸邦 stride=1)",
    )
    parser.add_argument(
        "--region",
        choices=sorted(REGIONS),
        default="myanmar",
        help="下载区域: myanmar=缅甸全境(默认), northern_shan=掸邦放大图",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已存在的下载文件",
    )
    args = parser.parse_args()

    try:
        url, dataset_id, dest = resolve_target(args.region, args.stride)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"下载 ETOPO 2022 {args.region} 区域高程 (数据集 {dataset_id})")
    print(url)
    download(
        url,
        dest,
        description="ETOPO 高程",
        force=args.force,
        magic=MAGIC_NETCDF,
    )

    print(
        "Natural Earth 10m 国界由根目录 download_data.py 预取到共享缓存 "
        "(data/cartopy/), 本脚本不再下载."
    )
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
