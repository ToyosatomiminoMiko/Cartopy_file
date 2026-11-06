# 数据准备与缓存

所有数据都在首次准备时下载一次, 之后就只读本地文件; 绘图脚本本身不联网. 本页说明数据放在
哪、从哪来、用什么命令准备、怎么检查.

## 目录与缓存

| 位置 | 内容 | 谁维护 |
| --- | --- | --- |
| `data/cartopy/` | cartopy 内置 Natural Earth 底图, 全项目共用 | 根目录 `download_data.py` |
| `<子项目>/data/raw/` | 该子项目下载原样: ETOPO NetCDF、GADM/OSM 原始 JSON、Natural Earth 旧副本 | 该子项目的 `download_*.py` |
| `<子项目>/data/derived/` | 由脚本加工出来的: 解压目录、生成的边界 GeoJSON | 该子项目的 `prepare_*.py` |
| `AmericaArmy/data.geojson` | 基地点位, 仓库自带 | — |

`raw` 与 `derived` 分开的理由: 前者是一次下载、永不改写的原始资产, 后者可以随时删掉重算
(删它不会触发重新联网). 因此模块也按职责拆开, 各只做一件事:

- `download_*.py`: 只把数据下载/解压进 `raw/`, 不加工; 已存在就跳过;
- `prepare_*.py`: 只读 `raw/`、只写 `derived/`, 不联网; 每次运行都全量重建;
- 这些模块**不是可执行文件**: 每个子项目只有一个入口 `<子项目>/main.py`, 用 `download` /
  `prepare` 子命令调用它们, 模块之间不 import 对方的私有函数;
- 一个子项目没有派生需求时(缅甸的 ETOPO、苏联的高程)就没有 `prepare_*.py`.

`**/data` 在 `.gitignore` 里, 数据不随仓库提交; 换机器或重新 clone 后重跑准备命令即可恢复.
唯一入库的数据文件是 `AmericaArmy/data.geojson`.

本机 `/home` 是只读挂载, cartopy/matplotlib 的默认缓存目录不可写, 所以缓存统一放在仓库内.
需要把共用缓存放到别的可写磁盘时设 `CARTOPY_FILE_DATA=/path/to/data`; 定位逻辑与各环境变量
见 [`reference/data.md`](reference/data.md).

## 数据源与许可

外部数据源全部登记在 [`src/cartopy_file/sources.py`](../src/cartopy_file/sources.py): URL 模板、
版本、许可、进图署名都只写一次, 子项目只引用 id. 新增数据源改那一个文件.

| id | 数据集 | 版本 | 用途 | 许可 |
| --- | --- | --- | --- | --- |
| `natural-earth` | Natural Earth(10m / 110m) | 5.1.1 | 海岸线、国界、河流、湖泊、陆地、海洋 | public domain |
| `etopo-2022` | NOAA ETOPO 2022(15 弧秒) | v1 | 地形高程 | 美国联邦政府作品, public domain |
| `gadm-4.1` | GADM | 4.1 | 缅甸/乌克兰/俄罗斯一级行政区 | 学术与非商业用途免费, 商用需授权 |
| `openstreetmap` | OpenStreetMap(Overpass 快照) | 无版本号 | 特区边界、乌克兰河流/水库、德左边界 | ODbL 1.0 |
| `ocha-hno-2021` | OCHA HDX 2021 HNO GCA/NGCA | 2021 | 乌克兰顿巴斯接触线 | 按其发布页的许可与署名要求 |
| `hydrobasins` | HydroSHEDS(HydroBASINS) | v1c | 伏尔加河流域边界 | 免费, 需按发布页署名 |

引用产物时请按上表署名数据来源. 产物 geo.json 的 `suggestions.source` 就是由这份登记自动
生成的(每个数据源一条, 带发布页 URL), 不再手写.

### 版本号怎么钉

版本号写在 URL 或文件名里的(GADM `gadm41_*`、ETOPO `ETOPO_2022_v1_15s`、HydroBASINS `v1c`)
直接记录版本字符串. **Natural Earth 是唯一例外**: S3 下载地址不带版本号, 换版会原地覆盖
同名文件, 所以额外用缓存里的 `*.VERSION.txt` 校验(`--check` 会逐字比对, 不符即报「版本不符」),
并在确实停在旧版本时把版本显式钉在 `Dataset.version` 上(缅甸的河流副本是 5.0.0, 换版会改变
河网几何). 细节见 [`reference/datasets.md`](reference/datasets.md).

## 准备命令总表

下载命令"文件已存在就跳过", 重复执行不会重新下载; 派生命令每次都重建(不联网). 命令都从子项目的
唯一入口 `main.py` 发出: 先 `download`, 再 `prepare`; 出图是同一个入口的 `render`.

