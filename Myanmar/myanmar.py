#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Draw a full-territory topographic map of the Republic of the Union of Myanmar.

是什么: 读取本地 NOAA ETOPO 2022 缅甸区域高程, 用兰勃特等角圆锥投影绘制全国
地形图, 叠加 Natural Earth 10m 国界(仅陆上段, 半透明红色)与邻国国界(灰虚线),
并画出主要城市点; 海岸线不单独绘制, 海陆界线由地形配色在 0 m 处的跳变表达.
文字与版面由前端接管, 本脚本同时产出同名的 geo.json: 底图只画地理要素, 地名/
色标/标题/来源只以 ``GeoDoc`` 数据形式登记, 不再画任何文字; 字段与口径见
``docs/reference/geo.md``. 完整说明(投影选择、数据来源、运行方式)见
``docs/maps/myanmar.md``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import matplotlib.colors as mcolors  # 构造 0 m 处断开的海陆色带
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网线位置定位
import numpy as np  # 数组运算
from shapely.ops import unary_union  # 合并多块几何, 得到缅甸整体轮廓

import map_lib  # 与本目录共用的 ETOPO/晕渲/边界工具

# cartopy 底图缓存统一到仓库 data/cartopy, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy

configure_cartopy()

from cartopy_file.output import apply_svg_output

# 底图 + geo.json 出图: save_map 同时写裁到地图框的 SVG 与同名 geo.json,
# 见 docs/reference/geo.md.
from cartopy_file.geo import GeoDoc, figure_frame, relief_from_cmap, save_map

# 国界与海岸线重合时只保留国界: 用共享剪枝工具裁掉沿海段, 见 docs/reference/overlap.md.
from cartopy_file.overlap import cut, overlap_mask

# 产物统一为 SVG, 见 docs/reference/output.md.
apply_svg_output()


# ============================
# 配置
# ============================
# 本地数据目录, 必须在导入 matplotlib 之前定义.
# Natural Earth 10m 国家边界目录(由 download_etopo.py 解压得到).
BOUNDARY_DIR = DATA_DIR / "ne_10m_admin_0_countries"

# 地图显示范围, 单位为度, 格式 [min_lon, max_lon, min_lat, max_lat].
# 缅甸实际范围约 92.17~101.17°E, 9.79~28.54°N; 四周各留出约 5° 余量,
# 让孟加拉国、印度东北部、中国云南、泰国、老挝和安达曼海进入画面作为地理参照.
# 注意: download_etopo.py 下载的高程子集是 85.3~107.7°E / 4.9~31.1°N, 比这个画框大,
# 原因是圆锥投影的矩形画框顶边会张开到约 85.4~107.6°E, 子集必须盖住它才不会露出空白.
EXTENT = [87.0, 106.0, 5.0, 31.0]

# 投影参数: 兰勃特等角圆锥投影(Lambert Conformal Conic).
# 选择理由见 docs/maps/myanmar.md; 中央经线取缅甸中部 96.5°E, 标准纬线取 10°N 与 27°N,
# 使全国范围的比例误差最小(标准纬线上比例因子恰为 1).
PROJECTION = ccrs.LambertConformal(
    central_longitude=96.5,
    central_latitude=19.5,
    standard_parallels=(10.0, 27.0),
)
# Natural Earth 里缅甸的英文国名, 用于筛选边界.
MYANMAR_NAMES = ("Myanmar", "Burma")

# 数据未覆盖区域的底图配色: 先画 Natural Earth 陆地 + 海洋底色, 再叠加 ETOPO 地形.
# 原因见 map_lib.add_base_map(): 圆锥投影的矩形画框会探出 ETOPO 子集的范围,
# 用真实海陆分布打底比直接留白更不容易误导读者. 两色与 ELEV_CMAP 两端一致,
# 只在 ETOPO 子集边缘露出来时可见.
BASE_OCEAN_COLOR = "#a2d0ee"
BASE_LAND_COLOR = "#dce4a2"

# 地形配色与山体阴影参数.
# 高程范围取 ±5000 m 与 USSR 图一致; 该子集西北角是喜马拉雅山, 最高约 8100 m,
# 超出上限的高程饱和在色带末端的近雪白色.
ELEV_VMIN, ELEV_VMAX = -5000, 5000


