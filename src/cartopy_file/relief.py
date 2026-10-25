#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# relief.py
# 地形图共用工具: 定位并读取 ETOPO 2022 NetCDF 高程、合成高程配色
# 与山体晕渲、读取 Natural Earth 国界、铺海陆底色.
# 原先这些函数只存在于 Myanmar/map_lib.py; 乌克兰图同样需要, 因此上移到
# 项目共享包里, 由各图种脚本统一导入, 避免同一套算法维护多份.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Reusable relief / basemap helpers for the topographic map scripts.

是什么:
    - ``find_etopo``: 按区域名(如 ``myanmar`` / ``ukraine``)和采样步长
      定位本地 ETOPO 2022 NetCDF 文件;
    - ``load_elevation``: 读取高程数组与一维经纬度, 纬度统一翻成南->北,
      方便直接交给 ``imshow(origin="lower")``;
    - ``make_relief``: 把高程色带与 ``LightSource`` 山体晕渲合成 RGB;
    - ``load_countries`` / ``add_base_map``: 读取 Natural Earth 国家边界,
      在画地形前铺一层真实海陆底色.
    - ``clip_to_axes``: 把面几何裁到当前坐标范围, 避免把画面外的底图顶点写进
      SVG(PNG 时无所谓, 矢量输出时画面外顶点同样占字节).

为什么要把它们放进共享包:
    这些逻辑与具体国家无关, 只是"读高程 + 画地形"的公共部分. Myanmar 系列
    与 Ukraine 图都要用; 放在 ``src/cartopy_file`` 后, 普通 ``import`` 即可,
    不必再用 ``sys.path.insert`` 去引用别的图种目录. 各脚本仍自己决定
    MPLCONFIGDIR(必须在导入 matplotlib 之前设置), 本模块不做全局副作用.

警告:
    本模块会导入 matplotlib/cartopy, 调用方必须保证在 ``import`` 本模块之前
    已经设置好 ``MPLCONFIGDIR``(见 ``cartopy_file.data.prepare_matplotlib_env``),
    否则本机只读的 ``~/.config`` 会让 matplotlib 每次重建字体缓存.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.colors as mcolors  # 归一化与山体晕渲
import matplotlib.pyplot as plt  # 绘图
import numpy as np  # 数组运算
import xarray as xr  # 读取 NetCDF
from cartopy import crs as ccrs  # 投影转换
from shapely.geometry import box  # 底图裁剪窗口

__all__ = [
    "find_etopo",
    "load_elevation",
    "make_relief",
    "load_countries",
    "add_base_map",
    "clip_to_axes",
]


def find_etopo(
    data_dir: Path,
    region: str,
    stride: int | None = None,
    env_path: str | None = None,
) -> Path:
    """按区域名定位本地 ETOPO NetCDF 文件.

    文件名约定: ETOPO_2022_v1_15s_{region}_stride{N}.nc.
    优先级: 显式 stride > env_path(环境变量覆盖) > data/ 下该区域步长最小(分辨率最高)的文件.
    """
    if env_path:
        return Path(env_path)
    if stride is not None:
        return data_dir / f"ETOPO_2022_v1_15s_{region}_stride{stride}.nc"

    candidates = sorted(data_dir.glob(f"ETOPO_2022_v1_15s_{region}_stride*.nc"))
    if not candidates:
        return data_dir / f"ETOPO_2022_v1_15s_{region}_stride2.nc"

    # 文件名形如 ..._stride8.nc / ..._stride2.nc; 数值越小分辨率越高.
    def stride_of(path: Path) -> int:
        digits = "".join(ch for ch in path.stem.split("stride")[-1] if ch.isdigit())
        return int(digits) if digits else 10**6

    return min(candidates, key=stride_of)


