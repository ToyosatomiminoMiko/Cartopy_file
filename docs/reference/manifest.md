# 数据清单契约 (manifest.json)

- 源码: 读取侧 [`src/cartopy_file/catalog.py`](../../src/cartopy_file/catalog.py); 写出一侧在
  数据项目 `src/miko_gis_data/manifest.py`(独立仓库, 本仓不链接)
- 导入: `from cartopy_file.catalog import catalog_for`

## 是什么

`<数据根>/manifest.json` 是渲染仓与数据项目 `miko_gis_data` 之间**唯一的耦合面**: 数据项目把
各区域的数据集事实(来源,版本,本地路径,覆盖范围,采样步长,署名)写成这份 JSON, 渲染仓只读它,
按数据集 id 取路径与署名. 两个仓库互不 import, 数据项目可以整体移走, 移走后换
`CARTOPY_FILE_DATA` 指过去即可.

清单是**确定性**的: 键顺序由构造顺序固定, 路径全部相对数据根, 不含绝对路径与时间戳, 中文不
转义, 结尾一个换行. 同一份配置重复 `publish` 得到逐字节相同的文件, 所以可以拿
`publish --check` 判断它是否与配置一致.

- 生成: 数据项目 `python main.py publish`(`all` 的最后一步也会写);
- 位置: 数据根根目录, 由数据项目 `data_root()` 决定;
- 读取: 渲染仓 `cartopy_file.catalog`, 契约的字段解析在 `_parse_item` / `_parse_source`.

## 关键行为

### 顶层字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `format` | string | 固定为 `miko-gis-data/manifest`; 渲染仓按它识别清单, 不符直接拒绝 |
| `version` | int | 契约版本, 当前为 `1`; 字段或语义变更时加 1, 渲染仓只读自己支持的版本 |
| `groups` | object | 区域名 -> 一个区域的数据块; 区域名即数据项目 `regions/<region>/` 目录名, 也是渲染仓 `DATA_GROUP` 的取值 |

### 区域块(`groups.<region>`)

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `title` | string | 区域显示名(如 `缅甸`), 只用于人读与文档; `Catalog.title` 读它 |
| `items` | array | 该区域的数据集数组, 见下表 |

### 数据集条目(`groups.<region>.items[]`)

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | string | 数据集 id, 区域内唯一; 渲染仓按它引用(`Sheet.dataset_ids` / `Sheet.dem_id` / `Catalog.get`) |
| `kind` | string | `file`(单文件) / `zip`(压缩包解压到 `dest` 目录) / `cartopy-ne`(Natural Earth 共享图层) / `derived`(派生脚本生成) / `script`(下载脚本自行抓取) / `local`(仓库自带) |
| `note` | string | 人读说明; 渲染仓缺数据报错时也会带出它当提示 |
| `optional` | bool | 可选缓存: 缺失不算数据项目 `check` 的失败项 |
| `dest` | string | 主路径, 相对 `<数据根>/<region>/`; `cartopy-ne` 为空(位置由 `resolution/category/name` 决定) |
| `files` | array | 判定"已就位"的 glob, 相对 `<数据根>/<region>/`; 为空时用 `dest`. `dest` 是目录(kind=`zip`)时用 `["<dest>/*"]` 这类写法 |
| `version` | string | 数据集级版本覆盖; 为空表示沿用数据源版本. 只在数据确实停在旧版本时写(如缅甸河流钉在 Natural Earth 5.0.0) |
| `stride` | int 或 null | ETOPO 类数据的采样步长; 其它数据为 null |
| `bbox` | object 或 null | 数据覆盖范围 `{lon_min, lon_max, lat_min, lat_max}`; 有值时渲染仓用它核对画框覆盖 |
| `resolution` | string | 仅 `cartopy-ne`: 分辨率(`10m` / `110m`) |
| `category` | string | 仅 `cartopy-ne`: `physical` / `cultural` |
| `name` | string | 仅 `cartopy-ne`: Natural Earth 图层名(如 `admin_0_countries`) |
| `source` | object 或 null | 数据来源的静态事实, 见下表; 仓库自带数据为 null |

### 来源对象(`items[].source`)

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | string | 数据源 id(如 `natural-earth`), 署名按它去重 |
| `title` | string | 数据源名(如 `NOAA ETOPO 2022`) |
| `version` | string | 数据源版本口径; 版本被数据集覆盖时, 署名里会改写版本号 |
| `homepage` | string | 发布页 URL, 长期有效, 进产物「数据来源」 |
| `credit` | string | 进图署名短句, 含许可要求必须出现的文字(如 ODbL 的署名) |

### 语义与约定

- `format` 或 `version` 不符时渲染仓**明确拒绝**并给出可执行提示: 格式不符 -> 用当前版本的
  数据项目重新 `publish`; 版本不符 -> 同步升级/降级两边的仓库. 不猜字段, 不做兼容读取;
- 所有路径相对 `<数据根>/<region>/`(清单里的 `dest`/`files`), 数据根因此可整体搬运;
- 数据集 `id` 是渲染侧代码与产物的键: 改名等于改产物(已存的排版按 label id 回查, 数据集 id
  影响 `dataset_ids`/`dem_id` 与署名), 属于要单独评审的改动;
