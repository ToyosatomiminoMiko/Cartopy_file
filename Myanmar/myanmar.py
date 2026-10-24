#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# myanmar.py
# 读取本地 NOAA ETOPO 2022 缅甸区域高程 NetCDF,
# 用兰勃特等角圆锥投影绘制缅甸联邦共和国全境地形图,
# 叠加 Natural Earth 10m 海岸线与国界,并标注邻国、城市和海域.
# 运行前先执行: python download_etopo.py
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Draw a full-territory topographic map of the Republic of the Union of Myanmar.

Data: NOAA NCEI ETOPO 2022 15-arc-second global relief (NOAA ERDDAP subset,
downloaded by ``download_etopo.py``) + Natural Earth 10m boundaries.

Projection: Lambert Conformal Conic centred on 96.5E / 19.5N with standard
parallels 10N and 27N.  Myanmar is strongly elongated north-south
(about 9.8N-28.5N, 92.2E-101.2E), so a conformal conic is preferred over
Mercator (which over-inflates area at 28N) and over azimuthal projections
(which suit round regions rather than narrow north-south strips).  With the
standard parallels close to the country's latitude limits the scale error
across Myanmar stays well under 1%.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# plt.rcParams 只能在导入 matplotlib 之后设置, 但缓存目录必须在导入前指定.
# 原因: 本机 ~/.config/matplotlib 不可写, 不设置 MPLCONFIGDIR 时每次启动都会
# 在临时目录重建字体缓存并打印警告, 出图变慢; 这里默认指向 data/ 下被忽略的目录.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # 地图投影
import cartopy.feature as cfeature  # 海岸线和国界等自然要素
import matplotlib.cm as cm  # 构造独立色标用的 ScalarMappable
import matplotlib.patheffects as pe  # 文字描边, 保证在深色地形上仍可读
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网刻度定位
import numpy as np  # 数组运算
from shapely.ops import unary_union  # 合并多块几何, 得到缅甸整体轮廓

import map_lib  # 与本目录共用的 ETOPO/晕渲/边界工具

# 中文字体: 优先等宽 CJK 字体, 没有时回退到 DejaVu Sans(中文会显示为方框).
# 不使用 Noto Sans CJK SC: 本机装的是可变字体 TTC, matplotlib 只能识别其 Thin 实例,
# 请求常规字重会告警并回退成极细笔画; Noto Sans Mono CJK SC 默认实例字重正常.
plt.rcParams["font.sans-serif"] = ["Noto Sans Mono CJK SC", "DejaVu Sans"]
# 使用 Unicode 负号, 避免坐标轴上的负号显示异常.
plt.rcParams["axes.unicode_minus"] = False


# ============================
# 配置
# ============================
# 本地数据目录 DATA_DIR 见文件顶部(必须在导入 matplotlib 之前定义).
# Natural Earth 10m 国家边界目录(由 download_etopo.py 解压得到).
BOUNDARY_DIR = DATA_DIR / "ne_10m_admin_0_countries"

# 地图显示范围, 单位为度, 格式 [min_lon, max_lon, min_lat, max_lat].
# 缅甸实际范围约 92.17~101.17°E, 9.79~28.54°N; 四周各留出约 5° 余量,
# 让孟加拉国、印度东北部、中国云南、泰国、老挝和安达曼海进入画面作为地理参照.
# 注意: download_etopo.py 下载的高程子集是 85.3~107.7°E / 4.9~31.1°N, 比这个画框大,
# 原因是圆锥投影的矩形画框顶边会张开到约 85.4~107.6°E, 子集必须盖住它才不会露出空白.
EXTENT = [87.0, 106.0, 5.0, 31.0]

# 投影参数: 兰勃特等角圆锥投影(Lambert Conformal Conic).
# 选择理由见文件顶部说明; 中央经线取缅甸中部 96.5°E, 标准纬线取 10°N 与 27°N,
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
# 用真实海陆分布打底比直接留白更不容易误导读者.
BASE_OCEAN_COLOR = "#cfe0ee"
BASE_LAND_COLOR = "#efe9cf"

