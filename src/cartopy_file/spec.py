# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Per-sheet rendering spec: pure data, importable without matplotlib or cartopy.

是什么: 一张图的全部可配置事实——画框、投影、画布、色带、经纬网、地名、点标记、图例与
文案, 以及子项目下的产物目录布局(地图进 ``map/``、文字信息进 ``text/``).
这里只有 dataclass 与校验, 不 import matplotlib/cartopy, 所以 ``tools/`` 里的检查脚本
可以不画图就把所有实例的产物路径与数据依赖列出来.
完整说明(为什么用数据类、字段口径、与 runner/layers 的分工)见 ``docs/reference/spec.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "CCRS_KINDS",
    "City",
    "Extent",
    "Graticule",
    "Label",
    "LegendEntry",
    "MAP_DIR",
    "Projection",
    "Relief",
    "Sheet",
    "TEXT_DIR",
    "check_slug",
    "geo_path_for",
    "map_path",
    "text_path",
]

# 子项目下的产物目录: 地图(SVG)与文字信息(geo.json)分开放, 前端按目录成对取用.
MAP_DIR = "map"
TEXT_DIR = "text"


def map_path(root: str | Path, out: str) -> Path:
    """子项目 ``root`` 里地图产物的路径: ``<root>/map/<out>``."""
    return Path(root) / MAP_DIR / out


def text_path(root: str | Path, out: str) -> Path:
    """子项目 ``root`` 里文字信息产物的路径: ``<root>/text/<out 的 stem>.geo.json``."""
    return Path(root) / TEXT_DIR / f"{Path(out).stem}.geo.json"


def geo_path_for(svg_path: str | Path) -> Path:
    """由地图产物路径反推文字信息路径, 供只拿到产物路径的检查工具使用.

    地图必须位于 ``<子项目>/map/`` 下; 不做"同级目录找 geo"的回退——布局只有一种,
    回退会让旧布局的残留文件继续被当成有效产物.
    """
    svg_path = Path(svg_path)
    if svg_path.parent.name != MAP_DIR:
        raise ValueError(f"地图产物必须在 <子项目>/{MAP_DIR}/ 下: {svg_path}")
    return svg_path.parent.parent / TEXT_DIR / f"{svg_path.stem}.geo.json"


# 投影 kind(蛇形) -> cartopy.crs 里的类名. 新增投影只改这里, 别在各脚本里各写一套.
CCRS_KINDS = {
    "lambert_conformal": "LambertConformal",
    "lambert_azimuthal_equal_area": "LambertAzimuthalEqualArea",
    "plate_carree": "PlateCarree",
    "orthographic": "Orthographic",
    "mercator": "Mercator",
    "equal_earth": "EqualEarth",
    "robinson": "Robinson",
}


def _finite(name: str, value: Any) -> float:
    """校验一个数值字段是有限数, 返回 float."""
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name} 必须是有限数, 得到 {value!r}")
    return number


def _color(name: str, value: str) -> str:
    """校验颜色是本项目统一使用的 #rrggbb(小写化由调用方保留原样)."""
    text = str(value)
    if len(text) != 7 or not text.startswith("#"):
        raise ValueError(f"{name} 必须是 #rrggbb, 得到 {value!r}")
    return text


# 标识符段(name / id_kind)的写法: 小写 ASCII, 单词之间用 - _ . 连接.
# 为什么不允许中文: geo.json 的 id 是要被前端当键用、被旧布局文件当标识符引用的,
# 显示用的中文名一律放在 labels[].text / legend.entries[].label 里.
_SLUG_RE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*\Z")


def check_slug(name: str, value: str) -> str:
    """校验一个标识符段是小写 ASCII slug; 不合格时抛 ValueError(带人话提示)."""
    text = str(value)
    if not _SLUG_RE.fullmatch(text):
        raise ValueError(
            f"{name} 必须是小写 ASCII slug(字母/数字, 用 - _ . 连接, 如 belarus、"
            f"black-sea), 得到 {text!r}; 中文只放在 text/label 里"
        )
    return text


