#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""提交时把中文全角标点转成半角: git 钩子与命令行共用.

是什么: 按 ``CHAR_MAP`` 把文本里的中文全角标点(括号,逗号,句号,引号,冒号,顿号,
    破折号等)替换成半角 ASCII. 两种用法:

    * 文件模式 ``python tools/autorun.py <file> [<file>...]``: 原地改写, 二进制文件跳过;
    * 管道模式 ``python tools/autorun.py < in > out``: 从 stdin 读, 转到 stdout.

    ``.githooks/pre-commit`` 对本次暂存的每个文本文件调用文件模式; 部署步骤与原理见
    ``docs/conventions.md`` 的"标点与提交钩子"一节.

为什么:
    * 钩子放在版本库: ``.git/hooks`` 不进版本库, 换机器或重新 clone 后就会静默失效.
      改用 ``.githooks/`` + ``core.hooksPath`` 后钩子跟随仓库提交, 每个 clone 只做一次
      ``git config --local core.hooksPath .githooks``.
    * 为什么可以对本文件自己生效: 映射表的键一律写成 ``\\uXXXX`` 转义, 源文件里不含全角
      字面量; 本文件与钩子的注释也只写半角标点, 转换因此幂等, 不会每次提交都产生无意义
      diff(``docs/conventions.md`` 的文风一节要求的正是半角标点).
    * 钩子本身是 bash: 它在执行途中被改写会让后面的语句读错, 所以钩子里把正在运行的自己
      排到最后处理. 本文件是 Python, CPython 在执行前已把整个源文件读入并编译, 磁盘上的
      改写不影响本次运行, 不需要同样处理.

注意:
    * 二进制文件读取时抛 ``UnicodeDecodeError``, 调用方跳过, 不影响提交;
    * 文件模式会真的改写工作区文件(钩子随后把改过的文件 ``git add`` 回暂存区), 所以
      ``git status`` 未必看得到差异, 但磁盘内容已经变了;
    * 读写都用 ``newline=""``: 原样保留 CRLF/LF, 不会因为"顺手规范化换行"而制造无关 diff.
"""

from __future__ import annotations

import re
import sys

# 全角标点 -> ASCII 映射表; 键一律写成 \uXXXX 转义(理由见模块 docstring).
CHAR_MAP = {
    "\uff09": ")",  # 全角右圆括号 -> 半角右圆括号
    "\uff08": "(",  # 全角左圆括号 -> 半角左圆括号
    "\uff0c": ",",  # 全角逗号 -> 半角逗号
    "\u3002": ".",  # 全角句号 -> 半角句点
    "\u201c": '"',  # 全角左双引号 -> 半角双引号
    "\u201d": '"',  # 全角右双引号 -> 半角双引号
    "\u2018": "'",  # 全角左单引号 -> 半角单引号
    "\u2019": "'",  # 全角右单引号 -> 半角单引号
    "\uff1b": ";",  # 全角分号 -> 半角分号
    "\u2014": "-",  # 全角破折号 -> 半角连字符
    "\uff1a": ":",  # 全角冒号 -> 半角冒号
    "\u3001": ",",  # 全角顿号 -> 半角逗号
    "\u2192": "->",  # 全角箭头 -> 半角箭头
    "\u3011": "]",  # 全角右方括号 -> 半角右方括号
    "\u3010": "[",  # 全角左方括号 -> 半角左方括号
    "\u2026": "...",  # 全角省略号 -> 三个半角点
    "\uff1f": "?",  # 全角问号 -> 半角问号
    "\uff01": "!",  # 全角叹号 -> 半角叹号
    "\u3008": "<",  # 全角左尖括号 -> 半角小于号
    "\u3009": ">",  # 全角右尖括号 -> 半角大于号
    "\u300a": "<<",  # 全角左书名号 -> 两个半角小于号
    "\u300b": ">>",  # 全角右书名号 -> 两个半角大于号
    "\uff5e": "~",  # 全角波浪号 -> 半角波浪号
}

# 键都是单字符, 交替匹配不存在前缀冲突, 不必按长度排序; re.escape 保证字面量安全.
pattern = re.compile("|".join(re.escape(key) for key in CHAR_MAP))


def transform(text):
    """把文本里的全角标点换成半角, 返回新文本; 不修改入参."""
    return pattern.sub(lambda match: CHAR_MAP[match.group(0)], text)


def fix_file(filepath):
    """原地转换一个文件, 返回它是否真的被改写.

    True  = 内容里有全角标点, 文件已就地改写;
    False = 内容本来就合规, 盘上没动.

    二进制文件抛 UnicodeDecodeError, 由调用方决定怎么处理(钩子与命令行都跳过):
    本函数不吞这个信号, 否则调用方分不清"跳过了"和"没问题".
    """
    with open(filepath, "r", encoding="utf-8", newline="") as handle:
        content = handle.read()

    new_content = transform(content)
    if content == new_content:
        return False

    with open(filepath, "w", encoding="utf-8", newline="") as handle:
        handle.write(new_content)
    return True


def main(argv):
    """命令行入口: 有参数走文件模式, 无参数走管道模式."""
    if argv:
        failed = False
        for filepath in argv:
            try:
                changed = fix_file(filepath)
            except UnicodeDecodeError:
                continue
            except OSError as error:
                print(f"[fix_punctuation] error: {filepath}: {error}", file=sys.stderr)
                failed = True
                continue

            if changed:
                print(f"[fix_punctuation] fixed: {filepath}")

        return 1 if failed else 0

    sys.stdout.write(transform(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
