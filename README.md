# Cartopy_file

四组地图(缅甸、苏联、乌克兰、伏尔加河流域)的 cartopy 绘图脚本, 共用一套可安装的 `cartopy_file` 包. 产物统一
为单个自包含的**纯几何** SVG: 只有地理图形, 不含文字、图例、色标、标题与刻度文字; 文字与版面由
`miko_svg_editor` 的前端排版接管(迁移中).

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

| 脚本 | 产物(与脚本同目录) |
| --- | --- |
| `Myanmar/myanmar.py` | `myanmar_topography_etopo2022_lambert_conformal.svg` |
| `Myanmar/myanmar_admin.py` | `myanmar_administrative_divisions_bilingual.svg` |
| `Myanmar/northern_shan.py` | `northern_shan_topography_etopo2022_lambert_conformal.svg` |
| `USSR/ussr.py` | `ussr_topography_etopo2022_lambert_azimuthal.svg` |
| `Ukraine/ukraine.py` | `ukraine_borders_1991_2014_2022_lambert_conformal.svg` |
| `Volga/volga.py` | `volga_basin_topography_etopo2022_lambert_conformal.svg`(流域图)<br>`volga_basin_republics_topography_etopo2022_lambert_conformal.svg`(周边共和国图) |

每张图的前置数据、`--stride` / `--dpi` / `--show` 选项和设计取舍见
[docs/index.md](docs/index.md) 里的图种页.

产物统一由 [src/cartopy_file/output.py](src/cartopy_file/output.py) 保存: 只是一张纯几何地图, 海岸线、
国界、河流、湖泊与填色都是矢量, 不含文字、图例、色标、标题和刻度文字. 文字与版面(标题/图例/色标/
刻度/注/来源)由 `miko_svg_editor` 的前端排版接管, 迁移尚未完成. 唯一的栅格是山体晕渲, 以 base64
内嵌在同一个 `.svg` 里, 所以产物始终是单个自包含文件(`--dpi` 只影响晕渲像素密度, 默认 300). 出图
不写时间戳、内部 id 固定, 同一份数据重复运行得到相同内容. 实现与理由见
[docs/reference/output.md](docs/reference/output.md).

`AmericaArmy/` 下的两张 PNG 是早期手工上传的底图素材, 不由任何脚本生成
(`AmericaArmy/main.py` 只画图不落盘), 因此没有对应的 SVG 产物.

**本轮只改脚本、未重出产物**: 仓内现有的 7 张 SVG 仍是改造前"带文字/图例/色标/标题"的版本,
保留给 `miko_svg_editor` 迁移时抽取地名等元数据用; 等前端排版接管后再统一重出纯几何产物.

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
