#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Volga subproject command-line entry: download / prepare / render / all.

是什么: 伏尔加子项目唯一的可执行入口. 子命令分别委托给 ``download_data``(下载/解压),
``prepare_data``(raw -> derived 派生)与 ``volga``(出两张图)三个模块的 ``run()``; 模块按
子命令**延迟导入**, 所以 ``download``/``prepare`` 不会拖起 matplotlib, 三个模块本身也不再
带 argparse. ``all`` 依次跑下载 -> 派生 -> 出图, 任一步失败即停.
完整说明(数据源/两个准备步骤的分工/出图命令)见 ``docs/maps/volga.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md;
# 三个模块自己也会 setdefault, 这里提前设好让最坏情况也落在仓库内.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

# render --sheet 的取值; all = 两张都出.
SHEETS = ("all", "basin", "republics")


def build_parser() -> argparse.ArgumentParser:
    """子命令与参数; 各子命令的选项与对应模块 run() 的参数一一对应."""
    parser = argparse.ArgumentParser(
        prog="python Volga/main.py",
        description="伏尔加河流域子项目统一入口: 下载 ETOPO/GADM/HydroBASINS,派生流域 GeoJSON,出两张图.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    download = subparsers.add_parser("download", help="下载/解压 ETOPO,GADM,HydroBASINS")
    download.add_argument("--check", action="store_true", help="只检查数据是否齐全, 不联网")
    download.add_argument("--force", action="store_true", help="强制重新下载/解压原始数据")
    download.add_argument(
        "--skip-basin", action="store_true", help="跳过 HydroBASINS 下载(只准备 ETOPO 与 GADM)"
    )

    prepare = subparsers.add_parser("prepare", help="从 raw 派生三个 GeoJSON")
    prepare.add_argument(
        "--skip-basin", action="store_true", help="跳过流域派生(只重建行政区与国界)"
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
        help="使用 data/raw 下对应采样步长的 ETOPO 文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    render.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="内嵌晕渲栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    render.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")

    subparsers.add_parser("all", help="依次执行 download -> prepare -> render")
    return parser


def run(argv: list[str] | None = None) -> int:
    """解析子命令并执行; 返回退出码(0 成功, 非 0 表示数据缺失或已中断)."""
    args = build_parser().parse_args(argv)

    if args.command == "download":
        import download_data

        return download_data.run(
            check=args.check, force=args.force, skip_basin=args.skip_basin
        )

    if args.command == "prepare":
        import prepare_data

        return prepare_data.run(skip_basin=args.skip_basin)

    if args.command == "render":
        import volga

        sheets = None if args.sheet == "all" else (args.sheet,)
        return volga.run(
            sheets=sheets, stride=args.stride, dpi=args.dpi, show=args.show
        )

    # all: 下载 -> 派生 -> 出图, 任一步非 0 就停下(不带着缺数据继续往下跑).
    import download_data
    import prepare_data
    import volga

    status = download_data.run()
    if status:
        return status
    status = prepare_data.run()
    if status:
        return status
    return volga.run()


if __name__ == "__main__":
    try:
        status = run()
    except KeyboardInterrupt:
        print("\n用户中断; 重新运行可继续未完成的部分.", file=sys.stderr)
        status = 130
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        status = 1
    raise SystemExit(status)
