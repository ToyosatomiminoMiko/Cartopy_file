# Cartopy_file

五组地图(缅甸,苏联,乌克兰,伏尔加河流域,美军基地演示)的 cartopy 渲染仓. 每个子项目一个
目录, 目录里的 `config.py` 声明该子项目用哪个数据区域(`DATA_GROUP`)与每张图的规格
(画框/投影/色带/经纬网/文案), 出图流程与图层原语都在共享包 `src/cartopy_file/`.

这仓分两层: **数据**由独立数据项目 `miko_gis_data` 负责 -- 只做下载/入库/解压, 把原始数据
原样放进数据根并写一份 `manifest.json`; **清洗/派生/裁剪**与出图在本仓完成. 本仓读清单与它
指向的原始文件, 用 `<子项目>/main.py prepare` 生成 `build/` 下的派生 GeoJSON, 再
`render` 出图; 全程**不联网**. 两个仓库靠这份 JSON 契约耦合, 互不 import. 数据项目可以单独
移走, 换位置时改本仓根目录 `config.toml` 的 `data_root` 即可.

每张图产出两个文件: 地图(裁到地图框的**纯几何底图**, 只有地理图形, 不含文字,图例,色标,标题与
刻度文字)写到 `<子项目>/map/<stem>.svg`, 文字信息(地图框,经纬刻度,初始标注候选,色标,图例与
默认文案)写到 `<子项目>/text/<stem>.geo.json`. 同一张图的 `.svg` 与 `.geo.json` stem 相同,
分目录存放. 文字与版面由 `miko_svg_editor` 的前端排版接管, geo.json 让前端知道每个地名该
放在哪, 刻度/图例/色标用什么口径.

## 结构

```
Cartopy_file/
├── README.md               安装,数据准备,派生,出图
├── pyproject.toml          依赖与打包(uv_build)
├── AGENTS.md               必须做 / 禁止做的硬规矩
├── docs/                   概念 / 图种 / 参考三层
├── src/cartopy_file/       共享包
│   ├── data.py             数据根 / manifest / cartopy 缓存定位
│   ├── catalog.py          读 manifest,给出 Catalog / DatasetView / SourceInfo
│   ├── geometry.py         派生共用几何工具(修复/确定性 GeoJSON/椭球量算)
│   ├── spec.py             实例规格(画框/投影/色带/经纬网/地名/文案/产物目录)
│   ├── layers.py           图层原语(底图/晕渲/经纬网/城市点/geo 收集)
│   ├── runner.py           统一出图流程与回调契约
│   ├── geo.py              底图裁剪与 geo.json
│   ├── output.py           纯几何 SVG 出口
│   ├── relief.py           高程,晕渲,海陆底色
│   └── overlap.py          边界重合剪枝
├── Myanmar/                缅甸子项目: 3 张图 + prepare.py(派生)
├── USSR/                   苏联子项目(无派生数据)
├── Ukraine/                乌克兰子项目: prepare.py(派生) + 1 张图
├── Volga/                  伏尔加河流域子项目: 流域图 + 周边共和国图 + prepare.py(派生)
├── AmericaArmy/            演示子项目: 框架用法的最小例子
├── tools/                  check_docs.py / check_geo.py / check_all.py / autorun.py
└── global.py               一次性演示脚本
```

每个子项目只有 `config.py`,`main.py` 与若干模块: `main.py` 是**唯一可执行文件**, 有派生数据的
子项目有 `prepare`(生成 `<子项目>/build/` 下的派生 GeoJSON)与 `render`(出图)两个子命令,
没有派生数据的子项目只有 `render`; 其余 `.py` 只导出 `run()`, 直接运行会报错并指向入口.
`build/` 是可丢弃的中间产物(已在 `.gitignore`), 删掉后重跑 `prepare` 即可重建, 不触发下载.

## 安装

依赖声明在 `pyproject.toml`, 共享代码在 `src/cartopy_file/`. 需要 Python 3.15+
(`.python-version` 固定为 3.15). 用 uv 同步环境:

```bash
uv sync                # 新建/同步 .venv, 默认包含 dev 组
uv pip install -e .    # 已有 .venv, 只把本项目以可编辑模式装进去
```

调试用的 ipykernel / debugpy 在 `dev` 依赖组里, `uv sync` 会一并安装.

首次 clone 后还要启用提交钩子(每个 clone 各做一次, 钩子把暂存文件里的全角标点转半角):

```bash
git config --local core.hooksPath .githooks
```

