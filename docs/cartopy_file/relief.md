# 地形/底图共用工具 (cartopy_file.relief)

- 源码: [`src/cartopy_file/relief.py`](../../src/cartopy_file/relief.py)
- 用法: 先设置 `MPLCONFIGDIR`, 再 `from cartopy_file.relief import ...`
- 警告: 本模块导入即加载 matplotlib/cartopy, 调用方必须在 import 本模块**之前**设置好
  `MPLCONFIGDIR`

## 是什么

地形图共用工具: 读取 ETOPO 2022 NetCDF 高程、合成高程配色与山体晕渲、读取 Natural Earth
国界、铺海陆底色.

- `find_etopo(data_dir, region, stride=None, env_path=None)`: 按区域名(如 `myanmar` /
  `ukraine`)与采样步长定位本地高程文件;
- `load_elevation(path)`: 读高程数组与一维经纬度, 纬度统一翻成南->北, 交给
  `imshow(origin="lower")` 即可;
- `make_relief(z, lat, lon, *, vmin, vmax, ...)`: 把高程色带与 `LightSource` 晕渲合成 RGB;
- `load_countries(boundary_dir)` / `add_base_map(ax, world, *, ocean_color, land_color)`:
  读 Natural Earth 国界, 在画地形前铺一层真实海陆底色;
- `clip_to_axes(ax, geoms)`: 把面几何裁到当前坐标范围, 避免画面外顶点写进 SVG(矢量输出
  时同样占字节).

## 关键行为

- `find_etopo()`: 文件名约定为 `ETOPO_2022_v1_15s_{region}_stride{N}.nc`; 优先级为显式
  `stride` > 环境变量 `env_path` > `data/` 下该区域步长最小(分辨率最高)的文件; 一个都
  没有时返回 `stride2` 的路径, 由调用方检查是否存在;
- `load_elevation()`: 读到三维时取第一个时间片; 打印文件形状与经纬度/高程范围;
- `make_relief()`: 纯高程色带在低地几乎只有一两种颜色, 看不出山脊河谷; 用坡度算出的
  明暗乘到配色上, 地形细节才显现. `dx`/`dy` 必须与 `z` 同单位(米), 否则坡度与阴影浓淡
  会错. `shade_strength=None` 用软光混合(`blend_mode="soft"`); 给定数值时改用"只压暗"的
  乘法晕渲, 适合浅色底图上的平原国家; `shade_floor` 是压暗下限, 水面(`z < 0`)不晕渲;
- `load_countries()`: 读 10m 国界 shapefile; 文件不存在时打印警告并返回 `None`, 调用方
  据此跳过底图与国界;
- `clip_to_axes()`: 底图是全球国家多边形(约 55 万顶点), 不裁时单这一层填色就让 SVG 大出
  十几 MB; 裁剪窗口取 `ax.get_extent(PlateCarree)`, 一定盖住整个画面, 外观不变. 跨 180°
  经线的图幅不裁(shapely 的 `box` 不处理经度环绕);
- `add_base_map()`: 画框四角可能探出 ETOPO 子集范围, 或近岸有缺测; 用 Natural Earth
  陆地多边形盖在海洋色背景上, 比露出白色空白更不误导.

## 用法

```python
from pathlib import Path

from cartopy_file.data import prepare_matplotlib_env

prepare_matplotlib_env()  # 必须在导入 matplotlib 之前

from cartopy_file.relief import (  # noqa: E402
    add_base_map,
    find_etopo,
    load_countries,
    load_elevation,
    make_relief,
)

etopo_path = find_etopo(Path("Myanmar/data"), "myanmar")
if not etopo_path.exists():
    raise FileNotFoundError(f"未找到高程数据: {etopo_path}")

lon, lat, z = load_elevation(etopo_path)
world = load_countries(Path("Myanmar/data/ne_10m_admin_0_countries"))
add_base_map(ax, world, ocean_color=BASE_OCEAN_COLOR, land_color=BASE_LAND_COLOR)

relief_rgba, norm, cmap = make_relief(z, lat, lon, vmin=-5000, vmax=6000)
ax.imshow(relief_rgba, origin="lower", extent=(lon[0], lon[-1], lat[0], lat[-1]))
```
