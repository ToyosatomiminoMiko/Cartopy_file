#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Hand-tuned map label layout stored beside each figure, outside the drawing code.

是什么: 把"标签最终写在哪"从绘图脚本里拆出来, 存成与产物同名的 ``<name>.labels.json``;
``save_svg`` 出图时自动读取并施加位移, 并在图上补画新增的文字标注. 这样一个标签被
哪个数字挡住时, 用鼠标调一次就固化成布局文件, 重跑脚本不会丢掉手工调整.
完整说明(文件格式、坐标系、编辑器用法)见 ``docs/reference/labels.md``.
"""

from __future__ import annotations

import base64
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "LABEL_PREFIX",
    "MARKER_PREFIX",
    "PLACEMENT_SUFFIX",
    "Placements",
    "apply",
    "dump",
    "label_id",
    "load",
    "placement_path",
    "read_marker",
    "write_marker",
]

# 可编辑标签的 id 前缀. 编辑器和本模块都靠它从整张 SVG 里认出"这是标签".
# 用前缀而不是清单: 脚本给标签设 gid 即可, 布局文件只需要记录被改过的那些.
LABEL_PREFIX = "label-"

# 布局文件后缀: 与产物同名, 只把最后的 .svg 换掉, 例如 a.svg -> a.labels.json.
PLACEMENT_SUFFIX = ".labels.json"

# 文件格式标记与版本; 结构不兼容时靠它给出明确报错而不是静默错位.
FORMAT = "cartopy-file-labels"
VERSION = 1

# 出图时写进 SVG 的标记: 记录"这张图实际施加了哪份布局".
# 为什么需要: 编辑器要区分"SVG 里已经烤进布局"和"布局比 SVG 新(还没重跑脚本)",
# 否则重开会把同一段位移算两遍. 标记用 base64 包住 JSON, 避免注释里出现 "--".
MARKER_PREFIX = "cartopy-file-labels:"
_MARKER_RE = re.compile(
    r"<!--\s*" + re.escape(MARKER_PREFIX) + r"([A-Za-z0-9+/=]+)\s*-->"
)

# 新增标注的默认样式. 编辑器从图上已有标签抄样式写进文件, 缺字段时按这里兜底.
_STYLE_DEFAULTS: dict[str, Any] = {
    "font_size": 10.0,
    "color": "#000000",
    "italic": False,
    "weight": "normal",
    "halo_color": "#ffffff",
    "halo_width": 2.5,
    "anchor": "start",
}

# SVG text-anchor -> matplotlib horizontalalignment.
_ANCHORS = {"start": "left", "middle": "center", "end": "right"}

# 坐标与位移保留 3 位小数: SVG 用户单位是 pt, 0.001pt 远小于一个像素,
# 但能让 JSON 的 git diff 不被浮点尾数噪声淹没.
_DIGITS = 3


@dataclass
class Placements:
    """一张图的标签布局: 已有标签的位移 + 新增的文字标注.

    moved: 标签 id -> ``{"dx": float, "dy": float, "text": str}``. dx/dy 是相对脚本
        默认位置的位移, 单位是 SVG 用户单位(= pt), y 轴向下(与 SVG 一致).
        存位移而不是绝对坐标: 脚本改了默认位置后, 手工调整仍然跟着标签走.
    added: 新增标注的列表, 每项见 ``docs/reference/labels.md`` 的字段说明.
    source: 读取时对应的布局文件路径; 编辑器界面用来显示"保存到哪".
    figure: 布局文件里记录的产物名, load 时用来检查是否读错了文件.
    """

    moved: dict[str, dict[str, Any]] = field(default_factory=dict)
    added: list[dict[str, Any]] = field(default_factory=list)
    source: Path | None = None
    figure: str = ""

    def __bool__(self) -> bool:
        """没有任何调整时视为空, 方便调用方判断"这张图要不要处理"."""
        return bool(self.moved or self.added)


def label_id(kind: str, name: str, index: int | None = None) -> str:
    """拼一个跨版本稳定的标签 id, 同时就是布局文件里的键.

    是什么: ``label-<kind>-<name>[-<index>]``, 例如 ``label-city-莫斯科``.
    kind: 标签类别(city/river/sea/country/highland/republic/...), 由脚本自己定.
    name: 人类可读的净名, 例如数据结构的英文键或图上的中文名; 不要带换行和空格.
    index: 同一类别同一名字出现多次时(例如两条"伏尔加河"), 传 1 起算的序号.
    """
    base = f"{LABEL_PREFIX}{kind}-{name.strip()}"
    if index is None:
        return base
    return f"{base}-{int(index)}"


def placement_path(svg_path: str | Path) -> Path:
    """产物路径对应的布局文件路径: 只替换最后的后缀, 不改目录."""
    return Path(svg_path).with_suffix(PLACEMENT_SUFFIX)


def load(path: str | Path) -> Placements:
    """读取并校验布局文件.

    文件不存在或结构不合法时抛 ValueError/OSError: 出图宁可失败也不静默忽略
    手工调整, 否则产物会悄悄退回默认位置.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # 报错要带文件名, 否则不知道该改哪个
        raise ValueError(f"标签布局文件不是合法 JSON: {path}: {exc}") from exc
    return from_document(data, source=path)


