#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""AmericaArmy subproject entry point: render the demonstration map.

是什么: 框架演示子项目的唯一可执行入口, 只有 ``render`` 一个子命令; ``--dpi`` 控制内嵌
栅格的像素密度, ``--show`` 保存后弹出交互窗口. 图规格(含地名/图例/文案)在 ``config.py``,
draw 回调在 ``america_army.py``(没有动态 geo 数据, 所以不用写 collect); 本文件只解析命令行
并懒导入渲染模块--演示子项目没有数据准备步骤, 所以没有 download/prepare 子命令.
完整说明(最小子项目要写什么,回调契约)见 ``docs/add-map.md``.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """构造命令行: 只有 render 子命令(演示子项目没有数据准备)."""
    parser = argparse.ArgumentParser(
        prog="python AmericaArmy/main.py",
        description="AmericaArmy 演示子项目统一入口: 出一张世界底图 + 基地点位演示图.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    render = subparsers.add_parser("render", help="出图(地图 SVG + 同名 geo.json)")
    render.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="内嵌栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    render.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    return parser


def run(argv: list[str] | None = None) -> int:
    """解析命令行并调用渲染模块; 返回进程退出码(0 成功).

    为什么渲染模块在函数里才 import: 命令行解析应当与绘图栈(matplotlib/cartopy)解耦,
    只有真正出图时才付出加载成本.
    """
    args = build_parser().parse_args(argv)
    from america_army import run as render_run

    return render_run(dpi=args.dpi, show=args.show)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\n用户中断.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