# 地形配色与山体阴影参数.
# 高程范围取 ±5000 m 与 USSR 图一致; 该子集西北角是喜马拉雅山, 最高约 8100 m,
# 超出上限的部分用色标末端的 extend 三角形表示"被截断"而不是画成纯白大块.
ELEV_VMIN, ELEV_VMAX = -5000, 5000
ELEV_CMAP = "terrain"
# 方位角 315°(西北方向来光)是地形晕渲的制图惯例: 山脊西北坡受光、东南坡背光,
# 这样阴影方向与人的直觉一致; 高度角 45° 兼顾平原与陡坡的对比度.
HILLSHADE_AZIMUTH = 315
HILLSHADE_ALTITUDE = 45
# 垂直夸张 1.5 倍: ETOPO 15 弧秒数据在 1:1000 万级地图上起伏很弱,
# 不夸张时低地几乎看不出山脊与河谷的走向.
HILLSHADE_VERT_EXAG = 1.5

# 邻国与海域文字标注: (经度, 纬度, 文字).
# 坐标是 PlateCarree 经纬度, 由 transform 转换到当前投影.
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
# 城市标注: (经度, 纬度, 名称, 是否首都).
# 首都用星形标记, 其余用圆点, 便于快速定位.
CITIES = [
    (96.10, 19.75, "内比都", True),
    (96.16, 16.87, "仰光", False),
    (96.08, 21.98, "曼德勒", False),
]

# 图标题: 第一行说明国家与数据源, 第二行说明投影与参数.
TITLE = (
    "缅甸联邦共和国全境地形图\n"
    "NOAA ETOPO 2022 | 兰勃特等角圆锥投影"
    "(中央经线 96.5°E, 标准纬线 10°N / 27°N)"
)
# 输出图片路径, 300 dpi 适合打印或后续排版.
OUT_PNG = ROOT / "myanmar_topography_etopo2022_lambert_conformal.png"


def add_myanmar_boundary(ax: plt.Axes, world) -> None:
    """Outline the whole Myanmar territory in red using Natural Earth 10m."""
    if world is None:
        return

    # Natural Earth 版本不同可能用 NAME / NAME_EN / ADMIN, 逐个兜底.
    name_columns = [c for c in ("NAME", "NAME_EN", "ADMIN") if c in world.columns]
    mask = np.zeros(len(world), dtype=bool)
    for col in name_columns:
        mask |= world[col].isin(MYANMAR_NAMES).to_numpy()

    myanmar = world[mask]
    if myanmar.empty:
        print("警告: Natural Earth 数据中未找到缅甸, 跳过红色国界.")
        return

    # 缅甸由大陆主体和安达曼海若干岛屿组成, 合并成一个 MultiPolygon 后再画.
    boundary = unary_union(myanmar.geometry)
    ax.add_geometries(
        [boundary],
        crs=ccrs.PlateCarree(),
        edgecolor="red",
        facecolor="none",
        linewidth=2.2,
        zorder=6,
    )
    print(f"缅甸边界: {len(myanmar)} 个要素, 边界框 {myanmar.total_bounds.round(2)}")


