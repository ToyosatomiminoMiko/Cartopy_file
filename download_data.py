#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Prefetch the shared cartopy basemap data and check the project data inventory.

是什么: 预取全项目共用的 Natural Earth 底图; ``--check`` 只检查数据清单是否就位(不联网).
完整说明(为什么集中预取、缓存位置与退出码)见 ``docs/download_data.md``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from cartopy.io import shapereader

from cartopy_file.data import (
    configure_cartopy,
    natural_earth_paths,
    project_root,
    shared_data_dir,
)

# cartopy 内置底图: (分辨率, 类别, 名称, 使用位置).
# 名称必须与 cartopy.feature 里的一致, 否则会下到用不上的数据.
NE_FEATURES = [
    # 缅甸系列(myanmar.py / northern_shan.py)显式使用 10m.
    ("10m", "physical", "coastline", "myanmar.py 海岸线 / ukraine.py 剪国界岸段"),
    ("10m", "cultural", "admin_0_boundary_lines_land", "myanmar.py / ukraine.py 国界"),
    ("10m", "physical", "rivers_lake_centerlines", "northern_shan.py / ukraine.py 河流"),
    ("10m", "physical", "lakes", "northern_shan.py 湖泊"),
    # 全球/苏联图按范围自动选 110m(cartopy 的 AdaptiveScaler 默认比例尺).
    ("110m", "physical", "land", "AmericaArmy/main.py 陆地底色"),
    ("110m", "physical", "ocean", "AmericaArmy/main.py 海洋底色"),
    ("110m", "physical", "coastline", "ussr.py / AmericaArmy/main.py 海岸线"),
    ("110m", "physical", "lakes", "AmericaArmy/main.py 湖泊"),
    ("110m", "physical", "rivers_lake_centerlines", "AmericaArmy/main.py 河流"),
    ("110m", "cultural", "admin_0_boundary_lines_land", "ussr.py / AmericaArmy/main.py 国界"),
]

# 各图种自己的数据: (分组, 说明, 相对仓库根的 glob, 缺失时的准备命令).
# 用 glob 是为了兼容不同 stride 的文件名: 同一区域只下载一次, 之后按文件名
# 复用分辨率最高的一份, 不会再下载.
LOCAL_DATA = [
    ("缅甸", "ETOPO 2022 缅甸区域高程", "Myanmar/data/ETOPO_2022_v1_15s_myanmar_stride*.nc",
     "python Myanmar/download_etopo.py"),
    ("缅甸", "掸邦放大图高程", "Myanmar/data/ETOPO_2022_v1_15s_northern_shan_stride*.nc",
     "python Myanmar/download_etopo.py --region northern_shan --stride 1"),
    ("缅甸", "Natural Earth 10m 国界", "Myanmar/data/ne_10m_admin_0_countries/*.shp",
     "python Myanmar/download_etopo.py"),
    ("缅甸", "Natural Earth 10m 河流", "Myanmar/data/ne_10m_rivers_lake_centerlines/*.shp",
     "python Myanmar/prepare_admin_data.py"),
    ("缅甸", "省邦级行政区 GeoJSON", "Myanmar/data/myanmar_admin1.geojson",
     "python Myanmar/prepare_admin_data.py"),
    ("缅甸", "OSM 特区/自治区域边界", "Myanmar/data/regions/shan_north_boundaries.geojson",
     "python Myanmar/download_regions.py"),
    ("缅甸", "OSM 画框附近国界", "Myanmar/data/regions/osm_country_borders.geojson",
     "python Myanmar/download_regions.py"),
    ("苏联", "ETOPO 2022 苏联区域高程", "USSR/data/ETOPO_2022_v1_15s_ussr_stride*.nc",
     "python USSR/download_etopo.py"),
    ("苏联", "Natural Earth 10m 国界", "USSR/data/ne_10m_admin_0_countries/*.shp",
     "python USSR/download_etopo.py"),
    ("乌克兰", "ETOPO 2022 乌克兰区域高程", "Ukraine/data/ETOPO_2022_v1_15s_ukraine_stride*.nc",
     "python Ukraine/download_data.py"),
    ("乌克兰", "Natural Earth 10m 国界", "Ukraine/data/ne_10m_admin_0_countries/*.shp",
     "python Ukraine/download_data.py"),
    ("乌克兰", "GADM 4.1 乌克兰一级行政区", "Ukraine/data/gadm41_UKR/gadm41_UKR_1.json",
     "python Ukraine/download_data.py"),
    ("乌克兰", "OCHA 2021 GCA/NGCA 分区", "Ukraine/data/ocha_gca_ngca/*.shp",
     "python Ukraine/download_data.py"),
    ("乌克兰", "1991 年边界/州界", "Ukraine/data/ukraine_1991.geojson",
     "python Ukraine/download_data.py"),
    ("乌克兰", "2014 年克里米亚控制线", "Ukraine/data/crimea_2014_line.geojson",
     "python Ukraine/download_data.py"),
    ("乌克兰", "2014 年顿巴斯控制区", "Ukraine/data/occupied_2014.geojson",
     "python Ukraine/download_data.py"),
    ("乌克兰", "2014 年顿巴斯接触线", "Ukraine/data/contact_line_2014.geojson",
     "python Ukraine/download_data.py"),
    ("乌克兰", "2022 年俄方宣称四州边界", "Ukraine/data/claimed_2022.geojson",
     "python Ukraine/download_data.py"),
    ("美军基地", "基地点位 GeoJSON", "AmericaArmy/data.geojson", "(仓库自带, 无需下载)"),
]

