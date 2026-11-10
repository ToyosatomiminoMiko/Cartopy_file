# 出图流程 (cartopy_file.runner)

- 源码: [`src/cartopy_file/runner.py`](../../src/cartopy_file/runner.py)
- 导入: `from cartopy_file import runner`

## 是什么

所有图种共用的出图骨架: 建画布 -> 核对数据覆盖 -> 读高程 -> 铺底图与晕渲 -> 调图种自己的
图层函数 -> 版面 -> 量地图框 -> 收集 geo.json -> 保存产物.

图种脚本自己只剩两样东西: 数据清单的引用(`config.py` 里的 `DATA_GROUP`, 运行时由
`catalog_for()` 变成 [`Catalog`](catalog.md))与规格(`SHEETS` 里的 `Sheet`, 图例与文案也声明
在这里), 外加一个 `draw` 回调. 没有图种特有动态数据时不用写 `collect`:
`render` 缺省用 `layers.standard_collect`, 把 `Sheet` 里的地名/经纬刻度/色标/图例/文案
写进 geo.json.

## 关键行为

固定顺序(顺序本身就是契约):

0. `_require_shared_layers(sheet, catalog)`: 核对 `sheet.dataset_ids` 里登记为 `cartopy-ne` 的
   共享 Natural Earth 图层是否都在本地缓存. 缺层在画图前就抛 `FileNotFoundError` 并指向数据
   项目的 `download`, 不会写出缺底图/国界的半成品;
1. `layers.figure_axes(sheet)` 建画布并 `set_extent`; 量出画框投影后的实际覆盖 `covered`;
2. 若 `sheet.basemap`, 读共享 Natural Earth 国家多边形并铺海陆底色;
3. 若 `sheet.dem_id`, 按 `catalog.get(dem_id)` 取数据集, 核对它的 `bbox` 是否盖住 `covered`
   (盖不住打印警告), 读高程, 按 `Sheet.relief` 铺晕渲; `dem_path` 传入时直接用那个文件;
4. 调 `draw(ctx)` -- 图种特有的图层, 包括城市点,经纬网; 叠放顺序由 `draw` 决定;
5. 若 `sheet.tight_layout`, 先 `plt.tight_layout()`;
6. `GeoDoc(figure_frame(fig, ax))`, 调 `collect(doc, ctx)` 登记 geo; `collect=None` 时调
   `layers.standard_collect(doc, ax, sheet, catalog)`;
7. `save_map()` 把裁到地图框的纯几何 SVG 写到 `<子项目>/map/`,文字信息 geo.json 写到
   `<子项目>/text/`; 两个路径由 `spec` 的 `map_path`/`text_path` 拼.

`RenderContext` 字段: `sheet`,`catalog`,`root`,`fig`,`ax`,`world`,`lon`/`lat`/`z`
(有高程时),`covered`,`label_vars`. `catalog` 就是 `catalog_for(config.DATA_GROUP)` 的结果.

`render` 的其它参数:

- `catalog`(必填): 该子项目的 [`Catalog`](catalog.md), 由入口或绘图模块用
  `catalog_for(config.DATA_GROUP)` 取;
- `collect=None`: 用默认收集(见上); 只有在图种有动态数据(图例按主题变化,图上有算出来的
  数值)时才自己写 `collect`, 并且仍建议在里面调 `layers.standard_collect` 再补字段;
- `label_vars`: 地名 `text`,`notes`,`area_annotation` 里的 `{name:.0f}` 占位符取值,
  出图时才知道的数(如流域面积)走这里, 不要让 `config.py` 去读数据;
- `area_annotation`: 图外面积注记(geo.suggestions 的对应字段), 同样是出图时才知道的数;
- `close` / `dpi` / `show`: 关窗,内嵌栅格密度,保存后弹窗.

命令行参数(`--dpi` / `--show` / `--stride` 等)由子项目入口 `main.py` 解析, 本模块只接收
解析好的值; 入口与绘图模块的分工见 [reference/spec.md](spec.md) 与
[docs/conventions.md](../conventions.md) 的「脚本入口」一节.

## 用法

绘图模块只暴露 `run(...)`, 命令行参数由子项目入口 `main.py` 解析后传入:

```python
from cartopy_file import runner
from cartopy_file.catalog import catalog_for
from cartopy_file.relief import find_etopo

SHEET = config.SHEET_MYANMAR
CATALOG = catalog_for(config.DATA_GROUP)

def run(*, stride=None, dpi=None, show=False) -> int:
    etopo = find_etopo(CATALOG.raw_dir, "myanmar", stride)
    # 没有动态数据: 不传 collect, 由 standard_collect 按 Sheet 写 geo.
    runner.render(SHEET, root=ROOT, catalog=CATALOG,
                  draw=draw, dem_path=etopo, dpi=dpi, show=show)

    # 有动态数据时(例: 伏尔加的面积)传参, 同样不用写 collect:
    # runner.render(SHEET, ..., catalog=CATALOG, label_vars={"area_wan": 140.0},
    #               area_annotation=["伏尔加河流域", "约 {area_wan:.0f} 万 km²"])
    return 0
```

## 注意事项

- **collect 只在有动态数据时写**: 静态图例/文案一律声明在 `Sheet` 里, 模块里手拼
  geo 字段会让「改图」变成「改两处」;
- **量地图框必须在最后**: `figure_frame` 会先 `apply_aspect()`, 只有版面与所有图层都画完
  之后量, 得到的才是最终裁剪框; 提前量会让底图与 geo.json 错位;
- 不要用 `bbox_inches="tight"`: 它会把几何再平移缩放一次, 引入第二套坐标, 让 geo 的锚点
  对不上底图; 裁剪只改根标签的 viewBox;
- 不要用 `constrained_layout`/`tight_layout` 去「顺手修版面」: cartopy 0.25 在非矩形投影上
  会让 gridliner 用未闭合顶点构造多边形而抛 `GEOSException`. 需要 `tight_layout` 的图(苏联)
  通过 `Sheet.tight_layout=True` 启用该行为;
- 覆盖不足只打印警告不报错: 画框角落本来就有底图颜色兜底, 但看到警告应当回数据项目核对区域
  配置的 `bbox`(它写进 manifest, 出图时与画框比对), 那说明下载范围和绘图范围又分叉了;
- 共享图层缺失是**硬失败**: `_require_shared_layers` 在画图前抛错, 提示到数据项目跑
  `python main.py download`; 不要改成静默跳过, 那会写出缺底图的产物;
- 一个进程出多张图时逐个 `render`(伏尔加的两张图), 每张都会独立建画布并在结束时关闭;
- 回调里不要自己调 `save_map`/`figure_frame`: 那是 `render` 的职责, 两处都做会写出两份产物;
- 需要在高程铺图**之前**预处理 z(例如按海岸线/湖泊把里海低地的负高程修正回陆地)时,
  把 `Sheet.dem_id` 留空, 在 `run()` 里 `load_elevation()` 预处理一次, 再在 `draw()` 里调
  `layers.add_relief`(伏尔加两张图就是这样): 图层仍是框架原语, 只是绕开了 runner 的自动
  铺图那一步, 代价是同时绕开它的数据覆盖警告, 所以清单里的 `bbox` 要自己核对;
- 同理, 底纹需要特殊合成(透明遮罩/插值/命名色带软光)时也在 `draw()` 里画, 见
  [reference/layers.md](layers.md) 的注意事项.
