# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Volga subproject: the render spec of the two Volga maps.

是什么: 伏尔加流域两张图的规格(画框,投影,色带,经纬网,版式,文案), 两图共用一套数值;
以及 ``prepare`` 生成的三个派生 GeoJSON 在本子项目 ``build/`` 下的位置. 原始数据清单与
下载范围在数据项目 miko_gis_data; 清洗/裁剪口径在本子项目的 prepare.py.
完整说明见 ``docs/reference/spec.md``; 两个图种的设计取舍见 ``docs/maps/volga.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cartopy_file.spec import (
    Extent,
    Graticule,
    Label,
    LegendEntry,
    Projection,
    Relief,
    Sheet,
    build_path,
)

ROOT = Path(__file__).resolve().parent

# 数据项目 miko_gis_data 里这个区域的 manifest 键(group).
DATA_GROUP = "volga"

# ============================
# 派生产物(本仓 prepare.py 生成, 目录布局见 docs/reference/spec.md)
# ============================
# 清洗/裁剪后的 GeoJSON 放在本子项目 build/ 下: 它是图种口径的中间产物, 不属于数据根;
# 删掉后重跑 ``python Volga/main.py prepare`` 即可恢复(不会重新联网).
VOLGA_SUBJECTS_GEOJSON = build_path(ROOT, "volga_subjects.geojson")
VOLGA_BASIN_GEOJSON = build_path(ROOT, "volga_basin.geojson")
RUSSIA_BORDER_GEOJSON = build_path(ROOT, "russia_border.geojson")

# ============================
# 画框
# ============================
# 流域图画框: 西界留出瓦尔代丘陵(伏尔加河源头)以西约 1.7°; 东界到乌拉尔山西坡;
# 南界 44.4°N 覆盖里海西北岸与三角洲; 北界 62.3°N 留出上卡马河源地的余量.
EXTENT_BASIN = Extent(30.3, 62.3, 44.4, 62.3)

# 周边共和国图画框: 不画科米与卡尔梅克后按内容收窄, 北到 59°N(科米南缘以南),
# 西到 40°E(上伏尔加), 东到 60°E(卡马河以东的乌拉尔西坡); 南界沿用 44.4°N,
# 保留流域三角洲与里海西北岸.
EXTENT_REPUBLICS = Extent(40.0, 60.0, 44.4, 59.0)

# ============================
# 投影 / 色带 / 经纬网
# ============================
# 兰勃特等角圆锥: 中央经线取流域中部, 标准纬线夹住画框南北缘(47°N / 57°N),
# 使流域主体处于低形变区.
PROJECTION = Projection(
    "lambert_conformal",
    {
        "central_longitude": 46.0,
        "central_latitude": 53.0,
        "standard_parallels": (47.0, 57.0),
    },
)

# 高程配色与晕渲: 画框内最低为里海约 -1000 m, 最高为南乌拉尔山约 1640 m;
# 取 -2500~2500 m 的两端余量. 色带在 0 m 处断开(水/陆), 陆地锚点密集放在
# 0~500 m 的伏尔加平原; 晕渲用"只压暗"的乘法因子(relief.make_relief 的
# shade_strength), 平原不会被压成灰底. 理由见 docs/maps/volga.md 设计要点 4.
VOLGA_RELIEF = Relief(
    vmin=-2500,
    vmax=2500,
    name="volga_relief",
    sea=(
        (-2500, "#07203c"),
        (-2000, "#0f3c66"),
        (-1250, "#1b628f"),
        (-700, "#2f82b5"),
        (-300, "#5aa2cd"),
        (-100, "#75b3db"),
        (-20, "#8cc4e7"),
        (-1, "#a2d0ee"),
    ),
    land=(
        (1, "#c9d98d"),
        (40, "#cfd990"),
        (90, "#d9dd96"),
        (150, "#e0e19c"),
        (230, "#ddd596"),
        (340, "#d6c58a"),
        (500, "#c4a873"),
        (700, "#ab8a5e"),
        (950, "#8f7049"),
        (1200, "#7a5f40"),
        (1550, "#786a58"),
        (1900, "#9c9186"),
        (2500, "#d9d5cd"),
    ),
    ticks=(-2000, -1000, 0, 500, 1000, 1500, 2000),
    title="高程 / 水深",
    unit="m",
    # 平原起伏只有几十米, 不夸张看不出河谷与丘陵.
    vert_exag=3.0,
    shade_strength=1.7,
    zorder=1.0,
)

