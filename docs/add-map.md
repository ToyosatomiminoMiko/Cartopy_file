# 新增图种或共享模块

照着这个清单做, 新图种就能接进数据清单、文档和出图约定. 想看最小可运行例子, 读
[`AmericaArmy/`](../AmericaArmy) 的 `config.py` + `main.py`: 全项目里唯一一个「一个文件放数据
清单, 一个文件放一对回调」的演示, 没有历史包袱.

## 新增图种

### 1. 建目录与 `config.py`

新目录 `<Name>/`, 里面至少两个文件: `config.py`(数据 + 规格)和绘图脚本. `config.py` 必须导出
`DATASETS` 与 `SHEETS`, 工具(`download_data.py --check`、`tools/check_geo.py`)会自动收录,
**不需要**再去改任何清单:

```python
from pathlib import Path

from cartopy_file.datasets import Dataset, dataset_set
from cartopy_file.sources import erddap_url, ne_url
from cartopy_file.spec import Extent, Graticule, Projection, Relief, Sheet, sheets_of

ROOT = Path(__file__).resolve().parent
EXTENT = Extent(87.0, 106.0, 5.0, 31.0)
# 下载范围从画框推出来: 与绘图共用同一个 extent, 不再另写一份.
BBOX = EXTENT.padded(lon=1.7, lat=0.1)

DATASETS = dataset_set("缅甸", ROOT / "data", [
    Dataset(id="etopo-myanmar", kind="file", source_id="etopo-2022",
            url=erddap_url("etopo-2022", stride=2,
                           lon_range=(BBOX.lon_min, BBOX.lon_max),
                           lat_range=(BBOX.lat_min, BBOX.lat_max)),
            dest="raw/ETOPO_2022_v1_15s_myanmar_stride2.nc",
            files=("raw/ETOPO_2022_v1_15s_myanmar_stride*.nc",),
            bbox=BBOX, stride=2, note="ETOPO 2022 缅甸区域高程"),
    Dataset(id="ne-countries-10m", kind="cartopy-ne", source_id="natural-earth",
            resolution="10m", category="cultural", name="admin_0_countries",
            version_file="ne_10m_admin_0_countries.VERSION.txt"),
])

SHEET = Sheet(id="myanmar", out="myanmar_topography.svg", extent=EXTENT, …)
SHEETS = sheets_of([SHEET])
```

- 产物目录约定: 地图写到 `<Name>/map/<stem>.svg`, 文字信息写到 `<Name>/text/<stem>.geo.json`,
  同一张图两个文件 stem 相同; `Sheet.out` 只写地图文件名, 不要带 `map/`, 目录由
  `spec.map_path`/`text_path` 拼;
- 数据目录约定: `<Name>/data/raw/` 放下载原样, `<Name>/data/derived/` 放脚本生成物;
- 数据源只引用 [`sources.py`](../src/cartopy_file/sources.py) 里已登记的 id; 新数据源先在那
  一个文件里登记 URL/版本/许可/署名, 并在 [`data-preparation.md`](data-preparation.md) 的
  "数据源与许可"表里加一行;
- 一个脚本出多张图(伏尔加)就写多个 `Sheet`, 都放进 `SHEETS`.

### 2. 绘图脚本

脚本顶部顺序是硬约束(`MPLCONFIGDIR` 必须在导入 matplotlib 之前设好), 之后只写一对回调:

```python
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / ".mplcache"))

import config
from cartopy_file import layers, runner
from cartopy_file.relief import find_etopo

SHEET, DATASETS = config.SHEET, config.DATASETS

def draw(ctx):          # 图种特有的图层, 顺序与改前成品一致
    …
    layers.add_cities(ctx.ax, SHEET.cities)
    layers.add_gridlines(ctx.ax, SHEET)

def collect(doc, ctx):  # 登记 geo
    layers.standard_collect(doc, ctx.ax, SHEET, DATASETS)

def main():
    parser = build_parser()   # runner.add_standard_arguments(parser) 提供 --dpi/--show
    runner.render(SHEET, root=ROOT, catalog=DATASETS, draw=draw, collect=collect,
                  dem_path=find_etopo(ROOT / "data" / "raw", "<region>"))
```

