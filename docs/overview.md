# 项目总览

这个仓库把五组地图(缅甸,苏联,乌克兰,伏尔加河流域,美军基地演示)放在一起, 共用一套
cartopy 绘图工具. 每个子项目一个目录, 重复的代码集中到可安装的共享包 `src/cartopy_file/`.

## 目录结构

```
Cartopy_file/
├── README.md               安装与快速开始
├── pyproject.toml          依赖与打包(uv_build)
├── docs/                   本目录: 概念 / 图种 / 参考三层
├── data/                   cartopy 共用的 Natural Earth 底图缓存(不入库)
├── download_data.py        共用底图预取 + 全项目数据清单检查
├── src/cartopy_file/       共享包: 数据层 / 规格 / 图层 / 出图流程 / 几何工具
├── Myanmar/                缅甸子项目: 3 张图 + config.py + main.py(唯一入口) + 模块 + data/
├── USSR/                   苏联子项目
├── Ukraine/                乌克兰子项目
├── Volga/                  伏尔加河流域子项目: 流域图 + 周边共和国图, 两图共用一套规格
├── AmericaArmy/            演示子项目: 框架用法的最小例子
├── tools/                  仓库工具: check_docs.py / check_geo.py / check_all.py
└── global.py               一次性演示脚本
```

每个子项目的可执行文件**只有一个** `main.py`, 用子命令(`download` / `prepare` / `render` /
`all`)编排流程; 其余 `.py` 都是模块, 只导出 `run()`, 直接运行会报错并指向入口. 每个子项目下的
`map/` 放地图产物(SVG), `text/` 放文字信息产物(geo.json); 同一张图的两个文件 stem 相同,分目录
存放, 都不入库.

## 四层结构

1. **框架层**([`src/cartopy_file/`](../src/cartopy_file)): 可安装的包, 放所有子项目共用的
   能力: 数据源登记,下载,数据集清单,配置模型,图层原语,出图流程,几何工具.
2. **子项目层**([`docs/maps/`](maps)): 一个目录就是一个子项目, 内含 `config.py`(该子项目的
   数据与实例规格),`main.py`(唯一可执行入口),若干模块(下载/派生/绘图)和私有数据目录
   `<子项目>/data/`.
3. **数据集配置**([`config.py`](../Myanmar/config.py) 里的 `DATASETS`): 每个子项目声明自己要用
   哪些数据--从哪下,什么版本,覆盖哪个范围,放哪,怎么校验. 数据准备模块与绘图模块都从
   这里取参数, 不再各写一份.
4. **实例配置**([`config.py`](../Myanmar/config.py) 里的 `SHEETS`): 一张产物就是一个
   `Sheet`(画框/投影/画布/色带/经纬网/地名/文案). 一个脚本可以有多张(伏尔加的两张图).

`config.py` 只放**数值**; 这些值的类型与校验在 [`src/cartopy_file/spec.py`](../src/cartopy_file/spec.py)
(参考页 [`reference/spec.md`](reference/spec.md)). 分开的理由: 类型不随图种变, 配置每个子项目
一份; 新加一个子项目只写 `config.py`, 不用碰共享包.

## 数据流

```
download_data.py ──► data/cartopy/ ─┐
<子项目>/main.py download ──► <子项目>/download_*.py ──► <子项目>/data/raw/ ──┐
<子项目>/main.py prepare  ──► <子项目>/prepare_*.py  ──► <子项目>/data/derived/ ─┴─► config.py ──► runner.render ──┬─► <子项目>/map/<stem>.svg
<子项目>/main.py render   ──► <子项目>/<绘图模块>.py ──────────────────────────────────────────────────────────────┴─► <子项目>/text/<stem>.geo.json
```

下载与派生各是一个模块, 但只由 `main.py` 按子命令调用; 绘图模块同理. 绘图不联网: 数据在首次
准备时下载一次, 之后出图只读本地文件; 要素缺缓存时 cartopy 会在渲染中临时联网, 所以共用底图
要用 `download_data.py` 预取. 详见 [`data-preparation.md`](data-preparation.md).

产物是裁到地图框的纯几何 `.svg`(地图)与 `<stem>.geo.json`(文字信息), 同 stem 分目录, 由脚本
按需生成,不提交; 文字与版面迁到 `miko_svg_editor` 的前端排版, geo.json 提供前端建默认排版
所需的标注/刻度/色标/图例/文案.

## 共享包模块

顶层 `__init__.py` 只重导出纯数据模块(`data` / `datasets` / `sources` / `spec` / `output`);
其余一律按子模块导入: 会拉进 matplotlib/cartopy 的(`geo` / `relief` / `layers` / `runner`)按需
导入, 纯几何工具(`overlap` / `geometry`)也保持子模块形态, 避免数据准备脚本与 `tools/` 被绘图
栈拖慢.

| 模块 | 内容 | 参考页 |
| --- | --- | --- |
| `data` | 数据目录,cartopy/matplotlib 缓存定位,子项目自动发现 | [`reference/data.md`](reference/data.md) |
| `sources` | 外部数据源登记: URL 模板/版本/许可/进图署名 | [`reference/datasets.md`](reference/datasets.md) |
| `fetch` | 下载/续传/重试/魔数校验/解压 | [`reference/datasets.md`](reference/datasets.md) |
| `datasets` | 数据集规格与清单(`Dataset`/`DatasetSet`) | [`reference/datasets.md`](reference/datasets.md) |
| `spec` | 实例规格: 画框/投影/色带/经纬网/地名/文案 | [`reference/spec.md`](reference/spec.md) |
| `geometry` | 几何修复,确定性 GeoJSON 写出,面积/长度/顶点量算(纯几何) | [`reference/geometry.md`](reference/geometry.md) |
| `layers` | 图层原语: 底图/晕渲/经纬网/城市点/geo 收集 | [`reference/layers.md`](reference/layers.md) |
| `runner` | 统一出图流程与回调契约 | [`reference/runner.md`](reference/runner.md) |
| `geo` | 底图裁剪,geo.json(标注/刻度/色标/图例/文案) | [`reference/geo.md`](reference/geo.md) |
| `output` | 唯一的纯几何 SVG 出口 | [`reference/output.md`](reference/output.md) |
| `relief` | 高程读取,配色与山体晕渲,海陆底色 | [`reference/relief.md`](reference/relief.md) |
| `overlap` | 边界重合剪枝(按子模块导入) | [`reference/overlap.md`](reference/overlap.md) |

## 为什么要有共享包

子项目目录里只有 `main.py` 是"从脚本所在目录运行"的可执行文件, 它靠脚本目录在 `sys.path` 上
导入同目录模块与 `config.py`; 共享代码放进已安装的包后普通 `import` 即可, 不必再用
`sys.path.insert` 去操作外层目录. 安装方式见 [README](../README.md) 的"安装"一节.
`config.py` 需要被工具按 `<子项目>.config` 导入; 其余模块由 `main.py` 导入, 不能单独运行.
