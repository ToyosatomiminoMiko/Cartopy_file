#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Myanmar subproject entry point: download / prepare / render / all.

是什么: 缅甸子项目的唯一可执行入口. ``download`` 把 ETOPO 高程子集、OSM 特区边界/国界,
以及行政区派生所需的 GADM/NE 河流/OSM 内比都原始数据下载/入库到 ``Myanmar/data/raw/``;
``prepare`` 只读 ``raw/`` 重建 ``Myanmar/data/derived/myanmar_admin1.geojson``(不联网);
``render`` 按 ``--sheet`` 出一到三张图, 地图进 ``Myanmar/map/``、文字信息进
``Myanmar/text/``; ``all`` 依次跑前三个子命令.
为什么只有一个入口: 全项目约定「一个子项目一个可执行文件, 其余 .py 只导出 run()」;
参数解析与退出码归这里, 模块不再各自解析命令行; 子命令分派用懒导入, download 不加载
matplotlib/cartopy, render 不加载下载栈.
完整说明(三张图的投影/数据源/运行方式)见 ``docs/maps/myanmar.md``、
``docs/maps/myanmar-admin.md`` 与 ``docs/maps/northern-shan.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md;
# 各渲染模块自己也会 setdefault, 这里提前设好保证缓存始终落在仓库内.
ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / ".mplcache"))

# download --region 的取值 -> download_etopo 内部的区域名(下划线形式: 下载文件名与
# find_etopo 的 glob 都用它). all = 两个 ETOPO 区域都下载.
DOWNLOAD_REGIONS = {
    "myanmar": "myanmar",
    "northern-shan": "northern_shan",
}

# render --sheet 的取值 -> 对应的渲染模块名(按需导入). 渲染顺序始终按
# config.SHEETS 登记的顺序, 不按本字典的顺序.
RENDER_MODULES = {
    "myanmar": "myanmar",
    "myanmar-admin": "myanmar_admin",
    "northern-shan": "northern_shan",
}