钩子的原理与映射表见 [docs/conventions.md](docs/conventions.md) 的"标点与提交钩子"一节.

## 数据准备

下载/入库/解压在独立数据项目 `miko_gis_data` 里完成, 产物是数据根里的原始文件与
`manifest.json`; 它**不做派生**. 到数据项目根目录执行(首次 clone 后 `uv sync` 一次; 下面的
命令假设它与本仓平级, 即 `../miko_gis_data`, 放在别处就换成实际路径):

```bash
cd ../miko_gis_data
uv sync
python main.py check      # 只检查原始数据是否齐全/版本相符, 不联网; 有缺失退出码 1
python main.py download   # 预取共享 Natural Earth 图层 + 下载/解压各区域原始数据(已存在就跳过)
python main.py publish    # 重建 <数据根>/manifest.json 给渲染仓读
python main.py all        # 依次 download -> publish -> check
```

常用选项: `--group {all,america_army,myanmar,ukraine,ussr,volga}` 只处理一个区域;
`download` 另有 `--region/--stride/--force/--skip-regions/--skip-basin`, 含义见
`python main.py <子命令> --help`. `publish --check` 只比较清单与配置, 不写盘.

数据根默认是数据项目里的 `data/`. 渲染仓只认一个来源: 仓根 `config.toml` 的 `data_root`
(本机配置, 不进 git). 数据项目在本仓之外, 所以本机只做一次配置, 之后照常出图:

```toml
# <仓根>/config.toml
data_root = "<数据项目>/data"
```

数据根布局: `manifest.json`(清单契约), `cartopy/`(全项目共用的 Natural Earth 缓存),
`<region>/raw/`(各区域的原始数据, region 就是 `DATA_GROUP` 的取值). 清单只登记原始数据,
没有 `kind=derived` 条目; 清单格式与字段见
[docs/reference/manifest.md](docs/reference/manifest.md), 目录约定与数据源见
[docs/data-preparation.md](docs/data-preparation.md).

`raw/` 只放下载原样(解压目录也在这里, 永不改写), 都相对 `<数据根>/<region>/` 定位, 清单里的
`dest`/`files` 也是这个口径. 数据与清单都不进 git: `**/data` 与 `/config.toml` 已在
`.gitignore`, 换机器后重跑上面的准备命令即可恢复.

## 派生数据

数据根里只有原始数据, 没有派生 GeoJSON; 清洗/裁剪/拼装在本仓各自子项目的 `prepare.py` 里完成. 首次出图
前跑一次(数据已就位时很快, 不联网):

```bash
python Myanmar/main.py prepare    # -> Myanmar/build/*.geojson
python Ukraine/main.py prepare    # -> Ukraine/build/*.geojson(12 份)
python Volga/main.py prepare      # -> Volga/build/*.geojson; --skip-basin 跳过流域派生
```

苏联与美军基地演示没有派生数据, 不用 prepare. 派生产物是图种口径的中间结果, 不在数据根里,
也不登记进 manifest; 删掉 `build/` 重跑 `prepare` 即可恢复. 流程与分工见
[docs/reference/prepare.md](docs/reference/prepare.md).

## 出图

每张图除 `.svg` 底图外, 还在对应子项目的 `text/` 下写同 stem 的 `<stem>.geo.json`,
前端(`miko_svg_editor`)用它建默认排版.

| 入口命令 | 地图(产物在 `<子项目>/map/`) |
| --- | --- |
| `python Myanmar/main.py render --sheet myanmar` | `myanmar_topography_etopo2022_lambert_conformal.svg` |
| `python Myanmar/main.py render --sheet myanmar-admin` | `myanmar_administrative_divisions_bilingual.svg` |
| `python Myanmar/main.py render --sheet northern-shan` | `northern_shan_topography_etopo2022_lambert_conformal.svg` |
| `python USSR/main.py render` | `ussr_topography_etopo2022_lambert_azimuthal.svg` |
| `python Ukraine/main.py render` | `ukraine_borders_1991_2014_2022_lambert_conformal.svg` |
| `python Volga/main.py render` | `volga_basin_topography_etopo2022_lambert_conformal.svg`(流域图)<br>`volga_basin_republics_topography_etopo2022_lambert_conformal.svg`(周边共和国图) |
| `python AmericaArmy/main.py render` | `america_army_bases.svg`(框架用法演示, 定点位) |