def make_relief_cmap(vmin: float, vmax: float) -> mcolors.LinearSegmentedColormap:
    """高程/水深双色带: 深蓝(深水) -> 浅蓝(0 m 水面) | 浅绿(0 m 陆地) -> 黄 -> 棕 -> 雪白.

    为什么在 0 m 处断开(与 Ukraine 图同一套思路):
        本图不再单独画海岸线(见 draw_borders), 海陆界线只由这条色界表达.
        "terrain" 是单段色带, 0 m 落在中点附近: -1 m 的海面与 +1 m 的陆地
        几乎同色, 去掉海岸线后伊洛瓦底江三角洲、若开海岸这些低地岸边会糊成
        一片, 分不出哪里是海. 这里让水色在 0 m 处直接跳到陆色, 浅海也一眼
        是"水"; 陆地段把锚点密集放在 0~500 m, 低地高程差异才拉得开.

    返回的色带配合 Normalize(vmin, vmax) 使用(Normalize 保持线性, 只是中点处
    色带不连续); N=2048 是为了让 0 m 处的水/陆跳变只占一个色阶宽度. 海水
    锚点比 Ukraine 图更深, 因为安达曼海最深约 4700 m. 颜色按 (高程 m, 十六
    进制) 给出, 便于按数据调整.
    """
    sea = [
        (-5000, "#06213d"),
        (-3500, "#0d3355"),
        (-2000, "#0f3c66"),
        (-1250, "#1b628f"),
        (-700, "#2f82b5"),
        (-300, "#5aa2cd"),
        (-100, "#75b3db"),
        (-20, "#8cc4e7"),
        (-1, "#a2d0ee"),
    ]
    land = [
        (1, "#dce4a2"),
        (75, "#dde3a4"),
        (175, "#e8dd92"),
        (300, "#dbc786"),
        (500, "#c8aa72"),
        (800, "#ad8a5f"),
        (1100, "#937147"),
        (1500, "#7d613e"),
        (2000, "#84725c"),
        (3000, "#b9aa97"),
        (4200, "#dddad2"),
        (5000, "#f6f5f1"),
    ]

    def u(elev: float) -> float:
        return (elev - vmin) / (vmax - vmin)

    anchors = [(u(e), color) for e, color in sea] + [(u(e), color) for e, color in land]
    return mcolors.LinearSegmentedColormap.from_list("myanmar_relief", anchors, N=2048)


ELEV_CMAP = make_relief_cmap(ELEV_VMIN, ELEV_VMAX)
# 方位角 315°(西北方向来光)是地形晕渲的制图惯例: 山脊西北坡受光、东南坡背光,
# 这样阴影方向与人的直觉一致; 高度角 45° 兼顾平原与陡坡的对比度.
HILLSHADE_AZIMUTH = 315
HILLSHADE_ALTITUDE = 45
# 垂直夸张 1.5 倍: ETOPO 15 弧秒数据在 1:1000 万级地图上起伏很弱,
# 不夸张时低地几乎看不出山脊与河谷的走向.
HILLSHADE_VERT_EXAG = 1.5

# 国界配色(与 Ukraine 图一致): 红色半透明, 让地形与下层要素透出来.
COLOR_BORDER = "#c62828"
BORDER_ALPHA = 0.62
BORDER_WIDTH = 2.7
# 邻国国界: 中性灰虚线, 只作定位参照, 不与红色国界争视觉层级.
COLOR_NEIGHBOR = "#8a8a8a"

# 国界剪掉沿海段的缓冲半径(度). Natural Earth 的国界面沿海岸闭合, 整圈画出来
# 会在若开/德林达依海岸与安达曼海岛屿上多出一条红色海岸线; 本图不画海岸线,
# 所以国界也只留陆上段. 0.06° 在 20°N 一带约 6 km, 覆盖国界折线与海岸线折线
# 的数字化偏差; 剪剩的碎段按 COAST_CLIP_MIN_LEN(约 3 km)丢掉.
COAST_CLIP_DEG = 0.06
COAST_CLIP_MIN_LEN = 0.03
# 邻国国界从缅甸国界两侧这么宽的走廊里剪掉, 避免在红色国界下面透出一条
# 与它平行的灰虚线.
NEIGHBOR_GAP_DEG = 0.06


# 邻国与海域名称: (经度, 纬度, 文字). 这是改前成品上的地名, 现在只登记到
# geo.labels, 不再画文字; 坐标仍是 PlateCarree 经纬度(与旧版文字的落点一致).
COUNTRY_LABELS = [
    (99.6, 29.9, "中国"),
    (89.2, 25.4, "印度"),
    (89.6, 22.8, "孟加拉国"),
    (101.3, 16.0, "泰国"),
    (103.4, 19.6, "老挝"),
]
SEA_LABELS = [
    (89.8, 15.8, "孟加拉湾"),
    (96.8, 9.3, "安达曼海"),
]
# 国名: 单独放在国土中北部, 用 role=country-name 让前端给深红色; 位置避开城市
# 地名防压盖. 旧版不用 fontweight="bold"(本机 CJK 可变字体只能取到默认实例),
# 靠更大的字号突出国名, 字号仍是本脚本的数据(22pt).
COUNTRY_NAME = (95.6, 23.5, "缅甸")

