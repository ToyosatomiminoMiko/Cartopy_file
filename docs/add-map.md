# 新增图种或共享模块

照着这个清单做, 新图种就能接进数据清单,文档和出图约定. 工作分三段: **数据项目
`miko_gis_data`** 下载/入库/解压原始数据并发布清单, **本仓 `prepare.py`** 按图种口径清洗/
派生到 `<子项目>/build/`, **本仓绘图模块**只读本地文件出图; 两仓只靠 `manifest.json` 耦合
(契约见 [reference/manifest.md](reference/manifest.md)). 想看最小可运行例子, 读
[`AmericaArmy/`](../AmericaArmy): `config.py`(`DATA_GROUP` + 规格) + `main.py`(唯一入口) +
`america_army.py`(draw 回调), 数据只有共享 Natural Earth 图层, 没有派生步骤.

## 新增图种

### 1. 数据项目: 声明数据集并发布清单

先在数据项目里把这个区域的**原始数据**准备好(不产生派生数据):

- 新建 `src/miko_gis_data/regions/<region>/config.py`, 导出
  `DATASETS = dataset_set("<显示名>", ROOT, [...])`. 每条 `Dataset` 声明来源(`source_id`),
  下载地址,本地路径(`dest`, 相对 `<数据根>/<region>/`),就位 glob(`files`),覆盖范围(`bbox`),
  采样步长与版本;
- 下载脚本放同一目录, 命名 `download_*.py`: 只写 `raw/`(下载/解压/入库, 不加工), 只导出
  `run()`, 由数据项目入口的 `download` 子命令调用. 数据项目没有 `prepare` 子命令, 也不写
  `derived` 数据集;
- 需要新数据源时先在 `src/miko_gis_data/sources.py` 登记 URL 模板,版本,许可与进图署名, 再在
  `Dataset.source_id` 里引用; 同时更新数据项目的 `docs/data-preparation.md` 与本仓
  [data-preparation.md](data-preparation.md) 的"数据源与许可"表;
- 区域名(目录名)就是 manifest 的 group 键, 也是渲染侧 `DATA_GROUP` 的取值;
- 注意 `bbox` 要盖住投影后的画框四角(理由见 [data-preparation.md](data-preparation.md) 的
  ETOPO 一节), 出图时 `runner` 会核对;
- 最后在数据项目根目录跑:

```bash
python main.py download --group <region>   # 原始数据进 <数据根>/<region>/raw/
python main.py publish                     # 写 <数据根>/manifest.json
python main.py check --group <region>      # 应全部"已存在"
```

### 2. 渲染侧: 建目录与 `config.py`

新目录 `<Name>/`, 里面至少三个文件: `config.py`(规格 + `DATA_GROUP` + 派生路径),`main.py`
(唯一可执行入口), 绘图模块(`<name>.py`); 需要派生数据时再加 `prepare.py`.
`config.py` 必须导出 `DATA_GROUP` 与 `SHEETS`, `tools/check_geo.py` 会自动收录产物, **不需要**
再去改任何清单:

```python
from pathlib import Path

from cartopy_file.spec import Extent, Graticule, Projection, Relief, Sheet, build_path

ROOT = Path(__file__).resolve().parent
# 数据项目里这个区域的 manifest 键(group).
DATA_GROUP = "myanmar"

# 派生数据: 本仓 prepare.py 生成, 不属于数据根(见 docs/reference/prepare.md).
DERIVED_GEOJSON = build_path(ROOT, "myanmar_admin1.geojson")

EXTENT = Extent(87.0, 106.0, 5.0, 26.0)
SHEET = Sheet(
    id="myanmar",
    out="myanmar_topography.svg",
    extent=EXTENT,
    projection=Projection("lambert_conformal", {...}),
    relief=Relief(vmin=-5000, vmax=5000, name="myanmar_relief", ...),
    graticule=Graticule(3.0, 5.0, lon_ticks=(...), lat_ticks=(...)),
    dataset_ids=("etopo-myanmar", "ne-countries-10m"),
    dem_id="etopo-myanmar",
    labels=(...),
    title="缅甸联邦共和国全境地形图",
)
SHEETS = (SHEET,)
```

- `DATA_GROUP` 必须与数据项目 `regions/<region>/` 的目录名一致, 否则 `catalog_for()` 报
  "manifest 里没有区域";
- `dataset_ids` 写数据项目里登记过的**原始**数据集 id, 顺序就是产物「数据来源」里署名的顺序;
  派生文件不在清单里, 不进 `dataset_ids`;