- 绘图脚本**不写任何文字**: 地名/标题/图例/色标/刻度/注与来源都由 `miko_svg_editor` 的前端
  排版接管; 脚本只画地理图形, 把这些信息往 `GeoDoc` 里登记(见
  [reference/geo.md](reference/geo.md) 与 [reference/layers.md](reference/layers.md));
- 新增标注时只选一个 role, 再给 text/坐标/字号; **不要写**颜色/描边/斜体/旋转(样式唯一真源
  是 `miko_svg_editor` 的 `src/config/text-style.ts`);
- 地形/晕渲/海陆底色不要复制: 用 [reference/layers.md](reference/layers.md) 与
  [reference/relief.md](reference/relief.md) 的函数; 边界重合剪枝用
  [reference/overlap.md](reference/overlap.md).

### 3. 数据准备脚本

- 文件名 `download_*.py`(下载原始数据)或 `prepare_*.py`(加工派生数据), 放同一目录;
- **一个脚本只做一件事**: `download_*.py` 只写 `data/raw/`(下载/解压/入库, 不加工),
  `prepare_*.py` 只读 `raw/`、只写 `data/derived/`(不联网); 两者各自有 `main()` 与
  `--check` 提示, 不互相 import 私有函数. 需要同时有两者时是两条独立命令, 见
  [data-preparation.md](data-preparation.md) 的准备命令总表;
- 下载一律走 [`cartopy_file.fetch`](../src/cartopy_file/fetch.py): `download()` 自带 `.part`
  续传、重试、内容魔数校验与可选 sha256, `post()` 用于 Overpass 这类实时查询接口,
  `extract_zip()` 解压并留 `.unpacked` 标记; URL/目标路径来自 `config.py` 的 `Dataset`;
- 幂等: 下载脚本文件已存在且非空就跳过, 提供 `--force` 覆盖; 派生脚本每次全量重建(产物可
  随时删), 不要各写一份下载循环;
- 产物落在 `data/raw/` 或 `data/derived/` 下, 并遵守"不入库"约定.

### 4. 文档

- 新建 `docs/maps/<slug>.md`, 按 [conventions.md](conventions.md) 的模板写;
- 在 [index.md](index.md) 的图种表加一行;
- 在 [data-preparation.md](data-preparation.md) 的"准备命令总表"加命令; 用到新数据源时补
  "数据源与许可"表(并先在 `sources.py` 登记);
- 脚本模块 docstring 的 `完整说明:` 指向新页面.

### 5. 自检

```bash
python download_data.py --check   # 新数据已自动进清单
python <Name>/<name>.py           # 出图
python <Name>/<name>.py           # 再跑一次, 产物(`map/` 下的 SVG 与 `text/` 下的 geo.json)应字节级不变
python tools/check_geo.py         # 无参: 产物清单由 config.py 自动派生, 不用手改
python tools/check_docs.py        # 文档链接/模板/索引全绿
```

## 新增共享模块

- 放 `src/cartopy_file/<module>.py`; 只有确实被多个子项目使用才上移, 单图种逻辑留在子目录;
- 顶层 `__init__.py` 只重导出纯数据模块(`data`/`output`, 现在是 `data`/`datasets`/`spec`/
  `sources`/`output`); 会拉进 matplotlib/cartopy 的模块(`geo`/`relief`/`layers`/`runner`)
  一律按子模块导入, 否则「数据准备脚本不 import matplotlib」和「工具不 import 绘图栈」两条
  约束会一起破掉;
- 纯几何/纯数据模块(如 `overlap`、`spec`、`datasets`)不要 import matplotlib/cartopy;
- 建 `docs/reference/<module>.md`(模板见 [conventions.md](conventions.md)), 并在
  [index.md](index.md) 与 [overview.md](overview.md) 的模块表里加一行;
- 改了被多个图种调用的函数时, 先 `grep` 出全部调用点, 再逐个跑受影响的脚本验证.

## 一次性脚本

- 临时/一次性脚本不要建文档页, 也不要在 `config.py` 里声明成必需数据集(除非产物确实要长期保留);
- 在脚本 docstring 里指向所属图种页, 在对应图种页或 [data-preparation.md](data-preparation.md)
  里用一段说明它的用途和是否还需要.
