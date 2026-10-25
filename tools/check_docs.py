#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Validate the docs tree: links, page templates, index coverage, source pointers.

是什么: 校验 README 与 docs/ 的相对链接、图种/参考页的元信息与节序、docs/index.md 的覆盖率、
以及源码 docstring 里 ``docs/...`` 指针是否指向存在的页面.
完整说明(为什么要校验、提交前怎么跑)见 ``docs/conventions.md`` 的维护流程一节.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INDEX = DOCS / "index.md"

# 图种页/参考页的固定节序; 允许整节省略, 不允许调换或自创.
MAP_SECTIONS = ["是什么", "设计要点", "数据", "运行", "注意事项"]
REFERENCE_SECTIONS = ["是什么", "关键行为", "用法", "注意事项"]
# 页面开头元信息里必须出现的字段.
MAP_META = ["源码", "产物"]
REFERENCE_META = ["源码", "导入"]
# 没有文档指针的脚本: 一次性演示, 不在文档体系内.
NO_POINTER = {"global.py", "AmericaArmy/main.py"}

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
POINTER_RE = re.compile(r"docs/[A-Za-z0-9_./-]+\.md")


def markdown_files() -> list[Path]:
    """README 与 docs 下的全部 Markdown 文件."""
    return [ROOT / "README.md", *sorted(DOCS.rglob("*.md"))]


def outside_fences(path: Path) -> list[tuple[int, str]]:
    """返回代码围栏之外的行(行号, 内容).

    为什么: 页面里的示例链接、`##` 标题都写在代码块里, 不能当成真的链接/节标题.
    """
    lines: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append((lineno, line))
    return lines


def check_links(path: Path, errors: list[str]) -> int:
    """检查一个 Markdown 文件里的相对链接; 返回检查过的链接条数."""
    count = 0
    for lineno, line in outside_fences(path):
        for target in LINK_RE.findall(line):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            count += 1
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                rel = path.relative_to(ROOT)
                errors.append(f"{rel}:{lineno}: 链接不存在: {target}")
    return count


def check_page_template(path: Path, errors: list[str]) -> None:
    """校验图种页/参考页的标题、元信息和二级节序."""
    rel = path.relative_to(ROOT)
    is_map = path.parent == DOCS / "maps"
    is_ref = path.parent == DOCS / "reference"
    if not (is_map or is_ref):
        return

    sections = MAP_SECTIONS if is_map else REFERENCE_SECTIONS
    meta = MAP_META if is_map else REFERENCE_META

    lines = outside_fences(path)
    headings = [(n, l[3:].strip()) for n, l in lines if l.startswith("## ")]
    h1 = [(n, l) for n, l in lines if l.startswith("# ")]
    if not h1:
        errors.append(f"{rel}: 缺少一级标题")
        return

    # 元信息: 一级标题到第一个二级标题之间的 "- 字段:" 行.
    first_h2 = headings[0][0] if headings else 10**9
    meta_text = "\n".join(l for n, l in lines if h1[0][0] < n < first_h2)
    for field in meta:
        if f"- {field}:" not in meta_text:
            errors.append(f"{rel}: 元信息缺少 `- {field}:`")

    actual = [title for _, title in headings]
    unknown = [t for t in actual if t not in sections]
    if unknown:
        errors.append(f"{rel}: 自创节 {unknown}, 允许的节是 {sections}")
    order = [sections.index(t) for t in actual if t in sections]
    if order != sorted(order):
        errors.append(f"{rel}: 节序不符合 {sections}")


def check_index_coverage(errors: list[str]) -> int:
    """docs/index.md 必须链接到 docs 下除自身外的每一页."""
    linked: set[Path] = set()
    for lineno, line in outside_fences(INDEX):
        for target in LINK_RE.findall(line):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split("#", 1)[0]
            if target.endswith(".md"):
                linked.add((INDEX.parent / target).resolve())

    expected = {p.resolve() for p in DOCS.rglob("*.md") if p != INDEX}
    for missing in sorted(expected - linked):
        errors.append(f"docs/index.md: 未收录 {missing.relative_to(ROOT)}")
    return len(expected)


def check_source_pointers(errors: list[str]) -> int:
    """源码 docstring/注释里的 docs/... 指针必须指向存在的页面."""
    checked = 0
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if ".venv" in rel.parts or "data" in rel.parts or rel.as_posix() in NO_POINTER:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        pointers = POINTER_RE.findall(text)
        if not pointers:
            errors.append(f"{rel}: 没有指向 docs/ 的完整说明指针")
            continue
        for pointer in pointers:
            checked += 1
            if not (ROOT / pointer).is_file():
                errors.append(f"{rel}: 文档指针不存在: {pointer}")
    return checked


def main() -> None:
    errors: list[str] = []
    mds = markdown_files()
    links = sum(check_links(p, errors) for p in mds)
    pages = 0
    for page in sorted(DOCS.rglob("*.md")):
        if page in (INDEX, DOCS / "conventions.md"):
            continue
        if page.parent in (DOCS / "maps", DOCS / "reference"):
            check_page_template(page, errors)
            pages += 1
    indexed = check_index_coverage(errors)
    pointers = check_source_pointers(errors)

    if errors:
        print(f"文档检查失败: {len(errors)} 项")
        for error in errors:
            print(f"  ERROR {error}")
        sys.exit(1)
    print(
        f"文档检查通过: {len(mds)} 个 Markdown 文件, {links} 条链接, "
        f"{pages} 个模板页, 索引 {indexed} 页, 源码指针 {pointers} 处"
    )


if __name__ == "__main__":
    main()