- 派生路径用 `spec.build_path(ROOT, "<文件名>")` 声明, 产物固定在本子项目 `build/` 下;
- `dem_id` 指向其中的高程数据集, `runner` 用它核对面画框覆盖并读高程; 不铺高程的图留空;
- 数据集从哪里下,什么版本,放哪,都由数据项目声明; 本仓 `config.py` 只写本子项目的规格与
  `DATA_GROUP`, 不重复数据集清单;
- 产物目录约定: 地图写到 `<Name>/map/<stem>.svg`, 文字信息写到 `<Name>/text/<stem>.geo.json`,
  同一张图两个文件 stem 相同; `Sheet.out` 只写地图文件名, 不要带 `map/`, 目录由
  `spec.map_path`/`text_path` 拼;
- 一个子项目出多张图(伏尔加)就写多个 `Sheet`, 都放进 `SHEETS`, 由入口的 `--sheet` 选择.

### 3. 渲染侧: `prepare.py`(只有需要派生数据的图种)

如果这张图需要清洗/裁剪/拼装原始数据, 新建 `<Name>/prepare.py`:

```python
"""按本图口径派生数据; 命令行入口是 python <Name>/main.py prepare.

完整说明见 ``docs/reference/prepare.md`` 与 ``docs/maps/<slug>.md``.
"""

import config
from cartopy_file.catalog import catalog_for
from cartopy_file.geometry import feature, write_geojson

CATALOG = catalog_for(config.DATA_GROUP)
RAW = CATALOG.path("<原始数据集 id>")
OUT = config.DERIVED_GEOJSON

def run() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write_geojson(OUT, [feature(..., {...})])
    return 0

if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python <Name>/main.py prepare")
```

- 只读数据清单指向的 `raw/` 与共享 Natural Earth 图层, **不联网**; 缺数据时 `FileNotFoundError`
  并给出数据项目 `download --group <region>` 命令;
- 只写 `<Name>/build/`, 不写数据根, 不手写数据来源;
- 几何修复/拆面线/删小孔/写确定性 GeoJSON/量面积长度用
  [reference/geometry.md](reference/geometry.md), 不要各写一份;
- 产物必须可复现: 不写时间戳, 不依赖未排序的集合, 坐标精度与键序固定.

### 4. 渲染侧: 入口 `main.py`

每个子项目**只有一个可执行文件** `main.py`, 有派生数据的图种提供 `prepare` 与 `render`
两个子命令; 分派时懒导入模块(解析命令行不加载绘图栈), 返回退出码. `--stride` / `--dpi` /
`--show` 与多图子项目的 `--sheet` 都在这里定义:

```python
import argparse
import sys

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python Name/main.py")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="读数据仓原始数据, 重建 <Name>/build/ 下的派生 GeoJSON")
    render = sub.add_parser("render", help="出图(地图 SVG + 同名 geo.json)")
    render.add_argument("--stride", type=int, default=None)
    render.add_argument("--dpi", type=int, default=None)
    render.add_argument("--show", action="store_true")
    return parser

def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        from prepare import run as prepare_run
        return prepare_run()
    from name import run as render_run
    return render_run(stride=args.stride, dpi=args.dpi, show=args.show)

if __name__ == "__main__":
    raise SystemExit(run())
```

- 没有 `download` / `all`: 下载/解压在数据项目, 本仓入口只做 `prepare` 与 `render`;
- 所有选项在入口里定义, 模块只收关键字参数, 不自己解析命令行;
- 入口 docstring 加 `完整说明: docs/...` 指针(`check_docs.py` 会校验每个 `.py` 都有文档指针).

### 5. 绘图模块

模块顶部顺序是硬约束(`MPLCONFIGDIR` 必须在导入 matplotlib 之前设好), 然后拿 `Catalog`,
只画图种特有的图层; 需要派生数据时读 `config.py` 里 `build_path(...)` 给的路径:

```python
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / ".mplcache"))

import config
from cartopy_file import layers, runner
from cartopy_file.catalog import catalog_for
from cartopy_file.relief import find_etopo

SHEET = config.SHEET
CATALOG = catalog_for(config.DATA_GROUP)

def draw(ctx):
    ...  # 图种特有的图层, 按该图种要求的叠放顺序画
    layers.add_cities(ctx.ax, SHEET.cities)
    layers.add_gridlines(ctx.ax, SHEET)

def run(*, stride=None, dpi=None, show=False) -> int:
    etopo = find_etopo(CATALOG.raw_dir, "<region>", stride)
    runner.render(SHEET, root=ROOT, catalog=CATALOG, draw=draw,
                  dem_path=etopo, dpi=dpi, show=show)
    return 0

if __name__ == "__main__":
    raise SystemExit("本文件是模块, 不能直接运行; 请用统一入口: python <Name>/main.py render")
```

