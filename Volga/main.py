#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Volga subproject entry point: prepare derived data and render the two maps.

是什么: 伏尔加子项目唯一的可执行入口. ``prepare`` 读数据仓的原始数据, 按本图口径派生
流域/行政区/国界三个 GeoJSON 到 ``Volga/build/``; ``render`` 出流域图与周边共和国图,
地图进 ``Volga/map/``, 文字信息进 ``Volga/text/``.
子命令用懒导入: prepare 只加载 shapely/geopandas, render 才加载 matplotlib/cartopy.
完整说明(数据源/两个子命令的分工/出图命令)见 ``docs/maps/volga.md`` 与
``docs/reference/prepare.md``.
"""

from __future__ import annotations

import argparse
import sys

# render --sheet 的取值; all = 两张都出.
SHEETS = ("all", "basin", "republics")


def build_parser() -> argparse.ArgumentParser:
    """构造命令行: prepare(派生) 与 render(出图) 两个子命令."""
    parser = argparse.ArgumentParser(
        prog="python Volga/main.py",
        description="伏尔加河流域子项目统一入口: 派生数据(prepare)与出两张图(render).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    prepare = subparsers.add_parser(
        "prepare",
        help="读数据仓原始数据, 重建 Volga/build/ 下的三个派生 GeoJSON",
    )
    prepare.add_argument(
        "--skip-basin",
        action="store_true",
        help="跳过流域派生, 只重建行政区与国界",
    )

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

    if args.command == "prepare":
        from prepare import run as prepare_run

        return prepare_run(skip_basin=args.skip_basin)

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