@dataclass(frozen=True)
class Extent:
    """地图范围, 每一端都用显式字段名, 不再靠位置猜顺序.

    为什么不用四元组: 全仓同时存在两套顺序——cartopy ``set_extent`` 要
    (min_lon, max_lon, min_lat, max_lat), shapely ``box`` 要
    (min_lon, min_lat, max_lon, max_lat). 以前靠注释维持, 伏尔加的同一个文件里
    两套都出现过. 这里用命名把顺序写死, 需要哪个顺序就调 ``as_list``/``as_bbox``.
    """

    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float

    def __post_init__(self) -> None:
        for name in ("lon_min", "lon_max", "lat_min", "lat_max"):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if not self.lon_min < self.lon_max:
            raise ValueError(f"Extent 需要 lon_min < lon_max, 得到 {self}")
        if not self.lat_min < self.lat_max:
            raise ValueError(f"Extent 需要 lat_min < lat_max, 得到 {self}")
        if not (-180.0 <= self.lon_min and self.lon_max <= 360.0):
            raise ValueError(f"Extent 经度超出 [-180, 360]: {self}")
        if not (-90.0 <= self.lat_min and self.lat_max <= 90.0):
            raise ValueError(f"Extent 纬度超出 [-90, 90]: {self}")

    @property
    def as_list(self) -> list[float]:
        """cartopy ``set_extent`` 的顺序: [min_lon, max_lon, min_lat, max_lat]."""
        return [self.lon_min, self.lon_max, self.lat_min, self.lat_max]

    @property
    def as_bbox(self) -> tuple[float, float, float, float]:
        """shapely ``box`` 的顺序: (min_lon, min_lat, max_lon, max_lat)."""
        return (self.lon_min, self.lat_min, self.lon_max, self.lat_max)

    def padded(self, *, lon: float = 0.0, lat: float = 0.0) -> Extent:
        """四周各外扩若干度; 数据集的覆盖范围由画框推出来, 不再另写一套数字."""
        return Extent(
            self.lon_min - lon,
            self.lon_max + lon,
            self.lat_min - lat,
            self.lat_max + lat,
        )

    def contains(self, other: Extent, *, tol: float = 1e-9) -> bool:
        """other 是否被本范围盖住(允许 tol 的浮点误差)."""
        return (
            self.lon_min - tol <= other.lon_min
            and other.lon_max <= self.lon_max + tol
            and self.lat_min - tol <= other.lat_min
            and other.lat_max <= self.lat_max + tol
        )

    def contains_point(self, lon: float, lat: float, *, pad: float = 0.0) -> bool:
        """点是否落在范围内(可给 pad 度外扩); 用来跳过画框外的地名/城市点."""
        return (
            self.lon_min - pad <= lon <= self.lon_max + pad
            and self.lat_min - pad <= lat <= self.lat_max + pad
        )


@dataclass(frozen=True)
class Projection:
    """cartopy 投影的纯数据写法: ``kind`` 是类名的蛇形, ``params`` 是构造参数.

    为什么不在 spec 里直接放 ``ccrs.LambertConformal(...)``: 那个对象一构造就要
    导入 cartopy(以及背后的 GEOS/PROJ), 会让 ``tools/`` 里的枚举变重; 而且
    dataclass 的冻结语义也保不住外部对象. 真正构造在 ``layers.build_projection``.
    """

    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in CCRS_KINDS:
            raise ValueError(
                f"未登记的投影 kind={self.kind!r}; 已登记: {sorted(CCRS_KINDS)}"
            )
        object.__setattr__(self, "params", dict(self.params))

    @property
    def class_name(self) -> str:
        """cartopy.crs 里的类名, 供 layers 取类."""
        return CCRS_KINDS[self.kind]


