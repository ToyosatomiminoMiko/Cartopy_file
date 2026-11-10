# 新增图种或共享模块

照着这个清单做, 新图种就能接进数据清单,文档和出图约定. 工作分两边: **渲染仓**写绘图规格与
绘图模块, **数据项目 `miko_gis_data`** 声明数据集并发布清单; 两边只靠 `manifest.json` 耦合
(契约见 [reference/manifest.md](reference/manifest.md)). 想看最小可运行例子, 读
[`AmericaArmy/`](../AmericaArmy): `config.py`(`DATA_GROUP` + 规格) + `main.py`(唯一入口) +
`america_army.py`(draw 回调), 数据只有共享 Natural Earth 图层, 没有历史包袱.

## 新增图种

### 1. 数据项目: 声明数据集并发布清单

先在数据项目里把这个区域的数据准备好:

- 新建 `src/miko_gis_data/regions/<region>/config.py`, 导出
  `DATASETS = dataset_set("<显示名>", ROOT, [...])`. 每条 `Dataset` 声明来源(`source_id`),
  下载地址,本地路径(`dest`, 相对 `<数据根>/<region>/`),就位 glob(`files`),覆盖范围(`bbox`),
  采样步长与版本;
- 下载/派生脚本放同一目录: `download_*.py` 只写 `raw/`(下载/解压/入库, 不加工),
  `prepare_*.py` 只读 `raw/`,只写 `derived/`(不联网); 两者只导出 `run()`, 由数据项目入口的
  `download` / `prepare` 子命令调用, 互不 import 私有函数;
- 需要新数据源时先在 `src/miko_gis_data/sources.py` 登记 URL 模板,版本,许可与进图署名, 再在
  `Dataset.source_id` 里引用; 同时更新数据项目的 `docs/data-preparation.md` 与本仓
  [data-preparation.md](data-preparation.md) 的"数据源与许可"表;
- 区域名(目录名)就是 manifest 的 group 键, 也是渲染侧 `DATA_GROUP` 的取值;
- 注意 `bbox` 要盖住投影后的画框四角(理由见 [data-preparation.md](data-preparation.md) 的
  ETOPO 一节), 出图时 `runner` 会核对;
- 最后在数据项目根目录跑:

```bash
python main.py download --group <region>
python main.py prepare --group <region>   # 没有派生需求时跳过
python main.py publish                    # 写 <数据根>/manifest.json
python main.py check --group <region>     # 应全部"已存在"
```

### 2. 渲染侧: 建目录与 `config.py`

新目录 `<Name>/`, 里面至少三个文件: `config.py`(规格 + `DATA_GROUP`),`main.py`(唯一可执行
入口), 绘图模块(`<name>.py`). `config.py` 必须导出 `DATA_GROUP` 与 `SHEETS`,
`tools/check_geo.py` 会自动收录产物, **不需要**再去改任何清单:

```python
from pathlib import Path

from cartopy_file.spec import Extent, Graticule, Projection, Relief, Sheet

ROOT = Path(__file__).resolve().parent
# 数据项目里这个区域的 manifest 键(group).
DATA_GROUP = "myanmar"

EXTENT = Extent(87.0, 106.0, 5.0, 31.0)
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
- `dataset_ids` 写数据项目里登记过的数据集 id, 顺序就是产物「数据来源」里署名的顺序;
- `dem_id` 指向其中的高程数据集, `runner` 用它核对面画框覆盖并读高程; 不铺高程的图留空;
- 数据集从哪里下,什么版本,放哪,都由数据项目声明, 本仓 `config.py` **不再有 `DATASETS`**;
- 产物目录约定: 地图写到 `<Name>/map/<stem>.svg`, 文字信息写到 `<Name>/text/<stem>.geo.json`,
  同一张图两个文件 stem 相同; `Sheet.out` 只写地图文件名, 不要带 `map/`, 目录由
  `spec.map_path`/`text_path` 拼;
- 一个子项目出多张图(伏尔加)就写多个 `Sheet`, 都放进 `SHEETS`, 由入口的 `--sheet` 选择.

### 3. 渲染侧: 入口 `main.py`

每个子项目**只有一个可执行文件** `main.py`, 只有 `render` 子命令; 分派时懒导入绘图模块
(命令行解析不加载绘图栈), 返回退出码. `--stride` / `--dpi` / `--show` 与多图子项目的
`--sheet` 都在这里定义:

```python
import argparse
import sys

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python Name/main.py")
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render", help="出图(地图 SVG + 同名 geo.json)")
    render.add_argument("--stride", type=int, default=None)
    render.add_argument("--dpi", type=int, default=None)
    render.add_argument("--show", action="store_true")
    return parser

