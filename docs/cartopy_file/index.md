# 项目共享包 (cartopy_file)

- 源码: [`src/cartopy_file/__init__.py`](../../src/cartopy_file/__init__.py)
- 用途: 各图种脚本共用的代码入口(字体、数据/缓存定位、SVG 出图、几何与地形工具)
- 安装: 仓库根执行 `uv pip install -e .`(见根 [README.md](../../README.md))

## 是什么

把重复代码集中成一个可安装的包: 子目录脚本直接运行时只有脚本所在目录在 `sys.path` 上,
共享代码放进已安装的包后普通 `import` 即可, 不必再用 `sys.path.insert` 操作外层目录.

| 模块 | 内容 |
| --- | --- |
| [`data`](data.md) | 数据目录与 cartopy/matplotlib 缓存定位 |
| [`fonts`](fonts.md) | 全局字体(中英文逐字符回退) |
| [`output`](output.md) | 唯一的 SVG 出图入口 |
| [`overlap`](overlap.md) | 边界重合剪枝(按子模块导入) |
| [`relief`](relief.md) | 地形/底图共用工具(按子模块导入) |

顶层 `__all__` 重导出 `data` / `fonts` / `output` 的常用符号; `overlap` 与 `relief`
不重导出, 避免所有脚本都连带导入 shapely / matplotlib.
