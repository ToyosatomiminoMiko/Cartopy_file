#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download the ETOPO 2022 subsets declared in the Myanmar dataset inventory.

是什么: 按 ``Myanmar/config.py`` 里登记的 ETOPO 数据集(URL、下载范围、dest 命名约定)
从 NOAA ERDDAP 下载区域高程子集; 目标文件已存在时跳过, 中断过可续传. 本文件是模块,
只导出 ``run()``, 由统一入口 ``python Myanmar/main.py download`` 调用.
Natural Earth 10m 国界不再由本脚本下载: 它由根目录 ``download_data.py`` 预取到全项目
共享缓存 ``data/cartopy/``, 绘图脚本通过 cartopy 的缓存路径直接读取.
完整说明(为什么用 ERDDAP、下载范围、--region/--stride 的含义)见
``docs/data-preparation.md`` 的 ETOPO 一节; 数据集层见 ``docs/reference/datasets.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 图种规格与数据集清单: ETOPO 的 URL/范围/dest 只写在那里, 见 docs/reference/datasets.md.
import config
from cartopy_file.fetch import MAGIC_NETCDF, download
from cartopy_file.sources import erddap_url

# --region -> config 里对应的 ETOPO 数据集 id; 下载范围与默认步长都在数据集里声明.
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
    dataset = config.DATASETS.get(REGIONS[region])
    actual_stride = dataset.stride if stride is None else stride
    if actual_stride is None:
        raise ValueError(f"数据集 {dataset.id} 没有登记 stride, 请用 --stride 指定")
    if actual_stride < 1:
        raise ValueError(f"--stride 必须 >= 1, 得到 {actual_stride}")
    if actual_stride == dataset.stride:
        return dataset.url, dataset.id, config.DATASETS.path(dataset)

    bbox = dataset.bbox
    if bbox is None:
        raise ValueError(f"数据集 {dataset.id} 没有登记 bbox, 无法换算下载范围")
    url = erddap_url(
        dataset.source_id,
        stride=actual_stride,
        lon_range=(bbox.lon_min, bbox.lon_max),
        lat_range=(bbox.lat_min, bbox.lat_max),
    )
    dest = config.DATASETS.root / DEST_TEMPLATE.format(
        region=region, stride=actual_stride
    )
    return url, dataset.id, dest


def run(*, region: str = "myanmar", stride: int | None = None, force: bool = False) -> int:
    """下载一个区域的 ETOPO 子集; 返回 0=成功, 1=参数错误(区域或 stride 非法)."""
    if region not in REGIONS:
        print(
            f"错误: 未知的下载区域 {region!r}; 可选: {', '.join(sorted(REGIONS))}",
            file=sys.stderr,
        )
        return 1
    try:
        url, dataset_id, dest = resolve_target(region, stride)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(f"下载 ETOPO 2022 {region} 区域高程 (数据集 {dataset_id})")
    print(url)
    download(
        url,
        dest,
        description="ETOPO 高程",
        force=force,
        magic=MAGIC_NETCDF,
    )

    print(
        "Natural Earth 10m 国界由根目录 download_data.py 预取到共享缓存 "
        "(data/cartopy/), 本脚本不再下载."
    )
    if region == "myanmar":
        print("\n完成。现在可运行: python Myanmar/main.py render --sheet myanmar")
    else:
        print("\n完成。现在可运行: python Myanmar/main.py render --sheet northern-shan")
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python Myanmar/main.py <子命令>")
