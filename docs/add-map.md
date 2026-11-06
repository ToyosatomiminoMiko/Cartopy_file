# 新增图种或共享模块

照着这个清单做, 新图种就能接进数据清单,文档和出图约定. 想看最小可运行例子, 读
[`AmericaArmy/`](../AmericaArmy): `config.py`(数据与规格) + `main.py`(唯一入口) +
`america_army.py`(draw 回调 + config 里声明的标签), 没有历史包袱.

## 新增图种

### 1. 建目录与 `config.py`

新目录 `<Name>/`, 里面至少三个文件: `config.py`(数据 + 规格),`main.py`(唯一可执行入口),
绘图模块(`<name>.py`). `config.py` 必须导出
`DATASETS` 与 `SHEETS`, 工具(`download_data.py --check`,`tools/check_geo.py`)会自动收录,
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

SHEET = Sheet(id="myanmar", out="myanmar_topography.svg", extent=EXTENT, ...)
SHEETS = sheets_of([SHEET])
```

- 产物目录约定: 地图写到 `<Name>/map/<stem>.svg`, 文字信息写到 `<Name>/text/<stem>.geo.json`,
  同一张图两个文件 stem 相同; `Sheet.out` 只写地图文件名, 不要带 `map/`, 目录由
  `spec.map_path`/`text_path` 拼;
- 数据目录约定: `<Name>/data/raw/` 放下载原样, `<Name>/data/derived/` 放脚本生成物;
- 数据源只引用 [`sources.py`](../src/cartopy_file/sources.py) 里已登记的 id; 新数据源先在那
  一个文件里登记 URL/版本/许可/署名, 并在 [`data-preparation.md`](data-preparation.md) 的
  "数据源与许可"表里加一行;
- 一个子项目出多张图(伏尔加)就写多个 `Sheet`, 都放进 `SHEETS`, 由入口的 `--sheet` 选择.

### 2. 入口 `main.py`

每个子项目**只有一个可执行文件** `main.py`: 用 argparse 子命令编排 `download` / `prepare` /
`render` / `all`, 分派时懒导入模块(下载路径不导入绘图栈), 每个分支返回退出码.

```python
import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 缓存目录必须在导入 matplotlib 之前指定, 见 docs/reference/data.md.
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / ".mplcache"))

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="main.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render", help="出图")
    render.add_argument("--dpi", type=int, default=None)
    render.add_argument("--show", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "render":
        import myanmar  # 懒导入: 只有出图才拉绘图栈
        return myanmar.run(dpi=args.dpi, show=args.show)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
```

- 子命令按需要增减: 没有派生需求就没有 `prepare`, 没有下载就没有 `download`;
- 所有选项(如 `--stride`,`--sheet`)在入口里定义, 模块只收关键字参数, 不自己解析命令行;
- 入口 docstring 加 `完整说明: docs/...` 指针(`check_docs.py` 会校验每个 `.py` 都有文档指针).

### 3. 绘图模块

模块顶部顺序是硬约束(`MPLCONFIGDIR` 必须在导入 matplotlib 之前设好), 之后只写一对回调:

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
    ...
    layers.add_cities(ctx.ax, SHEET.cities)
    layers.add_gridlines(ctx.ax, SHEET)

# 图例/文案都声明在 Sheet 里(legend/legend_title/title/notes), 没有动态数据时
# 不用写 collect: runner.render(collect=None) 缺省会调 standard_collect.
def collect(doc, ctx):  # 只有在有出图时才知道的数据时才写
    layers.standard_collect(doc, ctx.ax, SHEET, DATASETS)

def run(*, stride=None, dpi=None, show=False) -> int:
    etopo = find_etopo(ROOT / "data" / "raw", "<region>", stride)
    runner.render(SHEET, root=ROOT, catalog=DATASETS, draw=draw,
                  dem_path=etopo, dpi=dpi, show=show)
    return 0

if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python <Name>/main.py render")
```

- 绘图模块**不能直接运行**: 直接执行时只打印指向入口的错误; 参数由入口传入;
- 绘图模块**不写任何文字**: 地名/标题/图例/色标/刻度/注与来源都由 `miko_svg_editor` 的前端
  排版接管; 模块只画地理图形, 把这些信息往 `GeoDoc` 里登记(见
  [reference/geo.md](reference/geo.md) 与 [reference/layers.md](reference/layers.md));
- 新增标注时只选一个 role, 再给 text/坐标/字号; **不要写**颜色/描边/斜体/旋转(样式唯一真源
  是 `miko_svg_editor` 的 `src/config/text-style.ts`);
- 地形/晕渲/海陆底色不要复制: 用 [reference/layers.md](reference/layers.md) 与
  [reference/relief.md](reference/relief.md) 的函数; 边界重合剪枝用
  [reference/overlap.md](reference/overlap.md); 几何修复/写 GeoJSON 用
  [reference/geometry.md](reference/geometry.md).

### 4. 数据准备模块

- 文件名 `download_*.py`(下载原始数据)或 `prepare_*.py`(加工派生数据), 放同一目录;
- **一个模块只做一件事**: `download_*.py` 只写 `data/raw/`(下载/解压/入库, 不加工),
  `prepare_*.py` 只读 `raw/`,只写 `data/derived/`(不联网); 两者只导出 `run()`, 不带命令行
  入口, 由入口的 `download` / `prepare` 子命令调用, 不互相 import 私有函数; 需要同时有两者时
  是入口的两个子命令, 见 [data-preparation.md](data-preparation.md) 的准备命令总表;
- 下载一律走 [`cartopy_file.fetch`](../src/cartopy_file/fetch.py): `download()` 自带 `.part`
  续传,重试,内容魔数校验与可选 sha256, `post()` 用于 Overpass 这类实时查询接口,
  `extract_zip()` 解压并留 `.unpacked` 标记; URL/目标路径来自 `config.py` 的 `Dataset`;
- 幂等: 下载脚本文件已存在且非空就跳过, 提供 `--force` 覆盖; 派生脚本每次全量重建(产物可
  随时删), 不要各写一份下载循环;
- 产物落在 `data/raw/` 或 `data/derived/` 下, 并遵守"不入库"约定.

### 5. 文档

- 新建 `docs/maps/<slug>.md`, 按 [conventions.md](conventions.md) 的模板写, 元信息三行
  (`源码` / `入口` / `产物`)必填;
- 在 [index.md](index.md) 的图种表加一行(入口列写出图命令);
- 在 [data-preparation.md](data-preparation.md) 的"准备命令总表"加入口命令; 用到新数据源时补
  "数据源与许可"表(并先在 `sources.py` 登记);
- 入口与模块 docstring 的 `完整说明:` 指向新页面.

### 6. 自检

```bash
python download_data.py --check                                # 新数据已自动进清单
python <Name>/main.py render                                   # 出图
python <Name>/main.py render                                   # 再跑一次, 产物(`map/` 下的 SVG 与 `text/` 下的 geo.json)应字节级不变
python <Name>/main.py download                                 # 子命令各自可单独跑, 也能 `all` 串起来
python tools/check_geo.py                                      # 无参: 产物清单由 config.py 自动派生, 不用手改
python tools/check_docs.py                                     # 文档链接/模板/索引全绿
```

## 新增共享模块

- 放 `src/cartopy_file/<module>.py`; 只有确实被多个子项目使用才上移, 单图种逻辑留在子目录;
- 顶层 `__init__.py` 只重导出纯数据模块(`data`/`output`, 现在是 `data`/`datasets`/`spec`/
  `sources`/`output`); 会拉进 matplotlib/cartopy 的模块(`geo`/`relief`/`layers`/`runner`)
  一律按子模块导入, 否则「数据准备脚本不 import matplotlib」和「工具不 import 绘图栈」两条
  约束会一起破掉;
- 纯几何/纯数据模块(如 `overlap`,`geometry`,`spec`,`datasets`)不要 import matplotlib/cartopy;
- 建 `docs/reference/<module>.md`(模板见 [conventions.md](conventions.md)), 并在
  [index.md](index.md) 与 [overview.md](overview.md) 的模块表里加一行;
- 改了被多个图种调用的函数时, 先 `grep` 出全部调用点, 再逐个跑受影响的脚本验证.

## 一次性脚本

- 临时/一次性脚本不要建文档页, 也不要在 `config.py` 里声明成必需数据集(除非产物确实要长期保留);
- 在脚本 docstring 里指向所属图种页, 在对应图种页或 [data-preparation.md](data-preparation.md)
  里用一段说明它的用途和是否还需要.