# 城市点: (经度, 纬度, 名称, 是否首都).
# 首都用星形标记, 其余用圆点, 便于快速定位; 城名只登记到 geo.labels, 不再绘制.
CITIES = [
    (96.10, 19.75, "内比都", True),
    (96.16, 16.87, "仰光", False),
    (96.08, 21.98, "曼德勒", False),
]
# 城名相对城点的偏移(度): 改前成品的文字落点, 现在只用来算 geo.labels 的锚点.
CITY_LABEL_DX = 0.18
CITY_LABEL_DY = -0.05

# 地名样式(颜色/斜体/描边/字重/行高等)由前端 role 表统一决定, 生成端只登记 role;
# 本脚本保留的只有字号这一层数据: 邻国名 13pt / 海域 12pt / 国名 22pt / 城名 10pt.

# 标题/副标题/来源: 旧版标题与底部来源文字的版面文案, 现在只作
# geo.suggestions 的默认值; 第一行是国家与数据源, 第二行是投影与参数.
TITLE = "缅甸联邦共和国全境地形图"
SUBTITLE = (
    "NOAA ETOPO 2022 | 兰勃特等角圆锥投影"
    "(中央经线 96.5°E, 标准纬线 10°N / 27°N)"
)
SOURCE = "数据: NOAA NCEI ETOPO 2022 (15 弧秒) | 边界: Natural Earth 10m"

# 高程色标刻度: 旧成品色标上标出的整千值, 前端 colorbar 直接复用.
RELIEF_TICKS = (-4000, -2000, 0, 2000, 4000)

# 经纬网样式: 与 add_gridlines 画出的线同源(gray / 0.6pt 实线 / 0.55 不透明度).
GRATICULE_STYLE = {
    "stroke": "#808080",
    "width_pt": 0.6,
    "dash": None,
    "opacity": 0.55,
}

# 输出路径(脚本同目录), 见 docs/reference/output.md.
OUT_SVG = ROOT / "myanmar_topography_etopo2022_lambert_conformal.svg"


def draw_borders(ax: plt.Axes, world) -> None:
    """画缅甸陆上国界(半透明红线)与邻国国界(灰虚线), 不画海岸线.

    为什么国界只画陆上段: 本图不画海岸线, 海陆界线由地形配色在 0 m 处的
    跳变表达(见 make_relief_cmap). 国界面本身沿海岸闭合, 整圈画出来就等于
    又画了一条红色海岸线; 所以先按 Natural Earth 海岸线缓冲剪掉沿海段,
    红线在孟加拉湾/安达曼海岸收笔, 岸线交给颜色分界. 岛屿(安达曼海群岛等)
    的边界整圈都贴着海岸线, 会被一并剪掉, 岛上只剩地形色斑 —— 这正是
    "不画海岸线"的直接结果.
    """
    if world is None:
        return

    # Natural Earth 版本不同可能用 NAME / NAME_EN / ADMIN, 逐个兜底.
    name_columns = [c for c in ("NAME", "NAME_EN", "ADMIN") if c in world.columns]
    mask = np.zeros(len(world), dtype=bool)
    for col in name_columns:
        mask |= world[col].isin(MYANMAR_NAMES).to_numpy()

    myanmar = world[mask]
    if myanmar.empty:
        print("警告: Natural Earth 数据中未找到缅甸, 跳过国界.")
        return

    # 缅甸由大陆主体和安达曼海若干岛屿组成, 合并成一个 MultiPolygon 后再处理.
    myanmar_geom = unary_union(myanmar.geometry)

    # 国界: 红色半透明实线, 只画陆上段.
    border = myanmar_geom.boundary
    coastline = map_lib.load_ne_layer("10m", "physical", "coastline")
    if coastline is not None:
        coast = unary_union(map_lib.clip_to_axes(ax, list(coastline.geometry)))
        border = cut(
            border,
            overlap_mask([coast], COAST_CLIP_DEG),
            min_length_deg=COAST_CLIP_MIN_LEN,
        )
    else:
        print("警告: 缺少海岸线数据, 国界无法剪掉沿海段, 将画出完整国界.")
    if border is not None:
        ax.add_geometries(
            [border],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=COLOR_BORDER,
            linewidth=BORDER_WIDTH,
            alpha=BORDER_ALPHA,
            zorder=6,
        )

    # 邻国国界: 细灰虚线, 只提供地理参照; 缅甸国界走廊里的段落剪掉,
    # 否则红线下面会透出一条与它平行的灰虚线.
    land_borders = map_lib.load_ne_layer("10m", "cultural", "admin_0_boundary_lines_land")
    if land_borders is not None:
        others = unary_union(map_lib.clip_to_axes(ax, list(land_borders.geometry)))
        others = others.difference(myanmar_geom.buffer(NEIGHBOR_GAP_DEG))
        if not others.is_empty:
            ax.add_geometries(
                [others],
                crs=ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=COLOR_NEIGHBOR,
                linewidth=0.7,
                linestyle=(0, (5, 3)),
                zorder=3,
            )

    print(f"缅甸边界: {len(myanmar)} 个要素, 边界框 {myanmar.total_bounds.round(2)}")