def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from name import run as render_run
    return render_run(stride=args.stride, dpi=args.dpi, show=args.show)

if __name__ == "__main__":
    raise SystemExit(run())
```

- 没有 `download` / `prepare` / `all`: 数据准备在数据项目, 本仓入口只出图;
- 所有选项在入口里定义, 模块只收关键字参数, 不自己解析命令行;
- 入口 docstring 加 `完整说明: docs/...` 指针(`check_docs.py` 会校验每个 `.py` 都有文档指针).

### 4. 绘图模块

模块顶部顺序是硬约束(`MPLCONFIGDIR` 必须在导入 matplotlib 之前设好), 然后拿 `Catalog`,
只画图种特有的图层:

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
    ...  # 图种特有的图层, 按原成品的叠放顺序画
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

- 数据路径**只从 `Catalog` 取**: `CATALOG.raw_dir` / `CATALOG.derived_dir` 是
  `<数据根>/<region>/{raw,derived}`, `CATALOG.path("<id>")` 是清单里登记的主路径; 不要写
  `<子项目>/data/...` 这类相对脚本的路径;
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

### 5. 文档

- 新建 `docs/maps/<slug>.md`, 按 [conventions.md](conventions.md) 的模板写, 元信息三行
  (`源码` / `入口` / `产物`)必填;
- "数据"一节写**数据根相对**路径(`<数据根>/<region>/raw/...`,`<数据根>/<region>/derived/...`,
  共享图层写 `<数据根>/cartopy/...`), 准备方式写数据项目的命令
  (`python main.py download --group <region>` 等);
- 在 [index.md](index.md) 的图种表加一行(入口列写出图命令);
- 用到新数据源时更新 [data-preparation.md](data-preparation.md) 的"数据源与许可"表, 并同步
  数据项目的对应文档;
- 入口与模块 docstring 的 `完整说明:` 指向新页面.

### 6. 自检

```bash
cd miko_gis_data
python main.py check --group <region>      # 数据齐全/版本相符
python main.py publish --check             # 清单与配置一致
cd ..
python <Name>/main.py render               # 出图
python <Name>/main.py render               # 再跑一次, 产物应字节级不变
uv run python tools/check_geo.py           # 无参: 产物清单由 config.py 的 SHEETS 自动派生
uv run python tools/check_docs.py          # 文档链接/模板/索引/源码指针全绿
uv run python tools/check_all.py           # 收尾: 上面两项 + 全仓语法编译
```

- `check_geo` 对不存在的产物打印"跳过(不存在)", 那是未覆盖, 不是通过;
- 同一份数据连跑两次产物应字节级一致; 不一致说明引入了不确定性(时间戳/随机数/未排序字典).

## 新增共享模块

- 放 `src/cartopy_file/<module>.py`; 只有确实被多个子项目使用才上移, 单图种逻辑留在子目录;
- 顶层 `__init__.py` 只重导出纯数据/纯标准库模块(`data`/`catalog`/`spec`/`output`); 会拉进
  matplotlib/cartopy 的模块(`geo`/`relief`/`layers`/`runner`)一律按子模块导入, 否则
  「渲染不联网」与「工具不 import 绘图栈」两条约束会一起破掉;
- 纯几何/纯数据模块(如 `overlap`,`spec`)不要 import matplotlib/cartopy;
- 建 `docs/reference/<module>.md`(模板见 [conventions.md](conventions.md)), 并在
  [index.md](index.md) 与 [overview.md](overview.md) 的模块表里加一行;
- 改了被多个图种调用的函数时, 先 `grep` 出全部调用点, 再逐个跑受影响的脚本验证.

## 一次性脚本

- 临时/一次性脚本不要建文档页, 也不要让数据项目把它声明成必需数据集(除非产物确实要长期保留);
- 在脚本 docstring 里指向所属图种页, 在对应图种页或 [data-preparation.md](data-preparation.md)
  里用一段说明它的用途和是否还需要.