def from_document(data: Any, *, source: Path | None = None) -> Placements:
    """把解析后的 JSON 对象转成 Placements.

    是什么: 一处校验所有字段. 出图与编辑器保存都走这里, 两边格式不会漂移.
    """
    if not isinstance(data, dict):
        raise ValueError("标签布局文件顶层必须是 JSON 对象")
    if data.get("format") != FORMAT:
        raise ValueError(
            f"不是标签布局文件(format 应为 {FORMAT!r}): {data.get('format')!r}"
        )
    if data.get("version") != VERSION:
        raise ValueError(
            f"标签布局文件版本不支持: {data.get('version')!r}(本程序支持 {VERSION})"
        )

    moved_raw = data.get("moved", {})
    if not isinstance(moved_raw, dict):
        raise ValueError("标签布局文件的 moved 必须是对象")
    moved: dict[str, dict[str, Any]] = {}
    for key, record in moved_raw.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            raise ValueError(f"moved 里的项必须是 字符串 -> 对象: {key!r}")
        dx = _finite(record.get("dx"), f"moved[{key!r}].dx")
        dy = _finite(record.get("dy"), f"moved[{key!r}].dy")
        entry: dict[str, Any] = {"dx": dx, "dy": dy}
        text = record.get("text")
        if text is not None:
            if not isinstance(text, str):
                raise ValueError(f"moved[{key!r}].text 必须是字符串")
            entry["text"] = text
        moved[key] = entry

    added_raw = data.get("added", [])
    if not isinstance(added_raw, list):
        raise ValueError("标签布局文件的 added 必须是数组")
    added = [_added_record(record, i) for i, record in enumerate(added_raw)]

    keys = [record["key"] for record in added]
    if len(set(keys)) != len(keys):
        raise ValueError(f"新增标注的 id 重复: {keys}")

    return Placements(
        moved=moved,
        added=added,
        source=source,
        figure=str(data.get("figure") or ""),
    )


def to_document(placements: Placements, *, figure: str = "") -> dict[str, Any]:
    """把 Placements 转成要写盘的 JSON 对象(位移与坐标四舍五入到 3 位).

    为什么在这里舍入而不是读入时: 只有写盘需要稳定, 读入的旧值保持原样才能
    叠加第二次拖动而不丢精度.
    """
    moved: dict[str, Any] = {}
    for key in sorted(placements.moved):
        record = placements.moved[key]
        entry: dict[str, Any] = {
            "dx": _round(record["dx"]),
            "dy": _round(record["dy"]),
        }
        if record.get("text"):
            entry["text"] = record["text"]
        moved[key] = entry

    added: list[dict[str, Any]] = []
    for record in placements.added:
        style = dict(_STYLE_DEFAULTS)
        style.update(record.get("style") or {})
        added.append(
            {
                "key": record["key"],
                "text": record["text"],
                "x": _round(record["x"]),
                "y": _round(record["y"]),
                "rotation": _round(record["rotation"]),
                "style": {
                    "font_size": _round(style["font_size"]),
                    "color": style["color"],
                    "italic": bool(style["italic"]),
                    "weight": style["weight"],
                    "halo_color": style["halo_color"],
                    "halo_width": _round(style["halo_width"]),
                    "anchor": style["anchor"],
                },
            }
        )

    return {
        "format": FORMAT,
        "version": VERSION,
        "figure": figure or placements.figure,
        "moved": moved,
        "added": added,
    }


