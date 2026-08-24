# -*- coding: utf-8 -*-
# ============================================================
# ussr.py
# 从本地 ETOPO 2022 NetCDF 读取苏联区域地形数据,
# 使用 Cartopy 绘制兰勃特等面积方位投影地形图,
# 并叠加 Natural Earth 前苏联加盟共和国合并边界.
# 运行前需确保 data/ 下存在高程 NetCDF 与边界 shapefile.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
import os  # 读取环境变量,例如 ETOPO_PATH
from pathlib import Path  # 统一使用 pathlib 处理文件路径

import cartopy.crs as ccrs  # 地图投影
import cartopy.feature as cfeature  # 海岸线,国界等自然要素
import geopandas as gpd  # 读取并处理 shapefile 边界
import matplotlib.pyplot as plt  # 绘图
import matplotlib.ticker as mticker  # 经纬网刻度定位
import numpy as np  # 数组运算
import xarray as xr  # 读取 NetCDF
from shapely.ops import unary_union  # 合并多个面为单一几何边界

# 设置 Matplotlib 中文字体,避免标题和警告中的中文显示为方框.
# 若系统中没有 Noto Sans CJK SC,会自动回退到 DejaVu Sans.
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "JetBrains Mono Slashed Medium"]
# 使用 Unicode 负号,避免坐标轴负号显示异常.
plt.rcParams["axes.unicode_minus"] = False


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
# 图标题,换行分隔数据来源、投影类型和投影中心.
title = (
    "USSR (ETOPO 2022,本地 NetCDF)\n"
    "兰勃特等面积方位投影(平面/方位投影)|中心 90°E, 55°N"
)


# ============================
# 1. 读取本地 ETOPO 2022 数据
# ============================
# 若高程文件不存在,直接给出可操作的修复提示,避免后续绘图报难懂的错.
if not ETOPO_PATH.exists():
    raise FileNotFoundError(
        f"未找到高程数据: {ETOPO_PATH}\n"
        "请先运行: python download_etopo.py\n"
        "或设置 ETOPO_PATH 指向已有的 ERDDAP NetCDF 文件"
    )

# 打开 NetCDF 文件; decode_times=False 避免把与时间无关的维度误解析成日期.
ds = xr.open_dataset(ETOPO_PATH, decode_times=False, engine="netcdf4")

# ERDDAP 使用 z / latitude / longitude 直接取 2D 数组绘制
# 避免 xarray 内部为 pcolormesh 生成巨大二维坐标网格
# 这里手动取出经度、纬度一维坐标以及高程二维数组.
elevation = ds["z"]
lon = elevation["longitude"].to_numpy()
lat = elevation["latitude"].to_numpy()
z = elevation.to_numpy()

# 如果纬度是从北到南排列,则翻转为从南到北,
# 这样才能与 imshow(origin="lower") 的显示方向保持一致.
if lat[0] > lat[-1]:
    lat = lat[::-1]
    z = z[::-1, :]

# 输出数组形状和实际经纬度范围,便于快速确认读取是否正确.
print(
    f"高程数据维度: {z.shape}, 范围: lon {lon[0]:.2f}~{lon[-1]:.2f}, lat {lat[0]:.2f}~{lat[-1]:.2f}"
)

# ============================
# 2. 绘制地图
# ============================
# 创建带指定投影的绘图对象, figsize 控制最终图片宽高比.
fig, ax = plt.subplots(figsize=(16, 12), subplot_kw={"projection": PROJECTION})
# 限定地图显示范围; 这里的范围坐标是 PlateCarree(经纬度).
ax.set_extent(extent, crs=ccrs.PlateCarree())

# 用 imshow 绘制规则网格高程,比 pcolormesh 更快、更省内存.
# origin="lower" 保证数组第一行对应图像底部;
# extent 告诉 Matplotlib 数据对应的经纬度范围;
# transform 表示这些坐标是经纬度,需要由 Cartopy 转换到投影坐标.
im = ax.imshow(
    z,
    origin="lower",
    extent=[lon[0], lon[-1], lat[0], lat[-1]],
    transform=ccrs.PlateCarree(),
    cmap="terrain",
    alpha=0.9,
    vmin=-5000,
    vmax=5000,
    interpolation="nearest",
)

