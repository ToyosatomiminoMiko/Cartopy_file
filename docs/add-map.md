# 新增图种或共享模块

照着这个清单做, 新图种能接进现有数据清单、文档和出图约定.

## 新增图种

### 1. 建目录与绘图脚本

- 新目录 `<Name>/`, 里面放绘图脚本 `<name>.py` 和私有数据目录 `<Name>/data/`;
- 脚本顶部的导入顺序是硬约束(缓存目录必须在导入 matplotlib 之前设好):

```python
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
os.environ.setdefault("MPLCONFIGDIR", str(DATA_DIR / ".mplcache"))

import cartopy.crs as ccrs  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from cartopy_file.data import configure_cartopy  # noqa: E402
from cartopy_file.fonts import apply_matplotlib_fonts  # noqa: E402
from cartopy_file.output import apply_svg_output, save_svg  # noqa: E402
from cartopy_file.relief import find_etopo, load_elevation  # noqa: E402

configure_cartopy()
apply_matplotlib_fonts()
apply_svg_output()

OUT_SVG = ROOT / "<product>.svg"
```

- 地图上的文字标注要给稳定 id: `ax.text(..., gid=label_id(kind, name[, index]))`, 名称用数据里
  的键或图上的名字, 同一名字多次出现才加序号; 标题/图例/色标/经纬网刻度/比例尺/资料来源这类
  版式文字不加. 标签编辑器靠它认标签, 见 [`reference/labels.md`](reference/labels.md);
- `main()` 用 argparse 提供 `--stride` / `--dpi` / `--show`(与现有图种一致), 高程文件路径
  支持 `<NAME>_ETOPO_PATH` 环境变量, 最后 `save_svg(fig, OUT_SVG, dpi=args.dpi)`;
- 地形/晕渲/海陆底色不要复制: 用 [`reference/relief.md`](reference/relief.md) 的函数;
- 边界重合剪枝用 [`reference/overlap.md`](reference/overlap.md), 不要各写一份 difference.

### 2. 数据准备脚本

- 文件名 `download_*.py`(下载原始数据)或 `prepare_*.py`(加工派生数据), 放同一目录;
- 幂等: 文件已存在且非空就跳过, 提供 `--force` 覆盖; 有需要时提供 `--check`(只检查不联网);
- 产物落在 `<Name>/data/` 下, 并遵守"不入库"约定(`**/data` 已被 `.gitignore` 忽略);
- 下载失败/中断要能重跑: 用 `.part` + Range 续传, 下载后校验文件头(参考各图种的 ETOPO
  下载实现, 见 [`data-preparation.md`](data-preparation.md)).

### 3. 接进全项目清单

改根目录 `download_data.py`, 否则 `python download_data.py --check` 不会提示新数据:

- 用到新的 cartopy 内置要素 → 往 `NE_FEATURES` 加一行(分辨率/类别/名称/使用位置), 名称必须
  与 `cartopy.feature` 里的一致;
- 新的本地数据 → 往 `LOCAL_DATA` 加一行(分组/说明/相对仓库根的 glob/准备命令);
- 缺失不影响出图的缓存 → 放 `OPTIONAL_DATA`.

### 4. 文档

- 新建 `docs/maps/<slug>.md`, 按 [`conventions.md`](conventions.md) 的模板写;
- 在 [`index.md`](index.md) 的图种表加一行;
- 在 [`data-preparation.md`](data-preparation.md) 的"准备命令总表"加命令, 需要新数据源时
  补"数据源与许可"表;
- 脚本模块 docstring 的 `完整说明:` 指向新页面.

### 5. 自检

```bash
python download_data.py --check   # 新数据已进清单且能检查到
python <Name>/<name>.py           # 出图
python <Name>/<name>.py           # 再跑一次, 产物应字节级不变(理由见 reference/output.md)
# 先改 tools/label_editor.toml 的 svg 指向新产物
python tools/label_editor.py      # 标签能拖、保存后重跑仍生效
python tools/check_docs.py        # 文档链接/模板/索引全绿
```

## 新增共享模块

- 放 `src/cartopy_file/<module>.py`; 只有确实被多个图种使用才上移, 单图种逻辑留在图种目录;
- 顶层 `__init__.py` 是否重导出要谨慎: 重导出会把该模块的依赖带给**所有**脚本; 现有约定是
  `data` / `fonts` / `output` 重导出, `relief` / `overlap` 按子模块导入;
- 纯几何模块(如 `overlap`)不要 import matplotlib/cartopy, 让数据准备脚本也能用;
- 建 `docs/reference/<module>.md`(模板见 [`conventions.md`](conventions.md)), 并在
  [`index.md`](index.md) 与 [`overview.md`](overview.md) 的模块表里加一行;
- 改了被多个图种调用的函数时, 同步检查各图种的调用点.

## 一次性脚本

- 临时/一次性脚本不要建文档页, 也不要放进 `download_data.py` 的必需清单(除非产物确实要长期
  保留);
- 在脚本 docstring 里指向所属图种页, 在对应图种页或 [`data-preparation.md`](data-preparation.md)
  里用一段说明它的用途和是否还需要.
