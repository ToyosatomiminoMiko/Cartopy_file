#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""USSR topography map: ETOPO 2022 relief with merged ex-USSR borders.

是什么: 从本地 ETOPO 2022 NetCDF 读取苏联区域高程, 用兰勃特等面积方位投影绘制
地形图, 并叠加 Natural Earth 的前苏联加盟共和国合并边界与海岸线.
文字与版面由前端接管, 本脚本同时产出同名的 geo.json: 底图只画地理要素, 色标/
标题/副标题只以 ``GeoDoc`` 数据形式登记, 不再画任何文字; 字段与口径见
``docs/reference/geo.md``. 完整说明: ``docs/maps/ussr.md``(投影/图幅内容/数据来源/
运行方式).
"""

import os  # 读取环境变量,例如 ETOPO_PATH
from pathlib import Path  # 统一使用 pathlib 处理文件路径

# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
from cartopy_file.data import configure_cartopy, prepare_matplotlib_env

prepare_matplotlib_env()

import cartopy.crs as ccrs  # 地图投影
import cartopy.feature as cfeature  # 海岸线等自然要素
import geopandas as gpd  # 读取并处理 shapefile 边界
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网刻度定位
import numpy as np  # 数组运算
import xarray as xr  # 读取 NetCDF
from shapely.ops import unary_union  # 合并多个面为单一几何边界

# cartopy 底图缓存统一到仓库 data/cartopy, 见 docs/reference/data.md.
configure_cartopy()

from cartopy_file.output import apply_svg_output

# 底图 + geo.json 出图: save_map 同时写裁到地图框的 SVG 与同名 geo.json,
# 见 docs/reference/geo.md.
from cartopy_file.geo import GeoDoc, figure_frame, relief_from_cmap, save_map

# 产物统一为 SVG, 见 docs/reference/output.md.
apply_svg_output()


# ============================
# 配置
# ============================
# 脚本所在目录,后续输出图片和查找数据都以它为基准.
ROOT = Path(__file__).resolve().parent
# 本地数据目录,用于存放 NetCDF 高程数据和 Natural Earth 边界数据.
DATA_DIR = ROOT / "data"

# ETOPO 高程文件的定位策略:
# 1) 优先使用环境变量 ETOPO_PATH,方便用户指向任意已有文件;
# 2) 否则自动查找 data 目录下 ETOPO_2022_v1_15s_ussr_stride*.nc.
# 兼容手动下载或不同采样步长的文件.
env_etopo = os.environ.get("ETOPO_PATH")
if env_etopo:
    ETOPO_PATH = Path(env_etopo)
else:
    # 排序后取第一个文件; 没有匹配时回退到默认步长 8 的文件名.
    candidates = sorted(DATA_DIR.glob("ETOPO_2022_v1_15s_ussr_stride*.nc"))
    ETOPO_PATH = (
        candidates[0] if candidates else DATA_DIR / "ETOPO_2022_v1_15s_ussr_stride8.nc"
    )

# Earth Topography and Bathymetry (ETOPO)
# 全球地形起伏数据集
# 美国国家海洋和大气管理局(NOAA)下属国家环境信息中心(NCEI)发布
# Natural Earth 10m 分辨率国家边界目录,用来绘制苏联轮廓.
BOUNDARY_DIR = DATA_DIR / "ne_10m_admin_0_countries"

# 地图显示范围,单位为度: 经度 15°E 向东跨过 180° 到 165°W.
# 不接受“最小值大于最大值”,所以下面把 -165 展开为 195.
extent = [15, 195, 15, 90]  # [min_lon, max_lon, min_lat, max_lat]

# 投影设置: 以苏联主体位置附近作为投影中心,减少边缘形变.
# 平面投影(方位投影),以苏联主体位置为中心
# 想换成球面正射外观时,可替换为：
# ccrs.Orthographic(central_longitude=90, central_latitude=55)
# 想换成等距方位投影时,可替换为：
# ccrs.AzimuthalEquidistant(central_longitude=90, central_latitude=55)
PROJECTION = ccrs.LambertAzimuthalEqualArea(central_longitude=105, central_latitude=55)

# 高程配色: 改前成品直接用 matplotlib 的 terrain 色带, 范围 ±5000 m(陆海两端饱和).
ELEV_VMIN, ELEV_VMAX = -5000, 5000
ELEV_CMAP = plt.get_cmap("terrain")

# 高程色标刻度: 改前成品色标上标出的整千值, 前端 colorbar 直接复用.
RELIEF_TICKS = (-4000, -2000, 0, 2000, 4000)

# 经纬网样式: 与 add_gridlines 画出的线同源(gray / 0.8pt 实线 / 0.6 不透明度).
GRATICULE_STYLE = {
    "stroke": "#808080",
    "width_pt": 0.8,
    "dash": None,
    "opacity": 0.6,
}

# 标题: 改前成品 title 的两行拆成标题与副标题, 只作 geo.suggestions 的默认值.
# 文字沿用旧版原文(副标题里的投影中心 90°E 是旧稿写法, 实际参数见 PROJECTION).
TITLE = "USSR (ETOPO 2022,本地 NetCDF)"
SUBTITLE = "兰勃特等面积方位投影(平面/方位投影)|中心 90°E, 55°N"

# 前苏联 15 个加盟共和国的 Natural Earth 英文国名.
USSR_REPUBLICS = [
    "Russia",
    "Ukraine",
    "Belarus",
    "Moldova",
    "Georgia",
    "Armenia",
    "Azerbaijan",
    "Kazakhstan",
    "Uzbekistan",
    "Turkmenistan",
    "Kyrgyzstan",
    "Tajikistan",
    "Lithuania",
    "Latvia",
    "Estonia",
]

# 内嵌晕渲栅格的像素密度; 旧脚本没有命令行参数, 固定 300(矢量部分与 dpi 无关).
DPI = 300

# 输出路径(脚本同目录), 见 docs/reference/output.md.
OUT_SVG = ROOT / "ussr_topography_etopo2022_lambert_azimuthal.svg"


# ============================
# 1. 读取本地 ETOPO 2022 数据
# ============================
def load_elevation() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """读取本地 ETOPO 2022 NetCDF, 返回 (经度, 纬度, 高程).

    若高程文件不存在, 直接给出可操作的修复提示, 避免后续绘图报难懂的错.
    纬度从北到南排列时翻转为从南到北, 才能与 imshow(origin="lower") 的方向一致.
    """
    if not ETOPO_PATH.exists():
        raise FileNotFoundError(
            f"未找到高程数据: {ETOPO_PATH}\n"
            "请先运行: python download_etopo.py\n"
            "或设置 ETOPO_PATH 指向已有的 ERDDAP NetCDF 文件"
        )

    # decode_times=False 避免把与时间无关的维度误解析成日期; with 保证关闭文件句柄.
    # ERDDAP 用 z / latitude / longitude 直接取 2D 数组, 避免 xarray 为 pcolormesh
    # 生成巨大二维坐标网格.
    with xr.open_dataset(ETOPO_PATH, decode_times=False, engine="netcdf4") as ds:
        elevation = ds["z"]
        lon = elevation["longitude"].to_numpy()
        lat = elevation["latitude"].to_numpy()
        z = elevation.to_numpy()

    if lat[0] > lat[-1]:
        lat = lat[::-1]
        z = z[::-1, :]

    # 输出数组形状和实际经纬度范围,便于快速确认读取是否正确.
    print(
        f"高程数据维度: {z.shape}, 范围: lon {lon[0]:.2f}~{lon[-1]:.2f}, "
        f"lat {lat[0]:.2f}~{lat[-1]:.2f}"
    )
    return lon, lat, z


# ============================
# 2. 边界数据与图幅内容
# ============================
def load_countries():
    """读取 Natural Earth 10m 国界 shapefile; 目录不存在时返回 None.

    不同版本的文件名不同, 按排序取第一个保证可复现.
    """
    boundary_shapefiles = (
        sorted(BOUNDARY_DIR.glob("*.shp")) if BOUNDARY_DIR.exists() else []
    )
    if not boundary_shapefiles:
        print("警告: 未找到 Natural Earth shapefile,跳过红色边界.")
        return None
    return gpd.read_file(boundary_shapefiles[0])


def add_ussr_border(ax: plt.Axes, world) -> None:
    """把 15 个加盟共和国合并成苏联外轮廓, 只画红色轮廓线.

    为什么只画线不填充: 苏联不是一个真实存在的国家面, 填充会盖住地形;
    轮廓与红星色是改前成品的口径.
    """
    if world is None:
        return

    # Natural Earth 字段因版本不同可能是 NAME/NAME_EN/ADMIN, 只保留实际存在的字段.
    name_columns = [c for c in ("NAME", "NAME_EN", "ADMIN") if c in world.columns]
    if not name_columns:
        raise RuntimeError("无法识别 Natural Earth 国名字段,请检查 shapefile.")

    # 优先使用第一个可用国名字段筛选出前苏联国家.
    name_column = name_columns[0]
    ussr_countries = world[world[name_column].isin(USSR_REPUBLICS)]
    if ussr_countries.empty:
        # 某些版本使用 sovereign 字段更准确,退化到所有字段模糊匹配.
        mask = np.zeros(len(world), dtype=bool)
        for col in name_columns:
            mask |= world[col].isin(USSR_REPUBLICS).to_numpy()
        ussr_countries = world[mask]

    if ussr_countries.empty:
        print("警告: 未在 Natural Earth 数据中找到目标国家,跳过红色边界.")
        return

    # 将多个加盟共和国几何合并成一个整体,得到苏联外轮廓.
    ussr_boundary = unary_union(ussr_countries.geometry)
    ax.add_geometries(
        [ussr_boundary],
        crs=ccrs.PlateCarree(),
        edgecolor="red",
        facecolor="none",
        linewidth=1.8,
    )


def add_gridlines(ax: plt.Axes) -> None:
    """经纬网: 纬度每 10°, 经度每 15°, 只画网线, 不画刻度文字.

    线位置只取画框内的整倍数; 刻度文字由前端按 geo.graticule 排版, 因此
    draw_labels=False, 与改前成品"无刻度文字"的口径一致.
    """
    gl = ax.gridlines(
        draw_labels=False,
        linewidth=GRATICULE_STYLE["width_pt"],
        color="gray",
        alpha=GRATICULE_STYLE["opacity"],
    )
    # 纬度每 10° 一条, 经度每 15° 一条; 经度上限要与展开后的 195° 对齐.
    gl.ylocator = mticker.FixedLocator(np.arange(20, 91, 10))
    gl.xlocator = mticker.FixedLocator(np.arange(15, 196, 15))


# ============================
# 3. geo.json 收集
# ============================
def collect_graticule(doc: GeoDoc) -> None:
    """登记经纬网样式; 改前成品没有刻度文字, 所以刻度数组留空.

    为什么不调 GeoDoc.add_graticule: 它会把画框内的整倍数刻度值也写进 geo,
    前端据此补出一圈旧成品没有的刻度文字. 这里用 set_graticule_style 只写与网线
    同源的样式, lon/lat 留空数组.
    """
    doc.set_graticule_style(
        stroke=GRATICULE_STYLE["stroke"],
        width_pt=GRATICULE_STYLE["width_pt"],
        dash=GRATICULE_STYLE["dash"],
        opacity=GRATICULE_STYLE["opacity"],
    )


def collect_relief(doc: GeoDoc) -> None:
    """登记高程色标数据: 与底图同一套 terrain 色带/范围, 刻度取改前成品的值."""
    doc.set_relief(
        relief_from_cmap(
            ELEV_CMAP,
            title="Elevation",
            unit="m",
            vmin=ELEV_VMIN,
            vmax=ELEV_VMAX,
            ticks=RELIEF_TICKS,
        )
    )


def collect_suggestions(doc: GeoDoc) -> None:
    """默认文案: 标题/副标题/色标标题, 只给前端预填, 不参与底图合成.

    改前成品没有地名、图例、图注与来源行, 所以其余字段一律不写;
    写了反而会让前端初始化出一块旧图没有的版面.
    """
    doc.set_suggestions(
        {
            "title": TITLE,
            "subtitle": SUBTITLE,
            "colorbar_title": "Elevation",
        }
    )


# ============================
# 4. 出图
# ============================
def build_map(lon: np.ndarray, lat: np.ndarray, z: np.ndarray, world):
    """按改前版式画一张纯几何图, 返回未保存的 Figure 与地图坐标区(geo 收集要用 ax)."""
    # 创建带指定投影的绘图对象, figsize 控制最终图片宽高比.
    fig, ax = plt.subplots(figsize=(16, 12), subplot_kw={"projection": PROJECTION})
    # 限定地图显示范围; 这里的范围坐标是 PlateCarree(经纬度).
    ax.set_extent(extent, crs=ccrs.PlateCarree())

    # 用 imshow 绘制规则网格高程,比 pcolormesh 更快、更省内存.
    # origin="lower" 保证数组第一行对应图像底部; extent 是数据对应的经纬度范围;
    # transform 表示这些坐标是经纬度,需要由 Cartopy 转换到投影坐标.
    ax.imshow(
        z,
        origin="lower",
        extent=[lon[0], lon[-1], lat[0], lat[-1]],
        transform=ccrs.PlateCarree(),
        cmap="terrain",
        alpha=0.9,
        vmin=ELEV_VMIN,
        vmax=ELEV_VMAX,
        interpolation="nearest",
    )

    # 叠加海岸线,便于观察陆地轮廓与地形之间的对应关系.
    ax.add_feature(cfeature.COASTLINE, linewidth=0.6, color="black")
    add_ussr_border(ax, world)
    add_gridlines(ax)
    return fig, ax


def main() -> None:
    lon, lat, z = load_elevation()
    world = load_countries()
    fig, ax = build_map(lon, lat, z, world)

    # 先收紧布局再量地图框: figure_frame 量到的必须是为最终排版定下的矩形.
    # 注意: save_map 保存时不传 bbox_inches="tight" —— 它会把几何再平移缩放一次,
    # 引入第二套坐标, 让 geo 的锚点与底图对不上; 裁剪由 save_map 只改根标签完成.
    plt.tight_layout()
    frame = figure_frame(fig, ax)
    doc = GeoDoc(frame)
    collect_graticule(doc)
    collect_relief(doc)
    collect_suggestions(doc)
    svg_path, geo_path = save_map(fig, OUT_SVG, doc, dpi=DPI)
    print(f"底图与 geo 已保存: {svg_path} + {geo_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
