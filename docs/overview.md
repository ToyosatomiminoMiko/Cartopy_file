# 项目总览

这个仓库把四组地图(缅甸、苏联、乌克兰、伏尔加河流域)放在一起, 共用一套 cartopy 绘图工具. 每个图种一个
目录, 重复的代码集中到可安装的共享包 `src/cartopy_file/`.

## 目录结构

```
Cartopy_file/
├── README.md               安装与快速开始
├── pyproject.toml          依赖与打包(uv_build)
├── docs/                   本目录: 概念 / 图种 / 参考三层
├── data/                   cartopy 共用的 Natural Earth 底图缓存(不入库)
├── download_data.py        共用底图预取 + 全项目数据清单检查
├── src/cartopy_file/       共享包: data / fonts / output / relief / overlap
├── Myanmar/                缅甸图种: 3 张图 + 数据准备脚本 + data/
├── USSR/                   苏联图种
├── Ukraine/                乌克兰图种
├── Volga/                  伏尔加河流域图种: 流域图 + 周边六个共和国图 + 数据准备脚本 + data/
├── AmericaArmy/            早期演示脚本与手工底图, 不在维护范围
├── global.py               一次性演示脚本
└── _stride1_chunked.py     一次性临时脚本(见 maps/northern-shan.md)
```

## 三层结构

1. **图种层**([`maps/`](maps)): 每个图种一个目录, 内含绘图脚本、数据准备脚本和私有数据目录
   `<图种>/data/`; 产物写到脚本同目录; 各图种之间不互相 import.
2. **共享层**([`src/cartopy_file/`](../src/cartopy_file)): 可安装的包, 放四组图共用的数据
   定位、字体、SVG 出图、地形与几何工具.
3. **数据层**([`data-preparation.md`](data-preparation.md)): 仓库 `data/cartopy/` 是全项目
   共用的 cartopy 底图缓存; 各图种自己的数据放在各自 `data/` 下.

## 数据流

```
download_data.py ──► data/cartopy/ ─┐
各图 download_*/prepare_* ──► <图种>/data/ ──┴──► 绘图脚本(只读本地) ──► .svg
```

绘图脚本不联网: 数据在首次准备时下载一次, 之后出图只读本地文件; 要素缺缓存时 cartopy 会在
渲染中临时联网, 所以共用底图要用 `download_data.py` 预取. 详见
[`data-preparation.md`](data-preparation.md).

## 共享包模块

顶层 `__init__.py` 重导出 `data` / `fonts` / `output` 的常用符号; `overlap` 与 `relief` 不
重导出, 避免所有脚本都连带导入 shapely / matplotlib.

| 模块 | 内容 | 参考页 |
| --- | --- | --- |
| `data` | 数据目录与 cartopy/matplotlib 缓存定位 | [`reference/data.md`](reference/data.md) |
| `fonts` | 全局字体(中英文逐字符回退) | [`reference/fonts.md`](reference/fonts.md) |
| `output` | 唯一的 SVG 出图入口 | [`reference/output.md`](reference/output.md) |
| `relief` | 高程读取、配色与山体晕渲、海陆底色 | [`reference/relief.md`](reference/relief.md) |
| `overlap` | 边界重合剪枝(按子模块导入) | [`reference/overlap.md`](reference/overlap.md) |

## 为什么要有共享包

子目录脚本直接运行时只有脚本所在目录在 `sys.path` 上; 共享代码放进已安装的包后普通
`import` 即可, 不必再用 `sys.path.insert` 去操作外层目录. 安装方式见
[README](../README.md) 的"安装"一节.
