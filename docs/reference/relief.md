# 地形/底图共用工具 (cartopy_file.relief)

- 源码: [`src/cartopy_file/relief.py`](../../src/cartopy_file/relief.py)
- 导入: 先设置 `MPLCONFIGDIR`, 再 `from cartopy_file.relief import ...`

## 是什么

地形图共用工具: 读取 ETOPO 2022 NetCDF 高程,合成高程配色与山体晕渲,读取 Natural Earth
国界,铺海陆底色.

- `find_etopo(data_dir, region, stride=None, env_path=None)`: 按区域名(如 `myanmar` /
  `ukraine`)与采样步长定位本地高程文件; `data_dir` 传
  [`Catalog.raw_dir`](catalog.md)(即 `<数据根>/<region>/raw`);
- `load_elevation(path)`: 读高程数组与一维经纬度, 纬度统一翻成南->北, 交给
  `imshow(origin="lower")` 即可;
- `make_relief(z, lat, lon, *, vmin, vmax, ...)`: 把高程色带与 `LightSource` 晕渲合成 RGB;
- `load_countries(boundary_dir)` / `add_base_map(ax, world, *, ocean_color, land_color)`:
  读 Natural Earth 国界, 在画地形前铺一层真实海陆底色;
- `load_ne_layer(resolution, category, name)`: 按 cartopy 缓存位置读取一份 Natural Earth
  图层(返回 `GeoDataFrame`, 缺失时 `None`), 用来取国界线或海岸线等单个图层;
- `clip_to_axes(ax, geoms)`: 把面几何裁到当前坐标范围, 避免画面外顶点写进 SVG(矢量输出时
  同样占字节).

## 关键行为

- `find_etopo()`: 文件名约定为 `ETOPO_2022_v1_15s_{region}_stride{N}.nc`; 优先级为环境变量
  `env_path` > 显式 `stride` > `data_dir` 下该区域步长最小(分辨率最高)的文件; 一个都没有时
  返回 `stride2` 的路径, 由调用方检查是否存在;
- `load_elevation()`: 读到三维时取第一个时间片; 打印文件形状与经纬度/高程范围;
- `make_relief()`: 纯高程色带在低地几乎只有一两种颜色, 看不出山脊河谷; 用坡度算出的明暗乘到
  配色上, 地形细节才显现. `dx`/`dy` 必须与 `z` 同单位(米), 否则坡度与阴影浓淡会错.
  `shade_strength=None` 用软光混合(`blend_mode="soft"`); 给定数值时改用"只压暗"的乘法晕渲,
  适合浅色底图上的平原国家; `shade_floor` 是压暗下限, 水面(`z < 0`)不晕渲;
- `load_countries()`: 读 10m 国界 shapefile; 文件不存在时打印警告并返回 `None`, 调用方据此
  跳过底图与国界;
- `load_ne_layer()`: 只读缓存(不联网), `.shp` 在即整层在; 与 `load_countries()` 的区别是
  按 resolution/category/name 取任意一层(如 `10m` / `physical` / `coastline`), 常用作裁剪
  蒙版或只画某一层线要素, 不会把整层海岸线当成要绘制的线画出来;
- `clip_to_axes()`: 底图是全球国家多边形(约 55 万顶点), 不裁时单这一层填色就让 SVG 大出十几
  MB; 裁剪窗口取 `ax.get_extent(PlateCarree)`, 一定盖住整个画面, 外观不变. 跨 180° 经线的
  图幅不裁(shapely 的 `box` 不处理经度环绕);
- `add_base_map()`: 画框四角可能探出 ETOPO 子集范围, 或近岸有缺测; 用 Natural Earth 陆地
  多边形盖在海洋色背景上, 比露出白色空白更不误导.

## 用法

```python
import config
from cartopy_file.catalog import catalog_for

from cartopy_file.data import prepare_matplotlib_env

prepare_matplotlib_env()  # 必须在导入 matplotlib 之前

from cartopy_file.relief import (  # noqa: E402
    add_base_map,
    find_etopo,
    load_elevation,
    load_ne_layer,
    make_relief,
)

# 高程在 <数据根>/<region>/raw 下; Natural Earth 图层读共享缓存(读不到时返回 None).
CATALOG = catalog_for(config.DATA_GROUP)
etopo_path = find_etopo(CATALOG.raw_dir, "myanmar")
if not etopo_path.exists():
    raise FileNotFoundError(
        f"未找到高程数据: {etopo_path}\n"
        "请先到数据项目 miko_gis_data 运行: python main.py download --group myanmar"
    )

lon, lat, z = load_elevation(etopo_path)
world = load_ne_layer("10m", "cultural", "admin_0_countries")
add_base_map(ax, world, ocean_color=BASE_OCEAN_COLOR, land_color=BASE_LAND_COLOR)

relief_rgba, norm, cmap = make_relief(z, lat, lon, vmin=-5000, vmax=6000)
ax.imshow(relief_rgba, origin="lower", extent=(lon[0], lon[-1], lat[0], lat[-1]))
```

## 注意事项

- 警告: 本模块导入即加载 matplotlib/cartopy, 调用方必须在 import 本模块**之前**设置好
  `MPLCONFIGDIR`(用 [`cartopy_file.data.prepare_matplotlib_env()`](data.md)), 否则默认落在
  HOME 下的 `~/.config` 会让 matplotlib 每次重建字体缓存;
- 各子项目模块直接 `from cartopy_file.relief import ...`;
- 共享的 cartopy 底图在 `<数据根>/cartopy`; 各区域自己的高程与原始矢量在
  `<数据根>/<region>/raw`(下载原样), `find_etopo` 的 `data_dir` 传这一层(绘图模块直接传
  `Catalog.raw_dir`). 派生矢量不在数据根里, 由本仓 `prepare` 写到 `<子项目>/build/`,
  分工见 [`data-preparation.md`](../data-preparation.md) 与
  [`prepare.md`](prepare.md);
- `load_countries()` 从指定目录读 10m 国界; 常规图种用 `layers.countries_frame()` 读共享
  缓存, 不要照它写新代码.
