#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""geo.json(mapdoc-geo v1)生成: 地图框、经纬刻度、初始标注、色标、图例与默认文案.

是什么: 本模块把「前端排版需要知道、但底图 SVG 里不画」的元数据收集成一个
``<产物名>.geo.json``: 地图框 ``base``(裁到地图框后的 viewBox 与尺寸)、经纬刻度
``graticule``、地名候选 ``labels``、高程色标 ``relief``、图例 ``legend`` 与默认文案
``suggestions``. 同时提供 ``save_map()``, 把 Figure 保存成裁到地图框的纯几何 SVG
(即契约里的 ``base.svg``)并写出同名的 geo.json.

为什么: 底图按约定「不含任何文字」(miko_svg_editor 的 C2), 前端不知道地名该放在哪,
也不知道刻度/色标/图例的口径. 这些数据只在 Cartopy 画图时天然存在(axes bbox、
locator、文字 artist 的锚点与样式、legend handles、colorbar 的 norm/cmap), 由这里
一次性收集比前端从成品 SVG 反推可靠. 字段与取值口径见 miko_svg_editor 的 PAGE-EDITOR.md §3
(``mapdoc-geo`` v1).

关键口径:
- 坐标单位是 SVG 用户单位(= pt, 1/72 英寸), 原点在原始 Figure 左上角, y 向下;
  底图 SVG 只改根标签的 viewBox/width/height 来裁到地图框, 坐标值本身不变,
  所以 geo 里的 x/y 可以直接对底图坐标使用;
- ``labels[].x/y`` 是**第一行文字的基线锚点**(前端 textLayout 把 y 当基线, 后续行
  按 ``font_size_pt * line_height`` 往下排), 不是 matplotlib 的 bbox 中心: 本模块把
  ``va="center"`` 的锚点换算成基线(见 ``BASELINE_RATIO``);
- ``labels[].rotation_deg`` 是 SVG 的旋转角(顺时针为正, 屏幕坐标 y 向下), 与
  matplotlib 的 ``rotation``(逆时针为正)符号相反; id 规则沿用旧 ``labels.py`` 的
  ``label-<kind>-<name>[-<index>]``, 便于旧布局文件迁移.

依赖: ``cartopy_file.output.save_svg``(唯一 SVG 出口); 坐标换算走 cartopy 的
PlateCarree->display 变换(与 ``GeoAxes.text`` 同一套, 实测与旧成品抽出的 geo 逐条
对齐). 完整说明: 见 ``docs/reference/geo.md``.
元信息: 2026-10, 迁移 miko_svg_editor 的 geo.json 契约; 契约见
miko_svg_editor 的 PAGE-EDITOR.md §3 与本仓 ``docs/reference/geo.md``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .output import save_svg

__all__ = [
    "BASELINE_RATIO",
    "FORMAT",
    "GeoDoc",
    "LABEL_KINDS",
    "LABEL_PREFIX",
    "VERSION",
    "Frame",
    "figure_frame",
    "label_id",
    "projected_angle",
    "relief_from_cmap",
    "save_map",
    "svg_point",
]

# 文件格式身份; 与 miko_svg_editor 的 mapdoc-geo 完全一致, 前端/Python 都按它校验.
FORMAT = "mapdoc-geo"
VERSION = 1

# 标签 id 前缀与类别枚举, 沿用旧 labels.py / 前端 §3; 前端按前缀认「这是地名」.
LABEL_PREFIX = "label-"
LABEL_KINDS = ("country", "sea", "highland", "river", "city", "area", "other")
LABEL_KIND_SET = frozenset(LABEL_KINDS)

# matplotlib 的 va 取值 -> 前端文字水平锚点; 垂直方向统一换算成第一行基线.
_ANCHORS = {"left": "start", "center": "middle", "right": "end"}
_LINE_ALIGN = {"start": "left", "middle": "center", "end": "right"}

# va="center" 时, matplotlib 把文字 bbox 的垂直中心放在锚点上; 前端把 geo 的 y 当
# 第一行基线. 对 DejaVu/Noto 这类常见字体, bbox 中心到基线的距离约为 0.36 em
# (从旧成品抽出的 39 条 Volga 标签实测恒为 0.36 x 字号), 因此单行文字要把锚点
# 下移 0.36 x 字号; 多行再按行距把首行基线移到整块中心之上 (见 _baseline_offset).
BASELINE_RATIO = 0.36

