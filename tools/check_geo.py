#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""检查产物是否满足「裁到地图框的纯底图 + geo.json」契约.

是什么: 读 ``<产物>.svg`` 与同名 ``.geo.json``, 检查底图根标签(viewBox/width/height)、
是否残留 ``<text>``、geo 的 format/version/base 是否与底图字节自洽, 以及
graticule/labels/relief/legend/suggestions 的结构与枚举是否合法; 有错时打印中文错误并
以退出码 1 结束.

为什么: 前端(miko_svg_editor)按同一份契约解析产物, 字段写错了要到合成阶段才报;
出图后先跑一遍这个检查, 能在本仓内定位问题. 完整契约见
``docs/reference/geo.md`` 与 miko 的 PAGE-EDITOR.md §3(``mapdoc-geo`` v2); 这里只做
结构级校验, 不判断标注位置是否美观, 也不校验文字样式(样式由前端 role 表决定).

用法:
    python tools/check_geo.py [<产物>.svg ...]
不给参数时检查 README 出图表里的全部产物(不存在的跳过并提示).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 与 docs/reference/geo.md / 契约 §3 一致的枚举. 角色枚举的唯一真源是 miko_svg_editor
# 的 src/config/text-style.ts 里的 MAP_LABEL_ROLES; 这里只是镜像, 顺序与它一致.
LABEL_ROLES = (
    "country",
    "country-name",
    "sea",
    "city",
    "city-reference",
    "river",
    "highland",
    "area",
    "area-muted",
    "area-accent-1",
    "area-accent-2",
    "area-accent-3",
    "area-accent-4",
    "area-basin",
)
LABEL_ROLE_SET = frozenset(LABEL_ROLES)
# v2 已删除的 v1 字段: 出现即说明产物没重新生成(旧契约的产物要拒绝).
REMOVED_LABEL_KEYS = ("kind", "lines", "color", "italic", "halo", "rotation_deg")
TEXT_ANCHORS = {"start", "middle", "end"}
SIDES_LON = {"bottom", "top"}
SIDES_LAT = {"left", "right"}
LEGEND_SHAPES = {"line", "rect", "point"}
LEGEND_MARKERS = {"star", "square", "circle"}
COLOR_RE = re.compile(r"#[0-9a-f]{6}\Z")

# README 出图表里的产物(相对仓库根). 新增图种时同步这里, 供无参自检覆盖.
PRODUCTS = (
    "Myanmar/myanmar_topography_etopo2022_lambert_conformal.svg",
    "Myanmar/myanmar_administrative_divisions_bilingual.svg",
    "Myanmar/northern_shan_topography_etopo2022_lambert_conformal.svg",
    "USSR/ussr_topography_etopo2022_lambert_azimuthal.svg",
    "Ukraine/ukraine_borders_1991_2014_2022_lambert_conformal.svg",
    "Volga/volga_basin_topography_etopo2022_lambert_conformal.svg",
    "Volga/volga_basin_republics_topography_etopo2022_lambert_conformal.svg",
)

_ROOT_TAG_RE = re.compile(rb"<svg\b[^>]*>", re.IGNORECASE)
_VIEWBOX_RE = re.compile(rb"""\bviewBox\s*=\s*["']([^"']*)["']""")
_WIDTH_RE = re.compile(rb"""\bwidth\s*=\s*["']([0-9.]+)\s*(?:pt|px)?["']""")
_HEIGHT_RE = re.compile(rb"""\bheight\s*=\s*["']([0-9.]+)\s*(?:pt|px)?["']""")


