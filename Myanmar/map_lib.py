#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# map_lib.py
# 缅甸系列地形图共用的绘图工具: 读取 ETOPO 高程、生成晕渲配色、
# 读取 Natural Earth 国家边界、铺海陆底色. 供 myanmar.py 与
# northern_shan.py 复用, 避免同一套逻辑维护两份.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Shared helpers for the Myanmar topographic map scripts."""

from __future__ import annotations

import os
from pathlib import Path

# matplotlib 的缓存目录必须在导入 matplotlib 之前确定; 本机 ~/.config 不可写.
# 放在 data/ 下(已被 .gitignore 忽略), 避免每次启动重建字体缓存.
# 各主脚本也会设置同样的路径; 这里再设一次是为了让本模块可被单独导入.
DATA_DIR = Path(__file__).resolve().parent / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import matplotlib.colors as mcolors  # 归一化与山体晕渲
import matplotlib.pyplot as plt  # 绘图
import numpy as np  # 数组运算
import xarray as xr  # 读取 NetCDF
from cartopy import crs as ccrs  # 投影转换


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
    cmap: str = "terrain",
    azimuth: float = 315,
    altitude: float = 45,
    vert_exag: float = 1.5,
    fraction: float = 1.2,
):
    """把高程配色与山体晕渲合成 RGB 图.

    晕渲的作用: 纯高程色带在低地(本区域大部分 500~1500 m)几乎只有一两种颜色,
    看不出山脊和河谷走向; 用坡度算出的明暗乘到配色上, 地形细节立刻显现.
    dx/dy 必须和 z 使用同一单位(米): LightSource 用高程差除以网格间距算坡度,
    单位不一致时坡度(以及阴影浓淡)会错.
    """
    cmap_obj = plt.get_cmap(cmap)
    norm = mcolors.Normalize(vmin, vmax)

    dlat = (lat[-1] - lat[0]) / (lat.size - 1)
    dlon = (lon[-1] - lon[0]) / (lon.size - 1)
    dy = 110540.0 * dlat  # 1° 纬度约 110.54 km
    dx = 111320.0 * np.cos(np.deg2rad(np.mean(lat))) * dlon  # 经度随纬度收缩

    light = mcolors.LightSource(azdeg=azimuth, altdeg=altitude)
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
    return rgba, norm, cmap_obj


def load_countries(boundary_dir: Path):
    """读取 Natural Earth 10m 国家边界; 文件不存在时返回 None(跳过底图与国界)."""
    shapefiles = sorted(boundary_dir.glob("*.shp")) if boundary_dir.exists() else []
    if not shapefiles:
        print("警告: 未找到 Natural Earth 边界 shapefile, 跳过底图填充与国界.")
        return None
    import geopandas as gpd  # 延迟导入: 没有边界数据时不需要它

    return gpd.read_file(shapefiles[0])


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
            world.geometry,
            crs=ccrs.PlateCarree(),
            facecolor=land_color,
            edgecolor="none",
            zorder=0,
        )
