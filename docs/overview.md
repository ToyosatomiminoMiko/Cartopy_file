# 项目总览

这个仓库是**渲染仓**: 把五组地图(缅甸,苏联,乌克兰,伏尔加河流域,美军基地演示)放在一起,
共用一套可安装的 cartopy 绘图包 `src/cartopy_file/`. 数据的获取/下载/派生/入库不在本仓,
由独立数据项目 `miko_gis_data` 负责; 本仓只读数据根里的 `manifest.json` 与它指向的文件.

## 目录结构

```
Cartopy_file/                 渲染仓(本仓)
├── README.md                 安装与快速开始
├── pyproject.toml            依赖与打包(uv_build)
├── AGENTS.md                 硬规矩
├── docs/                     本目录: 概念 / 图种 / 参考三层
├── src/cartopy_file/         共享包: 数据定位 / 清单 / 规格 / 图层 / 出图流程 / 几何工具
├── Myanmar/                  缅甸子项目: 3 张图 + config.py + main.py(唯一入口) + 绘图模块
├── USSR/                     苏联子项目
├── Ukraine/                  乌克兰子项目
├── Volga/                    伏尔加河流域子项目: 流域图 + 周边共和国图, 两图共用一套规格
├── AmericaArmy/              演示子项目: 框架用法的最小例子
├── tools/                    仓库工具: check_docs.py / check_geo.py / check_all.py / autorun.py
└── global.py                 一次性演示脚本

miko_gis_data/                独立数据项目(不在本仓结构里; 可整体移走)
├── main.py                   唯一入口: check / download / prepare / publish / all
├── src/miko_gis_data/        data / sources / fetch / datasets / ne / manifest / geometry
│   └── regions/<region>/     每个区域一份 config.py(数据集清单) + download_*/prepare_* 脚本
└── data/                     数据根(默认位置): manifest.json + cartopy/ + <region>/{raw,derived}
```

每个子项目的可执行文件**只有一个** `main.py`, 只有 `render` 子命令; 其余 `.py` 都是模块,
只导出 `run()`, 直接运行会报错并指向入口. 每个子项目下的 `map/` 放地图产物(SVG), `text/`
放文字信息产物(geo.json); 同一张图的两个文件 stem 相同,分目录存放, 都不入库.

`miko_gis_data/` 是独立仓库: 它有自己的 `pyproject.toml`,`main.py`,`docs/` 与 `data/`, 不依赖
绘图栈; 本仓的 `.gitignore` 忽略它, 文档里只以文字提到, 不建相对链接(整体移走后链接会断).

## 四层结构

1. **数据项目**(独立仓库 `miko_gis_data`): 下载外部数据到 `<数据根>/<region>/raw/`, 派生到
   `derived/`, 预取共享 Natural Earth 缓存到 `<数据根>/cartopy/`, 最后 `publish`
   `<数据根>/manifest.json`. 它是数据源与版本口径的唯一真源.
2. **共享包**([`src/cartopy_file/`](../src/cartopy_file)): 可安装的包, 放所有子项目共用的
   能力: 数据根/清单定位,实例规格,图层原语,出图流程,底图裁剪与几何工具. 本包不下载任何东西.
3. **子项目层**([`docs/maps/`](maps)): 一个目录就是一个子项目, 内含 `config.py`(该子项目的
   `DATA_GROUP` 与实例规格),`main.py`(唯一可执行入口)和若干绘图模块.
4. **配置**([`config.py`](../Myanmar/config.py)): `DATA_GROUP` 指向数据项目里的区域名
   (manifest 的 group 键), `SHEETS` 声明该子项目要出的图. 数据集清单(从哪下,什么版本,放哪)
   在数据项目的 `regions/<region>/config.py`, 不在本仓.

`config.py` 只放**数值**; 这些值的类型与校验在 [`src/cartopy_file/spec.py`](../src/cartopy_file/spec.py)
(参考页 [`reference/spec.md`](reference/spec.md)). 分开的理由: 类型不随图种变, 配置每个子项目
一份; 新加一个子项目只写 `config.py`, 不用碰共享包.

## 数据流

```
数据项目 miko_gis_data/
  download / prepare ──► <数据根>/<region>/{raw,derived}/ ─┐
  publish            ──► <数据根>/manifest.json ───────────┤
                                                          ▼
渲染仓 Cartopy_file/
  <子项目>/main.py render ──► 绘图模块 ──► catalog_for(DATA_GROUP) ──► runner.render ──┬─► <子项目>/map/<stem>.svg
                                                                                      └─► <子项目>/text/<stem>.geo.json
```

- 数据项目把数据与清单准备好后, 渲染仓用 `catalog_for(DATA_GROUP)` 读 manifest, 得到
  [`Catalog`](reference/catalog.md); 绘图模块用 `Catalog.path(id)` / `Catalog.raw_dir` 拿路径,
  `runner.render` 用 `Catalog` 核对图层就位情况, 并用 `Catalog.citation(sheet.dataset_ids)` 生成
  geo.json 的「数据来源」.
- **渲染不联网**: 数据在数据项目里下载一次, 出图只读本地文件; 共享 Natural Earth 图层缺缓存时
  `runner` 在画图前直接报错并指向数据项目的 `download`, 不会在渲染中临时联网.
- 产物是裁到地图框的纯几何 `.svg`(地图)与 `<stem>.geo.json`(文字信息), 同 stem 分目录, 由脚本
  按需生成,不提交; 文字与版面迁到 `miko_svg_editor` 的前端排版, geo.json 提供前端建默认排版
  所需的标注/刻度/色标/图例/文案.

## 与数据项目的边界

两个仓库**只靠 `manifest.json` 这一份 JSON 契约耦合**:

- 本仓不安装数据项目的 Python 包, 不 import 它的模块; 数据项目也不依赖 cartopy/matplotlib;
- 本仓只读数据根: `manifest.json`,`<数据根>/<region>/` 下的文件, 以及 `<数据根>/cartopy/`
  这个 Natural Earth 共享缓存;
- 数据根的定位两边读同一个环境变量 `CARTOPY_FILE_DATA`, 谁都不猜对方的绝对路径;
- 清单的字段与版本由 [reference/manifest.md](reference/manifest.md) 定义. 改字段/改版本必须
  两个仓库同步: 数据项目 `manifest.py` 的写出一侧, 本仓 `catalog.py` 的读取一侧;
- 数据源登记(URL,版本,许可,署名)的权威在数据项目的 `src/miko_gis_data/sources.py`; 本仓
  产物里的「数据来源」由 manifest 里的 `source` 字段复算, 不手写.

## 共享包模块

顶层 `__init__.py` 只重导出纯数据/纯标准库模块(`data` / `catalog` / `spec` / `output`);
其余一律按子模块导入: 会拉进 matplotlib/cartopy 的(`geo` / `relief` / `layers` / `runner`)
按需导入, 纯几何工具(`overlap`)也保持子模块形态, 避免 `tools/` 被绘图栈拖慢.

| 模块 | 内容 | 参考页 |
| --- | --- | --- |
| `data` | 数据根,manifest 与 cartopy/matplotlib 缓存定位,子项目自动发现 | [`reference/data.md`](reference/data.md) |
| `catalog` | 读 manifest: 按 id 取路径,判断就位,折署名 | [`reference/catalog.md`](reference/catalog.md) |
| `spec` | 实例规格: 画框/投影/色带/经纬网/地名/文案 | [`reference/spec.md`](reference/spec.md) |
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