def _number(value) -> bool:
    """是否是 exclude bool 的有限数字."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_product(svg_path: Path) -> list[str]:
    """检查一份产物, 返回中文错误列表(空 = 通过)."""
    errors: list[str] = []
    geo_path = svg_path.with_suffix(".geo.json")
    if not svg_path.is_file():
        return [f"缺少底图: {svg_path}"]
    if not geo_path.is_file():
        return [f"缺少 geo: {geo_path}"]
    data = svg_path.read_bytes()
    if b"<text" in data:
        errors.append("底图里出现 <text>(契约 C2: 纯几何底图不允许文字)")
    if data.count(b"</svg>") != 1:
        errors.append("底图根元素应恰好闭合一次")
    root = _ROOT_TAG_RE.search(data)
    view_box = None
    width_pt = height_pt = None
    if root is None:
        errors.append("找不到根 <svg> 标签")
    else:
        tag = root.group(0)
        match = _VIEWBOX_RE.search(tag)
        if match is None:
            errors.append("根 <svg> 缺少 viewBox")
        else:
            parts = match.group(1).split()
            if len(parts) != 4:
                errors.append(f"viewBox 必须是 4 个数, 得到 {match.group(1)!r}")
            else:
                try:
                    view_box = [float(part) for part in parts]
                except ValueError:
                    errors.append(f"viewBox 含非数字: {match.group(1)!r}")
        for pattern, label in ((_WIDTH_RE, "width"), (_HEIGHT_RE, "height")):
            found = pattern.search(tag)
            if found is None:
                errors.append(f"根 <svg> 缺少 {label}")
            elif label == "width":
                width_pt = float(found.group(1))
            else:
                height_pt = float(found.group(1))
    try:
        geo = json.loads(geo_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"geo 读不到或不是合法 JSON: {exc}"]
    if not isinstance(geo, dict):
        return errors + ["geo 顶层必须是对象"]
    if geo.get("format") != "mapdoc-geo":
        errors.append(f"geo.format 必须是 mapdoc-geo, 得到 {geo.get('format')!r}")
    if geo.get("version") != 2:
        errors.append(f"geo.version 必须是 2, 得到 {geo.get('version')!r}")
    base = geo.get("base")
    if not isinstance(base, dict):
        errors.append("geo.base 缺失")
    else:
        if base.get("sha256") != hashlib.sha256(data).hexdigest():
            errors.append("geo.base.sha256 与底图字节不一致(底图被改过或 sha 没更新)")
        if view_box is not None and base.get("view_box") != view_box:
            errors.append(f"geo.base.view_box 与底图根标签不一致: {base.get('view_box')} vs {view_box}")
        if width_pt is not None and not _number(base.get("width_pt")):
            errors.append("geo.base.width_pt 必须是数字")
        if height_pt is not None and not _number(base.get("height_pt")):
            errors.append("geo.base.height_pt 必须是数字")
        if view_box is not None and len(view_box) == 4:
            if not (abs(width_pt - view_box[2]) <= 0.01 and abs(height_pt - view_box[3]) <= 0.01):
                errors.append("底图根标签 width/height 与 viewBox 尺寸不一致")
    graticule = geo.get("graticule")
    if not isinstance(graticule, dict):
        errors.append("geo.graticule 缺失")
    else:
        style = graticule.get("style")
        if style is not None:
            if not isinstance(style, dict) or not COLOR_RE.fullmatch(str(style.get("stroke", ""))):
                errors.append("geo.graticule.style.stroke 必须是 #rrggbb")
            if not _number(style.get("width_pt")) or style["width_pt"] < 0:
                errors.append("geo.graticule.style.width_pt 必须是非负数字")
            if not _number(style.get("opacity")) or not 0 <= style["opacity"] <= 1:
                errors.append("geo.graticule.style.opacity 必须在 [0,1]")
        for axis, sides in (("lon", SIDES_LON), ("lat", SIDES_LAT)):
            ticks = graticule.get(axis)
            if not isinstance(ticks, list):
                errors.append(f"geo.graticule.{axis} 必须是数组")
                continue
            for index, tick in enumerate(ticks):
                path = f"geo.graticule.{axis}[{index}]"
                if not isinstance(tick, dict):
                    errors.append(f"{path} 必须是对象")
                    continue
                for key in ("value", "label", "x", "y", "side"):
                    if key not in tick:
                        errors.append(f"{path} 缺少 {key}")
                for key in ("value", "x", "y"):
                    if not _number(tick.get(key)):
                        errors.append(f"{path}.{key} 必须是数字")
                if tick.get("side") not in sides:
                    errors.append(f"{path}.side 必须是 {'|'.join(sorted(sides))} 之一")
    labels = geo.get("labels")
    if not isinstance(labels, list):
        errors.append("geo.labels 必须是数组")
    else:
        seen: set[str] = set()
        for index, label in enumerate(labels):
            path = f"geo.labels[{index}]"
            if not isinstance(label, dict):
                errors.append(f"{path} 必须是对象")
                continue
            for key in ("id", "role", "text", "x", "y", "anchor", "font_size_pt", "order"):
                if key not in label:
                    errors.append(f"{path} 缺少 {key}")
            for key in REMOVED_LABEL_KEYS:
                if key in label:
                    errors.append(f"{path}.{key} 是 v1 字段, v2 已删除(产物需重新生成)")
            if not isinstance(label.get("id"), str) or not label.get("id"):
                errors.append(f"{path}.id 必须是非空字符串")
            elif label["id"] in seen:
                errors.append(f"{path}.id 重复: {label['id']}")
            else:
                seen.add(label["id"])
            if label.get("role") not in LABEL_ROLE_SET:
                errors.append(f"{path}.role 必须是 {'|'.join(LABEL_ROLES)} 之一")
            if not isinstance(label.get("text"), str):
                errors.append(f"{path}.text 必须是字符串")
            for key in ("x", "y", "font_size_pt"):
                if not _number(label.get(key)):
                    errors.append(f"{path}.{key} 必须是数字")
            if _number(label.get("font_size_pt")) and not label["font_size_pt"] > 0:
                errors.append(f"{path}.font_size_pt 必须 > 0")
            if label.get("anchor") not in TEXT_ANCHORS:
                errors.append(f"{path}.anchor 必须是 start|middle|end")
            order = label.get("order")
            if not isinstance(order, int) or isinstance(order, bool):
                errors.append(f"{path}.order 必须是整数")
    relief = geo.get("relief")
    if relief is not None:
        if not isinstance(relief, dict):
            errors.append("geo.relief 必须是对象")
        else:
            for key in ("title", "unit", "vmin", "vmax", "stops", "ticks"):
                if key not in relief:
                    errors.append(f"geo.relief 缺少 {key}")
            if _number(relief.get("vmin")) and _number(relief.get("vmax")) and not relief["vmin"] < relief["vmax"]:
                errors.append("geo.relief.vmin 必须 < vmax")
            stops = relief.get("stops")
            if not isinstance(stops, list) or len(stops) < 2:
                errors.append("geo.relief.stops 至少 2 项")
            else:
                for offset, stop in enumerate(stops):
                    if not isinstance(stop, dict) or not COLOR_RE.fullmatch(str(stop.get("color", ""))):
                        errors.append(f"geo.relief.stops[{offset}].color 必须是 #rrggbb")
    legend = geo.get("legend")
    if legend is not None:
        if not isinstance(legend, dict) or not isinstance(legend.get("entries"), list):
            errors.append("geo.legend 必须是 {title, entries[]}")
        else:
            for index, entry in enumerate(legend["entries"]):
                path = f"geo.legend.entries[{index}]"
                if not isinstance(entry, dict):
                    errors.append(f"{path} 必须是对象")
                    continue
                if entry.get("shape") not in LEGEND_SHAPES:
                    errors.append(f"{path}.shape 必须是 line|rect|point")
                if entry.get("shape") == "point" and entry.get("marker") not in LEGEND_MARKERS:
                    errors.append(f"{path}.marker 对 point 条目必须是 star|square|circle")
                for key in ("stroke", "fill"):
                    value = entry.get(key)
                    if value is not None and not COLOR_RE.fullmatch(str(value)):
                        errors.append(f"{path}.{key} 必须是 null 或 #rrggbb")
    suggestions = geo.get("suggestions")
    if suggestions is not None:
        if not isinstance(suggestions, dict):
            errors.append("geo.suggestions 必须是对象")
        else:
            for key in ("notes", "area_annotation"):
                value = suggestions.get(key)
                if value is not None and (not isinstance(value, list) or not all(isinstance(item, str) for item in value)):
                    errors.append(f"geo.suggestions.{key} 必须是字符串数组")
    return errors


def main(argv: list[str]) -> int:
    """检查命令行给出的产物; 不给参数时检查 PRODUCTS 里的全部产物."""
    targets = [Path(arg) for arg in argv[1:]]
    if not targets:
        targets = [ROOT / relative for relative in PRODUCTS]
    failed = 0
    checked = 0
    for svg_path in targets:
        if not svg_path.is_file():
            print(f"跳过(不存在): {svg_path}")
            continue
        checked += 1
        errors = check_product(svg_path)
        geo_path = svg_path.with_suffix(".geo.json")
        if errors:
            failed += 1
            print(f"FAIL {svg_path.name}")
            for message in errors:
                print(f"  - {message}")
        else:
            print(f"OK   {svg_path.name} (+ {geo_path.name})")
    print(f"检查 {checked} 份产物, 失败 {failed} 份")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