# 经纬网: 经度每 5°,纬度每 2°; 点线在 0.5 pt 线宽下的成品 dash 是 (1, 1.65) x 0.5,
# 即 geo.graticule 里登记的 [0.5, 0.825]. 绘图端用 matplotlib 的 ":" 复现这条点线
# (``layers.add_gridlines`` 的 dash 会被 matplotlib 再乘一次线宽, 与 geo 契约的
# 成品值不同, 所以本图在 volga.py 里自己画网线, 见 docs/maps/volga.md 注意事项).
VOLGA_GRATICULE = Graticule(
    lon_step=5.0,
    lat_step=2.0,
    color="gray",
    stroke="#808080",
    width_pt=0.5,
    # dash 是原样给 ax.gridlines 的线型(不要乘线宽的预缩放值): ":" 对应 (1, 1.65);
    # geo 契约要的是乘过线宽的成品值, 所以显式给一份 geo_dash.
    dash=(1.0, 1.65),
    geo_dash=(0.5, 0.825),
    opacity=0.4,
    zorder=4.5,
)

# ============================
# 版式
# ============================
# 地图区高固定(英寸), 宽度按画框在目标投影下的宽高比算, 再加右侧原图例/色标/注面板的
# 旧占位, 得到画布宽. 这样两张画框不同的图都能让地图正好填满左侧地图区, 不靠留白对齐;
# 右侧留白等前端排版接管.
FIG_HEIGHT_IN = 12.2
MAP_LEFT_IN = 0.54
MAP_BOTTOM_IN = 0.8784
MAP_HEIGHT_IN = 9.8942
PANEL_GAP_IN = 0.218
PANEL_WIDTH_IN = 4.23
FIG_RIGHT_IN = 0.144

# 画框在兰勃特投影下的宽高比. 数值由 cartopy 的
# ``LambertConformal.project_geometry(画框环, PlateCarree).bounds`` 算得(原
# ``_projected_aspect``); 这里写成常量是为了让 config.py 保持「纯数据,不 import
# cartopy」--数据清单检查只读本文件, 不必为两个数拖起整套投影库. 改画框必须重算:
# 公式与算法见 docs/maps/volga.md 设计要点 1.
ASPECT_BASIN = 1.2582431702887398
ASPECT_REPUBLICS = 0.9482197122151442


@dataclass(frozen=True)
class Layout:
    """画布与地图区的位置(figure 分数), 由画框的投影宽高比算出."""

    figsize: tuple[float, float]
    map_rect: tuple[float, float, float, float]
    map_width_in: float


def make_layout(aspect: float) -> Layout:
    """按画框宽高比定画布宽度, 并给出地图区的位置.

    画布宽度仍计入右侧面板的旧占位(见 PANEL_* 常量), 因此地图区的位置与大小与改前一致.
    """
    map_width_in = MAP_HEIGHT_IN * aspect
    fig_width_in = (
        MAP_LEFT_IN + map_width_in + PANEL_GAP_IN + PANEL_WIDTH_IN + FIG_RIGHT_IN
    )
    map_rect = (
        MAP_LEFT_IN / fig_width_in,
        MAP_BOTTOM_IN / FIG_HEIGHT_IN,
        map_width_in / fig_width_in,
        MAP_HEIGHT_IN / FIG_HEIGHT_IN,
    )
    return Layout(
        figsize=(fig_width_in, FIG_HEIGHT_IN),
        map_rect=map_rect,
        map_width_in=map_width_in,
    )


LAYOUT_BASIN = make_layout(ASPECT_BASIN)
LAYOUT_REPUBLICS = make_layout(ASPECT_REPUBLICS)
LAYOUTS = {"basin": LAYOUT_BASIN, "republics": LAYOUT_REPUBLICS}

