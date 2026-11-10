# 数据清单读取 (cartopy_file.catalog)

- 源码: [`src/cartopy_file/catalog.py`](../../src/cartopy_file/catalog.py)
- 导入: `from cartopy_file.catalog import Catalog, DatasetView, SourceInfo, catalog_for`

## 是什么

数据清单(`<数据根>/manifest.json`)的**只读视图**. 独立数据项目 `miko_gis_data` 把各区域的
数据集事实写进这份 JSON, 本仓按它取路径,判断数据是否就位,并复算产物里的「数据来源」署名.

- `catalog_for(group)`: 按区域名(manifest 的 group 键, 即子项目 `config.py` 的 `DATA_GROUP`)
  取一个 `Catalog`; 进程内缓存;
- `Catalog`: 一个区域的清单集合. `get(id)` 取 `DatasetView`, `path(id)` 给主路径,
  `exists(id)` 判就位, **`raw_dir` / `derived_dir`** 给区域数据目录, `citation(ids)` 折署名;
- `DatasetView`: 一份数据集的只读视图, 字段与数据项目的 `Dataset` 一一对应(少了下载参数);
- `SourceInfo`: 数据来源的静态事实, 用于复算署名.

为什么用 JSON 而不是 import 数据项目: 数据项目要能单独移走, 两个仓库只靠这份文件格式耦合;
渲染仓不安装数据项目的 Python 包, 数据项目也不依赖绘图栈. 字段与版本见
[manifest.md](manifest.md).

## 关键行为

### 清单的加载与校验

- 第一次调用 `catalog_for()` 时才读 `<数据根>/manifest.json`(位置由
  [`data.manifest_path()`](data.md) 给出), 之后整个进程复用同一份解析结果;
- 文件不存在: `FileNotFoundError`, 提示到数据项目运行 `python main.py all`, 或把
  `CARTOPY_FILE_DATA` 指向已就绪的数据根;
- `format` 必须是 `miko-gis-data/manifest`: 否则 `RuntimeError`, 提示用当前版本的数据项目重新
  `publish`;
- `version` 必须是 `1`(模块常量 `SUPPORTED_VERSION`): 否则 `RuntimeError`, 提示同步升级/降级
  两边的仓库. 本模块只读它支持的版本, 不猜字段;
- group 不存在: `KeyError`, 列出 manifest 里已发布的区域名. 常见原因是 `DATA_GROUP` 与数据
  项目的 `regions/<region>/` 目录名不一致.

### `Catalog`

- 属性: `group`(区域名), `title`(清单里的显示名), `root`(`<数据根>/<group>`),
  `items`(该区域的 `DatasetView` 元组); 支持 `iter()` 与 `len()`;
- `get(dataset_id)`: 按 id 取; id 写错时 `KeyError`, 消息里列出该区域所有可用 id;
- `raw_dir` / `derived_dir`: `<数据根>/<group>/raw` 与 `<数据根>/<group>/derived`;
- `patterns(dataset)`: 判定"就位"用的 glob(相对区域数据目录); 取 `files`, 为空时退回
  `(dest,)`;
- `path(dataset)`: 主路径. `kind="cartopy-ne"` 时按 `resolution/category/name` 走 cartopy 的
  Natural Earth 缓存定位([`data.natural_earth_paths()`](data.md)), 返回缓存里已存在的那份
  (不存在时返回目标路径); 其余 kind 返回 `root / dest`, 没有 `dest` 时 `ValueError`;
- `exists(dataset)`: 只查本地, 不联网. `cartopy-ne` 看主路径是不是文件; 其余按 `patterns`
  逐个 glob, 真正取出一个匹配项才算存在(`Path.glob` 返回生成器, 生成器对象本身恒为真,
  不能直接判真).

### 署名

- `DatasetView.version_label`: 数据集自己的 `version` 优先, 否则用数据源的 `version`;
- `DatasetView.credit`: 数据源写好的署名短句; 数据集覆盖了版本(`version` 与数据源不同)时
  改写成 `"<title> <version>"`;
- `Catalog.citation(dataset_ids)`: 把用到的数据集折成产物「数据来源」一行:
  - 按数据源 `id` 去重, 顺序按首次出现;
  - 一个数据源的版本集合恰好等于数据源版本(或没有版本)时用 `credit`, 否则写成
    `"<title> <v1>/<v2>"`;
  - 每条后面追加数据源 `homepage`(发布页 URL, 长期有效);
  - 各条之间用 ` · ` 连接. 算法与数据项目的 `DatasetSet.citation` 一致, 保证迁移前后产物
    字节不变; 改这里要同步数据项目.

## 用法

绘图模块在文件顶部按 `DATA_GROUP` 拿一次 `Catalog`, 之后只用它取路径:

```python
import config
from cartopy_file.catalog import catalog_for
from cartopy_file.relief import find_etopo
from cartopy_file import runner

CATALOG = catalog_for(config.DATA_GROUP)

def run(*, stride=None, dpi=None, show=False) -> int:
    # 高程文件在 <数据根>/<region>/raw/, find_etopo 的目录参数直接用 Catalog.raw_dir.
    etopo = find_etopo(CATALOG.raw_dir, "myanmar", stride)

    # 派生 GeoJSON 的主路径: 清单里的 dest 相对 <数据根>/<region>/.
    # 缺文件时 exists() 为 False, 由模块报错并指向数据项目的 prepare 命令.
    admin = CATALOG.path("myanmar-admin1")

    # 出图: runner 用 Catalog 核对共享图层是否就位, 并按 sheet.dataset_ids 生成数据来源.
    runner.render(config.SHEET, root=ROOT, catalog=CATALOG, draw=draw,
                  dem_path=etopo, dpi=dpi, show=show)
    return 0
```

## 注意事项

- **不要手写数据来源**: `runner` 缺省的 `standard_collect` 已经用
  `Catalog.citation(sheet.dataset_ids)` 生成 `suggestions.source`; 手写会漏掉 ODbL 这类许可
  要求的署名;
- **不要把区域数据路径写死**: 用 `CATALOG.raw_dir` / `CATALOG.path(id)`, 数据根搬到别处时
  不用改代码; 也不要拼 `../data/...` 这类相对脚本的路径;
- **清单只由数据项目生成**: 本仓没有写清单的代码, 手改 `<数据根>/manifest.json` 会在下次
  `publish` 时被覆盖;
- **字段变更必须两仓同步**: 新增/改名字段要同时改数据项目的 `manifest.py` 与这里的
  `_parse_item`/`_parse_source`, 并把 `version` 加 1; 只改一边会在加载时被格式/版本校验拒绝;
- **`exists()` 是就位判断, 不是内容校验**: 版本是否相符由数据项目的 `check` 负责; 本仓只保证
  文件在;
- **进程内缓存**: 同一进程里第一次 `catalog_for()` 后数据根就固定了; 测试里要切换
  `CARTOPY_FILE_DATA` 时在调用前设, 不要指望已缓存的 `Catalog` 跟着变.
