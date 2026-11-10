#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""USSR subproject entry point: render the USSR topography map.

是什么: 苏联子项目的唯一可执行入口, 只有 ``render`` 子命令; 地图进 ``USSR/map/``,
文字信息进 ``USSR/text/``. 数据(ETOPO 高程与共享 Natural Earth 图层)由独立数据项目
miko_gis_data 准备, 本入口不再提供 download/prepare.
为什么只有一个入口: 全项目约定「一个子项目一个可执行文件, 其余 .py 只导出 run()」;
参数解析与退出码归这里, 模块不再各自解析命令行.
完整说明(投影,数据来源,运行方式)见 ``docs/maps/ussr.md``.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """构造命令行: 只有 render 子命令(数据准备在 miko_gis_data)."""
    parser = argparse.ArgumentParser(
        prog="python USSR/main.py",
        description="苏联子项目统一入口: 出图(数据由 miko_gis_data 准备).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    render = subparsers.add_parser("render", help="出图(地图 SVG + 同名 geo.json)")
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
        help="内嵌栅格的像素密度(dpi); 矢量部分与 dpi 无关, 缺省用 spec 里的值",
    )
    render.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    return parser


def run(argv: list[str] | None = None) -> int:
    """解析命令行并调用渲染模块; 返回进程退出码(0 成功)."""
    args = build_parser().parse_args(argv)
    from ussr import run as render_run

    return render_run(stride=args.stride, dpi=args.dpi, show=args.show)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\n用户中断.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