# 数字保留 3 位小数: geo 契约要求 3 位以内; 底图 viewBox 另按 6 位处理(见 _format_pt),
# 两边都从同一份 Frame 生成, 这样 prepare 脚本逐值比对不会因舍入差报错.
_GEO_DIGITS = 3
_FRAME_DIGITS = 6

# 根 <svg> 标签与 viewBox/width/height 属性: 只改根标签, 其余字节原样保留.
_ROOT_TAG_RE = re.compile(rb"<svg\b[^>]*>", re.IGNORECASE)
_VIEWBOX_ATTR_RE = re.compile(rb"""\bviewBox\s*=\s*(["'])(.*?)\1""", re.DOTALL)
_WIDTH_ATTR_RE = re.compile(rb"""\bwidth\s*=\s*(["'])(.*?)\1""", re.DOTALL)
_HEIGHT_ATTR_RE = re.compile(rb"""\bheight\s*=\s*(["'])(.*?)\1""", re.DOTALL)

# geo 里的颜色统一小写 #rrggbb, 与前端/Python 合成侧口径一致.
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\Z")

# 经纬刻度标签的格式: 整数度写 "35°E" / "46°N", 带小数时写度分 "35°30′E".
# 为什么不直接用 cartopy 的 formatter: formatter 受 rcParams 影响(数字格式/
# 半球写法), 版本升级可能改变输出; 这里只保留项目实际用到的两种写法.
_DEGREE = "\N{DEGREE SIGN}"
_MINUTE = "\N{PRIME}"


def _clean(value: float, digits: int = _GEO_DIGITS) -> float:
    """有限浮点数收敛到指定位数; 结果仍写 float(整数也不写 int), 保证 JSON 稳定."""
    if not math.isfinite(value):
        raise ValueError(f"geo 数值必须是有限数, 得到 {value!r}")
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0 else rounded


def _format_pt(value: float) -> str:
    """底图 viewBox/width/height 的写法: 6 位小数并去掉尾零, 与 geo.base 完全同源."""
    text = f"{float(value):.{_FRAME_DIGITS}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def label_id(kind: str, name: str, index: int | None = None) -> str:
    """拼一个跨版本稳定的标签 id: ``label-<kind>-<name>[-<index>]``.

    与旧 ``labels.py`` 的规则一致, 手工布局文件(labels.json)迁移到 scene 时靠 id 对齐.
    name 只去掉首尾空白, 不替换空格: 旧布局文件里的键就是这种写法, 改了反而对不上.
    """
    if not kind or not name.strip():
        raise ValueError(f"label_id 需要非空的 kind/name: {kind!r} {name!r}")
    base = f"{LABEL_PREFIX}{kind}-{name.strip()}"
    if index is None:
        return base
    return f"{base}-{int(index)}"


@dataclass(frozen=True)
class Frame:
    """地图框在底图坐标系(SVG pt, 原点为原 Figure 左上角, y 向下)里的矩形.

    为什么单独成类型: 底图裁剪、geo.base 与经纬刻度的边线都要用同一份数值;
    分开算就会因为浮点舍入出现「viewBox 与 geo.base 差 1e-9」这类不一致.
    """

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        """右边界 x."""
        return self.x + self.width

    @property
    def bottom(self) -> float:
        """下边界 y(屏幕坐标, 值越大越靠下)."""
        return self.y + self.height

    @property
    def view_box(self) -> list[float]:
        """geo.base.view_box 的 [x, y, w, h]."""
        return [self.x, self.y, self.width, self.height]


def figure_frame(fig, ax) -> Frame:
    """量出 ax 在当前 Figure 里占的地图框, 换算成 SVG pt 坐标.

    为什么先 apply_aspect: 地图坐标区默认 aspect="equal", 实际位置在绘制前才按
    投影宽高比修正; 直接读 get_position() 会拿到未修正的矩形, 裁剪框就和地图错位.
    """
    ax.apply_aspect()
    fig_width_pt = fig.get_size_inches()[0] * 72.0
    fig_height_pt = fig.get_size_inches()[1] * 72.0
    position = ax.get_position()
    return Frame(
        x=_clean(position.x0 * fig_width_pt, _FRAME_DIGITS),
        y=_clean((1.0 - position.y1) * fig_height_pt, _FRAME_DIGITS),
        width=_clean(position.width * fig_width_pt, _FRAME_DIGITS),
        height=_clean(position.height * fig_height_pt, _FRAME_DIGITS),
    )