def add_city_markers(ax: plt.Axes) -> None:
    """画出主要城市点: 首都用星形, 其余用空心圆."""
    for lon, lat, _, is_capital in CITIES:
        if is_capital:
            ax.plot(
                lon,
                lat,
                marker="*",
                markersize=13,
                markerfacecolor="#ffd200",
                markeredgecolor="black",
                markeredgewidth=0.8,
                transform=ccrs.PlateCarree(),
                zorder=8,
            )
        else:
            ax.plot(
                lon,
                lat,
                marker="o",
                markersize=5,
                markerfacecolor="white",
                markeredgecolor="black",
                markeredgewidth=1.0,
                transform=ccrs.PlateCarree(),
                zorder=8,
            )


def add_gridlines(ax: plt.Axes) -> None:
    """经纬网: 经度每 3°, 纬度每 5°, 只画网线, 不画刻度文字.

    线位置只取画框内 3°/5° 的整倍数; 改前这些刻度文字由 matplotlib 画, 现在改由
    前端按 geo.graticule 排版, 因此 draw_labels=False.
    """
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=False,
        linewidth=GRATICULE_STYLE["width_pt"],
        color="gray",
        alpha=GRATICULE_STYLE["opacity"],
        linestyle="-",
        zorder=4,
    )
    gl.xlocator = mticker.FixedLocator(np.arange(87, 107, 3))
    gl.ylocator = mticker.FixedLocator(np.arange(5, 32, 5))


# ============================
# geo.json 收集
# ============================
def collect_labels(doc: GeoDoc, ax: plt.Axes) -> None:
    """把旧成品上的地名整理成 geo.labels(role/位置/字号/锚点), 不画文字、不存样式.

    顺序沿用旧图: 邻国名 -> 海域名 -> 国名 -> 城名; 前端 scene 按 order 叠放.
    """
    for lon, lat, text in COUNTRY_LABELS:
        doc.add_label(ax, lon, lat, text, role="country", font_size_pt=13.0)
    for lon, lat, text in SEA_LABELS:
        doc.add_label(ax, lon, lat, text, role="sea", font_size_pt=12.0)
    lon, lat, text = COUNTRY_NAME
    # id 前缀由 role 家族映射成 country(见 geo.py 的 _ID_PREFIX), 保留旧的
    # label-country-缅甸.
    doc.add_label(ax, lon, lat, text, role="country-name", font_size_pt=22.0)
    for lon, lat, text, _is_capital in CITIES:
        # 城名用左下对齐贴住城点: 旧版是 (城点 + 平移) + ha="left".
        doc.add_label(
            ax, lon + CITY_LABEL_DX, lat + CITY_LABEL_DY, text,
            role="city", font_size_pt=10.0, ha="left",
        )


def collect_graticule(doc: GeoDoc, ax: plt.Axes) -> None:
    """把经纬刻度(值/文字/与地图框边线的交点)登记进 geo; 网线已由 add_gridlines 画好."""
    doc.add_graticule(
        ax,
        tuple(EXTENT),
        lon_step=3.0,
        lat_step=5.0,
        lon_side="bottom",
        lat_side="left",
        style=GRATICULE_STYLE,
    )


def collect_relief(doc: GeoDoc) -> None:
    """登记高程色标数据: 与底图同一套色带/范围, 刻度取改前成品色标上的值."""
    doc.set_relief(
        relief_from_cmap(
            ELEV_CMAP,
            title="高程 / 水深",
            unit="m",
            vmin=ELEV_VMIN,
            vmax=ELEV_VMAX,
            ticks=RELIEF_TICKS,
        )
    )