def add_labels(ax: plt.Axes) -> None:
    """Annotate neighbours, seas and main cities with haloed text."""
    # 描边: 白色 2.5 磅轮廓 + 深色文字, 放在彩色地形上任何位置都看得清.
    halo = [pe.withStroke(linewidth=3.0, foreground="white")]

    for lon, lat, text in COUNTRY_LABELS:
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=13,
            color="#333333",
            ha="center",
            va="center",
            path_effects=halo,
            zorder=5,
        )
    for lon, lat, text in SEA_LABELS:
        ax.text(
            lon,
            lat,
            text,
            transform=ccrs.PlateCarree(),
            fontsize=12,
            color="#1f4e79",
            style="italic",
            ha="center",
            va="center",
            path_effects=halo,
            zorder=5,
        )
    # 国名单独标注, 放在国土中北部, 用深红色与红色国界呼应.
    # 不用 fontweight="bold": 该 CJK 可变字体没有可用的 Bold 实例, 请求粗体只会回退并告警,
    # 这里用更大的字号和深红色来突出国名.
    # 位置避开曼德勒、内比都等城市地名, 防止文字互相压盖.
    ax.text(
        95.6,
        23.5,
        "缅甸",
        transform=ccrs.PlateCarree(),
        fontsize=22,
        color="#8b0000",
        ha="center",
        va="center",
        path_effects=halo,
        zorder=9,
    )
    for lon, lat, name, is_capital in CITIES:
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
        ax.text(
            lon + 0.18,
            lat - 0.05,
            name,
            transform=ccrs.PlateCarree(),
            fontsize=10,
            color="black",
            ha="left",
            va="center",
            path_effects=halo,
            zorder=9,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stride",
        type=int,
        default=None,
        help="使用 data/ 下对应采样步长的高程文件; 缺省自动选分辨率最高(步长最小)的一个",
    )
    parser.add_argument("--dpi", type=int, default=300, help="输出 PNG 分辨率, 默认 300")
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
    # 手动画布 + add_axes: 地图与色标的位置完全可控, 不依赖任何自动布局
    # (自动布局在带经纬网标签的圆锥投影上会出错, 原因见保存前的注释).
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
    relief, norm, cmap = map_lib.make_relief(
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
    # 色标单独占一个坐标轴, 避免 colorbar 抢走地图宽度导致版面偏移.
    # 由于画的是 RGB 图, 色标改用与晕渲同一套 norm/cmap 的 ScalarMappable.
    cax = fig.add_axes([0.868, 0.26, 0.017, 0.48])
    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])
    fig.colorbar(mappable, cax=cax, label="高程 / 水深 (m)", extend="max")

    # 海岸线与国界: cartopy 自动使用已缓存的 Natural Earth 10m 数据.
    # 必须用 edgecolor 而不是 color: 这两个要素的 facecolor 被预定义为 "never",
    # 传 color= 会同时设置面颜色, cartopy 会打出 "facecolor will have no effect" 警告.
    ax.add_feature(cfeature.COASTLINE.with_scale("10m"), linewidth=0.6, edgecolor="black", zorder=3)
    ax.add_feature(
        cfeature.BORDERS.with_scale("10m"),
        linewidth=0.6,
        linestyle="--",
        edgecolor="#555555",
        zorder=3,
    )

    add_myanmar_boundary(ax, world)
    add_labels(ax)

    # 经纬网: 经度每 3°, 纬度每 5°, 只保留左侧和底部标签, 避免画面边缘拥挤.
    # rotate_labels=False: 圆锥投影下经线是斜的, 默认会让底部经度标签跟着旋转,
    # 旋转后的汉字/数字不易读, 这里统一保持水平.
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        x_inline=False,
        y_inline=False,
        linewidth=0.6,
        color="gray",
        alpha=0.55,
        linestyle="-",
        zorder=4,
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.rotate_labels = False
    gl.xlocator = mticker.FixedLocator(np.arange(87, 107, 3))
    gl.ylocator = mticker.FixedLocator(np.arange(5, 32, 5))
    gl.xlabel_style = {"size": 10, "color": "#444444"}
    gl.ylabel_style = {"size": 10, "color": "#444444"}

    # 用 figure 级标题而不用 ax.set_title: cartopy 的 GeoAxes 会在有经纬网标签时
    # 重新计算标题位置, 与多行标题叠加容易出现标题被移出画布的问题.
    fig.suptitle(TITLE, fontsize=16, y=0.985, va="top")
    # 数据来源放在画面底部, 不遮挡地图主体.
    fig.text(
        0.5,
        0.015,
        "数据: NOAA NCEI ETOPO 2022 (15 弧秒) | 边界: Natural Earth 10m",
        ha="center",
        va="bottom",
        fontsize=9,
        color="#666666",
    )

    # 注意: 这里既不能用 plt.tight_layout()/constrained_layout, 也不能用
    # bbox_inches="tight".
    # 原因: cartopy 0.25 在非矩形投影上绘制经纬网标签时, 布局引擎触发的提前绘制
    # 会让 gridliner 用未闭合的边界顶点构造多边形, 抛 shapely GEOSException;
    # 而 bbox_inches="tight" 又会把 gridliner 标签的包围盒算错, 导致图片被裁掉一截.
    fig.savefig(OUT_PNG, dpi=args.dpi)
    print(f"地图已保存: {OUT_PNG}")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