- `version` 是"覆盖"而不是"追加": 数据源版本与数据集版本不一致时, `Catalog.citation` 用
  `"<title> <version>"` 改写署名, 保证产物写的是磁盘上实际的版本;
- `bbox` 只用于覆盖核对, 不参与下载; 下载范围由数据项目区域配置里的 `padded(...)` 推出并写进
  这里, 出图时 `runner` 比对投影后的画框四角;
- `optional` 只影响数据项目 `check` 的失败计数, 渲染仓不据此放宽缺文件判断.

### 渲染仓一侧怎么读

1. `catalog_for(group)` -> `_load()`: 读文件, 校验 `format` 与 `version`, 把每条 item 解析成
   `DatasetView`, 把 `source` 解析成 `SourceInfo`; 文件缺失/格式不符/版本不符/区域不存在都抛
   带命令提示的错误;
2. `Catalog.get(id)` / `path(id)` / `exists(id)` / `raw_dir` / `derived_dir` /
   `citation(ids)` 见 [reference/catalog.md](catalog.md);
3. `runner.render` 用 `Catalog` 核对 `sheet.dataset_ids` 里声明为 `cartopy-ne` 的图层是否
   就位(缺了在画图前就报错), 用 `sheet.dem_id` 对应条目的 `bbox` 核对覆盖, 用
   `Catalog.citation` 写 geo.json 的 `suggestions.source`.

### 数据项目一侧怎么生成

- 每个 `src/miko_gis_data/regions/<region>/config.py` 导出
  `DATASETS = dataset_set("<显示名>", ROOT, [...])`, 每条 `Dataset` 的来源事实来自
  `sources.py`;
- `manifest.build()` 按区域顺序汇总, `manifest.dump()` 用固定键顺序与 `indent=2` 序列化;
- `manifest.write()` 写 `<数据根>/manifest.json`, `publish --check` 拿磁盘内容与 `dump()`
  逐字节比较;
- 新增区域 = 新建 `regions/<region>/` 目录(带 `config.py`) + `publish`; 渲染仓只要把
  `DATA_GROUP` 设成同一个区域名就能读.

### 改字段必须两仓同步

1. 定字段名与语义, 数据项目 `manifest.py` 的 `_item_payload`/`_source_payload` 与
   `MANIFEST_VERSION` 加 1;
2. 本仓 `catalog.py` 的 `SUPPORTED_VERSION` 与 `_parse_item`/`_parse_source` 同步;
3. 数据项目重新 `publish`, 本仓重出图, 再用 `check_docs`/`check_geo`/`check_all` 验证;
4. 只改一边会被格式/版本校验挡住, 不要试图在读取侧做兼容猜测.

## 用法

读取(渲染仓):

```python
from cartopy_file.catalog import catalog_for

catalog = catalog_for("myanmar")
item = catalog.get("etopo-myanmar")
print(item.kind, item.stride, item.bbox, item.credit)
print(catalog.path(item))          # <数据根>/myanmar/raw/...
print(catalog.exists(item))        # 本地是否有匹配文件, 不联网
```

清单片段(数据项目生成):

```json
{
  "format": "miko-gis-data/manifest",
  "version": 1,
  "groups": {
    "myanmar": {
      "title": "缅甸",
      "items": [
        {
          "id": "etopo-myanmar",
          "kind": "file",
          "note": "ETOPO 2022 缅甸区域高程(stride 2 = 30 弧秒)",
          "optional": false,
          "dest": "raw/ETOPO_2022_v1_15s_myanmar_stride2.nc",
          "files": ["raw/ETOPO_2022_v1_15s_myanmar_stride*.nc"],
          "version": "",
          "stride": 2,
          "bbox": {"lon_min": 85.3, "lon_max": 107.7, "lat_min": 4.9, "lat_max": 31.1},
          "resolution": "",
          "category": "",
          "name": "",
          "source": {
            "id": "etopo-2022",
            "title": "NOAA ETOPO 2022",
            "version": "v1 (15 arc-second)",
            "homepage": "https://www.ncei.noaa.gov/products/etopo-global-relief-model",
            "credit": "NOAA ETOPO 2022 (15″)"
          }
        }
      ]
    }
  }
}
```

## 注意事项

- **不要手改** `<数据根>/manifest.json`: 它由数据项目 `publish` 从配置重新生成, 手改会在下次
  发布时丢掉; 要改数据事实就改数据项目的区域配置;
- 清单里的路径**必须是相对路径**: 写绝对路径会让数据根不可搬运, 也会让产物的署名/结构随
  机器变化;
- 换数据根位置只改 `CARTOPY_FILE_DATA`, 不要改清单; 数据项目与渲染仓读同一个变量;
- `json.dumps` 的键顺序是构造顺序, 修改 `build()` 时保序(用普通 dict, 不要用集合重排);
- `version` 加 1 是**破坏性**变更: 旧版渲染仓会拒绝新清单, 反之亦然; 两个仓库要在同一批
  改动里升级;
- 数据集的 `id` 已被文档与代码引用(`Sheet.dataset_ids`,`Sheet.dem_id`, 图种页的数据表),
  改名时全仓 `grep` 一遍, 并重出受影响的产物.
