#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Volga subproject entry point: render the two Volga maps.

是什么: 伏尔加子项目唯一的可执行入口, 只有 ``render`` 子命令; 出流域图与周边共和国图,
地图进 ``Volga/map/``, 文字信息进 ``Volga/text/``. 数据(ETOPO/GADM/HydroBASINS 原始
数据与派生流域 GeoJSON)由独立数据项目 miko_gis_data 准备, 本入口不再提供 download/prepare.
完整说明(数据源/两个准备步骤的分工/出图命令)见 ``docs/maps/volga.md``.
"""

from __future__ import annotations

import argparse
import sys

# render --sheet 的取值; all = 两张都出.
SHEETS = ("all", "basin", "republics")


def build_parser() -> argparse.ArgumentParser:
    """构造命令行: 只有 render 子命令(数据准备在 miko_gis_data)."""
    parser = argparse.ArgumentParser(
        prog="python Volga/main.py",
        description="伏尔加河流域子项目统一入口: 出两张图(数据由 miko_gis_data 准备).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    render = subparsers.add_parser("render", help="出图(地图进 map/, 文字信息进 text/)")
    render.add_argument(
        "--sheet",
        choices=SHEETS,
        default="all",
        help="只出其中一张图; 缺省 all 两张都出(产物与改前一致)",
    )
    render.add_argument(
        "--stride",
        type=int,
        default=None,
        help="使用数据根里对应采样步长的 ETOPO 文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    render.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="内嵌晕渲栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    render.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    return parser


def run(argv: list[str] | None = None) -> int:
    """解析子命令并执行; 返回退出码(0 成功)."""
    args = build_parser().parse_args(argv)

    from volga import run as render_run

    sheets = None if args.sheet == "all" else (args.sheet,)
    return render_run(sheets=sheets, stride=args.stride, dpi=args.dpi, show=args.show)


if __name__ == "__main__":
    try:
        status = run()
    except KeyboardInterrupt:
        print("\n用户中断.", file=sys.stderr)
        status = 130
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        status = 1
    raise SystemExit(status)
