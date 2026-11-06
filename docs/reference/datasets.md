# 数据层 (cartopy_file.datasets)

- 源码: [`src/cartopy_file/datasets.py`](../../src/cartopy_file/datasets.py)、[`sources.py`](../../src/cartopy_file/sources.py)、[`fetch.py`](../../src/cartopy_file/fetch.py)
- 导入: `from cartopy_file.datasets import Dataset, dataset_set`、`from cartopy_file.sources import source, ne_url, erddap_url`、`from cartopy_file import fetch`

## 是什么

数据层的三个模块: `sources` 登记外部数据源(URL 模板/版本/许可/署名), `fetch` 做下载与
解压, `datasets` 描述「一个子项目要哪些数据、放哪、怎么校验」并与实例规格互相引用.
一页写清是因为它们只有一个用法: 在子项目的 `specs.py` 里声明一份 `DATASETS`, 数据准备
脚本与绘图脚本都从它取参数.

`DATASETS` 是数据清单的唯一真源: 根目录 `python download_data.py --check` 汇总所有子项目
的清单, `tools/check_geo.py` 的产物清单也由同一批 `specs.py` 派生, 不再有第二处手写表.

## 关键行为

### Dataset

| 字段 | 含义 |
| --- | --- |
| `id` | 子项目内唯一; `Sheet.dataset_ids` 与 `Sheet.dem_id` 引用它 |
| `kind` | `file` 单文件下载 / `zip` 下载并解压 / `cartopy-ne` 共享缓存里的 Natural Earth 图层 / `derived` 本子项目脚本生成 / `script` 脚本自己抓取(Overpass 等) / `local` 仓库自带 |
| `source_id` | `sources.SOURCES` 里的 id; 项目自带数据留空 |
| `url` / `dest` | 下载地址与相对子项目 `data/` 的目标路径(`raw/...` 或 `derived/...`) |
| `files` | 判定「已就位」的 glob; 缺省用 `dest`. 同一区域不同 stride 的高程文件靠它共存 |
| `bbox` / `stride` | 数据覆盖范围与采样步长. `bbox` 从画框推出来(`Extent.padded(...)`), 出图时会核对是否盖住投影后的画框 |
| `version` / `version_file` | 版本口径与校验文件(如 `ne_10m_admin_0_countries.VERSION.txt`); 不写 `version` 时用数据源的版本 |
| `optional` | 可选缓存, 缺失不算失败 |

### DatasetSet

- `path()` 数据集在本地的主路径; `exists()` 是否可用; `check()` 逐项返回检查结果;
- `citation(ids)` 把用到的数据集折成产物「数据来源」一行, 每个数据源只出现一次, 且带发布页
  地址(许可要求署名的数据源, 署名写在 `Source.credit` 里);
- `raw_dir` / `derived_dir` 是 `data/raw` 与 `data/derived` 的路径.

### 目录约定

```
<Sub>/data/raw/       下载原样: 原始 NetCDF / zip / GeoJSON
<Sub>/data/derived/   由脚本加工出来的: 解压目录、生成的边界 GeoJSON
data/cartopy/         全项目共用的 Natural Earth 缓存(由根目录 download_data.py 预取)
```

`raw` 一次下载、永不改写; `derived` 可以随时删掉重算, 删它不会触发重新联网.

### 版本怎么钉

- 版本号写在 URL/文件名里的(GADM `gadm41_*`、ETOPO `ETOPO_2022_v1_15s`、HydroBASINS `v1c`)
  直接记录版本字符串;
- **Natural Earth 是唯一的例外**: S3 下载地址不带版本号, 换版会原地覆盖同名文件. 所以:
  1. `Source.version` 记录当前使用的版本(5.1.1);
  2. 缓存里随 zip 解出来的 `*.VERSION.txt` 是唯一证据, 用 `Dataset.version_file` 指向它,
     `--check` 逐字比对(不符即报「版本不符」);
  3. 确实停在旧版本的数据(缅甸的河流副本是 5.0.0)在 `Dataset.version` 里显式钉住, 并写进
     `note`, 而不是悄悄跟着共享缓存走——换版会改变河网几何, 必须单独评审;
  4. 需要「内容也不许换」时用 `Dataset` 之外的 `fetch.download(..., expected_sha256=...)`,
     校验失败会删掉半成品并提示同步更新版本口径.

## 用法

```python
from cartopy_file.datasets import Dataset, dataset_set
from cartopy_file.sources import erddap_url, ne_url
from cartopy_file.spec import Extent

EXTENT = Extent(87.0, 106.0, 5.0, 31.0)
# 下载范围从画框推出来, 与绘图共用同一个 extent.
BBOX = EXTENT.padded(lon=1.7, lat=0.1)

DATASETS = dataset_set("缅甸", ROOT / "data", [
    Dataset(id="etopo-myanmar", kind="file", source_id="etopo-2022",
            url=erddap_url("etopo-2022", stride=2,
                           lon_range=(BBOX.lon_min, BBOX.lon_max),
                           lat_range=(BBOX.lat_min, BBOX.lat_max)),
            dest="raw/ETOPO_2022_v1_15s_myanmar_stride2.nc",
            files=("raw/ETOPO_2022_v1_15s_myanmar_stride*.nc",),
            bbox=BBOX, stride=2),
    Dataset(id="ne-countries-10m", kind="cartopy-ne", source_id="natural-earth",
            resolution="10m", category="cultural", name="admin_0_countries",
            version_file="ne_10m_admin_0_countries.VERSION.txt"),
])

for line in DATASETS.check():
    print(line.state, line.dataset_id, line.detail)
```

下载:

```python
from cartopy_file import fetch

fetch.download(url, dest, description="ETOPO 高程", magic=fetch.MAGIC_NETCDF)
fetch.extract_zip(archive, dest_dir)
```

## 注意事项

- **不要在两处各写一份画框**: 下载范围只能从 `specs.py` 里的 `Sheet.extent` 推出来
  (`Extent.padded(...)` 或就地声明的 `Extent`), 绘图那一侧用同一个 `Sheet.extent`;
- `bbox` 要盖住投影后的画框, 而不只是经纬度矩形: 圆锥投影的矩形画框顶边会张开, 只按经纬度
  下载会在画框角上露白. `runner` 出图时会打印覆盖不足的警告, 看到就回来核对(不要改回去
  再写一份数字);
- `cartopy-ne` 的「已存在」以**项目缓存**为准: 只有 `~/.local/share/cartopy` 里有不算就位
  (`--check` 报「版本不符/只在旧缓存」), 因为换机器就没了;
- Natural Earth 的 zip 解出来是 `目录/数据文件` 结构, 而 cartopy 找的是 `类别目录/ne_*.shp`
  平铺结构; 手工复制时两种都要照顾(根目录 `download_data.py` 的 `_copy_shapefile_set`
  已经把 `.README.html` / `.VERSION.txt` 也一起复制);
- 版本不符是失败而不是警告: 产物是「当前代码 + 当前数据」生成的, 换版后底图与文档就对不上了;
- 「下载压缩包再解压」有两种登记方式: ① ``kind="zip"``, ``dest`` 指向解压目录(缅甸的河流副本);
  ② 拆成两条——``kind="file"`` 的压缩包放 ``raw/`` + ``kind="derived"`` 的解压目录(伏尔加的
  HydroBASINS). 同一子项目里选一种即可, 别一半一半, 否则 ``--check`` 会报出重复或对不上的项.