# ============================
# 图种特有图层的数据
# ============================
# 图面配色: 主题层各一个固定颜色, 避免读图歧义.
COLOR_BASIN_FILL = "#3f8fc4"   # 流域面: 浅蓝, 叠在地形上不抢细节
COLOR_BASIN_EDGE = "#1b5c8c"   # 流域界: 深蓝
COLOR_BASIN_ALPHA = 0.15
COLOR_REPUBLIC_FILL = "#7b5aa6"   # 联邦主体共和国: 蓝紫, 与蓝色水系/暖色地形都分得开
COLOR_REPUBLIC_EDGE = "#4a2f6b"
COLOR_REPUBLIC_ALPHA = 0.23
COLOR_SUBJECT = "#5f6b73"      # 其余联邦主体界: 中性灰虚线, 只作背景
COLOR_BORDER = "#4a4a4a"       # 国界(GADM 4.1 口径)
COLOR_RIVER = "#5c93bf"        # 支流
COLOR_RIVER_MEDIUM = "#4a86b8"  # 较大支流
COLOR_RIVER_TRUNK = "#2d6ea6"  # 干流(高等级/大流量河段)
COLOR_RIVER_HALO = "#e8f4ff"   # 干流白描边
COLOR_WATER = "#b9d7ee"        # 梯级水库水面
COLOR_WATER_EDGE = "#4a7fb0"

# 周边八个联邦主体共和国(GADM NAME_1): 流域直接覆盖/紧邻的民族共和国.
# 流域图不画行政区; 共和国图只保留前六个, 科米与卡尔梅克不画.
REPUBLICS = (
    "Tatarstan",
    "Bashkortostan",
    "Chuvash",
    "Mariy-El",
    "Mordovia",
    "Udmurt",
    "Kalmyk",
    "Komi",
)
REPUBLICS_SHOWN = REPUBLICS[:6]
REPUBLICS_HIDDEN = frozenset(REPUBLICS[6:])

# 共和国名称: GADM NAME_1 -> (经度, 纬度, 文字). 放在各共和国境内的空旷处,
# 避开首府城点与主要河湖.
# id 的 slug 用 key 的小写形式(如 tatarstan,mariy-el), 与 GADM 的 NAME_1 一一对应.
REPUBLIC_LABELS: dict[str, tuple[float, float, str]] = {
    "Tatarstan": (50.30, 54.85, "鞑靼斯坦共和国"),
    "Bashkortostan": (56.60, 53.35, "巴什科尔托斯坦共和国"),
    "Chuvash": (47.05, 55.28, "楚瓦什共和国"),
    "Mariy-El": (48.90, 57.22, "马里埃尔共和国"),
    "Mordovia": (44.50, 54.85, "莫尔多瓦共和国"),
    "Udmurt": (52.60, 57.55, "乌德穆尔特共和国"),
    "Kalmyk": (45.25, 46.78, "卡尔梅克共和国"),
    "Komi": (54.50, 61.00, "科米共和国"),
}