def svg_point(ax, lon: float, lat: float) -> tuple[float, float]:
    """把 (经度, 纬度) 换算成底图坐标(SVG pt, y 向下).

    为什么用 PlateCarree 的 mpl transform: ``ax.text(..., transform=PlateCarree())``
    画文字时 matplotlib 走的就是这条变换; 用同一条路径算锚点, 才能和旧成品 SVG 里
    文字的 translate 逐点对上(实测 39 条 Volga 标签 x 完全一致).
    """
    import cartopy.crs as ccrs

    display_x, display_y = ccrs.PlateCarree()._as_mpl_transform(ax).transform((lon, lat))
    fig = ax.figure
    scale = 72.0 / fig.dpi
    return display_x * scale, fig.get_size_inches()[1] * 72.0 - display_y * scale


def projected_angle(
    projection, lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    """两点连线在投影平面里的方向角(matplotlib rotation, 逆时针为正, 度).

    为什么在投影平面里算: matplotlib 的 rotation 是屏幕角; 兰勃特/方位投影下经线
    并不竖直, 直接拿经纬度差算 atan2 会得到与屏幕不一致的角度, 河名会明显偏离河道.
    """
    x1, y1 = projection.transform_point(lon1, lat1, _plate_carree())
    x2, y2 = projection.transform_point(lon2, lat2, _plate_carree())
    return float(math.degrees(math.atan2(y2 - y1, x2 - x1)))


def _plate_carree():
    """懒加载 PlateCarree, 避免本模块在纯数据脚本里也硬依赖 cartopy."""
    import cartopy.crs as ccrs

    return ccrs.PlateCarree()


def _normalize_rotation(rotation_deg: float) -> float:
    """归一到 (-180, 180], 与前端/抽取侧的 rotation_deg 口径一致."""
    value = float(rotation_deg) % 360.0
    if value > 180.0:
        value -= 360.0
    return _clean(value)


def _baseline_offset(
    va: str, font_size_pt: float, line_count: int, linespacing: float
) -> float:
    """锚点到首行基线的垂直偏移(底图坐标, 正值向下).

    单行 va=center: 0.36 x 字号; 多行 va=center: 整块 bbox 居中, 首行基线在中心上方
    ``(行数-1) x 行距 / 2`` 处, 所以再减去那一半. va=baseline 时锚点本身就是基线.
    """
    if va == "baseline":
        return 0.0
    if va != "center":
        raise ValueError(f"不支持的垂直对齐 va={va!r}(只支持 center/baseline)")
    return BASELINE_RATIO * font_size_pt - (line_count - 1) * linespacing * font_size_pt / 2.0


def _offset_point(
    origin: tuple[float, float], offset: float, rotation_deg: float
) -> tuple[float, float]:
    """把「沿文字向下 offset」的偏移量按 SVG 旋转角转到屏幕上.

    旋转角是 SVG 的(顺时针为正, y 向下): 文字向下方向 = (sin(r), cos(r)) 的反向?
    实测(乌拉尔山 +78° matplotlib -> SVG -78°)偏移量为 (0.36*字号*sin(-r), ...),
    即 delta = (-offset*sin(r), offset*cos(r)).
    """
    radians = math.radians(rotation_deg)
    x, y = origin
    return x - offset * math.sin(radians), y + offset * math.cos(radians)


def _fixed_ticks(lo: float, hi: float, step: float) -> list[float]:
    """区间 [lo, hi] 内 step 的整倍数, 与脚本里 np.arange 的取点规则一致."""
    if step <= 0:
        raise ValueError(f"刻度步长必须 > 0, 得到 {step!r}")
    start = math.ceil(lo / step) * step
    values: list[float] = []
    value = start
    while value <= hi + 1e-9:
        values.append(round(value, 10))
        value += step
    return values


def _degree_label(value: float, positive: str, negative: str) -> str:
    """经纬度刻度文字: 整数度写 ``35°E``, 带小数写度分 ``35°30′E``."""
    direction = positive if value >= 0 else negative
    magnitude = abs(float(value))
    degrees = int(math.floor(magnitude + 1e-9))
    minutes_total = (magnitude - degrees) * 60.0
    minutes = int(round(minutes_total))
    if minutes >= 60:
        degrees += 1
        minutes -= 60
    if minutes == 0:
        return f"{degrees}{_DEGREE}{direction}"
    return f"{degrees}{_DEGREE}{minutes:02d}{_MINUTE}{direction}"


def _lon_label(value: float) -> str:
    """经度刻度文字(东经 E / 西经 W)."""
    return _degree_label(value, "E", "W")


def _lat_label(value: float) -> str:
    """纬度刻度文字(北纬 N / 南纬 S)."""
    return _degree_label(value, "N", "S")


def _linspace(lo: float, hi: float, count: int) -> list[float]:
    """等距采样(含两端); 只用于求网格线与地图框边界的交点."""
    if count < 2:
        return [lo]
    step = (hi - lo) / (count - 1)
    return [lo + index * step for index in range(count)]


def _invert_svg(ax, x_pt: float, y_pt: float) -> tuple[float, float]:
    """底图坐标(SVG pt) -> (经度, 纬度); 沿地图框边线反查网格线交点时使用."""
    fig = ax.figure
    fig_height_pt = fig.get_size_inches()[1] * 72.0
    display_x = x_pt * fig.dpi / 72.0
    display_y = (fig_height_pt - y_pt) * fig.dpi / 72.0
    projection_x, projection_y = ax.transData.inverted().transform((display_x, display_y))
    lon, lat = _plate_carree().transform_point(projection_x, projection_y, ax.projection)
    return float(lon), float(lat)


def _edge_samples(
    ax, frame: Frame, side: str, *, count: int = 401
) -> list[tuple[float, float, float]]:
    """沿地图框一条边等距取 (另一轴坐标, 经度, 纬度).

    为什么沿边反查而不是解投影方程: 网格线与矩形边线的交点就是边线内某个点,
    把边线采样后用经/纬度插值即得交点位置; 不必假设经线是直线或平行圈是圆弧,
    对任意投影都成立.
    """
    samples: list[tuple[float, float, float]] = []
    for ratio in _linspace(0.0, 1.0, count):
        if side in ("bottom", "top"):
            x_pt = frame.x + ratio * frame.width
            y_pt = frame.bottom if side == "bottom" else frame.y
            lon, lat = _invert_svg(ax, x_pt, y_pt)
            samples.append((x_pt, lon, lat))
        else:
            y_pt = frame.y + ratio * frame.height
            x_pt = frame.x if side == "left" else frame.right
            lon, lat = _invert_svg(ax, x_pt, y_pt)
            samples.append((y_pt, lon, lat))
    return samples


def _interpolate_crossing(
    samples: Sequence[tuple[float, float, float]], target: float, index: int
) -> float | None:
    """在边线采样里找经度(index=1)/纬度(index=2)等于 target 的位置(第 0 列).

    返回 None 表示该刻度在画框内与这条边不相交(例如窄画框里的刻度), 调用方跳过.
    """
    previous = samples[0]
    for current in samples[1:]:
        before = previous[index] - target
        after = current[index] - target
        if before == 0:
            return previous[0]
        if after == 0:
            return current[0]
        if (before < 0) != (after < 0):
            ratio = -before / (after - before)
            return previous[0] + ratio * (current[0] - previous[0])
        previous = current
    return None


def relief_from_cmap(
    cmap,
    *,
    title: str,
    unit: str,
    vmin: float,
    vmax: float,
    ticks: Sequence[float],
    stops: int = 21,
) -> dict[str, Any]:
    """从 matplotlib colormap 采一组等距 stop, 组成 geo.relief.

    为什么采样而不是导出 colormap 的锚点: 前端的色标是「若干 stop + 线性渐变」,
    等距 21 个 stop 已看不出色带接缝(21 个也是旧成品抽取出来的口径), 且不同版本
    matplotlib 的锚点数据结构不稳定, 采样结果只依赖颜色本身.
    """
    import matplotlib.colors as mcolors

    if not vmax > vmin:
        raise ValueError(f"relief 需要 vmax > vmin, 得到 {vmin!r} / {vmax!r}")
    if stops < 2:
        raise ValueError(f"relief.stops 至少 2 项, 得到 {stops!r}")
    entries = []
    for index in range(stops):
        offset = index / (stops - 1)
        color = mcolors.to_hex(cmap(offset), keep_alpha=False).lower()
        entries.append({"offset": _clean(offset), "color": color})
    return {
        "title": title,
        "unit": unit,
        "vmin": _clean(vmin),
        "vmax": _clean(vmax),
        "stops": entries,
        "ticks": [_clean(float(tick)) for tick in ticks],
    }


def _legend_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """规整一条图例数据: 补齐可缺省字段并校验枚举, 与 §3 的 legend.entries 同形."""
    shape = entry.get("shape")
    if shape not in ("line", "rect", "point"):
        raise ValueError(f"图例条目 shape 必须是 line|rect|point, 得到 {shape!r}")
    label = entry.get("label")
    if not isinstance(label, str) or not label:
        raise ValueError(f"图例条目缺少非空 label: {entry!r}")
    marker = entry.get("marker")
    if shape == "point":
        if marker not in ("star", "square", "circle"):
            raise ValueError(f"point 图例条目 marker 必须是 star|square|circle, 得到 {marker!r}")
    elif marker is not None:
        raise ValueError(f"非 point 图例条目的 marker 必须为 null, 得到 {marker!r}")
    stroke = entry.get("stroke")
    fill = entry.get("fill")
    if stroke is not None and not _COLOR_RE.fullmatch(str(stroke)):
        raise ValueError(f"图例 stroke 必须是 #rrggbb, 得到 {stroke!r}")
    if fill is not None and not _COLOR_RE.fullmatch(str(fill)):
        raise ValueError(f"图例 fill 必须是 #rrggbb, 得到 {fill!r}")
    dash = entry.get("dash")
    if dash is not None:
        if not isinstance(dash, (list, tuple)) or len(dash) != 2:
            raise ValueError(f"图例 dash 必须是 null 或 [on, off], 得到 {dash!r}")
        dash = [_clean(float(dash[0])), _clean(float(dash[1]))]
    opacity = float(entry.get("opacity", 1.0))
    if not 0.0 <= opacity <= 1.0:
        raise ValueError(f"图例 opacity 必须在 [0, 1], 得到 {opacity!r}")
    result: dict[str, Any] = {
        "label": label,
        "shape": shape,
        "stroke": None if stroke is None else str(stroke).lower(),
        "width_pt": _clean(float(entry.get("width_pt", 0.0))),
        "dash": dash,
        "fill": None if fill is None else str(fill).lower(),
        "opacity": _clean(opacity),
        "marker": marker,
    }
    # v2 预留字段: v1 契约没有多行图例与 hatch, 但旧图种确实用到; 这里原样带上,
    # 前端 v1 校验会忽略未知键, 将来升 v2 时不用再回头改数据.
    if "label_lines" in entry:
        lines = entry["label_lines"]
        if not isinstance(lines, (list, tuple)) or not lines or not all(
            isinstance(item, str) and item for item in lines
        ):
            raise ValueError(f"图例 label_lines 必须是非空字符串数组, 得到 {lines!r}")
        result["label_lines"] = [str(item) for item in lines]
    if "hatch" in entry and entry["hatch"] is not None:
        result["hatch"] = str(entry["hatch"])
    return result


@dataclass
class _Label:
    """收集阶段的标签记录; 写盘时再转成 §3 的 dict."""

    id: str
    kind: str
    text: str
    lines: list[str]
    x: float
    y: float
    rotation_deg: float
    anchor: str
    font_size_pt: float
    color: str
    italic: bool
    halo: dict[str, Any] | None
    order: int


@dataclass
class _Tick:
    """收集阶段的经纬刻度记录."""

    value: float
    label: str
    x: float
    y: float
    side: str


@dataclass
class GeoDoc:
    """一张图的 geo 元数据收集器; 脚本把所有图层画完后往里填, 最后 save_map 写盘.

    为什么用可变收集器而不是一次性传参: 脚本按图层顺序画图, 每层天然知道自己的
    标注/图例/文案; 收集器让「画地理」和「攒元数据」在同一处发生, 不必事后再从
    Figure 里翻 artist.
    """

    frame: Frame
    labels: list[_Label] = field(default_factory=list)
    lon_ticks: list[_Tick] = field(default_factory=list)
    lat_ticks: list[_Tick] = field(default_factory=list)
    relief: dict[str, Any] | None = None
    legend: dict[str, Any] | None = None
    suggestions: dict[str, Any] | None = None
    graticule_style: dict[str, Any] | None = None
    base_sha256: str = ""

    # ---------------------------------------------------------------- 地名

    def add_label(
        self,
        ax,
        lon: float,
        lat: float,
        text: str,
        *,
        kind: str,
        name: str | None = None,
        index: int | None = None,
        id_kind: str | None = None,
        font_size_pt: float,
        color: str,
        ha: str = "center",
        va: str = "center",
        rotation_deg: float = 0.0,
        linespacing: float = 1.2,
        italic: bool = False,
        halo: dict[str, Any] | None = None,
    ) -> None:
        """登记一条地名候选(底图坐标), 不画文字.

        text 里的换行会拆成 lines; x/y 输出第一行基线锚点(见模块 docstring);
        rotation_deg 传 matplotlib 的 rotation(逆时针为正), 这里换算成 SVG 角.
        """
        if kind not in LABEL_KIND_SET:
            raise ValueError(f"label kind 必须是 {LABEL_KINDS} 之一, 得到 {kind!r}")
        if ha not in _ANCHORS:
            raise ValueError(f"ha 必须是 {tuple(_ANCHORS)} 之一, 得到 {ha!r}")
        if not _COLOR_RE.fullmatch(str(color)):
            raise ValueError(f"label color 必须是 #rrggbb, 得到 {color!r}")
        lines = text.split("\n")
        anchor_x, anchor_y = svg_point(ax, lon, lat)
        rotation_svg = _normalize_rotation(-float(rotation_deg))
        offset = _baseline_offset(va, float(font_size_pt), len(lines), float(linespacing))
        x, y = _offset_point((anchor_x, anchor_y), offset, rotation_svg)
        if halo is not None:
            if not isinstance(halo, dict) or not _COLOR_RE.fullmatch(str(halo.get("color"))):
                raise ValueError(f"label halo 必须是 {{'color': '#rrggbb', 'width_pt': >0}}, 得到 {halo!r}")
            if not float(halo.get("width_pt", 0.0)) > 0:
                raise ValueError(f"label halo.width_pt 必须 > 0, 得到 {halo!r}")
        self.labels.append(
            _Label(
                id=label_id(id_kind or kind, name if name is not None else text, index),
                kind=kind,
                text=text,
                lines=lines,
                x=_clean(x),
                y=_clean(y),
                rotation_deg=rotation_svg,
                anchor=_ANCHORS[ha],
                font_size_pt=_clean(float(font_size_pt)),
                color=str(color).lower(),
                italic=bool(italic),
                halo=None
                if halo is None
                else {"color": str(halo["color"]).lower(), "width_pt": _clean(float(halo["width_pt"]))},
                order=len(self.labels),
            )
        )

    # ---------------------------------------------------------------- 经纬刻度

    def add_graticule(
        self,
        ax,
        extent: tuple[float, float, float, float],
        *,
        lon_step: float,
        lat_step: float,
        lon_side: str = "bottom",
        lat_side: str = "left",
        style: dict[str, Any] | None = None,
    ) -> None:
        """按画框内的整倍数刻度收集经纬刻度(坐标取网格线与地图框边线的交点).

        extent: (min_lon, max_lon, min_lat, max_lat) 画框; 刻度值只取框内整倍数,
        与脚本画网线的 FixedLocator 同源. lon_side/lat_side 决定刻度画在哪条边,
        前端只用到经度的 x 与纬度的 y, 但这里把边线上的另一个坐标也写成边线值,
        方便人工核对.
        """
        if lon_side not in ("bottom", "top"):
            raise ValueError(f"lon_side 必须是 bottom|top, 得到 {lon_side!r}")
        if lat_side not in ("left", "right"):
            raise ValueError(f"lat_side 必须是 left|right, 得到 {lat_side!r}")
        lon_lo, lon_hi, lat_lo, lat_hi = extent
        edge_y = self.frame.bottom if lon_side == "bottom" else self.frame.y
        edge_x = self.frame.x if lat_side == "left" else self.frame.right
        lon_samples = _edge_samples(ax, self.frame, lon_side)
        for value in _fixed_ticks(lon_lo, lon_hi, lon_step):
            x = _interpolate_crossing(lon_samples, value, 1)
            if x is None:
                continue
            self.lon_ticks.append(
                _Tick(
                    value=_clean(value),
                    label=_lon_label(value),
                    x=_clean(x),
                    y=_clean(edge_y),
                    side=lon_side,
                )
            )
        lat_samples = _edge_samples(ax, self.frame, lat_side)
        for value in _fixed_ticks(lat_lo, lat_hi, lat_step):
            y = _interpolate_crossing(lat_samples, value, 2)
            if y is None:
                continue
            self.lat_ticks.append(
                _Tick(
                    value=_clean(value),
                    label=_lat_label(value),
                    x=_clean(edge_x),
                    y=_clean(y),
                    side=lat_side,
                )
            )
        if style is not None:
            self.graticule_style = {
                "stroke": str(style["stroke"]).lower(),
                "width_pt": _clean(float(style["width_pt"])),
                "dash": None
                if style.get("dash") is None
                else [_clean(float(style["dash"][0])), _clean(float(style["dash"][1]))],
                "opacity": _clean(float(style.get("opacity", 1.0))),
            }

    # ---------------------------------------------------------------- 其它块

    def set_graticule_style(
        self,
        *,
        stroke: str,
        width_pt: float,
        dash: Sequence[float] | None,
        opacity: float,
    ) -> None:
        """只登记经纬网线型, 不登记刻度(旧图没有刻度文字时可单独用它).

        与 ``add_graticule(style=...)`` 的 style 同形; 两个入口写同一个字段,
        不要混用两套格式.
        """
        if not _COLOR_RE.fullmatch(str(stroke)):
            raise ValueError(f"graticule stroke 必须是 #rrggbb, 得到 {stroke!r}")
        self.graticule_style = {
            "stroke": str(stroke).lower(),
            "width_pt": _clean(float(width_pt)),
            "dash": None
            if dash is None
            else [_clean(float(dash[0])), _clean(float(dash[1]))],
            "opacity": _clean(float(opacity)),
        }

    def set_relief(self, relief: dict[str, Any]) -> None:
        """设置高程色标数据(直接用 ``relief_from_cmap`` 的返回值)."""
        self.relief = relief

    def set_legend(self, title: str, entries: Sequence[dict[str, Any]]) -> None:
        """设置图例标题与条目; 条目经 ``_legend_entry`` 规整, 避免各脚本写法漂移."""
        if not entries:
            raise ValueError("geo.legend.entries 不能为空(没有图例就不要 set_legend)")
        self.legend = {"title": title, "entries": [_legend_entry(entry) for entry in entries]}

    def set_suggestions(self, suggestions: dict[str, Any]) -> None:
        """设置默认文案候选(title/subtitle/notes/source/area_annotation/...)."""
        allowed = {
            "title",
            "subtitle",
            "notes",
            "source",
            "area_annotation",
            "legend_title",
            "colorbar_title",
        }
        unknown = set(suggestions) - allowed
        if unknown:
            raise ValueError(f"suggestions 含未知字段: {sorted(unknown)}")
        self.suggestions = dict(suggestions)

    # ---------------------------------------------------------------- 写盘

    def to_document(self) -> dict[str, Any]:
        """转成 §3 的 geo 对象; 缺省块不写(契约允许 labels/relief/legend/suggestions 缺省)."""
        if not self.base_sha256:
            raise ValueError("base_sha256 为空: 先由 save_map() 保存底图再写 geo")
        if not self.frame.width > 0 or not self.frame.height > 0:
            raise ValueError(f"地图框尺寸必须 > 0, 得到 {self.frame}")
        document: dict[str, Any] = {
            "format": FORMAT,
            "version": VERSION,
            "base": {
                "sha256": self.base_sha256,
                "view_box": [float(value) for value in self.frame.view_box],
                "width_pt": float(self.frame.width),
                "height_pt": float(self.frame.height),
            },
            "graticule": {
                "lon": [
                    {
                        "value": tick.value,
                        "label": tick.label,
                        "x": tick.x,
                        "y": tick.y,
                        "side": tick.side,
                    }
                    for tick in self.lon_ticks
                ],
                "lat": [
                    {
                        "value": tick.value,
                        "label": tick.label,
                        "x": tick.x,
                        "y": tick.y,
                        "side": tick.side,
                    }
                    for tick in self.lat_ticks
                ],
                "style": self.graticule_style,
            },
            "labels": [
                {
                    "id": label.id,
                    "kind": label.kind,
                    "text": label.text,
                    "lines": label.lines,
                    "x": label.x,
                    "y": label.y,
                    "rotation_deg": label.rotation_deg,
                    "anchor": label.anchor,
                    "font_size_pt": label.font_size_pt,
                    "color": label.color,
                    "italic": label.italic,
                    "halo": label.halo,
                    "order": label.order,
                }
                for label in self.labels
            ],
        }
        if self.relief is not None:
            document["relief"] = self.relief
        if self.legend is not None:
            document["legend"] = self.legend
        if self.suggestions is not None:
            document["suggestions"] = self.suggestions
        return document

    def to_json(self) -> str:
        """序列化为文件内容: UTF-8 中文不转义, 2 空格缩进, 末尾一个换行(便于 diff)."""
        return json.dumps(self.to_document(), ensure_ascii=False, indent=2) + "\n"


def _rewrite_root_frame(path: Path, frame: Frame) -> None:
    """把 SVG 根标签的 viewBox/width/height 改成地图框, 其余字节不动.

    为什么只改根标签: matplotlib 输出的坐标本来就是原 Figure 坐标系, 把 viewBox
    改成地图框即可完成裁剪(y 轴不变), 既不用重新变换几何, 也让 geo 里的坐标与
    底图坐标天然一致; 重新保存成 bbox_inches 的形式会引入第二套坐标.
    """
    data = path.read_bytes()
    match = _ROOT_TAG_RE.search(data)
    if match is None:
        raise ValueError(f"SVG 里找不到根 <svg> 标签: {path}")
    tag = match.group(0)
    width = _format_pt(frame.width).encode()
    height = _format_pt(frame.height).encode()
    view_box = (
        f"{_format_pt(frame.x)} {_format_pt(frame.y)} "
        f"{_format_pt(frame.width)} {_format_pt(frame.height)}"
    ).encode()
    if _VIEWBOX_ATTR_RE.search(tag) is None:
        tag = tag[:-1] + b' viewBox="' + view_box + b'">'
    else:
        tag = _VIEWBOX_ATTR_RE.sub(
        lambda m: b"viewBox=" + m.group(1) + view_box + m.group(1), tag, count=1
    )
    tag = _WIDTH_ATTR_RE.sub(
        lambda m: b"width=" + m.group(1) + width + b"pt" + m.group(1), tag, count=1
    )
    tag = _HEIGHT_ATTR_RE.sub(
        lambda m: b"height=" + m.group(1) + height + b"pt" + m.group(1), tag, count=1
    )
    path.write_bytes(data[: match.start()] + tag + data[match.end() :])


def save_map(fig, svg_path: str | Path, doc: GeoDoc, *, dpi: float | None = None):
    """保存裁到地图框的纯几何 SVG(底图)与同名 geo.json, 返回 (svg 路径, geo 路径).

    顺序: 先 save_svg 写出完整 Figure, 再改根标签裁到 doc.frame, 最后按最终字节
    算 sha256 写 geo. 这样满足契约「geo.base.sha256 是底图文件的 sha256」.
    """
    svg_path = Path(svg_path)
    if doc.frame is None or doc.frame.width <= 0 or doc.frame.height <= 0:
        raise ValueError("save_map 需要有效的 GeoDoc.frame")
    save_svg(fig, svg_path, dpi=dpi)
    _rewrite_root_frame(svg_path, doc.frame)
    data = svg_path.read_bytes()
    if b"<text" in data:
        raise ValueError(f"底图里不允许出现文字(契约 C2): {svg_path}")
    if data.count(b"</svg>") != 1:
        raise ValueError(f"底图根元素必须恰好闭合一次: {svg_path}")
    doc.base_sha256 = hashlib.sha256(data).hexdigest()
    geo_path = svg_path.with_suffix(".geo.json")
    geo_path.write_text(doc.to_json(), encoding="utf-8")
    return svg_path, geo_path