def dump(placements: Placements, path: str | Path, *, figure: str = "") -> Path:
    """原子地写出布局文件(先写临时文件再 rename), 返回写入路径."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = to_document(placements, figure=figure)
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    # 临时文件与目标同目录, 保证 rename 是同一个文件系统上的原子操作.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path


def apply(fig, placements: Placements) -> None:
    """把布局施加到一个已经画好、还没保存的 Figure 上.

    是什么: 已有标签按 id 平移, 新增标注作为 figure 级文字补画上去.
    注意: 同一个 Figure 只能施加一次, 重复施加会把位移叠加两遍.
    """
    from matplotlib.text import Text

    if getattr(fig, "_cartopy_file_labels_applied", False):
        print("警告: 标签布局已施加过, 跳过重复施加(同一 Figure 只能施加一次)")
        return
    fig._cartopy_file_labels_applied = True  # noqa: SLF001 - 只作幂等标记

    by_gid: dict[str, list[Any]] = {}
    for artist in fig.findobj(match=lambda item: isinstance(item, Text)):
        gid = artist.get_gid()
        if gid:
            by_gid.setdefault(gid, []).append(artist)

    missing: list[str] = []
    unsupported: list[str] = []
    for gid, record in placements.moved.items():
        artists = by_gid.get(gid)
        if not artists:
            missing.append(gid)
            continue
        if len(artists) > 1:
            print(f"警告: 标签 id 重复({len(artists)} 个), 位移会同时作用: {gid}")
        for artist in artists:
            if not _shift_artist(artist, float(record["dx"]), float(record["dy"])):
                unsupported.append(gid)

    if missing:
        shown = ", ".join(missing[:5]) + ("" if len(missing) <= 5 else ", ...")
        print(
            f"警告: 布局文件里有 {len(missing)} 个标签在图里找不到, 已忽略: {shown}"
        )
    if unsupported:
        shown = ", ".join(sorted(set(unsupported))[:5])
        print(
            f"警告: {len(set(unsupported))} 个标签是不支持位移的注释类型, 已忽略: {shown}"
        )

    for record in placements.added:
        if record["key"] in by_gid:
            print(f"警告: 新增标注的 id 与图上已有标签重复, 跳过: {record['key']}")
            continue
        _add_custom(fig, record)


def _shift_artist(artist, dx: float, dy: float) -> bool:
    """把一个文字画师在画布上平移 (dx, dy) pt; 不支持的画师返回 False.

    为什么不能用"改 transform"一招走完: 普通 ``Text`` 的位置是 transform 作用在
    (x, y) 上, 在显示坐标里补一段平移就行; 但 ``Annotation`` 每次绘制时自己把
    ``xytext``(可以是 "offset points") 换算成显示坐标并把 transform 换成单位阵,
    改 transform 会被它覆盖掉. 对 offset points 的注释位置直接加减 pt 才是稳的.
    """
    from matplotlib.text import Annotation
    from matplotlib.transforms import ScaledTranslation

    if isinstance(artist, Annotation):
        if artist.anncoords != "offset points":
            return False
        x, y = artist.xyann
        # annotation 的 y 轴向上, 布局文件沿用 SVG 约定 y 向下.
        artist.xyann = (x + dx, y - dy)
        return True

    # 位移量与 dpi 无关: 布局文件里的 dx/dy 是"图上量出来的 pt"(SVG 用户单位),
    # 用 ScaledTranslation(英寸 × 绘制时 dpi)表达, SVG 后端按 72dpi 绘制时正好得到
    # 同样的 pt 数, 交互窗口里则是同样的物理尺寸.
    # 组合顺序必须是 ``原变换 + 平移``: 先做投影/坐标变换, 再在显示坐标里平移;
    # 反过来会把 pt 当成经纬度加进数据坐标.
    figure = artist.get_figure(root=True)
    shift = ScaledTranslation(dx / 72.0, -dy / 72.0, figure.dpi_scale_trans)
    artist.set_transform(artist.get_transform() + shift)
    return True


def read_marker(svg_path: str | Path) -> Placements | None:
    """读出 SVG 里记录的"实际施加的布局"; 没有标记(或标记损坏)时返回 None.

    为什么不用文件时间戳判断"布局是否已经烤进图里": 复制/检出会改时间, 而内容
    标记不会骗人. 标记由 ``save_svg`` 写入, 编辑器靠它决定位移要不要再叠加.
    """
    path = Path(svg_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    return marker_from_svg(text)


def marker_from_svg(svg_text: str) -> Placements | None:
    """从 SVG 文本里解析布局标记; 未标记/无法解析时返回 None."""
    match = _MARKER_RE.search(svg_text)
    if match is None:
        return None
    try:
        data = json.loads(base64.b64decode(match.group(1)))
        return from_document(data)
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def write_marker(svg_path: str | Path, placements: Placements) -> None:
    """把"已施加的布局"以注释形式写进 SVG(紧跟 ``<svg ...>`` 开标签).

    标记只是自描述信息: 查看器会忽略注释, 去掉标记也不影响画面, 只是编辑器会
    认为这张图没有烤进任何布局.
    """
    path = Path(svg_path)
    text = path.read_text(encoding="utf-8")
    if _MARKER_RE.search(text) is not None:  # 重出图不该有旧标记, 有就先清掉
        text = _MARKER_RE.sub("", text, count=1)
    payload = json.dumps(
        to_document(placements),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    marker = f"<!-- {MARKER_PREFIX}{base64.b64encode(payload).decode('ascii')} -->"
    match = re.search(r"<svg\b[^>]*>", text)
    if match is None:
        raise ValueError(f"SVG 里找不到 <svg> 开标签, 无法写入布局标记: {path}")
    text = text[: match.end()] + "\n" + marker + text[match.end() :]
    path.write_text(text, encoding="utf-8")


def _add_custom(fig, record: dict[str, Any]) -> None:
    """按布局文件补画一条新增标注.

    SVG 的 ``y`` 是文字基线的位置(不是顶部/中心), 所以落到 Figure 上要用
    ``va="baseline"`` 才能与编辑器里看到的位置一致; 旋转方向也相反(SVG 顺时针为正).
    """
    import matplotlib.patheffects as path_effects

    style = dict(_STYLE_DEFAULTS)
    style.update(record.get("style") or {})

    width_in, height_in = fig.get_size_inches()
    x = float(record["x"]) / (72.0 * width_in)
    y = 1.0 - float(record["y"]) / (72.0 * height_in)

    effects = None
    if float(style["halo_width"]) > 0 and style["halo_color"]:
        effects = [
            path_effects.withStroke(
                linewidth=float(style["halo_width"]),
                foreground=style["halo_color"],
            )
        ]

    artist = fig.text(
        x,
        y,
        record["text"],
        transform=fig.transFigure,
        ha=_ANCHORS.get(style["anchor"], "left"),
        va="baseline",
        fontsize=float(style["font_size"]),
        color=style["color"],
        style="italic" if style["italic"] else "normal",
        weight=style["weight"],
        rotation=-float(record["rotation"]),
        rotation_mode="anchor",
        zorder=25,
        path_effects=effects,
    )
    artist.set_gid(record["key"])


def _added_record(record: Any, index: int) -> dict[str, Any]:
    """校验一条新增标注并补默认样式."""
    where = f"added[{index}]"
    if not isinstance(record, dict):
        raise ValueError(f"{where} 必须是对象")
    key = record.get("key")
    if not isinstance(key, str) or not key.startswith(LABEL_PREFIX):
        raise ValueError(f"{where}.key 必须以 {LABEL_PREFIX!r} 开头: {key!r}")
    if any(char.isspace() for char in key):
        raise ValueError(f"{where}.key 不能含空白: {key!r}")
    text = record.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError(f"{where}.text 必须是非空字符串")

    raw_style = record.get("style") or {}
    if not isinstance(raw_style, dict):
        raise ValueError(f"{where}.style 必须是对象")
    style = dict(_STYLE_DEFAULTS)
    for name, default in _STYLE_DEFAULTS.items():
        if name not in raw_style:
            continue
        value = raw_style[name]
        if isinstance(default, bool):
            style[name] = bool(value)
        elif isinstance(default, float):
            style[name] = _finite(value, f"{where}.style.{name}")
        else:
            if not isinstance(value, str):
                raise ValueError(f"{where}.style.{name} 必须是字符串")
            style[name] = value
    if style["anchor"] not in _ANCHORS:
        raise ValueError(f"{where}.style.anchor 只能是 {sorted(_ANCHORS)}")

    return {
        "key": key,
        "text": text,
        "x": _finite(record.get("x"), f"{where}.x"),
        "y": _finite(record.get("y"), f"{where}.y"),
        "rotation": _finite(record.get("rotation", 0.0), f"{where}.rotation"),
        "style": style,
    }


def _finite(value: Any, where: str) -> float:
    """取值并确认是有限数值; 布局文件里的 NaN/Inf 会让矩阵变换直接出乱码."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{where} 必须是数值: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{where} 必须是有限数值: {value!r}")
    return number


def _round(value: float) -> float:
    """写盘用的定点小数; -0.0 统一成 0.0, 免得 diff 出现 "-0.0"."""
    rounded = round(float(value), _DIGITS)
    return 0.0 if rounded == 0 else rounded