# 城市: (经度, 纬度, 名称, id slug, 类型, 文字偏移经度, 文字偏移纬度, 水平对齐).
# 类型: capital=首都(星形), rep=共和国首府(方块), city=一般城市(圆点).
# 偏移与对齐是改前成品的文字落点, 现在只用来产出 geo.labels 的锚点, 不再画文字.
# slug 是小写 ASCII, 只进 id(见 docs/reference/spec.md 的 Label); 显示名只进 text.
CITIES = [
    (37.617, 55.755, "莫斯科", "moscow", "capital", 0.12, 0.14, "left"),
    (35.900, 56.858, "特维尔", "tver", "city", 0.10, 0.10, "left"),
    (39.873, 57.626, "雅罗斯拉夫尔", "yaroslavl", "city", -0.12, 0.16, "right"),
    (40.926, 57.768, "科斯特罗马", "kostroma", "city", 0.12, -0.16, "left"),
    (44.002, 56.326, "下诺夫哥罗德", "nizhny-novgorod", "city", 0.10, 0.10, "left"),
    (49.660, 58.603, "基洛夫", "kirov", "city", 0.10, 0.10, "left"),
    (56.248, 58.010, "彼尔姆", "perm", "city", 0.10, 0.10, "left"),
    (53.204, 56.852, "伊热夫斯克", "izhevsk", "rep", 0.10, 0.10, "left"),
    (49.122, 55.788, "喀山", "kazan", "rep", 0.10, 0.10, "left"),
    (55.972, 54.738, "乌法", "ufa", "rep", 0.10, 0.10, "left"),
    (50.150, 53.195, "萨马拉", "samara", "city", 0.10, 0.10, "left"),
    (48.403, 54.317, "乌里扬诺夫斯克", "ulyanovsk", "city", 0.10, 0.10, "left"),
    (46.034, 51.533, "萨拉托夫", "saratov", "city", 0.10, 0.10, "left"),
    (44.501, 48.708, "伏尔加格勒", "volgograd", "city", 0.10, 0.10, "left"),
    (48.034, 46.349, "阿斯特拉罕", "astrakhan", "city", 0.10, 0.10, "left"),
    (47.251, 56.132, "切博克萨雷", "cheboksary", "rep", -0.10, -0.12, "right"),
    (47.890, 56.638, "约什卡尔奥拉", "yoshkar-ola", "rep", 0.10, -0.12, "left"),
    (45.184, 54.183, "萨兰斯克", "saransk", "rep", 0.10, -0.10, "left"),
    (45.000, 53.195, "奔萨", "penza", "city", 0.10, -0.10, "left"),
    (39.741, 54.626, "梁赞", "ryazan", "city", 0.10, 0.10, "left"),
    (55.097, 51.768, "奥伦堡", "orenburg", "city", 0.10, 0.10, "left"),
    (44.256, 46.307, "埃利斯塔", "elista", "rep", -0.12, -0.12, "right"),
    (50.836, 61.668, "瑟克特夫卡尔", "syktyvkar", "rep", 0.10, 0.10, "left"),
]

# 河名: (经度, 纬度, 文字, id slug). 文字放在河道旁的陆地上; 旋转由前端处理.
# 同一条河标两段时 slug 相同, 由建表函数按河名表顺序加 -1/-2 序号(见 _river_labels).
RIVER_LABELS = [
    (43.05, 56.10, "伏尔加河", "volga"),
    (45.35, 49.90, "伏尔加河", "volga"),
    (53.40, 55.35, "卡马河", "kama"),
    (41.55, 54.85, "奥卡河", "oka"),
    (56.30, 54.15, "别拉亚河", "belaya"),
    (50.20, 57.45, "维亚特卡河", "vyatka"),
]

# 邻国名称: 只标画框内可见的三个邻国: (经度, 纬度, 文字, id slug).
COUNTRY_LABELS = [
    (55.10, 47.60, "哈萨克斯坦", "kazakhstan"),
    (30.95, 53.45, "白俄罗斯", "belarus"),
    (33.10, 48.75, "乌克兰", "ukraine"),
]

# 海域名称: (经度, 纬度, 文字, id slug).
SEA_LABELS = [
    (50.60, 45.35, "里海", "caspian-sea"),
    (31.20, 45.05, "黑海", "black-sea"),
    (36.80, 46.05, "亚速海", "azov-sea"),
]

# 地貌名称: (经度, 纬度, 文字, id slug). 乌拉尔山的走向旋转由前端处理.
HIGHLAND_LABELS = [
    (33.10, 57.55, "瓦尔代丘陵", "valdai-hills"),
    (46.90, 52.20, "伏尔加高地", "volga-upland"),
    (47.40, 48.60, "里海低地", "caspian-lowland"),
    (59.30, 56.80, "乌拉尔山", "urals"),
]

# 河网分级: Natural Earth 10m 河流的 scalerank(数值越小越主要)分三档.
# 画框约 1:770 万比例尺, 正好是 Natural Earth 10m 的设计尺度.
RIVER_TRUNK_MAX_SCALERANK = 3   # 伏尔加干流
RIVER_MEDIUM_MAX_SCALERANK = 7  # 卡马/奥卡/维亚特卡/别拉亚等
RIVER_EXCLUDE_FEATURECLA = frozenset({"Canal"})