def load_elevation(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """读取 z 及一维经纬度坐标, 纬度统一为南->北, 以配合 imshow(origin="lower")."""
    ds = xr.open_dataset(path, decode_times=False, engine="netcdf4")
    elevation = ds["z"]
    if elevation.ndim == 3:
        dim = "time" if "time" in elevation.dims else elevation.dims[0]
        elevation = elevation.isel({dim: 0})

    lon = elevation["longitude"].to_numpy()
    lat = elevation["latitude"].to_numpy()
    z = elevation.to_numpy()

    if lat[0] > lat[-1]:
        lat = lat[::-1]
        z = z[::-1, :]

    ds.close()
    print(
        f"高程数据: {path.name}, 形状 {z.shape}, "
        f"经度 {lon[0]:.2f}~{lon[-1]:.2f}, 纬度 {lat[0]:.2f}~{lat[-1]:.2f}, "
        f"高程 {np.nanmin(z):.0f}~{np.nanmax(z):.0f} m"
    )
    return lon, lat, z


def make_relief(
    z: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    *,
    vmin: float,
    vmax: float,
    cmap: str | mcolors.Colormap = "terrain",
    azimuth: float = 315,
    altitude: float = 45,
    vert_exag: float = 1.5,
    fraction: float = 1.2,
    shade_strength: float | None = None,
    shade_floor: float = 0.55,
):
    """把高程配色与山体晕渲合成 RGB 图.

    晕渲的作用: 纯高程色带在低地(本区域大部分 0~500 m)几乎只有一两种颜色,
    看不出山脊和河谷走向; 用坡度算出的明暗乘到配色上, 地形细节立刻显现.
    dx/dy 必须和 z 使用同一单位(米): LightSource 用高程差除以网格间距算坡度,
    单位不一致时坡度(以及阴影浓淡)会错.

    shade_strength:
        缺省 None 时用 LightSource 的 blend_mode="soft"(保留高程配色 + 叠阴影),
        适合起伏大的区域. 但软光混合在浅色底图上对比度很低: 平原国家(如乌克兰
        大部分国土 0~300 m, 30″ ETOPO 上起伏只有几十米)几乎看不出地形.
        给定数值时改用"只压暗"的乘法晕渲:

            factor = 1 + shade_strength * (hillshade - sin(altitude))

        平地(坡度 0)的 hillshade = sin(altitude), 因子为 1; 背光坡压暗, 向阳坡
        不增亮(上限 1). 这样浅色底图不会被叠成白色, 而河谷/丘陵的阴影能显出来.
        shade_floor 是压暗的下限(最深阴影保留多少亮度), 防止陡坡变成黑块.
        水面(z < 0)不做晕渲: 海底地形不是这类图要表达的信息, 加了阴影反而把海
        压暗到与陆地同色.
    """
    cmap_obj = plt.get_cmap(cmap)
    norm = mcolors.Normalize(vmin, vmax)

    dlat = (lat[-1] - lat[0]) / (lat.size - 1)
    dlon = (lon[-1] - lon[0]) / (lon.size - 1)
    dy = 110540.0 * dlat  # 1° 纬度约 110.54 km
    dx = 111320.0 * np.cos(np.deg2rad(np.mean(lat))) * dlon  # 经度随纬度收缩

    light = mcolors.LightSource(azdeg=azimuth, altdeg=altitude)
    if shade_strength is None:
        # blend_mode="soft": 保留高程配色, 叠加阴影; 换成 "overlay" 会把低地压得过亮.
        rgba = light.shade(
            z,
            cmap=cmap_obj,
            norm=norm,
            blend_mode="soft",
            vert_exag=vert_exag,
            dx=dx,
            dy=dy,
            fraction=fraction,
        )
    else:
        shade = light.hillshade(z, vert_exag=vert_exag, dx=dx, dy=dy, fraction=fraction)
        flat = np.sin(np.deg2rad(altitude))  # 平地(坡度 0)的 hillshade 值
        factor = np.clip(1.0 + shade_strength * (shade - flat), shade_floor, 1.0)
        factor = np.where(z >= 0, factor, 1.0)  # 水面保持纯色
        base = cmap_obj(norm(z))
        rgb = np.clip(base[..., :3] * factor[..., None], 0.0, 1.0)
        rgba = np.dstack([rgb, np.ones_like(rgb[..., :1])])
    return rgba, norm, cmap_obj


def load_countries(boundary_dir: Path):
    """读取 Natural Earth 10m 国家边界; 文件不存在时返回 None(跳过底图与国界)."""
    shapefiles = sorted(boundary_dir.glob("*.shp")) if boundary_dir.exists() else []
    if not shapefiles:
        print("警告: 未找到 Natural Earth 边界 shapefile, 跳过底图填充与国界.")
        return None
    import geopandas as gpd  # 延迟导入: 没有边界数据时不需要它

    return gpd.read_file(shapefiles[0])


def clip_to_axes(ax: plt.Axes, geoms) -> list:
    """把面几何裁到当前坐标范围, 只保留画面(及其外接经纬度矩形)内的部分.

    为什么需要: 底图用的是 Natural Earth 10m 全球国家多边形(约 55 万顶点),
    画面里只用到其中很小一块. PNG 在栅格化时只关心画面内的像素, 画面外的
    顶点不产生任何代价; 但 SVG 是矢量输出, 每个顶点都会被写成一段路径数据,
    不裁的话单是这一层填色就有十几 MB(实测缅甸图 13.4 MB / 全图 26 MB).
    裁完外观完全不变: 窗口取 ``ax.get_extent(PlateCarree)``, 它一定盖住整个
    画面(非矩形投影时比画面还大, 多留的顶点本来也在画面外).

    跨 180° 经线的图幅不裁: shapely 的 box 不处理经度环绕, 会把跨线几何裁坏.
    """
    x0, x1, y0, y1 = ax.get_extent(crs=ccrs.PlateCarree())
    if not (x0 < x1 and x1 - x0 <= 300.0):
        return list(geoms)

    window = box(x0, y0, x1, y1)
    clipped = []
    for geom in geoms:
        if geom is None or geom.is_empty:
            continue
        part = geom.intersection(window)
        if not part.is_empty:
            clipped.append(part)
    return clipped


def add_base_map(
    ax: plt.Axes,
    world,
    *,
    ocean_color: str,
    land_color: str,
) -> None:
    """在画地形之前铺真实海陆底色.

    为什么需要: 画框四角可能探出 ETOPO 子集范围, 或者 ETOPO 在近岸有缺测;
    用 Natural Earth 陆地多边形盖在海洋色坐标轴背景上, 比露出白色空白更不误导.
    """
    ax.set_facecolor(ocean_color)
    if world is not None:
        ax.add_geometries(
            clip_to_axes(ax, world.geometry),
            crs=ccrs.PlateCarree(),
            facecolor=land_color,
            edgecolor="none",
            zorder=0,
        )
