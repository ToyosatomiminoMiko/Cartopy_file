#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Ukraine subproject entry point: download, prepare and render the overview map.

是什么: 乌克兰子项目的唯一可执行入口. ``download`` 把原始数据下载/入库到
``Ukraine/data/raw/``; ``prepare`` 由原始数据重建 ``Ukraine/data/derived/`` 的派生 GeoJSON;
``render`` 出图, 地图进 ``Ukraine/map/``、文字信息进 ``Ukraine/text/``; ``all`` 依次跑
前三个子命令.
为什么只有一个入口: 全项目约定「一个子项目一个可执行文件, 其余 .py 只导出 run()」;
参数解析与退出码归这里, 模块不再各自解析命令行. 子命令分派用懒导入, 只有真正执行的那一步
才加载下载/几何/绘图栈.
完整说明(设计取舍/数据来源/运行方式)见 ``docs/maps/ukraine.md``.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """构造命令行: download / prepare / render / all 四个子命令."""
    parser = argparse.ArgumentParser(
        prog="python Ukraine/main.py",
        description="乌克兰子项目统一入口: 下载原始数据、重建派生 GeoJSON、出图.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    download = subparsers.add_parser("download", help="下载/入库原始数据到 data/raw/")
    download.add_argument("--force", action="store_true", help="强制重新下载原始数据")
    download.add_argument("--check", action="store_true", help="只检查数据是否齐全, 不联网")

    subparsers.add_parser("prepare", help="由 data/raw/ 重建 data/derived/ 派生 GeoJSON")

    render = subparsers.add_parser("render", help="出图(地图 SVG + 同名 geo.json)")
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
        help="使用 data/raw 下对应采样步长的 ETOPO 文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    all_cmd.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="内嵌栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    all_cmd.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    return parser


def run(argv: list[str] | None = None) -> int:
    """解析命令行并按子命令分派; 返回进程退出码(0 成功).

    为什么分派处才 import: 命令行解析与下载/几何/绘图栈解耦, ``download`` 不加载绘图栈,
    ``render`` 不加载下载模块, ``all`` 依次调用三者.
    """
    args = build_parser().parse_args(argv)

    if args.command == "download":
        from download_data import run as download_run

        return download_run(force=args.force, check=args.check)

    if args.command == "prepare":
        from prepare_data import run as prepare_run

        return prepare_run()

    if args.command == "render":
        from ukraine import run as render_run

        return render_run(stride=args.stride, dpi=args.dpi, show=args.show)

    # all: download -> prepare -> render, 任一步失败就停, 不再继续后面的步骤.
    from download_data import run as download_run
    from prepare_data import run as prepare_run
    from ukraine import run as render_run

    status = download_run(force=False, check=False)
    if status != 0:
        return status
    status = prepare_run()
    if status != 0:
        return status
    return render_run(stride=args.stride, dpi=args.dpi, show=args.show)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\n用户中断。", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
