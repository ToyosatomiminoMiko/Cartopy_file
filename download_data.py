#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Prefetch the shared Natural Earth basemap data and check the whole-repo data inventory.

是什么: 全仓库数据清单的唯一入口. 清单不再手写, 而是从各子项目 ``<Sub>/specs.py``
的 ``DatasetSet`` 汇总而来; 本脚本只做两件事: 预取全项目共用的 Natural Earth 底图,
以及 ``--check`` 逐项核对本地数据是否就位(不联网).
完整说明(为什么集中预取、目录约定、退出码)见 ``docs/data-preparation.md``.
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys
from pathlib import Path

from cartopy_file.data import (
    configure_cartopy,
    natural_earth_paths,
    project_root,
    subproject_dirs,
)
from cartopy_file.datasets import CheckLine, Dataset, DatasetSet

# 子项目目录就是「层」: 每个目录的 specs.py 声明自己的数据集; 名单由目录结构自动发现.


def load_catalogs() -> list[tuple[str, DatasetSet]]:
    """导入每个子项目的 specs, 取回它声明的 DatasetSet."""
    root = project_root()
    added = str(root) not in sys.path
    if added:
        sys.path.insert(0, str(root))
    try:
        catalogs = []
        for name in subproject_dirs():
            module = importlib.import_module(f"{name}.specs")
            catalog = getattr(module, "DATASETS", None)
            if not isinstance(catalog, DatasetSet):
                raise SystemExit(f"{name}/specs.py 必须导出 DATASETS = dataset_set(...)")
            catalogs.append((name, catalog))
        return catalogs
    finally:
        if added:
            sys.path.remove(str(root))


def shared_ne_datasets(catalogs: list[tuple[str, DatasetSet]]) -> list[Dataset]:
    """汇总所有子项目用到的 Natural Earth 图层(去重), 供共享缓存预取."""
    seen: dict[tuple[str, str, str], Dataset] = {}
    for _, catalog in catalogs:
        for dataset in catalog:
            if dataset.kind != "cartopy-ne":
                continue
            key = (dataset.resolution, dataset.category, dataset.name)
            seen.setdefault(key, dataset)
    return list(seen.values())


def _copy_shapefile_set(source: Path, target: Path) -> None:
    """把一套 shapefile 从旧缓存复制到项目缓存(含 README/VERSION, 便于核对版本).

    cartopy 下载时是把 zip 里的文件一起解压的, 复制时也必须成套: 少一个 .shx/.dbf
    就读不出来; 少了 VERSION.txt 就丢失了「这份缓存是哪个版本」的唯一证据.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".README.html", ".VERSION.txt"):
        src = source.with_suffix(suffix)
        if src.exists():
            shutil.copy2(src, target.with_suffix(suffix))


def fetch_shared_features() -> int:
    """下载缺失的共用 Natural Earth 图层; 返回失败数量. 已存在的不联网."""
    catalogs = load_catalogs()
    configure_cartopy()
    shared = shared_ne_datasets(catalogs)
    print(f"共用 Natural Earth 图层: {len(shared)} 个(来自 {len(catalogs)} 个子项目)")

    failures = 0
    downloaded = 0
    for dataset in shared:
        existing, target = natural_earth_paths(
            dataset.resolution, dataset.category, dataset.name
        )
        label = f"ne_{dataset.resolution}_{dataset.name}"
        if target.exists():
            print(f"跳过(项目缓存已存在): {label}")
            continue
        if existing is not None:
            # 旧缓存(~/.local/share/cartopy)里有: 复制进项目缓存, 让仓库数据自包含,
            # 以后 HOME 缓存没了也不用重新下载.
            _copy_shapefile_set(existing, target)
            print(f"复制到项目缓存: {label} -> {target}")
            continue
        print(f"下载: {label} -> {target}")
        try:
            from cartopy.io import shapereader

            shapereader.natural_earth(dataset.resolution, dataset.category, dataset.name)
        except Exception as exc:  # noqa: BLE001 - 单个图层失败不应中断其余图层
            failures += 1
            print(f"  失败: {exc}", file=sys.stderr)
            continue
        downloaded += 1
        print(f"  完成: {target}")

    print(f"\n本次下载 {downloaded} 个图层, 失败 {failures} 个, 共需要 {len(shared)} 个.")
    return failures


def check_inventory(verbose: bool = True) -> int:
    """打印全仓库数据清单; 返回失败项数量(0 表示齐全)."""
    catalogs = load_catalogs()
    failed = 0
    total = 0
    for name, catalog in catalogs:
        if verbose:
            print(f"== {name}({len(catalog)} 项)")
        for line in catalog.check():
            total += 1
            if line.failed:
                failed += 1
            if verbose:
                print(
                    f"  [{_state_label(line)}] {line.dataset_id:<22s} "
                    f"{line.label:<28s} {line.detail}"
                )
    if verbose:
        print()
        if failed:
            print(f"共 {total} 项数据, {failed} 项缺失或版本不符. 按下面命令准备(已就位的会自动跳过):")
            for command in (
                "python download_data.py",
                "python Myanmar/download_etopo.py",
                "python Myanmar/download_regions.py",
                "python Myanmar/prepare_admin_data.py",
                "python USSR/download_etopo.py",
                "python Ukraine/download_data.py",
                "python Volga/download_data.py",
            ):
                print(f"  {command}")
        else:
            print(f"全部 {total} 项数据已就位, 可以直接出图, 不需要再下载.")
    return failed


def _state_label(line: CheckLine) -> str:
    """把检查状态翻成中文标签, 便于扫清单."""
    return {
        "ok": "已存在",
        "missing": "缺失",
        "drifted": "版本不符",
        "optional": "可选缺失",
    }.get(line.state, line.state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查数据清单, 不下载; 有缺失时退出码为 1",
    )
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check_inventory(verbose=True) == 0 else 1)

    failures = fetch_shared_features()
    print()
    failed = check_inventory(verbose=True)
    if failures or failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
