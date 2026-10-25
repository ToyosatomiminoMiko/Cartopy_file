# 缅甸脚本的绘图工具入口 (Myanmar/map_lib.py)

- 源码: [`Myanmar/map_lib.py`](../../Myanmar/map_lib.py)
- 用途: 缅甸绘图脚本 `import map_lib` 的兼容入口; 实现见
  [`src/cartopy_file/relief.py`](../../src/cartopy_file/relief.py)

## 是什么

缅甸系列地形图共用工具的兼容层: 重新导出 `cartopy_file.relief` 的 `add_base_map`、
`find_etopo`、`load_countries`、`load_elevation`、`make_relief`.

保留这个文件是因为 [`myanmar.py`](myanmar.md) 与 [`northern_shan.py`](northern_shan.md)
里写的是 `import map_lib`, 函数名不变可以避免改脚本; 实现只有 `cartopy_file.relief`
一份, 两个图种共用.

## 注意事项

导入本模块时会先设置 `MPLCONFIGDIR`(指向 `data/.mplcache`), 因为 `cartopy_file.relief`
会导入 matplotlib/cartopy; 这样本模块也可以被单独导入.