| 命令 | 产物 | 什么时候需要 |
| --- | --- | --- |
| `python download_data.py` | `data/cartopy/` 共用底图 | 每台机器一次 |
| `python Myanmar/main.py download` | 缅甸 ETOPO(stride=2, 掸邦 stride=1) 与 OSM 特区边界/国界 | 缅甸首次 |
| `python Myanmar/main.py prepare` | `Myanmar/data/derived/myanmar_admin1.geojson` 等 | 缅甸行政区图 |
| `python USSR/main.py download` | 苏联 ETOPO(默认 stride=8) | 苏联图 |
| `python Ukraine/main.py download` | `Ukraine/data/raw/` 全部原始数据 | 乌克兰图首次 |
| `python Ukraine/main.py prepare` | `Ukraine/data/derived/` 边界/水系 GeoJSON | 原始数据就位后 |
| `python Volga/main.py download` | `Volga/data/raw/` 原始数据 | 伏尔加河流域图首次 |
| `python Volga/main.py prepare` | `Volga/data/derived/` 行政区/流域/国界 GeoJSON | 原始数据就位后 |

只想备其中一部分时用子命令选项: 缅甸 `download --region {all,myanmar,northern-shan} --stride N`,
伏尔加 `download` / `prepare --skip-basin`(缺 HydroBASINS 时), 乌克兰与伏尔加 `download --check`
只检查不下载. 出图命令与可用选项见各图种页的"运行"一节.

想确认数据是否齐全(不联网、不下载):

```bash
python download_data.py --check   # 全部就位退出码 0, 有缺失退出码 1 并给出准备命令
```

清单不再手写: `--check` 逐个导入各子项目目录里的 `config.py`, 读出它声明的 `DATASETS`
(`DatasetSet`)后逐项核对. 所以:

- 新增子项目或新数据, 只改该子项目的 `config.py`, 不用回来改 `download_data.py`;
- 「就位」以项目缓存为准: 只有 `~/.local/share/cartopy` 里有不算就位(换机器就没了);
- 版本不符、只在旧缓存里, 都会算失败并打印原因.

## ETOPO 下载

各图种都用同一套 NOAA ERDDAP 下载方式(实现走 [`cartopy_file.fetch`](../src/cartopy_file/fetch.py),
下载范围来自各自 `config.py`):

- 不直接打开 NOAA OPeNDAP 的几十个瓦片(要在经度上跨瓦片拼接, 还要处理 0°/360° 与
  -180°/180° 两套经度约定), 改为向 ERDDAP 请求一次已裁剪、重采样好的区域 NetCDF,
  绘图时只读一个文件;
- ERDDAP 的经度是 0~360°, 跨 180° 的区域(如苏联图)要把负经度 +360;
- 区域范围要覆盖**投影后的矩形画框**四角, 而不是只按经纬度画框下载, 否则兰勃特投影画框的
  角上会露出没有高程数据的空白. 这个范围在 `config.py` 里由 `Sheet.extent.padded(...)` 推出,
  与绘图用的画框是同一个数据源, 出图时 `runner` 还会核对是否盖住;
- 默认步长按图幅大小选: 缅甸全境 `stride=2`(30 弧秒, 约 34 MB), 掸邦放大图 `stride=1`
  (15 弧秒), 苏联 `stride=8`(2 弧分, 约 45 MB), 乌克兰 `stride=2`;
- 断点续传: 中断留下 `.part` 文件, 再次运行尝试续传; 若服务器忽略 Range 直接返回完整数据,
  脚本会清空 `.part` 从头写, 避免拼出坏文件;
- 校验: ERDDAP 在子集过大或参数非法时会返回 HTML 错误页, HTTP 状态码却仍是 200; 脚本检查
  文件头(`CDF`/`HDF`), 不是 NetCDF 就删除并报错, 不会把 HTML 当缓存;
- 目标文件已存在且非空时跳过, 刷新加 `--force`.

各区域的下载范围与 `--stride` 取值写在对应图种页的"数据"一节.

## 注意事项

- 只有换机器或重新 clone 时才需要重跑准备命令; 同一份数据反复出图不会再下载;
- 网络受限时(ERDDAP、Overpass、GADM、OCHA 任一不可用), 可以手动把文件放进对应
  `data/raw/` 目录, 文件名按各子项目 `config.py` 里的 `dest` 约定, 脚本检测到就不下载;
- OSM 数据经公共 Overpass API 获取: 首次运行请求 relation 并缓存原始 JSON, 公共实例满负荷
  (502)时会轮换镜像; Overpass 是实时查询接口, 没有版本号, 缓存只能当快照用;
- 数据缺失时绘图会 `FileNotFoundError` 并提示对应的 `main.py` 子命令, 按提示跑即可.
