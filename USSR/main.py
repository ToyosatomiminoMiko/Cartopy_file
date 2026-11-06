#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""USSR subproject entry point: download ETOPO and render the USSR map.

是什么: 苏联子项目的唯一可执行入口. ``download`` 调下载模块把 ETOPO 子集写进
``USSR/data/raw/``; ``render`` 调绘图模块出图, 地图进 ``USSR/map/``,文字信息进
``USSR/text/``; ``all`` 先 download 再 render.
为什么只有一个入口: 全项目约定「一个子项目一个可执行文件, 其余 .py 只导出 run()」;
参数解析与退出码归这里, 模块不再各自解析命令行. 子命令分派用懒导入, 只有真正执行的那
一步才加载网络栈或 matplotlib/cartopy.
完整说明(投影,数据来源,运行方式)见 ``docs/maps/ussr.md``.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """构造命令行: download / render / all 三个子命令."""
    parser = argparse.ArgumentParser(
        prog="python USSR/main.py",
        description="苏联子项目统一入口: 准备 ETOPO 数据并出图.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    download = subparsers.add_parser("download", help="下载 ETOPO 2022 苏联区域高程子集")
    download.add_argument(
        "--stride",
        type=int,
        default=8,
        help="ERDDAP 采样步长;1=完整 15 弧秒,2=30 弧秒,4=1 弧分,8=2 弧分(默认,适合 300 dpi 出图)",
    )
    download.add_argument("--force", action="store_true", help="覆盖已存在的下载文件")

    render = subparsers.add_parser("render", help="出图(地图 SVG + 同名 geo.json)")
    render.add_argument(
        "--stride",
        type=int,
        default=None,
        help="使用 data/raw 下对应采样步长的高程文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    render.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="内嵌栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    render.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")

    all_cmd = subparsers.add_parser("all", help="先 download 再 render")
    all_cmd.add_argument(
        "--stride",
        type=int,
        default=8,
        help="ERDDAP 采样步长, 同时用于下载与挑选出图用的高程文件(默认 8)",
    )
    all_cmd.add_argument("--force", action="store_true", help="覆盖已存在的下载文件")
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

    为什么分派处才 import: 命令行解析与网络栈/绘图栈解耦, download 不加载 matplotlib,
    render 不加载下载模块, all 依次调用两者.
    """
    args = build_parser().parse_args(argv)

    if args.command == "download":
        from download_etopo import run as download_run

        return download_run(stride=args.stride, force=args.force)

    if args.command == "render":
        from ussr import run as render_run

        return render_run(stride=args.stride, dpi=args.dpi, show=args.show)

    from download_etopo import run as download_run
    from ussr import run as render_run

    status = download_run(stride=args.stride, force=args.force)
    if status != 0:
        return status
    return render_run(stride=args.stride, dpi=args.dpi, show=args.show)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\n用户中断.可重新运行脚本以续传未完成的文件.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