@dataclass(frozen=True)
class Relief:
    """高程色带与晕渲参数.

    mode:
        ``rgba``   把高程配色与山体晕渲合成为 RGB 图再 imshow(缅甸/乌克兰/伏尔加)。
        ``scalar`` 直接把高程数组交给 imshow, 用命名色带走 matplotlib 的 norm(苏联)。
    sea/land: ``rgba`` 模式的锚点 (高程 m, ``#rrggbb``), 按高程递增; 水面锚点到 -1 m,
        陆地锚点从 +1 m 起, 中间的空隙就是海陆跳变(不画海岸线的图靠它分出海陆).
    name: ``rgba`` 模式是色带名(只影响内部 id); ``scalar`` 模式是 matplotlib 色带名.
    zorder: None 表示不传(留给 matplotlib 默认), 苏联图就是这样.
    """

    vmin: float
    vmax: float
    name: str
    mode: str = "rgba"
    sea: tuple[tuple[float, str], ...] = ()
    land: tuple[tuple[float, str], ...] = ()
    ticks: tuple[float, ...] = ()
    title: str = "高程 / 水深"
    unit: str = "m"
    stops: int = 2048
    azimuth: float = 315
    altitude: float = 45
    vert_exag: float = 1.5
    shade_strength: float | None = None
    shade_floor: float = 0.55
    alpha: float = 1.0
    zorder: float | None = 1.0

    def __post_init__(self) -> None:
        if not self.vmin < self.vmax:
            raise ValueError(f"Relief 需要 vmin < vmax, 得到 {self.vmin!r} / {self.vmax!r}")
        if self.mode not in ("rgba", "scalar"):
            raise ValueError(f"Relief.mode 必须是 rgba|scalar, 得到 {self.mode!r}")
        if self.mode == "rgba":
            if not (self.sea and self.land):
                raise ValueError(f"Relief({self.name}) 的 rgba 模式需要 sea/land 锚点")
            if self.stops < 2:
                raise ValueError(f"Relief.stops 至少 2, 得到 {self.stops!r}")
            for _, color in (*self.sea, *self.land):
                _color("Relief 锚点颜色", color)
        if not self.name:
            raise ValueError("Relief.name 不能为空")


@dataclass(frozen=True)
class Graticule:
    """经纬网与经纬刻度的取值/线型; 网线与 geo.graticule 用同一份配置.

    lon_ticks/lat_ticks 是网线位置的精确取值(以前各脚本里写死 ``np.arange(...)``).
    空元组表示「按 extent 与步长取整倍数」.
    """

    lon_step: float
    lat_step: float
    lon_ticks: tuple[float, ...] = ()
    lat_ticks: tuple[float, ...] = ()
    lon_side: str = "bottom"
    lat_side: str = "left"
    # 网线颜色: 原样传给 ax.gridlines, 允许 "gray" 这类命名色(与改前成品逐字节一致才不重画).
    color: str = "gray"
    # geo.graticule 的颜色: 契约要求 #rrggbb, 所以单独存一份, 两处必须同色.
    stroke: str = "#808080"
    width_pt: float = 0.6
    # dash 是原样传给 ax.gridlines 的线型(未缩放); matplotlib 的 LineCollection 会
    # 再乘线宽, 所以 ":" 类点线要写成 (1, 1.65) 这种「除过线宽」的值.
    dash: tuple[float, float] | None = None
    # geo 契约要的是缩放后的实际 dash(如 0.5/0.825). 不写时沿用 dash;
    # 两者不一致时(也就是 matplotlib 乘过线宽的情况)必须显式给出, 否则契约值会错.
    geo_dash: tuple[float, float] | None = None
    opacity: float = 0.55
    zorder: float = 4.0

    def __post_init__(self) -> None:
        if not (self.lon_step > 0 and self.lat_step > 0):
            raise ValueError(f"Graticule 步长必须 > 0, 得到 {self}")
        if self.lon_side not in ("bottom", "top"):
            raise ValueError(f"lon_side 必须是 bottom|top, 得到 {self.lon_side!r}")
        if self.lat_side not in ("left", "right"):
            raise ValueError(f"lat_side 必须是 left|right, 得到 {self.lat_side!r}")
        _color("Graticule.stroke", self.stroke)

    @property
    def style(self) -> dict[str, Any]:
        """geo.add_graticule / geo.set_graticule_style 要的形状."""
        return {
            "stroke": self.stroke,
            "width_pt": self.width_pt,
            "dash": self.geo_dash if self.geo_dash is not None else self.dash,
            "opacity": self.opacity,
        }


