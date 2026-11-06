#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download and cache the raw inputs for the Ukraine overview map.

是什么: 下载乌克兰全图所需的原始数据(ETOPO/GADM/OCHA/OSM)到 ``Ukraine/data/raw/``,
只取数、不加工; 绘图用的派生 GeoJSON 由 ``Ukraine/prepare_data.py`` 生成.
下载地址、下载范围与本地路径全部来自 ``Ukraine/config.py``, 原始文件"已存在就跳过".
完整说明: ``docs/maps/ukraine.md``(数据来源/运行方式); 数据集层口径见
``docs/reference/datasets.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

# 下载层(续传/重试/魔数校验/解压), 见 docs/reference/datasets.md.
from cartopy_file.fetch import (
    MAGIC_JSON,
    MAGIC_NETCDF,
    MAGIC_ZIP,
    download,
    extract_zip,
    post,
)

# Overpass 公共实例: 依次尝试, 前一个 502/超时就换下一个.
from cartopy_file.sources import overpass_endpoints

# 数据集清单与下载参数(URL/bbox/本地路径的唯一真源), 见 docs/reference/spec.md.
import config

# ============================
# 路径
# ============================
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATASETS = config.DATASETS
# OCHA 压缩包落在 raw/ 根, 解压目录是 Dataset.dest(raw/ 与 derived/ 的目录口径见 config.py).
OCHA_DIR = DATASETS.path("ocha-gca-ngca")
OCHA_ZIP = DATA_DIR / config.OCHA_ARCHIVE


# ============================
# 下载(URL/bbox/路径全部来自 config.py; 已存在就跳过)
# ============================
def _fetch(dataset_id: str, description: str, *, magic=(), force: bool = False) -> Path:
    """按 config 里的数据集下载单个文件; 已存在且非空时 fetch.download 会跳过."""
    item = DATASETS.get(dataset_id)
    return download(
        item.url,
        DATASETS.path(item),
        description=description,
        force=force,
        magic=magic,
    )


def fetch_etopo(force: bool) -> None:
    print(f"下载 ETOPO 2022 乌克兰区域高程 (stride={config.ETOPO_STRIDE}, 约 30 弧秒)")
    print(f"  {DATASETS.get('etopo-ukraine').url}")
    _fetch("etopo-ukraine", "ETOPO 高程", magic=MAGIC_NETCDF, force=force)


def fetch_gadm(force: bool) -> None:
    print("下载 GADM 4.1 乌克兰一级行政区")
    _fetch("gadm41-ukr", "GADM 乌克兰一级行政区", magic=MAGIC_JSON, force=force)


def fetch_ocha(force: bool) -> None:
    print("下载 OCHA/HDX 2021 HNO 顿巴斯 GCA/NGCA 分区")
    item = DATASETS.get("ocha-gca-ngca")
    if DATASETS.exists(item) and not force:
        # 解压目录已就位时连压缩包都不碰: 删掉中间 zip 不该触发重新联网.
        print(f"已存在, 跳过 {item.note}: {DATASETS.path(item)}")
        return
    download(
        item.url,
        OCHA_ZIP,
        description="OCHA GCA/NGCA",
        force=force,
        magic=MAGIC_ZIP,
    )
    extract_zip(OCHA_ZIP, DATASETS.path(item), force=force)


def ensure_shared_layers() -> int:
    """检查共享缓存里的 Natural Earth 图层; 缺失只提示, 不在这里下载.

    为什么不在子项目里下: 这些图层是全仓共用的(cartopy 的 NEShpDownloader 管理),
    仓库根的 ``python download_data.py`` 统一预取; 子项目再下一份只会造成副本漂移.
    """
    missing = [
        item
        for item in DATASETS
        if item.kind == "cartopy-ne" and not DATASETS.exists(item)
    ]
    for item in missing:
        print(
            f"警告: 缺少共享 Natural Earth 图层 {item.resolution}/{item.category}/{item.name}; "
            "请先在仓库根运行: python download_data.py"
        )
    return len(missing)


