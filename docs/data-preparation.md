# 数据准备与缓存

数据分两段准备: **原始数据**由独立数据项目 `miko_gis_data` 下载/入库/解压, 写到数据根;
**派生数据**由本仓各子项目的 `prepare` 子命令从原始数据加工到 `<子项目>/build/`. 之后出图只读
本地文件, 渲染仓**不联网**. 本页说明数据放在哪,从哪来,用什么命令准备,以及渲染侧怎么确认数据
就位. 本仓与数据项目怎么分工见 [overview.md](overview.md) 的"与数据项目的边界"一节.

## 数据在哪

数据分两个可丢弃/可搬运的位置: 数据根(原始数据 + 清单)与各子项目的 `build/`(派生数据).

| 位置 | 内容 | 谁维护 |
| --- | --- | --- |
| `<数据根>/manifest.json` | 数据清单契约, 渲染仓只读它; 只登记原始数据 | 数据项目 `python main.py publish` |
| `<数据根>/cartopy/` | 全项目共用的 Natural Earth 缓存 | 数据项目 `download` 预取 |
| `<数据根>/<region>/raw/` | 该区域下载原样: ETOPO NetCDF,GADM/OSM 原始 JSON,压缩包与解压目录 | 数据项目该区域的 `download_*.py` |
| `<子项目>/build/*.geojson` | 按图种口径清洗/裁剪/拼装后的派生数据 | 本仓 `<子项目>/prepare.py` |
| `AmericaArmy/data.geojson` | 演示子项目的基地点位, 仓库自带(不在数据根里) | 本仓,入库 |

`<region>` 就是 manifest 里的 group 键, 也是本仓子项目 `config.py` 里 `DATA_GROUP` 的取值:
`america_army`,`myanmar`,`ussr`,`ukraine`,`volga`. 清单里的 `dest`/`files` 全部相对
`<数据根>/<region>/`, 所以数据根可以整体拷走, 里面不含绝对路径.

数据根固定是数据项目的 `data/` 目录(即 `<数据项目>/data/`). 数据项目往这里写, 渲染仓靠
仓根 `config.toml` 的 `data_root` 指过来, 不用环境变量:

```toml
# <渲染仓>/config.toml
data_root = "<数据项目>/data"
```

配置缺失或非法时 `data_root()` 直接报错, 不猜默认路径. 定位逻辑见
[reference/data.md](reference/data.md).

数据根里只有 `raw/`: 下载原样与解压目录都在这里, 数据项目不写派生 GeoJSON. 派生数据在本仓
`<子项目>/build/` 下, 删掉不触发下载, 重跑 `prepare` 即可恢复; 数据项目的 `check` 不检查它,
清单也不登记它. `**/data` 与 `/config.toml` 都在本仓 `.gitignore` 里, 数据与清单不随仓库提交;
换成新机器或重新 clone 后到数据项目重跑准备命令即可恢复. 唯一入库的数据文件是
`AmericaArmy/data.geojson`.

## 两段准备的分工

| 阶段 | 在哪 | 做什么 | 不做什么 |
| --- | --- | --- | --- |
| 下载/入库/解压 | 数据项目 `miko_gis_data` | 下原始文件,把压缩包解压到 `raw/`,写 `manifest.json` | 不裁剪, 不补缝, 不写 GeoJSON |
| 清洗/派生/裁剪 | 本仓 `<子项目>/prepare.py` | 读 `raw/` 与共享图层, 按图种口径生成 `build/*.geojson` | 不下载, 不改 `raw/`, 不写数据根 |

数据项目只写 `raw/` 与清单; 派生只在本仓 `<子项目>/prepare.py`, 不在数据项目里.

## 数据项目的命令

命令从数据项目的唯一入口 `main.py` 发出, 在数据项目根目录执行:

```bash
cd miko_gis_data
uv sync
python main.py check      # 逐项核对原始数据(不联网), 有缺失/版本不符退出码 1
python main.py download   # 预取共享 Natural Earth 图层 + 下载/解压各区域原始数据
python main.py publish    # 重建 <数据根>/manifest.json
python main.py all        # download -> publish -> check
```

