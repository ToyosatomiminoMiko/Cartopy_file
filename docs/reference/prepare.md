# 派生数据流程 (prepare)

- 源码: 各子项目的 `prepare.py`([`Myanmar/prepare.py`](../../Myanmar/prepare.py),
  [`Ukraine/prepare.py`](../../Ukraine/prepare.py), [`Volga/prepare.py`](../../Volga/prepare.py));
  共享几何工具在 [`src/cartopy_file/geometry.py`](../../src/cartopy_file/geometry.py)
- 导入: 命令行 `python <子项目>/main.py prepare`; 模块只导出 `run()`

## 是什么

**派生**(清洗/裁剪/补缝/拼装/属性整理)在本仓完成, 不在数据项目里做. 数据项目
`miko_gis_data` 只负责下载/入库/解压: 它把外部数据原样写进数据根 `<region>/raw/`, 并
`publish` 一份 `manifest.json`; 本仓的 `prepare` 子命令按图种口径读这些原始数据, 生成绘图
模块直接读取的派生 GeoJSON.

为什么这样分: 原始数据是通用资产, 洗法却是图种口径. 例如缅甸要把 GADM 与 OSM 内比都拼成
15 个单元并补缝, 乌克兰要把 OCHA 分区裁成接触线, 伏尔加要按 HydroBASINS 主流域合并 -- 这些
阈值与取舍只对某一张图有意义, 放在数据项目里会让数据仓背上一堆应用侧规则; 放在本仓,
数据仓只回答"数据是不是原样下到了", 应用侧回答"这张图要什么形状".

## 关键行为

### 派生数据放哪

- 产物写 `<子项目>/build/*.geojson`, 路径由
  [`spec.build_path()`](spec.md) 拼(`BUILD_DIR = "build"`), 不在数据根里;
- `build/` 是**可丢弃的中间产物**: 删掉后重跑对应子项目的 `prepare` 即可重建, 不需要
  重新下载. `.gitignore` 已忽略 `**/build/`, 不入库;
- 派生数据**不登记进 manifest**: 清单只描述数据项目提供的原始数据; 派生文件由本仓
  `config.py` 里的 `build_path(...)` 常量定位, 不经过 [`Catalog`](catalog.md);
- 每次运行都**全量重建**: 不判断增量, 不做缓存; 同一份原始数据重复 `prepare` 得到逐字节
  相同的 GeoJSON(坐标精度与键序固定, 见 [geometry.md](geometry.md)).

### 各子项目派生什么

| 子项目 | 子命令 | 产物(都在 `<子项目>/build/`) |
| --- | --- | --- |
| 缅甸 | `python Myanmar/main.py prepare` | `myanmar_admin1.geojson`,`shan_north_boundaries.geojson`,`osm_country_borders.geojson` |
| 乌克兰 | `python Ukraine/main.py prepare` | 12 份: `ukraine_oblasts`,`ukraine_1991`,`crimea_2014_line`,`occupied_2014`,`contact_line_2014`,`claimed_2022`,`transnistria`,`dnieper_river_osm`,`dnieper_water_osm`,`dniester_river_osm`,`southern_bug_river_osm`,`don_river_osm` |
| 伏尔加 | `python Volga/main.py prepare [--skip-basin]` | `volga_subjects.geojson`,`volga_basin.geojson`,`russia_border.geojson` |
| 苏联 / 美军基地演示 | 无 `prepare` | 没有派生数据, 入口只有 `render` |

各子项目具体怎么洗(数据源,阈值,拓扑自检)写在各图种页的"数据"一节, 这里不重复.

### 运行时序

1. 数据项目准备原始数据并发布清单(`download` -> `publish` -> `check`);
2. 本仓跑一次 `<子项目>/main.py prepare`, 生成 `build/` 下的派生 GeoJSON;
3. 本仓 `<子项目>/main.py render` 出图.

`prepare` **不联网**: 数据路径只由 manifest 里的 `dest`/`files` 定位, 缺文件时直接报错并指向
数据项目对应的 `download --group <region>`, 不会临时下载. `render` 同样只读本地文件.

### 懒加载与依赖

- 子项目 `main.py` 在分派子命令时才导入模块: `prepare` 才加载 shapely/geopandas,
  `render` 才加载 matplotlib/cartopy, 所以只出图或用 `tools/` 时不会拖起另一半依赖;
- 共享几何工具只依赖 shapely/pyproj/pandas, 不 import matplotlib/cartopy, 见
  [geometry.md](geometry.md).

## 用法

首次出图(数据项目与本仓平级时):

```bash
# 1) 数据项目: 下载原始数据 + 发布清单(不产生派生数据)
(cd ../miko_gis_data && python main.py download)
(cd ../miko_gis_data && python main.py publish)
(cd ../miko_gis_data && python main.py check)

# 2) 本仓: 派生 + 出图
python Myanmar/main.py prepare
python Myanmar/main.py render

python Ukraine/main.py prepare
python Ukraine/main.py render

python Volga/main.py prepare            # 或 --skip-basin 只重建行政区与国界
python Volga/main.py render

# 没有派生数据的子项目直接 render
python USSR/main.py render
python AmericaArmy/main.py render
```

只重建部分派生文件时(例如只改了行政区补缝逻辑):

```bash
python Myanmar/main.py prepare
python Myanmar/main.py render --sheet myanmar-admin
```

## 注意事项

- **删掉 `build/` 不会丢数据**: 原始数据还在数据根, `prepare` 不联网, 重跑即可恢复; 反过来
  只删 `build/` 而原始数据也没了就按报错提示回数据项目 `download`;
- **`prepare` 不下载**: 缺原始数据(例如 OSM 快照,HydroBASINS 解压目录)时报错并给出数据项目
  命令, 不要在本仓找下载脚本;
- **派生文件不进清单**: 数据项目的 `publish` 只汇总原始数据; 本仓的 `Sheet.dataset_ids` 只
  登记原始数据集, 派生文件用 `config.py` 的 `build_path(...)` 取;
- **改派生逻辑要重出图**: `build/` 里的几何变了, 对应图种的 `.svg` 与 `.geo.json` 必须重新
  生成, 否则 `geo.base.sha256` 与底图对不上;
- **确定性**: 派生输出不能含时间戳,随机数或未排序的集合; 同一份原始数据两次 `prepare` 应
  逐字节一致(实现见 [geometry.md](geometry.md) 的 `write_geojson`);
- **原始数据布局由数据项目决定**: 缅甸特区/国界存成 Overpass 原始响应
  `raw/regions/osm_shan_relations/group_XX.json` 与 `raw/regions/osm_country_borders.json`,
  拼装在 `Myanmar/prepare.py`; 伏尔加 HydroBASINS 由数据项目 `download` 解压到
  `raw/hybas_eu_lev05_v1c/`, manifest id 是 `hybas-eu-lev05`(`kind=zip`).
