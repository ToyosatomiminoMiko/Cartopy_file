# 实例规格 (cartopy_file.spec)

- 源码: [`src/cartopy_file/spec.py`](../../src/cartopy_file/spec.py)
- 导入: `from cartopy_file import spec`

## 是什么

一张图的全部可配置事实: 画框、投影、画布、色带、经纬网、地名、城市点与文案. 全部是冻结
dataclass, **不 import matplotlib/cartopy**, 因此 `tools/` 可以不画图就枚举出所有实例的
产物路径与数据依赖.

实例(`Sheet`)写在子项目的 `specs.py` 里, 与数据集清单放在同一个文件: 下载范围和绘图范围
因此只有一个作者, 不会再出现「下载脚本写一个画框、绘图脚本又写一个」的问题.

## 关键行为

- `Extent(lon_min, lon_max, lat_min, lat_max)`: 命名字段, 不用记顺序. `as_list` 给 cartopy
  `set_extent`, `as_bbox` 给 shapely `box`, `padded(lon=, lat=)` 由画框推数据范围,
  `contains(other)` 做覆盖判断;
- `Projection(kind, params)`: 纯数据的 cartopy 投影. `kind` 是类名的蛇形, 登记在
  `CCRS_KINDS`(lambert_conformal / lambert_azimuthal_equal_area / plate_carree /
  orthographic / mercator / equal_earth / robinson), 需要新投影时只在这里加一行;
- `Relief`: `mode="rgba"` 时给 `sea`/`land` 锚点(高程 m, `#rrggbb`), 由
  `layers.make_relief_cmap` 在 0 m 处断开的双色带; `mode="scalar"` 时直接用命名色带
  (`name="terrain"`) 交给 matplotlib. `zorder=None` 表示不传 zorder(留给 matplotlib 默认);
- `Graticule`: 步长 + 网线位置的**精确取值** `lon_ticks`/`lat_ticks`(以前是各脚本里的
  `np.arange(...)`). 取值必须逐条写死: 起点差一格就会在 SVG 里多出一条被裁剪的路径,
  产物就不再是同一份图. `color` 原样传给 `ax.gridlines`(允许 `"gray"`), `stroke` 是给
  geo.json 的 `#rrggbb` 副本;
- `Label`: `lon/lat/text/role/font_size_pt` 必填, `dx/dy`(度)是相对锚点的偏移,
  `ha` 是水平对齐, `name`/`id_kind` 用于拼稳定的 label id;
- `City`: 点标记的尺寸/填充/描边/边宽与是否首都(形状由 `layers.add_cities` 固定);
- `Sheet`: 一张产物. `out` 是相对子项目目录的产物文件名; `axes=None` 用 `plt.subplots`
  默认布局, 给矩形则用 `add_axes`; `basemap=False` 表示不铺共享海陆底色(图种自己画);
  `tight_layout=True` 表示量地图框前先 `plt.tight_layout()`(苏联图); `dataset_ids` 是
  数据来源的署名依据, `dem_id` 指向其中的高程数据集; `relief=None` 表示这张图不铺高程.

## 用法

```python
from cartopy_file.spec import City, Extent, Graticule, Label, Projection, Relief, Sheet

PROJECTION = Projection("lambert_conformal", {
    "central_longitude": 96.5, "central_latitude": 19.5,
    "standard_parallels": (10.0, 27.0),
})

SHEET = Sheet(
    id="myanmar",
    out="myanmar_topography_etopo2022_lambert_conformal.svg",
    extent=Extent(87.0, 106.0, 5.0, 31.0),
    projection=PROJECTION,
    figsize=(12, 15),
    axes=(0.075, 0.05, 0.78, 0.85),
    relief=Relief(vmin=-5000, vmax=5000, name="myanmar_relief",
                  sea=((-1, "#a2d0ee"),), land=((1, "#dce4a2"),),
                  ticks=(-4000, -2000, 0, 2000, 4000)),
    graticule=Graticule(3.0, 5.0, lon_ticks=(87.0, 90.0, 93.0), lat_ticks=(5.0, 10.0)),
    dataset_ids=("etopo-myanmar", "ne-countries-10m"),
    dem_id="etopo-myanmar",
    cities=(City(96.10, 19.75, 13, "#ffd200", "black", 0.8, capital=True, name="内比都"),),
    labels=(Label(95.6, 23.5, "缅甸", role="country-name", font_size_pt=22.0),),
    title="缅甸联邦共和国全境地形图",
    subtitle="…",
)
```

一个脚本出多张图时写 `SHEETS = (SHEET_A, SHEET_B)`; 工具(`download_data.py --check`、
`tools/check_geo.py`)会把它们自动收进清单与自检范围.

## 注意事项

- **纯数据**: 这里不要 import matplotlib/cartopy, 也不要读数据文件; 需要投影几何计算
  (例如按投影包围盒定画布宽高比)就留在子项目的 `specs.py` 里, 或把算好的数字写成常量
  并注释来源;
- 画框只有一处: 数据集的 `bbox` 用 `Sheet.extent.padded(...)` 推出来; 确实需要非对称余量时
  也在 `specs.py` 里紧接着写, 不要跑到下载脚本里再写一遍;
- `lon_ticks`/`lat_ticks` 是**产物级**的取值: 改它们会改变 SVG 字节. 只想要更密的刻度时,
  先确认这是设计变更而不是顺手重排;
- `Sheet.out` 必须 `.svg` 结尾; 一个 `SHEETS` 里 id 与产物名都不能重复;
- 文案(`title/subtitle/notes`)只写纯文本; 色标标题只在 `relief` 存在时输出
  (`colorbar_title`), 不铺高程的图不要留一个空色标版面.