| 命令 | 做什么 | 什么时候需要 |
| --- | --- | --- |
| `check` | 按各区域配置逐项核对原始文件与版本, 不联网 | 每次换机器/怀疑缺数据时 |
| `download` | 预取 `<数据根>/cartopy/` 的共享图层, 再把各区域原始数据下到 `raw/`(压缩包就地解压); 已存在就跳过 | 首次或换机器 |
| `publish` | 把各区域配置汇总成 `manifest.json`(只含原始数据) | 数据或配置变化后 |
| `all` | 依次跑上面三步 | 首次一键准备 |

选项:

- `--group {all,america_army,myanmar,ukraine,ussr,volga}`: 只处理一个区域, 缺省 `all`
  (`publish` 的 `--group` 只是保留参数, 清单总是整体生成);
- `download --region {all,myanmar,northern-shan}`: 仅缅甸, 选择 ETOPO 下载区域;
- `download --stride N`: 覆盖 ETOPO 类区域登记的默认采样步长;
- `download --force`: 覆盖已存在的下载文件/解压目录;
- `download --skip-regions`: 仅缅甸, 跳过掸邦特区边界/国界下载;
- `download --skip-basin`: 仅伏尔加, 跳过 HydroBASINS 下载/解压;
- `publish --check`: 只比较清单与当前配置, 不写盘.

每个区域具体下载什么, 由数据项目 `src/miko_gis_data/regions/<region>/config.py` 的
`DATASETS` 声明; 渲染仓不重复这份清单. 各图种的数据表见对应[图种页](maps).

## 本仓的 prepare(派生)

原始数据就位后, 在本仓根目录按子项目跑一次 `prepare`(不联网, 每次全量重建):

```bash
python Myanmar/main.py prepare    # -> Myanmar/build/{myanmar_admin1,shan_north_boundaries,osm_country_borders}.geojson
python Ukraine/main.py prepare    # -> Ukraine/build/ 下 12 份边界/河流 GeoJSON
python Volga/main.py prepare      # -> Volga/build/{volga_subjects,volga_basin,russia_border}.geojson
python Volga/main.py prepare --skip-basin   # 跳过流域派生, 只重建行政区与国界
```

苏联与美军基地演示没有派生数据, 入口只有 `render`. 派生模块读数据清单定位 `raw/`, 把结果
写进本子项目 `build/`(由 `config.py` 的 `build_path(...)` 声明); 缺原始数据时报错并指向数据
项目对应的 `download --group <region>`. `build/` 已在 `.gitignore`, 可以随时删除重跑.
流程,目录约定与各子项目派生内容见 [reference/prepare.md](reference/prepare.md).

## 数据源与许可

外部数据源的权威登记在数据项目的 `src/miko_gis_data/sources.py`: URL 模板,版本,许可,进图
署名都只写一次, 各区域配置只引用 id. 换数据源或改版本要改那一个文件, 并同步两个仓库的文档
(本页与数据项目的 `docs/data-preparation.md`).

| id | 数据集 | 版本 | 用途 | 许可 |
| --- | --- | --- | --- | --- |
| `natural-earth` | Natural Earth(10m / 110m) | 5.1.1 | 海岸线,国界,河流,湖泊,陆地,海洋 | public domain |
| `etopo-2022` | NOAA ETOPO 2022(15 弧秒) | v1 | 地形高程 | 美国联邦政府作品, public domain |
| `gadm-4.1` | GADM | 4.1 | 缅甸/乌克兰/俄罗斯一级行政区 | 学术与非商业用途免费, 商用需授权 |
| `hydrobasins` | HydroSHEDS(HydroBASINS) | v1c | 伏尔加河流域边界 | 免费, 需按发布页署名 |
| `ocha-hno-2021` | OCHA HDX 2021 HNO GCA/NGCA | 2021 | 乌克兰顿巴斯接触线 | 按其发布页的许可与署名要求 |
| `openstreetmap` | OpenStreetMap(Overpass 快照) | 无版本号 | 特区边界,乌克兰河流/水库,德左边界 | ODbL 1.0 |

引用产物时请按上表署名数据来源. 产物 geo.json 的 `suggestions.source` 由渲染仓按 manifest
里的 `source` 字段自动生成(每个数据源一条, 带发布页 URL), 不手写; 数据源或版本变了要重新
`publish` 清单并重新出图, 否则产物里的署名与实际数据不符. 版本覆盖的写法(例如缅甸河流钉在
Natural Earth 5.0.0)见 [reference/manifest.md](reference/manifest.md).

## ETOPO 下载

各图种都用同一套 NOAA ERDDAP 下载方式(实现在数据项目, 下载范围来自数据项目各区域的
`config.py`):

