#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download the ETOPO 2022 15-arc-second USSR subset.

是什么: 从 NOAA ERDDAP 下载苏联区域 ETOPO 高程子集(默认 stride=8, 约 45 MB); URL 与
下载范围来自 ``cartopy_file.sources`` 与 ``USSR/config.py``, 文件已就位时跳过、不重复下载.
Natural Earth 国界/海岸线由根目录 ``download_data.py`` 预取到共享缓存, 这里不再下载.
本文件是模块, 只导出 ``run()``; 命令行入口是 ``USSR/main.py download``.
完整说明(数据来源、下载范围、断点续传与退出码)见 ``docs/maps/ussr.md`` 与
``docs/data-preparation.md``.
"""

from __future__ import annotations

# 子项目配置(数据集清单 + 画框)与下载层, 见 docs/reference/datasets.md.
import config
from cartopy_file import fetch
from cartopy_file.sources import erddap_url


def run(*, stride: int = 8, force: bool = False) -> int:
    """下载(或确认已存在)ETOPO 苏联子集; 返回 0. 由 ``USSR/main.py download`` 调用."""
    if stride < 1:
        raise ValueError("--stride 必须 >= 1")

    datasets = config.DATASETS

    # ETOPO 子集: 文件名带 stride, 不同步长的文件可以共存(drawing 侧按步长挑).
    # 下载范围来自 config.py 的 ETOPO_BBOX_USSR, 与「这份数据覆盖多大」是同一个对象.
    bbox = config.ETOPO_BBOX_USSR
    etopo_path = datasets.raw_dir / f"ETOPO_2022_v1_15s_ussr_stride{stride}.nc"
    url = erddap_url(
        "etopo-2022",
        stride=stride,
        lon_range=(bbox.lon_min, bbox.lon_max),
        lat_range=(bbox.lat_min, bbox.lat_max),
    )
    print(f"下载 ETOPO 2022 苏联区域高程 (stride={stride})")
    print(url)
    fetch.download(
        url,
        etopo_path,
        description="ETOPO 高程",
        force=force,
        magic=fetch.MAGIC_NETCDF,
    )

    print("\n完成。现在可运行: python USSR/main.py render")
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python USSR/main.py <子命令>")