@dataclass(frozen=True)
class Label:
    """一条地名候选: 只描述语义与落点, 样式由前端 role 表决定.

    dx/dy 是相对锚点经纬度的偏移(度), 用于「城名贴在城点旁边」这类旧图排版.
    ``name`` 是 id 的标识符段(小写 ASCII slug), ``text`` 才是图上显示的文案:
    id 会被前端和旧布局文件当键用, 不能随显示文案(中文/换行/双语后缀)一起漂移.
    """

    lon: float
    lat: float
    text: str
    role: str
    font_size_pt: float
    name: str
    dx: float = 0.0
    dy: float = 0.0
    ha: str = "center"
    id_kind: str | None = None

    def __post_init__(self) -> None:
        if not float(self.font_size_pt) > 0:
            raise ValueError(f"Label.font_size_pt 必须 > 0, 得到 {self.font_size_pt!r}")
        if self.ha not in ("left", "center", "right"):
            raise ValueError(f"Label.ha 必须是 left|center|right, 得到 {self.ha!r}")
        check_slug("Label.name", self.name)
        if self.id_kind is not None:
            check_slug("Label.id_kind", self.id_kind)


@dataclass(frozen=True)
class LegendEntry:
    """一条图例: 只描述「一个符号」, 文案与顺序是数据, 排版由前端决定.

    字段与 ``geo.legend.entries`` 一一对应(见 docs/reference/geo.md);
    ``_legend_entry`` 还会再规整一遍, 这里在 import 期就报错, 免得画完图才发现.
    """

    label: str
    shape: str
    stroke: str | None = None
    fill: str | None = None
    width_pt: float = 1.0
    opacity: float = 1.0
    dash: tuple[float, float] | None = None
    marker: str | None = None
    hatch: str | None = None
    label_lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label:
            raise ValueError(f"LegendEntry.label 必须是非空字符串, 得到 {self.label!r}")
        if self.shape not in ("line", "rect", "point"):
            raise ValueError(f"LegendEntry.shape 必须是 line|rect|point, 得到 {self.shape!r}")
        if self.shape != "point" and self.marker is not None:
            raise ValueError(f"非 point 图例条目的 marker 必须为 None, 得到 {self.marker!r}")
        if self.marker is not None and self.marker not in ("star", "square", "circle"):
            raise ValueError(f"LegendEntry.marker 必须是 star|square|circle, 得到 {self.marker!r}")
        for field_name in ("stroke", "fill"):
            color = getattr(self, field_name)
            if color is not None:
                _color(f"LegendEntry.{field_name}", color)
        if not 0.0 <= float(self.opacity) <= 1.0:
            raise ValueError(f"LegendEntry.opacity 必须在 [0, 1], 得到 {self.opacity!r}")
        if self.dash is not None and len(self.dash) != 2:
            raise ValueError(f"LegendEntry.dash 必须是 None 或 (on, off), 得到 {self.dash!r}")
        if self.label_lines and not all(
            isinstance(item, str) and item for item in self.label_lines
        ):
            raise ValueError(
                f"LegendEntry.label_lines 必须是非空字符串元组, 得到 {self.label_lines!r}"
            )

    def as_geo(self) -> dict[str, Any]:
        """转成 ``GeoDoc.set_legend`` 要的 dict(缺省字段不写, 由 geo 侧补默认值)."""
        entry: dict[str, Any] = {
            "label": self.label,
            "shape": self.shape,
            "stroke": self.stroke,
            "width_pt": self.width_pt,
            "dash": self.dash,
            "fill": self.fill,
            "opacity": self.opacity,
            "marker": self.marker,
        }
        if self.label_lines:
            entry["label_lines"] = list(self.label_lines)
        if self.hatch is not None:
            entry["hatch"] = self.hatch
        return entry