def build_parser() -> argparse.ArgumentParser:
    """构造命令行: download / prepare / render / all 四个子命令."""
    parser = argparse.ArgumentParser(
        prog="python Myanmar/main.py",
        description="缅甸子项目统一入口: 下载数据、重建派生 GeoJSON、出图.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    download = subparsers.add_parser(
        "download", help="下载 ETOPO 子集、OSM 特区边界/国界与行政区原始数据"
    )
    download.add_argument(
        "--region",
        choices=("all", *DOWNLOAD_REGIONS),
        default="all",
        help="下载区域: all=两个 ETOPO 区域都下载(默认), myanmar=缅甸全境, northern-shan=掸邦放大图",
    )
    download.add_argument(
        "--stride",
        type=int,
        default=None,
        help="覆盖两个 ETOPO 区域的默认步长; 缺省各用 config 登记值(缅甸 2, 掸邦 1)",
    )
    download.add_argument("--force", action="store_true", help="覆盖已存在的下载文件")
    download.add_argument(
        "--skip-regions",
        action="store_true",
        help="跳过掸邦特区边界/国界下载(其余 ETOPO 与行政区原始数据照常准备)",
    )

    subparsers.add_parser("prepare", help="由原始数据重建行政区 GeoJSON")

    render = subparsers.add_parser("render", help="出图(地图 SVG + 同名 geo.json)")
    render.add_argument(
        "--sheet",
        choices=("all", *RENDER_MODULES),
        default="all",
        help="只出其中一张图; 缺省 all 按 config.SHEETS 顺序出全部三张",
    )
    render.add_argument(
        "--stride",
        type=int,
        default=None,
        help="使用 data/raw 下对应采样步长的 ETOPO 文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    render.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="内嵌栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    render.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")

    all_cmd = subparsers.add_parser("all", help="依次 download -> prepare -> render")
    all_cmd.add_argument(
        "--stride",
        type=int,
        default=None,
        help="覆盖两个 ETOPO 区域的默认步长, 同时用于挑选出图用的高程文件",
    )
    all_cmd.add_argument("--force", action="store_true", help="覆盖已存在的下载文件")
    all_cmd.add_argument(
        "--skip-regions",
        action="store_true",
        help="跳过 OSM 特区边界/国界下载(掸邦图会因缺区域数据失败)",
    )
    all_cmd.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="内嵌栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    all_cmd.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    return parser


def download(
    *,
    region: str = "all",
    stride: int | None = None,
    force: bool = False,
    skip_regions: bool = False,
) -> int:
    """下载三组原始数据: ETOPO 子集、掸邦特区边界/国界、行政区派生所需的 GADM/河流/缓存.

    为什么行政区那三份也在这里下: ``prepare_admin_data.py`` 约定只读 ``raw/`` 不联网,
    「下载」这件事必须只有 download 一个入口; 三组数据源不同(ERDDAP/Overpass/GADM),
    各自有独立模块, 本函数只负责编排与退出码.
    """
    from download_etopo import run as download_etopo_run

    regions = list(DOWNLOAD_REGIONS) if region == "all" else [region]
    for cli_region in regions:
        status = download_etopo_run(
            region=DOWNLOAD_REGIONS[cli_region], stride=stride, force=force
        )
        if status != 0:
            return status

    if not skip_regions:
        from download_regions import run as download_regions_run

        status = download_regions_run(force=force)
        if status != 0:
            return status
    else:
        print("已跳过掸邦特区边界/国界下载 (--skip-regions).")

    from download_admin_data import run as download_admin_run

    return download_admin_run(force=force)


def prepare() -> int:
    """由原始数据重建行政区 GeoJSON; 返回进程退出码."""
    from prepare_admin_data import run as prepare_run

    return prepare_run()


def render(
    *,
    sheet: str = "all",
    stride: int | None = None,
    dpi: int | None = None,
    show: bool = False,
) -> int:
    """按 ``config.SHEETS`` 的顺序渲染一或三张图; 返回进程退出码.

    为什么渲染顺序不按命令行选项字母序: ``config.SHEETS`` 是产物登记顺序, 也是
    check_geo 的检查顺序; 逐张渲染与 all 得到同一组文件.
    """
    import config
    from importlib import import_module

    sheet_ids = [item.id for item in config.SHEETS]
    if sheet != "all":
        sheet_ids = [sheet]
    for sheet_id in sheet_ids:
        module_name = RENDER_MODULES.get(sheet_id)
        if module_name is None:
            print(
                f"错误: 未知的图种 {sheet_id!r}; 可选: {', '.join(RENDER_MODULES)}",
                file=sys.stderr,
            )
            return 1
        status = import_module(module_name).run(stride=stride, dpi=dpi, show=show)
        if status != 0:
            return status
    return 0


def run(argv: list[str] | None = None) -> int:
    """解析命令行并按子命令分派; 返回进程退出码(0 成功).

    为什么分派处才 import: 命令行解析与下载/几何/绘图栈解耦, ``download`` 不加载
    matplotlib/cartopy, ``render`` 不加载下载模块, ``all`` 依次调用三者.
    """
    args = build_parser().parse_args(argv)

    if args.command == "download":
        return download(
            region=args.region,
            stride=args.stride,
            force=args.force,
            skip_regions=args.skip_regions,
        )

    if args.command == "prepare":
        return prepare()

    if args.command == "render":
        return render(sheet=args.sheet, stride=args.stride, dpi=args.dpi, show=args.show)

    # all: download -> prepare -> render, 任一步失败就停, 不带着缺数据继续往下跑.
    status = download(
        region="all", stride=args.stride, force=args.force, skip_regions=args.skip_regions
    )
    if status != 0:
        return status
    status = prepare()
    if status != 0:
        return status
    return render(sheet="all", stride=args.stride, dpi=args.dpi, show=args.show)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\n用户中断。可重新运行以续传未完成的下载。", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