- 不直接打开 NOAA OPeNDAP 的几十个瓦片(要在经度上跨瓦片拼接, 还要处理 0°/360° 与
  -180°/180° 两套经度约定), 而是向 ERDDAP 请求一次已裁剪,重采样好的区域 NetCDF,
  绘图时只读一个文件;
- ERDDAP 的经度是 0~360°, 跨 180° 的区域(如苏联图)要把负经度 +360;
- 区域范围要覆盖**投影后的矩形画框**四角, 而不是只按经纬度画框下载, 否则兰勃特投影画框的
  角上会露出没有高程数据的空白. 这个范围在数据项目里由区域画框 `padded(...)` 推出, 并写进
  清单的 `bbox`; 出图时 `runner` 会核对它是否盖住画框;
- 默认步长按图幅大小选: 缅甸全境 `stride=2`(30 弧秒, 约 34 MB), 掸邦放大图 `stride=1`
  (15 弧秒), 苏联 `stride=8`(2 弧分, 约 45 MB), 乌克兰 `stride=2`;
- 断点续传: 中断留下 `.part` 文件, 再次运行尝试续传; 若服务器忽略 Range 直接返回完整数据,
  脚本会清空 `.part` 从头写, 避免拼出坏文件;
- 校验: ERDDAP 在子集过大或参数非法时会返回 HTML 错误页, HTTP 状态码却仍是 200; 脚本检查
  文件头(`CDF`/`HDF`), 不是 NetCDF 就删除并报错, 不会把 HTML 当缓存;
- 目标文件已存在且非空时跳过, 刷新加 `--force`.

各区域的下载范围与 `--stride` 取值写在对应图种页的"数据"一节.

## 渲染侧怎么检查数据

- 想看缺什么: 到数据项目跑 `python main.py check`(不联网), 它会按区域逐项打印"已存在 /
  缺失 / 版本不符", 最后给出准备命令; 本仓的 `prepare` 也会在缺原始数据时报出缺哪个数据集;
- 直接出图也可以: 缺原始文件时渲染报错并指向数据项目的命令, 例如
  `python main.py download --group myanmar`; 缺派生文件时先跑
  `python <子项目>/main.py prepare`; 缺共享 Natural Earth 图层时 `runner` 在画图前就报错,
  不会写出缺底图的半成品;
- 数据覆盖不足只打印警告: 清单里 `bbox` 盖不住画框投影后的范围时, `runner` 提示回数据项目
  核对区域画框, 不中断出图(画框角落本来就有底图颜色兜底);
- 就位判断以数据根为准: 只有 `~/.local/share/cartopy` 里有不算就位; 渲染仓把 HOME 里已有的缓存
  登记成 `pre_existing_data_dir` 继续复用, 但项目自己需要一份自包含的数据根.

## 注意事项

- 只有换机器或重新 clone 时才需要重跑数据项目的准备命令; 同一份数据反复出图不会再下载;
- 网络受限时(ERDDAP,Overpass,GADM,OCHA 任一不可用), 可以手动把文件放进数据项目对应区域的
  `raw/` 目录, 文件名按该区域 `config.py` 的 `dest` 约定, 脚本检测到就不下载;
- OSM 数据经公共 Overpass API 获取: 首次运行请求 relation 并缓存原始 JSON, 公共实例满负荷
  (502)时会轮换镜像; Overpass 是实时查询接口, 没有版本号, 缓存只能当快照用. 缅甸把特区/
  国界存成原始响应(`raw/regions/osm_shan_relations/group_XX.json` 与
  `raw/regions/osm_country_borders.json`), 拼装在本仓 `Myanmar/prepare.py`;
- 不要手改 `<数据根>/manifest.json`: 它由 `publish` 从配置重新生成, 手改会在下次发布时丢掉;
  字段变更必须同步改两个仓库(见 [reference/manifest.md](reference/manifest.md));
- 数据根整体可搬运: 换位置只改渲染仓 `config.toml` 的 `data_root`, 清单里不含绝对路径;
- 数据项目的 `download` 下载/解压的是原始数据(伏尔加 HydroBASINS 解压到
  `raw/hybas_eu_lev05_v1c/`, manifest id `hybas-eu-lev05`,`kind=zip`), 不做派生;
- 本仓的 `prepare` 与绘图脚本都**不联网**, 也不提供下载/解压的子命令.