def collect_suggestions(doc: GeoDoc) -> None:
    """默认文案: 标题/副标题/来源/色标标题, 只给前端预填, 不参与底图合成.

    改前成品没有图例与图注, 所以不写 legend_title/notes/area_annotation;
    写了反而会让前端初始化出一块旧图没有的版面.
    """
    doc.set_suggestions(
        {
            "title": TITLE,
            "subtitle": SUBTITLE,
            "source": SOURCE,
            "colorbar_title": "高程 / 水深",
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stride",
        type=int,
        default=None,
        help="使用 data/ 下对应采样步长的高程文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="内嵌晕渲栅格的像素密度(dpi); 矢量部分与 dpi 无关, 默认 300",
    )
    parser.add_argument("--show", action="store_true", help="保存后弹出交互窗口(需要图形界面)")
    args = parser.parse_args()

    etopo_path = map_lib.find_etopo(
        DATA_DIR,
        "myanmar",
        args.stride,
        env_path=os.environ.get("MYANMAR_ETOPO_PATH"),
    )
    if not etopo_path.exists():
        raise FileNotFoundError(
            f"未找到高程数据: {etopo_path}\n"
            "请先运行: python download_etopo.py (或设置 MYANMAR_ETOPO_PATH)"
        )
    lon, lat, z = map_lib.load_elevation(etopo_path)

    # 画布偏竖长: 缅甸南北约 26°、东西约 19°, 投影后宽高比约 3:4,
    # 用 12x15 英寸能充分展示南北狭长的国土轮廓.
    # 手动画布 + add_axes: 地图位置完全可控, 不依赖任何自动布局.
    fig = plt.figure(figsize=(12, 15), facecolor="white")
    ax = fig.add_axes([0.075, 0.05, 0.78, 0.85], projection=PROJECTION)
    # GeoAxes 用 equal aspect 保持投影等比例, 在给定矩形内居中显示.
    ax.set_anchor("C")
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())

    # 先铺一层真实海陆底色, 再把 ETOPO 地形叠上去.
    world = map_lib.load_countries(BOUNDARY_DIR)
    map_lib.add_base_map(
        ax,
        world,
        ocean_color=BASE_OCEAN_COLOR,
        land_color=BASE_LAND_COLOR,
    )

    # 把高程配色与山体晕渲合成 RGB 图, 比单一高程色带更能读出山脊走向.
    relief, _, _ = map_lib.make_relief(
        z,
        lat,
        lon,
        vmin=ELEV_VMIN,
        vmax=ELEV_VMAX,
        cmap=ELEV_CMAP,
        azimuth=HILLSHADE_AZIMUTH,
        altitude=HILLSHADE_ALTITUDE,
        vert_exag=HILLSHADE_VERT_EXAG,
    )

    # imshow 比 pcolormesh 快得多: cartopy 内部会按 regrid_shape 做重投影采样.
    # regrid_shape 默认只有 750, 对 30 弧秒数据会糊成一片, 这里提到 3200.
    # 传 RGB 数组给 imshow 时不能再给 cmap/vmin/vmax (那是给标量数据用的).
    ax.imshow(
        relief,
        origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        regrid_shape=3200,
        interpolation="nearest",
        zorder=1,
    )

    # 海岸线不画: 海陆界线由 ELEV_CMAP 在 0 m 处的跳变表达. 国界只画陆上段
    # (半透明红线), 邻国国界用细灰虚线, 详见 draw_borders.
    draw_borders(ax, world)
    add_city_markers(ax)

    add_gridlines(ax)

    # 量地图框 -> 收集 geo -> 保存裁到地图框的底图与同名 geo.json.
    # 注意: 这里既不能用 plt.tight_layout()/constrained_layout, 也不能用
    # bbox_inches="tight". 原因: cartopy 0.25 在非矩形投影上让布局引擎提前绘制
    # 经纬网时, gridliner 会用未闭合的边界顶点构造多边形, 抛 shapely GEOSException;
    # 而 bbox_inches 会引入第二套坐标, 让 geo 的锚点与底图对不上 —— 裁剪交给
    # save_map 只改根标签的 viewBox.
    frame = figure_frame(fig, ax)
    doc = GeoDoc(frame)
    collect_labels(doc, ax)
    collect_graticule(doc, ax)
    collect_relief(doc)
    collect_suggestions(doc)
    svg_path, geo_path = save_map(fig, OUT_SVG, doc, dpi=args.dpi)
    print(f"底图与 geo 已保存: {svg_path} + {geo_path}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
