# Cartopy_file

四组地图(缅甸、苏联、乌克兰、伏尔加河流域)的 cartopy 绘图脚本, 共用一套可安装的 `cartopy_file` 包. 每张图
产出两个文件: 裁到地图框的**纯几何底图** `.svg`(只有地理图形, 不含文字、图例、色标、标题与刻度文字)和
同名 `.geo.json`(地图框、经纬刻度、初始标注候选、色标、图例与默认文案). 文字与版面由
`miko_svg_editor` 的前端排版接管, geo.json 让前端知道每个地名该放在哪、刻度/图例/色标用什么口径.

## 安装

依赖声明在 `pyproject.toml`, 共享代码在 `src/cartopy_file/`. 用 uv 同步环境:

```bash
uv sync                # 新建/同步 .venv, 默认包含 dev 组
uv pip install -e .    # 已有 .venv, 只把本项目以可编辑模式装进去
```

调试用的 ipykernel / debugpy 在 `dev` 依赖组里, `uv sync` 会一并安装.

## 准备数据

绘图脚本**不会**在出图时联网: 数据在首次准备时下载一次, 之后只读本地文件. 最少要跑:

```bash
python download_data.py           # 全项目共用的 Natural Earth 底图, 放到 data/cartopy/
python download_data.py --check   # 只检查不下载; 有缺失时退出码 1 并打印准备命令
```

各图种自己的数据(ETOPO 高程、行政区、OSM 边界等)由各自的脚本准备, 命令与数据清单见
[docs/data-preparation.md](docs/data-preparation.md). 只有换机器或重新 clone 时才需要重跑;
已存在的文件不会重复下载.

## 出图

每张图除 `.svg` 底图外, 还写一个同名的 `<stem>.geo.json`, 前端(`miko_svg_editor`)用它建默认排版.

| 脚本 | 产物(与脚本同目录) |
| --- | --- |
| `Myanmar/myanmar.py` | `myanmar_topography_etopo2022_lambert_conformal.svg` |
| `Myanmar/myanmar_admin.py` | `myanmar_administrative_divisions_bilingual.svg` |
| `Myanmar/northern_shan.py` | `northern_shan_topography_etopo2022_lambert_conformal.svg` |
| `USSR/ussr.py` | `ussr_topography_etopo2022_lambert_azimuthal.svg` |
| `Ukraine/ukraine.py` | `ukraine_borders_1991_2014_2022_lambert_conformal.svg` |
| `Volga/volga.py` | `volga_basin_topography_etopo2022_lambert_conformal.svg`(流域图)<br>`volga_basin_republics_topography_etopo2022_lambert_conformal.svg`(周边共和国图) |

每张图的前置数据、可用选项与设计取舍见 [docs/index.md](docs/index.md) 里的图种页.

产物由 [src/cartopy_file/geo.py](src/cartopy_file/geo.py) 统一保存: SVG 是纯几何底图, 海岸线、国界、
河流、湖泊与填色都是矢量, 不含文字、图例、色标、标题和刻度文字; 保存时只把根标签的 viewBox 裁到
地图框. 同名 `.geo.json` 按 `miko_svg_editor` 的 `mapdoc-geo` **v2** 契约写: `base`(底图 sha256/
viewBox/尺寸)、`graticule`(经纬刻度)、`labels`(地名候选: id/role/文字/坐标/锚点/字号/顺序)、
`relief`(色标)、`legend`(图例)与 `suggestions`(标题/副标题/注/来源). 标注样式(颜色/描边/斜体/
字重/字距/行高)不在地图产物里, 由 `miko_svg_editor/src/config/text-style.ts` 的角色表统一决定;
旧 v1 产物已被版本校验拒绝, 需要重新生成. 字段与口径见
[docs/reference/geo.md](docs/reference/geo.md). 唯一的栅格是山体晕渲, 以 base64 内嵌在同一个
`.svg` 里, 所以底图始终是单个自包含文件(`--dpi` 只影响晕渲像素密度, 默认 300). 出图不写时间戳、
内部 id 固定, 同一份数据重复运行得到相同内容. 实现与理由见
[docs/reference/output.md](docs/reference/output.md).

产物不入库: `.gitignore` 忽略 `*.svg` / `*.geo.json` / `*.png`, 仓内不放成品文件, 需要时按上表跑
脚本生成. 与前端排版的衔接(契约字段、字体嵌入等)见 `miko_svg_editor` 的
`docs/CARTOPY-MIGRATION.md`.

`AmericaArmy/` 只剩早期演示脚本 `main.py` 与基地点位 `data.geojson`, 早期手工上传的两张底图
素材已删除; `main.py` 只画图不落盘, 不在维护范围.

## 缓存

本机 `/home` 是只读挂载, 缓存统一放在仓库内(`data/cartopy/` 与各图种 `data/`, 均不入库). 需要
放到别的可写磁盘时设 `CARTOPY_FILE_DATA=/path/to/data`, 定位逻辑见
[docs/reference/data.md](docs/reference/data.md).

## 文档

[docs/index.md](docs/index.md) 是唯一入口: 概念(总览/数据/扩展)、图种(每张图一页)、参考(共享
模块 API)三层. 文档与注释的写法见 [docs/conventions.md](docs/conventions.md), 提交前跑
`python tools/check_docs.py`.

`global.py` 与 `AmericaArmy/main.py` 是一次性演示脚本, 没有对应文档页.

## 许可

代码以 GNU GPL v3 发布, 见 [LICENSE](LICENSE). 地图数据来自 Natural Earth、NOAA ETOPO 2022、
GADM、OpenStreetMap 与 OCHA HDX, 各自的许可与署名要求见
[docs/data-preparation.md](docs/data-preparation.md).