@dataclass(frozen=True)
class City:
    """一个城市点标记; 首都用星形, 其余用圆点(形状固定, 尺寸/颜色是数据)."""

    lon: float
    lat: float
    size: float
    facecolor: str
    edgecolor: str
    edge_width: float
    capital: bool = False
    name: str = ""


@dataclass(frozen=True)
class Sheet:
    """一张产物的完整规格; 一个脚本可以有多张(伏尔加的两张图就是两个 Sheet).

    ``out`` 只是地图文件名: 计划写到 ``<子项目>/map/<out>``, 文字信息写到
    ``<子项目>/text/<stem>.geo.json``, 目录由本模块的 ``map_path``/``text_path`` 决定.
    """

    id: str
    out: str
    extent: Extent
    projection: Projection
    figsize: tuple[float, float]
    graticule: Graticule
    # None 表示这张图不铺高程(演示图), 此时 dem_id 与色标都不出现.
    relief: Relief | None = None
    # None 表示用 plt.subplots 的默认布局(苏联图); 给了就是 add_axes 的矩形.
    axes: tuple[float, float, float, float] | None = None
    basemap: bool = True
    tight_layout: bool = False
    base_ocean: str = "#a2d0ee"
    base_land: str = "#dce4a2"
    regrid_shape: int | None = 3200
    dpi: int = 300
    dataset_ids: tuple[str, ...] = ()
    dem_id: str | None = None
    labels: tuple[Label, ...] = ()
    cities: tuple[City, ...] = ()
    # 图例整块声明在这里: 条目是数据, geo.json 的 legend 由 standard_collect 写.
    # 空元组表示这张图没有图例(此时 legend_title 必须为空).
    legend: tuple[LegendEntry, ...] = ()
    legend_title: str = ""
    # 经纬刻度文字: False 表示只登记网线线型、不输出刻度文字(苏联图的历史口径).
    graticule_ticks: bool = True
    title: str = ""
    subtitle: str = ""
    notes: tuple[str, ...] = ()
    colorbar_title: str = "高程 / 水深"
    # 图种特有的补充说明, 追加到「数据来源」末尾(如缩写表「MNDAA=…」).
    extra_source: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Sheet.id 不能为空")
        if not self.out.endswith(".svg"):
            raise ValueError(f"Sheet.out 必须是 .svg, 得到 {self.out!r}")
        if Path(self.out).name != self.out:
            raise ValueError(
                f"Sheet.out 只能是地图文件名, 目录由 <子项目>/{MAP_DIR} 决定: {self.out!r}"
            )
        if self.figsize[0] <= 0 or self.figsize[1] <= 0:
            raise ValueError(f"Sheet.figsize 必须为正, 得到 {self.figsize!r}")
        if self.dem_id is not None and self.dem_id not in self.dataset_ids:
            raise ValueError(
                f"Sheet.dem_id={self.dem_id!r} 必须在 dataset_ids={self.dataset_ids!r} 里"
            )
        if self.legend and not self.legend_title:
            raise ValueError(f"Sheet({self.id}) 有 legend 却没有 legend_title")
        if self.legend_title and not self.legend:
            raise ValueError(f"Sheet({self.id}) 有 legend_title 却没有 legend 条目")


def sheets_of(sheets) -> tuple[Sheet, ...]:
    """把一组 Sheet 统一成 tuple, 并检查 id/产物名不重复."""
    items = tuple(sheets)
    ids = [sheet.id for sheet in items]
    if len(set(ids)) != len(ids):
        raise ValueError(f"Sheet.id 重复: {ids}")
    outputs = [sheet.out for sheet in items]
    if len(set(outputs)) != len(outputs):
        raise ValueError(f"Sheet.out 重复: {outputs}")
    return items