# 图注: 面积由 Volga/volga.py 按派生流域面重算后填入 {area_wan:.0f}; 其余是固定文字.
NOTES_BASIN = (
    "注 1:流域为 HydroBASINS level 5 的伏尔加河主流域合并,面积约 {area_wan:.0f} 万 km²(HydroSHEDS 口径,不含里海).",
    "注 2:本图不画联邦主体行政区界,只保留俄罗斯国界(GADM 4.1 口径,不含克里米亚).",
    "注 3:河网与湖库为 Natural Earth 10m;河流按 scalerank 分三级,湖泊/水库按面填色;里海不在湖泊层,其水深仍由地形配色表达.",
    "注 4:地形 ETOPO 2022(15″);投影 Lambert Conformal Conic,中央经线 46°E,标准纬线 47°N / 57°N.",
)

NOTES_REPUBLICS = (
    "注 1:流域为 HydroBASINS level 5 的伏尔加河主流域合并,面积约 {area_wan:.0f} 万 km²(HydroSHEDS 口径,不含里海).",
    "注 2:加粗填色者为流域周边的六个联邦主体共和国,科米与卡尔梅克不画;其余联邦主体只画灰色虚线界线.行政区为 GADM 4.1,其俄罗斯国界口径不含克里米亚.",
    "注 3:河网与湖库为 Natural Earth 10m;河流按 scalerank 分三级,湖泊/水库按面填色;里海不在湖泊层,其水深仍由地形配色表达.",
    "注 4:地形 ETOPO 2022(15″);投影 Lambert Conformal Conic,中央经线 46°E,标准纬线 47°N / 57°N.",
)

# 图内流域面积注记: 只有共和国图把这块文字画在图内; 面积出图时才算得出来,
# 所以 text 里留 {area_wan:.0f} 占位符, 由 runner.render(label_vars=...) 在出图时填充.
BASIN_AREA_LABEL = (42.55, 51.95, "伏尔加河流域约 {area_wan:.0f} 万 km²", "volga-basin")
# 图外面积注记(geo.suggestions.area_annotation): 只有流域图用; 共和国图把同一块文字
# 画在图内, 不再给图外面板重复一份. 数值同样是出图时才知道的.
AREA_ANNOTATION = ("伏尔加河流域", "约 {area_wan:.0f} 万 km²")

# 图例: 只列该图实际画了的线型/面. 两张图共用流域/国界/水系/点位条目, 共和国图
# 在流域条目后多两条行政区条目(与 Theme.draw_admin 的开关一致).
# 条目顺序就是 geo.legend.entries 的顺序, 也是前端的排版顺序.
LEGEND_TITLE = "图例"
_LEGEND_BASIN_AREA = LegendEntry(
    "伏尔加河流域",
    "rect",
    stroke=COLOR_BASIN_EDGE,
    width_pt=2.0,
    fill=COLOR_BASIN_FILL,
    opacity=0.45,
)
# 共和国图独有的行政区条目.
_LEGEND_ADMIN = (
    LegendEntry(
        "周边联邦主体共和国",
        "rect",
        stroke=COLOR_REPUBLIC_EDGE,
        width_pt=1.8,
        fill=COLOR_REPUBLIC_FILL,
        opacity=0.45,
    ),
    LegendEntry(
        "其他联邦主体界",
        "line",
        stroke=COLOR_SUBJECT,
        width_pt=0.9,
        dash=(5.0, 3.0),
        opacity=0.8,
    ),
)
# 两张图共用的条目: 国界 -> 水系 -> 城市点位.
_LEGEND_COMMON = (
    LegendEntry("国界", "line", stroke=COLOR_BORDER, width_pt=1.4),
    LegendEntry("干流(伏尔加河等)", "line", stroke=COLOR_RIVER_TRUNK, width_pt=1.8),
    LegendEntry("支流", "line", stroke=COLOR_RIVER, width_pt=0.8),
    LegendEntry(
        "湖泊 / 水库水面",
        "rect",
        stroke=COLOR_WATER_EDGE,
        width_pt=0.6,
        fill=COLOR_WATER,
    ),
    LegendEntry(
        "首都", "point", stroke="#000000", width_pt=1.5, fill="#ffd200", marker="star",
    ),
    LegendEntry(
        "共和国首府", "point", stroke="#000000", width_pt=1.5,
        fill="#ffffff", marker="square",
    ),
    LegendEntry(
        "城市", "point", stroke="#000000", width_pt=1.5, fill="#ffffff", marker="circle",
    ),
)
LEGEND_BASIN = (_LEGEND_BASIN_AREA, *_LEGEND_COMMON)
LEGEND_REPUBLICS = (_LEGEND_BASIN_AREA, *_LEGEND_ADMIN, *_LEGEND_COMMON)