# 可选缓存: 缺了不影响出图, 只是下次跑数据准备脚本会重新联网取.
OPTIONAL_DATA = [
    ("缅甸", "GADM 4.1 原始行政区 JSON", "Myanmar/data/gadm41_MMR/gadm41_MMR_1.json"),
    ("缅甸", "OSM 内比都联邦区缓存", "Myanmar/data/osm_naypyidaw_union_territory.json"),
]


def _first_match(root: Path, pattern: str) -> Path | None:
    matches = sorted(root.glob(pattern))
    return matches[0] if matches else None


def check_inventory(verbose: bool = True) -> int:
    """打印数据清单; 返回缺失的必需项数量(0 表示齐全)."""
    root = project_root()
    configure_cartopy()

    missing = 0
    missing_hints: list[str] = []

    if verbose:
        print("== cartopy 共用底图 (data/cartopy)")
    for resolution, category, name, usage in NE_FEATURES:
        existing, target = natural_earth_paths(resolution, category, name)
        label = f"ne_{resolution}_{name}"
        if existing is None:
            missing += 1
            missing_hints.append("python download_data.py")
            if verbose:
                print(f"  [缺失] {label:<45s} {usage}  -> {target}")
        elif verbose:
            print(f"  [已存在] {label:<43s} {existing}")

    if verbose:
        print("\n== 各图种本地数据")
    for group, label, pattern, hint in LOCAL_DATA:
        path = _first_match(root, pattern)
        if path is None:
            missing += 1
            if not hint.startswith("("):
                missing_hints.append(hint)
            if verbose:
                print(f"  [缺失] {group:<6s} {label:<24s} ({pattern})")
        elif verbose:
            print(f"  [已存在] {group:<6s} {label:<24s} {path.relative_to(root)}")

    if verbose and OPTIONAL_DATA:
        print("\n== 可选缓存(缺失不影响出图)")
        for group, label, pattern in OPTIONAL_DATA:
            path = _first_match(root, pattern)
            state = "已存在" if path else "缺失"
            print(f"  [{state}] {group:<6s} {label}")

    if verbose:
        print()
        if missing:
            print(f"共 {missing} 项必需数据缺失. 按下面命令准备(已存在的会自动跳过):")
            for command in dict.fromkeys(missing_hints):
                print(f"  {command}")
        else:
            print("全部数据已就位, 可以直接出图, 不需要再下载.")
    return missing


def _copy_shapefile_set(source: Path, target: Path) -> None:
    """把一套 shapefile(.shp/.shx/.dbf/.prj/.cpg) 从旧缓存复制到项目缓存.

    cartopy 下载时是把 zip 里的这几个文件一起解压的, 复制时也必须成套,
    少一个 .shx/.dbf 时 cartopy 读不出来.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        src = source.with_suffix(suffix)
        if src.exists():
            shutil.copy2(src, target.with_suffix(suffix))


def fetch_shared_features() -> int:
    """下载缺失的共用底图要素; 返回失败数量. 已存在的不联网."""
    configure_cartopy()
    cache_dir = shared_data_dir() / "cartopy"
    print(f"cartopy 共用底图缓存目录: {cache_dir}")

    failures = 0
    downloaded = 0
    for resolution, category, name, usage in NE_FEATURES:
        existing, target = natural_earth_paths(resolution, category, name)
        label = f"ne_{resolution}_{name}"
        if existing is not None:
            if existing.resolve() != target.resolve():
                # 旧缓存(~/.local/share/cartopy)里有, 但项目缓存里没有:
                # 复制进项目缓存, 让仓库数据自包含, 以后即使 HOME 缓存
                # 不在了也不用重新下载.
                _copy_shapefile_set(existing, target)
                print(f"复制到项目缓存: {label} -> {target}")
            else:
                print(f"跳过(已存在): {label} -> {existing}")
            continue
        print(f"下载: {label} ({usage}) -> {target}")
        try:
            path = shapereader.natural_earth(resolution, category, name)
        except Exception as exc:  # noqa: BLE001 - 单个要素失败不应中断其余要素
            failures += 1
            print(f"  失败: {exc}", file=sys.stderr)
            continue
        downloaded += 1
        print(f"  完成: {path}")

    print(f"\n本次下载 {downloaded} 个要素, 失败 {failures} 个, 共需要 {len(NE_FEATURES)} 个.")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查数据清单, 不下载; 有缺失时退出码为 1",
    )
    args = parser.parse_args()

    if args.check:
        missing = check_inventory(verbose=True)
        sys.exit(0 if missing == 0 else 1)

    failures = fetch_shared_features()
    print()
    check_inventory(verbose=True)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