def _overpass(item, force: bool) -> None:
    """执行一条 Overpass QL 查询, 把原始 JSON 缓存到 dest(已存在则跳过).

    为什么不在绘图时联网: 渲染应该只读本地文件; 这里下载一次, 之后
    ``prepare_data.py`` 每次都从这份 JSON 重建派生 GeoJSON.
    为什么要换实例重试: 公共实例按请求排队, 高峰时会直接 502 或长时间排队;
    fetch.post 内部已按 3 次退避重试, 这里再按 sources 登记的实例依次轮换.
    """
    body = urllib.parse.urlencode({"data": config.OSM_QUERIES[item.id]}).encode()
    dest = DATASETS.path(item)
    last_error: Exception | None = None
    for endpoint in overpass_endpoints():
        try:
            post(endpoint, body, dest, description=item.note or item.id, force=force)
            payload = json.loads(dest.read_text(encoding="utf-8"))
            if "elements" not in payload:
                dest.unlink(missing_ok=True)
                raise RuntimeError(f"Overpass 返回异常(没有 elements): {endpoint}")
            print(
                f"完成: {dest.name} "
                f"({dest.stat().st_size / 1048576:.1f} MiB, {len(payload['elements'])} 元素)"
            )
            return
        except (OSError, ValueError, RuntimeError) as exc:
            last_error = exc
            print(f"  Overpass 失败({endpoint}): {exc}")
    raise RuntimeError(f"Overpass 下载失败: {item.note or item.id}: {last_error}")


def fetch_osm(force: bool) -> None:
    """下载全部 OSM 原始 JSON 缓存(河流/水库/德左边界/下游补段)."""
    print("下载 OpenStreetMap 河流与边界原始关系 (Overpass)")
    for item in DATASETS:
        if item.kind == "script" and item.source_id == "openstreetmap":
            _overpass(item, force=force)


# ============================
# 检查与主流程
# ============================
_STATE_LABELS = {
    "ok": "已存在",
    "missing": "缺失",
    "drifted": "版本漂移",
    "optional": "可选缺失",
}


def _missing_hint(dataset_id: str) -> str:
    """缺失项该跑哪个脚本: 原始数据归本脚本, 派生 GeoJSON 归 prepare_data.py.

    为什么要分流: 两个脚本各自只做一件事, 打印一条"万能命令"会让用户先跑错再发现.
    """
    kind = DATASETS.get(dataset_id).kind
    if kind == "derived":
        return "python Ukraine/prepare_data.py"
    if kind == "cartopy-ne":
        return "python download_data.py"
    return "python Ukraine/download_data.py"


def check_outputs(verbose: bool = True) -> int:
    """只检查、不联网: 返回缺失/漂移项数量(0 表示可以离线出图)."""
    lines = DATASETS.check()
    failed = [line for line in lines if line.failed]
    if verbose:
        for line in lines:
            print(f"  [{_STATE_LABELS[line.state]}] {line.dataset_id}: {line.detail}")
        if failed:
            print(f"\n共 {len(failed)} 项缺失/漂移, 请按下面命令准备(已存在的会自动跳过):")
            for command in sorted({_missing_hint(line.dataset_id) for line in failed}):
                print(f"  {command}")
        else:
            print("\n全部数据已就位, 可以运行: python Ukraine/ukraine.py")
    return len(failed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只检查数据是否齐全, 不联网")
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载原始数据(派生 GeoJSON 由 prepare_data.py 重建, 不受影响)",
    )
    args = parser.parse_args()

    if args.check:
        sys.exit(0 if check_outputs(verbose=True) == 0 else 1)

    fetch_etopo(force=args.force)
    ensure_shared_layers()
    fetch_gadm(force=args.force)
    fetch_ocha(force=args.force)
    fetch_osm(force=args.force)

    print("\n原始数据下载完成; 派生 GeoJSON 请运行: python Ukraine/prepare_data.py")
    check_outputs(verbose=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断; 重新运行可继续下载未完成的文件.")
        sys.exit(130)