出图前先确认该子项目的派生数据已在 `build/` 里(没有跑过就按上一节跑 `prepare`); 没有派生
数据的子项目直接 render. 不给 `--sheet` 时出该子项目的全部图(`Volga`,`Myanmar` 都是如此).
`render` 通用选项是
`--dpi`(内嵌晕渲像素密度)与 `--show`(保存后弹窗); 有 ETOPO 数据的图种另有
`--stride`(指定采样步长, 缺省自动挑分辨率最高的), 多图子项目另有 `--sheet`. 每张图的
前置数据,可用选项与设计取舍见 [docs/index.md](docs/index.md) 里的图种页.

产物由 [src/cartopy_file/geo.py](src/cartopy_file/geo.py) 统一保存: SVG 是纯几何底图,
海岸线,国界,河流,湖泊与填色都是矢量, 不含文字,图例,色标,标题和刻度文字; 保存时只把根标签
的 viewBox 裁到地图框. 文字信息由同一个入口写到 `<子项目>/text/<stem>.geo.json`, 按
`miko_svg_editor` 的 `mapdoc-geo` **v2** 契约写: `base`(底图 sha256/
viewBox/尺寸),`graticule`(经纬刻度),`labels`(地名候选: id/role/文字/坐标/锚点/顺序),
`relief`(色标),`legend`(图例)与 `suggestions`(标题/副标题/注/来源). 标注样式(字号/颜色/
描边/斜体/字重/字距/行高)不在地图产物里, 由 `miko_svg_editor/src/config/text-style.ts` 的
角色表统一决定; 字号是前端的纸张 mm 设计值, 与底图尺寸, 地图缩放都无关, 生成端不提供也不
推导任何样式数据; geo.json 只接受 v2 契约, 版本校验会拒绝其他版本, 不符时要重新生成. 字段与口径见
[docs/reference/geo.md](docs/reference/geo.md). 唯一的栅格是山体晕渲, 以 base64 内嵌在同一个
`.svg` 里, 所以底图始终是单个自包含文件(`--dpi` 只影响晕渲像素密度, 默认 300). 出图不写
时间戳, 内部 id 固定, 同一份数据重复运行得到相同内容. 实现与理由见
[docs/reference/output.md](docs/reference/output.md).

产物不入库: `.gitignore` 忽略 `*.svg` / `*.geo.json` / `*.png`, 仓内不放成品文件, 需要时按
上表命令生成. 与前端排版的衔接(契约字段,字体嵌入等)见 `miko_svg_editor` 的
`docs/CARTOPY-MIGRATION.md`.

`AmericaArmy/` 是**框架用法的最小演示**: 一个 `config.py`(本地点位 + 一个 Sheet +
`DATA_GROUP`),一个 `main.py`(唯一入口)加一个 `america_army.py`(一对 draw/collect 回调),
走和正式图种完全相同的出图流水线, 数据只有共享 Natural Earth 图层, 产物是
`AmericaArmy/map/america_army_bases.svg` 与 `AmericaArmy/text/america_army_bases.geo.json`
(同 stem 分目录). 想新增子项目时从这个目录抄结构, 见 [docs/add-map.md](docs/add-map.md).

## 缓存

缓存统一放在仓库或数据根里, 不依赖 HOME:

| 位置 | 内容 | 谁维护 |
| --- | --- | --- |
| `<数据根>/cartopy/` | Natural Earth 共享底图缓存 | 数据项目 `download` 预取 |
| `<仓根>/data/.mplcache` | matplotlib 的 `MPLCONFIGDIR` | 渲染仓 `prepare_matplotlib_env()` |

`<仓根>/data/` 只是渲染仓自己的可写缓存目录, **不是数据根**; 数据根只由 `config.toml` 指定.
定位逻辑见 [docs/reference/data.md](docs/reference/data.md).

## 文档

[docs/index.md](docs/index.md) 是唯一入口: 概念(总览/数据/扩展),图种(每张图一页),参考(共享
模块 API)三层. 文档与注释的写法见 [docs/conventions.md](docs/conventions.md), 提交前跑
`uv run python tools/check_all.py`(会自动跑 `tools/check_docs.py`).

`global.py` 是一次性演示脚本, 没有对应文档页. 数据项目 `miko_gis_data` 是另一个仓库, 本仓
只在文档里用文字提它, 不链接它的文件.

## 许可

代码以 GNU GPL v3 发布, 见 [LICENSE](LICENSE). 地图数据来自 Natural Earth,NOAA ETOPO 2022,
GADM,HydroSHEDS,OpenStreetMap 与 OCHA HDX, 各自的许可与署名要求见
[docs/data-preparation.md](docs/data-preparation.md).