@dataclass(frozen=True)
class Theme:
    """一张图的行政区主题开关与画框滤镜(``Sheet`` 没有这些图种特有字段).

    draw_admin: 是否画联邦主体行政区; area_label_in_map: 流域面积注记是否画在图内
    (流域图的同一块文字在旧版是图外面板, 由 geo.suggestions.area_annotation 带给前端).
    republics/hidden_subjects: 高亮的共和国与「既不填色也不画自己的界线」的共和国.
    """

    draw_admin: bool
    area_label_in_map: bool
    republics: tuple[str, ...] = ()
    hidden_subjects: frozenset[str] = frozenset()


THEMES = {
    "basin": Theme(draw_admin=False, area_label_in_map=False),
    "republics": Theme(
        draw_admin=True,
        area_label_in_map=True,
        republics=REPUBLICS_SHOWN,
        hidden_subjects=REPUBLICS_HIDDEN,
    ),
}

# ============================
# 地名表(按画框过滤后写进各自的 Sheet.labels)
# ============================
def _label(lon, lat, text, slug, role, **kwargs) -> Label:
    """写 Label 的短辅助函数; 顺序即前端叠放顺序, slug 是 id 的 ASCII 段."""
    return Label(lon, lat, text, role=role, name=slug, **kwargs)


def _river_labels(extent: Extent) -> tuple[Label, ...]:
    """河名: 同一条河标多段时 id 加 1 起算序号; 序号按河名表顺序计, 与改前一致."""
    counts: dict[str, int] = {}
    for _, _, _, slug in RIVER_LABELS:
        counts[slug] = counts.get(slug, 0) + 1
    seen: dict[str, int] = {}
    labels: list[Label] = []
    for lon, lat, text, slug in RIVER_LABELS:
        seen[slug] = seen.get(slug, 0) + 1
        if not extent.contains_point(lon, lat):
            continue
        # 重复河名把序号并进 slug(与改前 add_label 的 index 产出同名 id, 如 volga-1).
        name = f"{slug}-{seen[slug]}" if counts[slug] > 1 else slug
        labels.append(_label(lon, lat, text, name, "river"))
    return tuple(labels)


def _labels_for(extent: Extent, theme: Theme) -> tuple[Label, ...]:
    """按画框与主题生成一张图的完整地名表.

    顺序按旧图 zorder 升序登记(前端 scene 按 order 叠放): 国名/海名/地貌(9.0),
    图内流域名(9.2),共和国名(9.3),河名(9.4),城市(10.1). 画框外的候选跳过,
    与改前按画框过滤文字的行为一致.
    """
    labels: list[Label] = []
    labels += [
        _label(lon, lat, text, slug, "country")
        for lon, lat, text, slug in COUNTRY_LABELS
        if extent.contains_point(lon, lat)
    ]
    labels += [
        _label(lon, lat, text, slug, "sea")
        for lon, lat, text, slug in SEA_LABELS
        if extent.contains_point(lon, lat)
    ]
    labels += [
        _label(lon, lat, text, slug, "highland")
        for lon, lat, text, slug in HIGHLAND_LABELS
        if extent.contains_point(lon, lat)
    ]
    # 图内流域名: 只有共和国图在图上写「伏尔加河流域 / 面积」; 流域图的同一块
    # 文字走 AREA_ANNOTATION 带给前端(图外面板).
    if theme.area_label_in_map and extent.contains_point(*BASIN_AREA_LABEL[:2]):
        lon, lat, text, slug = BASIN_AREA_LABEL
        labels.append(_label(lon, lat, text, slug, "area-basin"))
    # 共和国名: id_kind=republic 保留旧的 label-republic-* 前缀.
    for key in theme.republics:
        lon, lat, text = REPUBLIC_LABELS[key]
        if not extent.contains_point(lon, lat):
            continue
        labels.append(
            _label(lon, lat, text, key.lower(), "area-accent-1", id_kind="republic")
        )
    labels += _river_labels(extent)
    # 城市: 文字跟着点位偏移; 大小城市靠符号区分.
    labels += [
        _label(lon + dx, lat + dy, text, slug, "city", ha=align)
        for lon, lat, text, slug, _kind, dx, dy, align in CITIES
        if extent.contains_point(lon, lat)
    ]
    return tuple(labels)


