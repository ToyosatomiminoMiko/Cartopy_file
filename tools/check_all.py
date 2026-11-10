#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""一条命令跑完项目全部自检.

是什么: 依次运行 ``tools/check_docs.py``,``tools/check_geo.py``, 再编译全仓 Python 源文件,
    任何一项失败就以退出码 1 结束, 并在最后打印逐项 PASS/FAIL 汇总.
    完整说明(为什么这样收敛,提交前怎么跑)见 ``docs/conventions.md`` 的维护流程一节.

为什么: 项目的硬性约束分散在多个独立脚本里, 靠人逐个记得跑一定会漏; 收敛成一条命令后
    ``AGENTS.md`` 只需写"结束前跑它", 失败会直接暴露而不是靠自觉. 语法编译放在这里是为了让
    连 import 都跑不到的低级错误先一步暴露, 而不是等出图时才炸.

用法:
    uv run python tools/check_all.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("tools/check_docs.py", "tools/check_geo.py")
# 不参与语法编译的目录: 依赖由 uv 管理, 数据根与产物不归本仓源码维护.
SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", "data"})


def run_script(relative: str) -> bool:
    """用子进程跑一个检查脚本, 子进程输出直接透传到终端; 返回是否通过."""
    print(f"\n== {relative} ==")
    completed = subprocess.run([sys.executable, str(ROOT / relative)], cwd=ROOT)
    return completed.returncode == 0


def compile_sources() -> bool:
    """编译全仓 Python 源文件, 捕获语法错误; 返回是否全部通过."""
    print("\n== 语法编译 ==")
    files = [
        path
        for path in sorted(ROOT.rglob("*.py"))
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
    ]
    failed: list[Path] = []
    for path in files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            failed.append(path)
            print(f"  ERROR {path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
    print(f"编译 {len(files)} 个文件, 失败 {len(failed)} 个")
    return not failed


def main() -> int:
    results = {name: run_script(name) for name in TOOLS}
    results["语法编译"] = compile_sources()
    print("\n== 汇总 ==")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [name for name, ok in results.items() if not ok]
    if failed:
        print(f"自检失败: {', '.join(failed)}")
        return 1
    print("自检全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
