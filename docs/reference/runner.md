# 出图流程 (cartopy_file.runner)

- 源码: [`src/cartopy_file/runner.py`](../../src/cartopy_file/runner.py)
- 导入: `from cartopy_file import runner`

## 是什么

所有图种共用的出图骨架: 建画布 -> 核对数据覆盖 -> 读高程 -> 铺底图与晕渲 -> 调图种自己的
图层函数 -> 版面 -> 量地图框 -> 收集 geo.json -> 保存产物.

图种脚本自己只剩三样东西: 数据(`specs.py` 里的 `DATASETS`)、规格(`SHEETS` 里的 `Sheet`)、
以及一对回调 `draw` / `collect`.

## 关键行为

固定顺序(顺序本身就是契约):

1. `layers.figure_axes(sheet)` 建画布并 `set_extent`; 量出画框投影后的实际覆盖 `covered`;
2. 若 `sheet.basemap`, 读共享 Natural Earth 国家多边形并铺海陆底色;
3. 若 `sheet.dem_id`, 核对数据集的 `bbox` 是否盖住 `covered`(盖不住打印警告), 读高程,
   按 `Sheet.relief` 铺晕渲;
4. 调 `draw(ctx)` —— 图种特有的图层, 包括城市点、经纬网, 顺序与改前成品一致;
5. 若 `sheet.tight_layout`, 先 `plt.tight_layout()`;
6. `GeoDoc(figure_frame(fig, ax))`, 调 `collect(doc, ctx)` 登记 geo;
7. `save_map()` 写裁到地图框的纯几何 SVG 与同名 geo.json.

`RenderContext` 字段: `sheet`、`catalog`、`root`、`fig`、`ax`、`world`、`lon`/`lat`/`z`
(有高程时)、`covered`.

`add_standard_arguments(parser)` 给脚本加全项目统一的 `--dpi` / `--show`; `run(...)` 是
`render(...)` 的标准命令行外壳.

## 用法

```python
import argparse
from cartopy_file import runner
from cartopy_file.relief import find_etopo

SHEET = specs.SHEET_MYANMAR
DATASETS = specs.DATASETS

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stride", type=int, default=None)
    runner.add_standard_arguments(parser)
    args = parser.parse_args()
    etopo = find_etopo(ROOT / "data" / "raw", "myanmar", args.stride)
    runner.render(SHEET, root=ROOT, catalog=DATASETS,
                  draw=draw, collect=collect,
                  dem_path=etopo, dpi=args.dpi, show=args.show)
```

## 注意事项

- **量地图框必须在最后**: `figure_frame` 会先 `apply_aspect()`, 只有版面与所有图层都画完
  之后量, 得到的才是最终裁剪框; 提前量会让底图与 geo.json 错位;
- 不要用 `bbox_inches="tight"`: 它会把几何再平移缩放一次, 引入第二套坐标, 让 geo 的锚点
  对不上底图; 裁剪只改根标签的 viewBox;
- 不要用 `constrained_layout`/`tight_layout` 去「顺手修版面」: cartopy 0.25 在非矩形投影上
  会让 gridliner 用未闭合顶点构造多边形而抛 `GEOSException`. 只有原来就用 `tight_layout`
  的图(苏联)通过 `Sheet.tight_layout=True` 保留该行为;
- 覆盖不足只打印警告不报错: 画框角落本来就有底图颜色兜底, 但看到警告应当回去核对
  `specs.py` 的 `bbox`, 那说明下载范围和绘图范围又分叉了;
- 一个进程出多张图时逐个 `render`(伏尔加的两张图), 每张都会独立建画布并在结束时关闭;
- 回调里不要自己调 `save_map`/`figure_frame`: 那是 `render` 的职责, 两处都做会写出两份产物;
- 需要在高程铺图**之前**预处理 z(例如按海岸线/湖泊把里海低地的负高程修正回陆地)时,
  把 `Sheet.dem_id` 留空, 在 `main()` 里 `load_elevation()` 预处理一次, 再在 `draw()` 里调
  `layers.add_relief`(伏尔加两张图就是这样): 图层仍是框架原语, 只是绕开了 runner 的自动
  铺图那一步, 代价是同时绕开它的数据覆盖警告, 所以 `specs.py` 的 bbox 要自己核对;
- 同理, 底纹需要特殊合成(透明遮罩/插值/命名色带软光)时也在 `draw()` 里画, 见
  [reference/layers.md](layers.md) 的注意事项.
