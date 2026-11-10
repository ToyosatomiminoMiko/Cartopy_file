#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Myanmar subproject entry point: prepare derived data and render the three maps.

是什么: 缅甸子项目的唯一可执行入口. ``prepare`` 读数据仓的原始数据, 按本图口径清洗/裁剪/
拼装后写到 ``Myanmar/build/``; ``render`` 按 ``--sheet`` 出一到三张图, 地图进
``Myanmar/map/``, 文字信息进 ``Myanmar/text/``.
为什么只有一个入口: 全项目约定「一个子项目一个可执行文件, 其余 .py 只导出 run()」;
参数解析与退出码归这里, 模块不再各自解析命令行. 子命令分派用懒导入, 只有真正出图时
才加载 matplotlib/cartopy, 只有 prepare 时才加载 shapely/geopandas.
完整说明(三张图的投影/数据源/运行方式)见 ``docs/reference/prepare.md``,
``docs/maps/myanmar.md``, ``docs/maps/myanmar-admin.md`` 与 ``docs/maps/northern-shan.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# render --sheet 的取值 -> 对应的渲染模块名(按需导入). 渲染顺序始终按
# config.SHEETS 登记的顺序, 不按本字典的顺序.
RENDER_MODULES = {
    "myanmar": "myanmar",
    "myanmar-admin": "myanmar_admin",
    "northern-shan": "northern_shan",
}


def build_parser() -> argparse.ArgumentParser:
    """构造命令行: prepare(派生) 与 render(出图) 两个子命令."""
    parser = argparse.ArgumentParser(
        prog="python Myanmar/main.py",
        description="缅甸子项目统一入口: 派生数据(prepare)与出图(render).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    subparsers.add_parser(
        "prepare",
        help="读数据仓原始数据, 重建 Myanmar/build/ 下的派生 GeoJSON",
    )

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


def prepare() -> int:
    """全量重建本子项目的派生数据; 返回进程退出码."""
    from importlib import import_module

    return import_module("prepare").run()


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
    from importlib import import_module

    import config

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
    """解析命令行并分派; 返回进程退出码(0 成功)."""
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        return prepare()
    return render(sheet=args.sheet, stride=args.stride, dpi=args.dpi, show=args.show)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("\n用户中断.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
