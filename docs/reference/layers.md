# 图层原语 (cartopy_file.layers)

- 源码: [`src/cartopy_file/layers.py`](../../src/cartopy_file/layers.py)
- 导入: `from cartopy_file import layers`

## 是什么

各图种脚本里重复的图层代码收成一组函数: 建画布与坐标区、铺海陆底色、画 ETOPO 晕渲、
经纬网、城市点、地名/刻度/色标/文案的 geo 收集.

只把「每张图都一样」的部分收上来; 国界、行政区填色、河流、流域这些图种特有的图层仍留在
各自脚本里, 用这里的原语和 `spec.py` 的数据去画.

## 关键行为

- `figure_axes(sheet)`: 按 `Sheet.axes`/`figsize`/`projection` 建画布, 设 `set_anchor("C")`
  与 `set_extent(sheet.extent.as_list)`; `covered_extent(ax)` 返回画框在经纬度上的实际覆盖
  (非矩形投影的矩形画框会探出 `set_extent` 给的经纬度矩形, 数据要盖住的是它);
- `add_base_map(ax, sheet, world=None)`: `world` 缺省读共享缓存里的 Natural Earth 10m
  国家多边形, 先铺真实海陆底色再叠地形——画框四角探出 ETOPO 子集时不会露白;
- `add_relief(ax, sheet, lon, lat, z)`: `rgba` 模式把配色与山体晕渲合成为 RGB 再
  `imshow`(`regrid_shape`/`zorder` 来自 spec), `scalar` 模式直接把高程交给 `imshow`;
- `add_gridlines(ax, sheet)`: 网线位置取 `Graticule.lon_ticks/lat_ticks`, 为空时按
  `Sheet.extent` 与步长取整倍数;
- `add_cities(ax, cities)`: 首都星形、其余空心圆, 只画点不画字;
- `collect_labels/collect_graticule/collect_relief`: 往 `GeoDoc` 登记地名、经纬刻度、色标;
  `suggestions(sheet, catalog)`: 文案 + 由 `DatasetSet.citation` 自动生成的「数据来源」;
- `standard_collect(doc, ax, sheet, catalog)`: 上面几步的默认顺序(地名 -> 刻度 -> 色标 ->
  文案); 图种需要动态标签/图例时自己按同样顺序调用, 不要复制实现;
- `make_relief_cmap(relief)`: 按锚点造 0 m 处断开的双色带; `ne_dir()`/`countries_frame()`:
  共享缓存里 Natural Earth 图层的目录/图层; `build_projection(projection)`: 纯数据投影 ->
  cartopy 对象.

## 用法

```python
from cartopy_file import layers

def draw(ctx):
    # 图种特有图层, 按原成品的叠放顺序画
    draw_borders(ctx.ax, ctx.world)
    layers.add_cities(ctx.ax, ctx.sheet.cities)
    layers.add_gridlines(ctx.ax, ctx.sheet)

def collect(doc, ctx):
    layers.collect_labels(doc, ctx.ax, ctx.sheet.labels)
    layers.collect_graticule(doc, ctx.ax, ctx.sheet)
    layers.collect_relief(doc, ctx.sheet)
    doc.set_suggestions(layers.suggestions(ctx.sheet, ctx.catalog))
```

## 注意事项

- `add_gridlines` 的位置必须与改前产物的 locator 取值逐条一致: 多一条网线就会在 SVG 里多
  一条被裁剪的路径, 产物字节就变了;
- `countries_frame()` 读的是**具体图层**(`admin_0_countries`), 不要把共享缓存的类别目录
  传进去按 `*.shp` 排序取第一个——同一目录下有几十个图层, 取错就是另一张图;
- 经纬网颜色按 `Graticule.color` 原样传给 `ax.gridlines`(`"gray"` 与 `"#808080"` 在
  matplotlib 里不是同一个颜色值), geo.json 那一侧用 `Graticule.stroke` 的 `#rrggbb`;
- `layers` 在 import 时就会调 `configure_cartopy()` 与 `apply_svg_output()`, 所以脚本
  仍然必须在 import matplotlib 之前设好 `MPLCONFIGDIR`(见 [reference/data.md](data.md));
- 这里不做 `tight_layout`/`bbox_inches="tight"`: 版面由 `Sheet.tight_layout` 与
  `runner` 控制, 原因见 [reference/runner.md](runner.md);
- `add_relief` 覆盖三种常见形态: 锚点色带 + 晕渲合成(`rgba`)、命名色带直出(`scalar`).
  图种需要更特别的合成时——例如「0 m 以下透明 + 双线性插值」(缅甸行政区图)或
  「命名色带 + soft 混合晕渲」(掸邦图)——在 `draw()` 里直接用 `relief.make_relief` 与
  `ax.imshow` 复刻, 色带/范围/来光/夸张系数仍从 `Sheet.relief` 取, 并把定制原因写在脚本
  顶部. 这类图把 `Sheet.dem_id` 留空, 由脚本自己读高程, 免得 runner 重复铺一层. 若以后
  要收编, 需要给 `Relief` 增加插值/混合开关, 属于会改产物字节的改动, 要单独评审.