# 两张图的画框不同, 过滤后的地名表各建一份: 流域图没有行政区与图内面积注记,
# 共和国图没有画框外的邻国/海名/地貌与城市.
LABELS_BASIN = _labels_for(EXTENT_BASIN, THEMES["basin"])
LABELS_REPUBLICS = _labels_for(EXTENT_REPUBLICS, THEMES["republics"])

# ============================
# 图规格
# ============================
SHEET_BASIN = Sheet(
    id="basin",
    out="volga_basin_topography_etopo2022_lambert_conformal.svg",
    extent=EXTENT_BASIN,
    projection=PROJECTION,
    figsize=LAYOUT_BASIN.figsize,
    relief=VOLGA_RELIEF,
    graticule=VOLGA_GRATICULE,
    axes=LAYOUT_BASIN.map_rect,
    basemap=False,
    tight_layout=False,
    # ETOPO 盖住整个画框, 只露边缘时用海水色兜底; 不铺 Natural Earth 陆地色.
    base_ocean="#a2d0ee",
    # 默认按 300 dpi 定晕渲栅格密度; 绘图脚本会按 --dpi 重算(与原实现一致).
    regrid_shape=max(1200, int(LAYOUT_BASIN.map_width_in * 300)),
    dataset_ids=(
        "etopo-volga",
        "hybas-eu-lev05",
        "gadm41-rus",
        "ne-rivers-10m",
        "ne-lakes-10m",
        "ne-ocean-10m",
        "ne-coastline-10m",
    ),
    title="伏尔加河流域地形图",
    subtitle="ETOPO 2022 | 流域: HydroSHEDS | 国界: GADM 4.1 | 兰勃特等角圆锥投影",
    labels=LABELS_BASIN,
    legend=LEGEND_BASIN,
    legend_title=LEGEND_TITLE,
    notes=NOTES_BASIN,
    colorbar_title="高程 / 水深",
)

SHEET_REPUBLICS = Sheet(
    id="republics",
    out="volga_basin_republics_topography_etopo2022_lambert_conformal.svg",
    extent=EXTENT_REPUBLICS,
    projection=PROJECTION,
    figsize=LAYOUT_REPUBLICS.figsize,
    relief=VOLGA_RELIEF,
    graticule=VOLGA_GRATICULE,
    axes=LAYOUT_REPUBLICS.map_rect,
    basemap=False,
    tight_layout=False,
    base_ocean="#a2d0ee",
    regrid_shape=max(1200, int(LAYOUT_REPUBLICS.map_width_in * 300)),
    dataset_ids=(
        "etopo-volga",
        "hybas-eu-lev05",
        "gadm41-rus",
        "ne-rivers-10m",
        "ne-lakes-10m",
        "ne-ocean-10m",
        "ne-coastline-10m",
    ),
    title="伏尔加河流域与周边联邦主体共和国地形图",
    subtitle="ETOPO 2022 | 流域: HydroSHEDS | 行政区: GADM 4.1 | 兰勃特等角圆锥投影",
    labels=LABELS_REPUBLICS,
    legend=LEGEND_REPUBLICS,
    legend_title=LEGEND_TITLE,
    notes=NOTES_REPUBLICS,
    colorbar_title="高程 / 水深",
)

SHEETS = (SHEET_BASIN, SHEET_REPUBLICS)
