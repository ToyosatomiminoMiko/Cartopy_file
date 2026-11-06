#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download the raw datasets that ``prepare_admin_data.py`` derives from.

是什么: 把行政区图所需的三份原始数据原样下载/解压到 ``Myanmar/data/raw/``:
GADM 4.1 缅甸一级行政区 JSON,Natural Earth 10m 河流(钉在 5.0.0 旧副本),
OSM 内比都联邦区 relation 的 Overpass 响应. 不做任何几何加工, 派生
``myanmar_admin1.geojson`` 是 ``prepare_admin_data.py`` 的事.
为什么单独一个模块: 全项目约定 ``download_*.py`` 只下载,``prepare_*.py`` 只读
``raw/`` 且不联网(见 docs/data-preparation.md); 这三份数据只被行政区图使用, 与
ETOPO,掸邦特区边界不同源不同频次, 分开才能单独重跑.
本文件是模块, 只导出 ``run()``, 由统一入口 ``python Myanmar/main.py download`` 调用.
完整说明(为什么混用 GADM/OSM,为什么补缝)见 ``docs/maps/myanmar-admin.md``;
数据集层见 ``docs/reference/datasets.md``.
"""

from __future__ import annotations

import urllib.parse

# 原始数据路径与版本都来自数据集清单, 不在本文件重写.
import config
from cartopy_file.fetch import MAGIC_JSON, MAGIC_ZIP, download, extract_zip, post
from cartopy_file.sources import gadm_url, overpass_endpoints

ADMIN_JSON = config.DATASETS.path(config.GADM_MMR_RAW)
RIVER_DIR = config.DATASETS.path(config.NE_RIVERS)
RIVER_SHP = RIVER_DIR / "ne_10m_rivers_lake_centerlines.shp"
NPT_JSON = config.DATASETS.path(config.NAYPYIDAW_CACHE)
NPT_RELATION_ID = 5996482


def download_rivers(*, force: bool = False) -> None:
    """下载并解压 Natural Earth 10m 河流(5.0.0 旧副本); 已解压时跳过.

    为什么钉住版本: 河网几何参与成品, 换版会改变图面; 共享缓存里若有别的版本不能
    顶替, 详见 docs/reference/datasets.md.
    """
    if RIVER_SHP.is_file() and not force:
        print(f"已存在, 跳过 Natural Earth 10m 河流: {RIVER_DIR}")
        return
    dataset = config.NE_RIVERS
    archive = RIVER_DIR.with_suffix(".zip")
    download(
        dataset.url,
        archive,
        description="Natural Earth 10m 河流压缩包",
        magic=MAGIC_ZIP,
        force=force,
    )
    extract_zip(archive, RIVER_DIR, force=force)
    # 版本号只在解压出来的 VERSION.txt 里, 下载地址不带版本号.
    found = config.DATASETS.version_of(dataset)
    if found and dataset.version and found != dataset.version:
        print(
            f"警告: 河流数据版本是 {found}, 期望 {dataset.version}; "
            "换版会改变河网几何, 请复核产物."
        )


def download_gadm(*, force: bool = False) -> None:
    """下载 GADM 4.1 缅甸一级行政区 JSON; 已存在时跳过."""
    download(
        gadm_url("MMR"),
        ADMIN_JSON,
        description="GADM 4.1 缅甸一级行政区",
        magic=MAGIC_JSON,
        force=force,
    )


def download_naypyidaw(*, force: bool = False) -> None:
    """抓取 OSM 内比都联邦区 relation 原始响应并缓存; 已缓存时跳过.

    为什么走 Overpass 并轮换镜像: 这是 relation 的原始快照, 公共实例偶尔返回 502,
    换镜像重试可以避免整个数据准备流程中断; 缓存只在缺失时请求, 不反复打公共接口.
    """
    query = f"[out:json][timeout:90];rel({NPT_RELATION_ID});out geom;"
    body = urllib.parse.urlencode({"data": query}).encode()
    last_error: Exception | None = None
    for url in overpass_endpoints():
        try:
            post(
                url,
                body,
                NPT_JSON,
                description="OSM 内比都联邦区",
                retries=2,
                timeout=180,
                force=force,
            )
            return
        except RuntimeError as exc:  # fetch.post 重试用尽后的统一异常
            last_error = exc
            print(f"  Overpass 请求失败 ({url}): {exc}")
    raise RuntimeError(f"无法从 Overpass 获取内比都联邦区边界: {last_error}")


def run(*, force: bool = False) -> int:
    """下载行政区派生所需的全部原始数据; 返回 0=成功."""
    download_gadm(force=force)
    download_rivers(force=force)
    download_naypyidaw(force=force)
    return 0


if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python Myanmar/main.py download")