- 数据路径**只从 `Catalog` 或 `config.build_path(...)` 取**: `CATALOG.raw_dir` 是
  `<数据根>/<region>/raw`, `CATALOG.path("<id>")` 是清单里登记的原始数据主路径; 派生 GeoJSON
  用 `config.py` 里的 `build_path(...)` 常量; 不要写 `<子项目>/data/...` 这类相对脚本的路径;
- 图例/文案都声明在 `Sheet` 里(legend/legend_title/title/notes), 没有动态数据时不用写
  `collect`: `runner.render(collect=None)` 缺省会调 `standard_collect`, 「数据来源」由
  `Catalog.citation(sheet.dataset_ids)` 自动生成;
- 绘图模块**不写任何文字**: 地名/标题/图例/色标/刻度/注与来源都由 `miko_svg_editor` 的前端
  排版接管; 模块只画地理图形, 把这些信息往 `GeoDoc` 里登记(见
  [reference/geo.md](reference/geo.md) 与 [reference/layers.md](reference/layers.md));
- 新增标注时只选一个 role, 再给单行 text/坐标(text 里不写换行, 折行由前端负责);
  **不要写**字号/颜色/描边/斜体/旋转(样式唯一真源是 `miko_svg_editor` 的
  `src/config/text-style.ts`);
- 地形/晕渲/海陆底色不要复制: 用 [reference/layers.md](reference/layers.md) 与
  [reference/relief.md](reference/relief.md) 的函数; 边界重合剪枝用
  [reference/overlap.md](reference/overlap.md).

### 6. 文档

- 新建 `docs/maps/<slug>.md`, 按 [conventions.md](conventions.md) 的模板写, 元信息三行
  (`源码` / `入口` / `产物`)必填;
- "数据"一节写**数据根相对**路径(`<数据根>/<region>/raw/...`, 共享图层写
  `<数据根>/cartopy/...`)与派生文件(`<子项目>/build/...`), 准备方式写数据项目的
  `download` 命令与本仓的 `prepare` 命令;
- 在 [index.md](index.md) 的图种表加一行(入口列写出图命令);
- 用到新数据源时更新 [data-preparation.md](data-preparation.md) 的"数据源与许可"表, 并同步
  数据项目的对应文档;
- 入口,`prepare.py` 与绘图模块 docstring 的 `完整说明:` 指向新页面(或
  [reference/prepare.md](reference/prepare.md)).

### 7. 自检

```bash
(cd ../miko_gis_data && python main.py check --group <region>)      # 原始数据齐全/版本相符
(cd ../miko_gis_data && python main.py publish --check)             # 清单与配置一致
python <Name>/main.py prepare              # 有派生数据时: 生成 <Name>/build/
python <Name>/main.py render               # 出图
python <Name>/main.py render               # 再跑一次, 产物应字节级不变
uv run python tools/check_geo.py           # 无参: 产物清单由 config.py 的 SHEETS 自动派生
uv run python tools/check_docs.py          # 文档链接/模板/索引/源码指针全绿
uv run python tools/check_all.py           # 收尾: 上面两项 + 全仓语法编译
```

- `check_geo` 对不存在的产物打印"跳过(不存在)", 那是未覆盖, 不是通过;
- 同一份数据连跑两次产物应字节级一致; 不一致说明引入了不确定性(时间戳/随机数/未排序字典).
  派生文件同理: 两次 `prepare` 应逐字节一致.

## 新增共享模块

- 放 `src/cartopy_file/<module>.py`; 只有确实被多个子项目使用才放进共享包, 单图种逻辑留在
  子目录(`geometry` 是各子项目 `prepare.py` 共用的纯几何层);
- 顶层 `__init__.py` 只重导出纯数据/纯标准库模块(`data`/`catalog`/`spec`/`output`); 会拉进
  matplotlib/cartopy 的模块(`geo`/`relief`/`layers`/`runner`)一律按子模块导入, 否则
  「渲染不联网」与「工具不 import 绘图栈」两条约束会一起破掉;
- 纯几何/纯数据模块(如 `overlap`,`spec`,`geometry`)不要 import matplotlib/cartopy
  (`geometry` 只依赖 shapely/pyproj/pandas, `prepare` 与 `tools/` 都要用);
- 建 `docs/reference/<module>.md`(模板见 [conventions.md](conventions.md)), 并在
  [index.md](index.md) 与 [overview.md](overview.md) 的模块表里加一行;
- 改了被多个图种调用的函数时, 先 `grep` 出全部调用点, 再逐个跑受影响的脚本验证.

## 一次性脚本

- 临时/一次性脚本不要建文档页, 也不要让数据项目把它声明成必需数据集(除非产物确实要长期保留);
- 在脚本 docstring 里指向所属图种页, 在对应图种页或 [data-preparation.md](data-preparation.md)
  里用一段说明它的用途和是否还需要.
