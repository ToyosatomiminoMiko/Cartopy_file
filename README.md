# Cartopy_file

四组地图(缅甸、苏联、乌克兰、伏尔加河流域)的 cartopy 绘图脚本, 共用一套可安装的 `cartopy_file` 包. 产物统一
为单个自包含 SVG.

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

产物统一由 [src/cartopy_file/output.py](src/cartopy_file/output.py) 保存: 文字、边界、河流、填色
都是矢量, 汉字以真 `<text>` 写入并把用到的字形裁成字体子集内嵌, 换台机器打开不缺字体、文字
还能选中/复制/检索; 唯一的栅格是山体晕渲, 以 base64 内嵌在同一个 `.svg` 里, 所以产物始终是
单个自包含文件(`--dpi` 只影响晕渲像素密度, 默认 300). 出图不写时间戳、内部 id 固定, 同一份
数据重复运行得到相同内容. 实现与理由见 [docs/reference/output.md](docs/reference/output.md).

`AmericaArmy/` 下的两张 PNG 是早期手工上传的底图素材, 不由任何脚本生成
(`AmericaArmy/main.py` 只画图不落盘), 因此没有对应的 SVG 产物.

## 调整标签位置

地图上的文字标注写死在绘图脚本里, 挪几个数字就要重跑整张图. 标签位置可以改用鼠标调:

```bash
python Volga/volga.py                    # 1. 先出图(慢, 一次就够)
python tools/label_editor.py Volga/volga_basin_topography_etopo2022_lambert_conformal.svg
                                         # 2. 浏览器里拖标签/加标注, Ctrl+S 存布局(快)
python Volga/volga.py                    # 3. 再跑一次, 产物带上手工位置
```

布局存成产物旁边的 `<产物>.labels.json`(与产物一起入库), 出图时自动施加, 所以重跑不会丢手工
调整. 坐标系、字段与实现见 [docs/reference/labels.md](docs/reference/labels.md), 编辑器用法与
常见问题见 [docs/label-editing.md](docs/label-editing.md).

## 字体

字体由 [src/cartopy_file/fonts.py](src/cartopy_file/fonts.py) 统一提供, 各绘图脚本不再单独设
`rcParams`; 在导入 matplotlib 之后调用 `apply_matplotlib_fonts()` 即可:

- 汉字: Noto Sans Mono CJK SC;
- 英文/数字: JetBrainsMonoSlashed-Medium(matplotlib 字体名 `JetBrains Mono Slashed Medium`).

逐字符回退的原理与坑见 [docs/reference/fonts.md](docs/reference/fonts.md).

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
