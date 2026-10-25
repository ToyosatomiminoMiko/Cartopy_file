# Cartopy_file

## 安装

依赖声明在 `pyproject.toml`，共享代码在 `src/cartopy_file/` 包里。用 uv 同步环境即可：

```bash
uv sync
```

如果已有可用的 `.venv`、只想把项目本身以可编辑模式装进去（不重建环境）：

```bash
uv pip install -e .
```

调试用的 ipykernel / debugpy 放在 `dev` 依赖组里，`uv sync` 默认会一并安装。

## 文档

本文件只讲安装、数据准备、出图和字体的总流程。每个脚本/模块的设计取舍、投影参数、
数据来源、坑和运行前置条件见 [`docs/`](docs/README.md)(一个源码文件一页)：

- 地图: [缅甸全境地形](docs/Myanmar/myanmar.md) · [缅甸行政区划](docs/Myanmar/myanmar_admin.md) · [掸邦/特区](docs/Myanmar/northern_shan.md) · [苏联](docs/USSR/ussr.md) · [乌克兰](docs/Ukraine/ukraine.md)
- 共享包: [cartopy_file 总览](docs/cartopy_file/index.md) · [数据与缓存](docs/cartopy_file/data.md) · [字体](docs/cartopy_file/fonts.md) · [SVG 出图](docs/cartopy_file/output.md) · [边界剪枝](docs/cartopy_file/overlap.md) · [地形工具](docs/cartopy_file/relief.md)
- 数据准备: [共用 Natural Earth 底图](docs/download_data.md) · [缅甸高程](docs/Myanmar/download_etopo.md) · [掸邦特区边界](docs/Myanmar/download_regions.md) · [缅甸行政区](docs/Myanmar/prepare_admin_data.md) · [苏联高程](docs/USSR/download_etopo.md) · [乌克兰数据](docs/Ukraine/download_data.md) · [缅甸 stride1 分块下载](docs/stride1_chunked.md)

## 数据与缓存

绘图脚本**不会**在出图时联网下载：所有数据都在首次准备时下载一次，之后就只读本地文件。
本机 `/home` 是只读挂载，用户目录里的默认缓存写不进去，所以缓存统一放在仓库内
（已被 `.gitignore` 忽略，不会进 git）：

| 位置 | 内容 |
| --- | --- |
| `data/cartopy/` | cartopy 内置 Natural Earth 底图，全项目共用（海岸线、国界、河流、湖泊） |
| `Myanmar/data/` | ETOPO 缅甸高程、Natural Earth 10m 国界/河流、行政区 GeoJSON、OSM 特区边界 |
| `USSR/data/` | ETOPO 苏联高程、Natural Earth 国界 |
| `Ukraine/data/` | ETOPO 乌克兰高程、Natural Earth 国界、GADM 4.1 乌克兰行政区、OCHA 2021 GCA/NGCA 分区及派生边界、OSM 第聂伯河干流与梯级水库、OSM 德涅斯特河与德左（PMR）参照面、南布格河/顿河下游补段（ODbL） |
| `AmericaArmy/data.geojson` | 基地点位，仓库自带 |

一次性准备（每条命令都是"文件已存在就跳过"，重复执行不会重新下载）：

```bash
python download_data.py                                              # 全项目共用底图
python Myanmar/download_etopo.py                                     # 缅甸全境高程 + 10m 国界
python Myanmar/download_etopo.py --region northern_shan --stride 1   # 掸邦放大图高程
python Myanmar/download_regions.py                                   # 掸邦特区/自治区域边界(OSM)
python Myanmar/prepare_admin_data.py                                 # 缅甸省邦级行政区 GeoJSON
python USSR/download_etopo.py                                        # 苏联高程 + 国界
python Ukraine/download_data.py                                      # 乌克兰高程/行政区/接触线 + OSM 第聂伯河、德涅斯特河/德左边界、南布格河/顿河下游, 并派生 1991/2014/2022 边界
```

只想确认数据是否齐全（不联网、不下载）：

```bash
python download_data.py --check
```

只有换机器或重新 clone 时才需要重跑上面的命令；同一份数据反复出图不会再下载。
需要把共用缓存放到别的可写磁盘时，设置环境变量 `CARTOPY_FILE_DATA=/path/to/data`
（定位逻辑见 [docs/cartopy_file/data.md](docs/cartopy_file/data.md)）。

## 出图

所有地图产物统一输出 **SVG**, 不再输出 PNG:

| 脚本 | 产物(与脚本同目录) |
| --- | --- |
| `Myanmar/myanmar.py` | `myanmar_topography_etopo2022_lambert_conformal.svg` |
| `Myanmar/myanmar_admin.py` | `myanmar_administrative_divisions_bilingual.svg` |
| `Myanmar/northern_shan.py` | `northern_shan_topography_etopo2022_lambert_conformal.svg` |
| `USSR/ussr.py` | `ussr_topography_etopo2022_lambert_azimuthal.svg` |
| `Ukraine/ukraine.py` | `ukraine_borders_1991_2014_2022_lambert_conformal.svg` |

统一入口是 [src/cartopy_file/output.py](src/cartopy_file/output.py): 各脚本在
`apply_matplotlib_fonts()` 之后调用 `apply_svg_output()`, 保存时用 `save_svg()` 而不是
`fig.savefig()`。文字、边界、河流、填色都是矢量, 汉字以字形路径写入, 换台机器打开不会缺
字体; 唯一的栅格是山体晕渲, 以 base64 内嵌在同一个 `.svg` 里, 所以产物始终是单个自包含
文件(`--dpi` 只影响晕渲像素密度, 默认 300)。出图不写时间戳、内部 id 固定, 同一份数据
重复运行得到相同内容。实现与理由见 [docs/cartopy_file/output.md](docs/cartopy_file/output.md)。

`AmericaArmy/` 下的两张 PNG 是早期手工上传的底图素材, 不由任何脚本生成
(`AmericaArmy/main.py` 只画图不落盘), 因此没有对应的 SVG 产物.

## 字体

所有图表的字体由 [src/cartopy_file/fonts.py](src/cartopy_file/fonts.py) 统一提供，
各绘图脚本不再单独设置 `rcParams`：

- 汉字: Noto Sans Mono CJK SC
- 英文/数字: JetBrainsMonoSlashed-Medium (matplotlib 字体名 `JetBrains Mono Slashed Medium`)

在导入 matplotlib 之后调用 `apply_matplotlib_fonts()` 即可；中英文如何按字符自动
切换、为什么不能用 `font.sans-serif` 等细节见 [docs/cartopy_file/fonts.md](docs/cartopy_file/fonts.md)。
