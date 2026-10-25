# 数据准备与缓存

所有数据都在首次准备时下载一次, 之后就只读本地文件; 绘图脚本本身不联网. 本页说明数据放在
哪、从哪来、用什么命令准备、怎么检查.

## 目录与缓存

| 位置 | 内容 | 谁维护 |
| --- | --- | --- |
| `data/cartopy/` | cartopy 内置 Natural Earth 底图, 全项目共用(海岸线、国界、河流、湖泊) | 根目录 `download_data.py` |
| `Myanmar/data/` | ETOPO 缅甸高程、Natural Earth 10m 国界/河流、行政区 GeoJSON、OSM 特区边界 | `Myanmar/download_etopo.py`、`download_regions.py`、`prepare_admin_data.py` |
| `USSR/data/` | ETOPO 苏联高程、Natural Earth 110m 国界 | `USSR/download_etopo.py` |
| `Ukraine/data/` | ETOPO 乌克兰高程、Natural Earth 10m 国界、GADM 4.1、OCHA 2021 GCA/NGCA、OSM 河流与德左边界、派生 GeoJSON | `Ukraine/download_data.py` |
| `AmericaArmy/data.geojson` | 基地点位, 仓库自带 | — |

`**/data` 在 `.gitignore` 里, 数据不随仓库提交; 换机器或重新 clone 后重跑准备命令即可恢复.
唯一入库的数据文件是 `AmericaArmy/data.geojson`(它不在被忽略的 `data/` 目录里).

本机 `/home` 是只读挂载, cartopy/matplotlib 的默认缓存目录不可写, 所以缓存统一放在仓库内.
需要把共用缓存放到别的可写磁盘时设 `CARTOPY_FILE_DATA=/path/to/data`; 定位逻辑与各环境变量
见 [`reference/data.md`](reference/data.md).

## 数据源与许可

| 数据集 | 用途 | 许可 |
| --- | --- | --- |
| Natural Earth(10m / 110m) | 海岸线、国界、河流、湖泊、陆地、海洋 | public domain |
| NOAA ETOPO 2022(15 弧秒) | 地形高程 | 美国联邦政府作品, public domain |
| GADM 4.1 | 缅甸/乌克兰一级行政区 | 学术与非商业用途免费, 商用需授权 |
| OpenStreetMap | 特区边界、乌克兰河流/水库、德左边界 | ODbL 1.0 |
| OCHA HDX 2021 HNO GCA/NGCA | 乌克兰顿巴斯接触线 | 按其发布页面的许可与署名要求 |

引用产物时请按上表署名数据来源.

## 准备命令总表

每条命令都是"文件已存在就跳过", 重复执行不会重新下载; 派生数据(如乌克兰的边界 GeoJSON)每次
重新生成.

| 命令 | 产物 | 什么时候需要 |
| --- | --- | --- |
| `python download_data.py` | `data/cartopy/` 共用底图 | 每台机器一次 |
| `python Myanmar/download_etopo.py` | 缅甸 ETOPO(stride=2)+ Natural Earth 10m 国界 | 缅甸全境图/行政区图 |
| `python Myanmar/download_etopo.py --region northern_shan --stride 1` | 掸邦 15 弧秒高程 | 掸邦/特区图 |
| `python Myanmar/download_regions.py` | OSM 特区边界与画框附近国界 | 掸邦/特区图 |
| `python Myanmar/prepare_admin_data.py` | `Myanmar/data/myanmar_admin1.geojson` 等 | 缅甸行政区图 |
| `python USSR/download_etopo.py` | 苏联 ETOPO(默认 stride=8)+ 110m 国界 | 苏联图 |
| `python Ukraine/download_data.py` | 乌克兰全部原始数据与派生 GeoJSON | 乌克兰图 |

想确认数据是否齐全(不联网、不下载):

```bash
python download_data.py --check   # 全部就位退出码 0, 有缺失退出码 1 并给出准备命令
```

`--check` 的清单分三部分: `download_data.py` 顶部的 `NE_FEATURES`(共用 cartopy 底图)、
`LOCAL_DATA`(各图种的必需本地数据)、`OPTIONAL_DATA`(缺失也不影响出图的缓存). 新增图种或
新数据时按 [`add-map.md`](add-map.md) 的清单补进去, 否则 `--check` 不会提示.

## ETOPO 下载

三组图都用同一套 NOAA ERDDAP 下载方式(实现分别在各图的数据准备脚本里):

- 不直接打开 NOAA OPeNDAP 的几十个瓦片(要在经度上跨瓦片拼接, 还要处理 0°/360° 与
  -180°/180° 两套经度约定), 改为向 ERDDAP 请求一次已裁剪、重采样好的区域 NetCDF,
  绘图时只读一个文件;
- ERDDAP 的经度是 0~360°, 跨 180° 的区域(如苏联图)要把负经度 +360;
- 区域范围要覆盖投影后的矩形画框四角, 而不是只按经纬度画框下载, 否则兰勃特投影画框的角上
  会露出没有高程数据的空白;
- 默认步长按图幅大小选: 缅甸全境 `stride=2`(30 弧秒, 约 34 MB), 掸邦放大图 `stride=1`
  (15 弧秒), 苏联 `stride=8`(2 弧分, 约 0.6 GB), 乌克兰 `stride=2`;
- 断点续传: 中断留下 `.part` 文件, 再次运行尝试续传; 若服务器忽略 Range 直接返回完整数据,
  脚本会清空 `.part` 从头写, 避免拼出坏文件;
- 校验: ERDDAP 在子集过大或参数非法时会返回 HTML 错误页, HTTP 状态码却仍是 200; 脚本检查
  文件头(`CDF`/`HDF`), 不是 NetCDF 就删除并报错, 不会把 HTML 当缓存;
- 目标文件已存在且非空时跳过, 刷新加 `--force`.

各区域的下载范围与 `--stride` 取值写在对应图种页的"数据"一节.

`_stride1_chunked.py` 是一次性临时脚本(早期把缅甸 15 弧秒高程分 8 个纬度带下载再拼接),
现在 `Myanmar/download_etopo.py --region northern_shan --stride 1` 已能一次拿到所需子集,
日常不需要它.

## 注意事项

- 只有换机器或重新 clone 时才需要重跑准备命令; 同一份数据反复出图不会再下载;
- 网络受限时(ERDDAP、Overpass、GADM、OCHA 任一不可用), 可以手动把文件放进对应 `data/`
  目录, 文件名按下表约定, 脚本检测到就不下载;
- OSM 数据经公共 Overpass API 获取: 首次运行请求 relation 并缓存原始 JSON, 公共实例满负荷
  (502)时脚本会在多个镜像间轮换重试, 并把关系分批请求避免超时;
- 数据缺失时绘图脚本会 `FileNotFoundError` 并提示对应的准备命令, 按提示跑即可.