# 添加色标,并标出高程单位.
fig.colorbar(im, ax=ax, fraction=0.025, pad=0.04, label="Elevation (m)")
# 叠加海岸线,便于观察陆地轮廓与地形之间的对应关系.
ax.add_feature(cfeature.COASTLINE, linewidth=0.6, color="black")

# ============================
# 3. 叠加苏联边界 合并前苏联加盟共和国
# ============================
# 前苏联 15 个加盟共和国的 Natural Earth 英文国名.
ussr_republics = [
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

# 若边界目录存在,则列出其中的 shapefile,并按文件名排序保证可复现.
boundary_shapefiles = (
    sorted(BOUNDARY_DIR.glob("*.shp")) if BOUNDARY_DIR.exists() else []
)
if boundary_shapefiles:
    # 读取第一个 shapefile; 这里通常就是 ne_10m_admin_0_countries.shp.
    world = gpd.read_file(boundary_shapefiles[0])

    # Natural Earth 字段因版本不同可能是 NAME/NAME_EN/ADMIN
    # 只保留当前文件中实际存在的国名字段.
    name_columns = [c for c in ("NAME", "NAME_EN", "ADMIN") if c in world.columns]
    if not name_columns:
        raise RuntimeError("无法识别 Natural Earth 国名字段,请检查 shapefile.")

    # 优先使用第一个可用国名字段筛选出前苏联国家.
    name_column = name_columns[0]
    ussr_countries = world[world[name_column].isin(ussr_republics)]
    if ussr_countries.empty:
        # 某些版本使用 sovereign 字段更准确,退化到所有字段模糊匹配
        # 主字段没有匹配时,遍历所有可用名称字段再做一次兜底筛选.
        mask = np.zeros(len(world), dtype=bool)
        for col in name_columns:
            mask |= world[col].isin(ussr_republics).to_numpy()
        ussr_countries = world[mask]

    if ussr_countries.empty:
        print("警告: 未在 Natural Earth 数据中找到目标国家,跳过红色边界.")
    else:
        # 将多个加盟共和国几何合并成一个整体,得到苏联外轮廓.
        ussr_boundary = unary_union(ussr_countries.geometry)
        # 只绘制红色轮廓线,不填充内部,避免盖住地形.
        ax.add_geometries(
            [ussr_boundary],
            crs=ccrs.PlateCarree(),
            edgecolor="red",
            facecolor="none",
            linewidth=1.8,
        )
else:
    print("警告: 未找到 Natural Earth shapefile,跳过红色边界.")

# ============================
# 4. 添加网格和标签
# ============================
# draw_labels=False 先关闭自动标签,下面再手动控制显示位置,
# 这样更容易统一标签的刻度密度和视觉样式.
gl = ax.gridlines(
    draw_labels=False,
    dms=True,
    x_inline=False,
    y_inline=False,
    linewidth=0.8,
    color="gray",
    alpha=0.6,
)
# 只显示左侧纬度标签和底部经度标签,减少上下左右的视觉拥挤.
gl.top_labels = False
gl.right_labels = False
# 纬度每 10° 一条,经度每 15° 一条; 经度上限要与展开后的 195° 对齐.
gl.ylocator = mticker.FixedLocator(np.arange(20, 91, 10))
gl.xlocator = mticker.FixedLocator(np.arange(15, 196, 15))

# 设置标题,pad 控制标题与地图之间的间距.
ax.set_title(title, fontsize=15, pad=20)

# 保存高清图片
# 先收紧布局,避免四周留下过多空白.
plt.tight_layout()

# 输出到脚本同目录,300 dpi 适合后续查看或排版使用.
save_img = False
if save_img:
    out_png = ROOT / "ussr_topography_etopo2022_lambert_azimuthal.png"
    # bbox_inches="tight" 会裁掉坐标区外多余的空白.
    plt.savefig(out_png, dpi=300, bbox_inches="tight")
    print(f"✅ 地图已保存为 {out_png}")

# 在图形界面中显示结果; 无图形界面环境可注释掉这一行.
plt.show()
