# 数据与缓存定位 (cartopy_file.data)

- 源码: [`src/cartopy_file/data.py`](../../src/cartopy_file/data.py)
- 导入: `from cartopy_file.data import prepare_matplotlib_env, configure_cartopy`

## 是什么

渲染仓唯一的"数据在哪,缓存放哪"入口. 数据由独立数据项目 `miko_gis_data` 准备, 本模块只定位,
不下载:

- `project_root()`: 渲染仓根目录;
- `local_data_dir()`: 渲染仓自己的可写缓存目录(`<仓根>/data`, 自动创建);
- `data_root()`: 数据根目录, 数据项目发布 `manifest.json` 与各区域数据的那个目录;
- `manifest_path()`: 数据清单的固定位置(`<数据根>/manifest.json`);
- `prepare_matplotlib_env()`: 在导入 matplotlib 之前把 `MPLCONFIGDIR` 指到可写目录;
- `configure_cartopy()`: 把 cartopy 的下载缓存定位到 `<数据根>/cartopy/`, 并登记旧缓存供只读
  复用;
- `natural_earth_paths()`: 查某个 Natural Earth 要素落在哪个缓存, 目标路径是哪, 不联网;
- `subproject_dirs()`: 渲染仓里的子项目目录名(判定标准是目录里有 `config.py`), 供
  `tools/check_geo.py` 自动枚举产物.

`data.py` 不解析 `manifest.json`; 清单的读取在 [`catalog.py`](catalog.md), 契约在
[`manifest.md`](manifest.md).

## 关键行为

| 内容 | 位置(缺省) | 覆盖方式 |
| --- | --- | --- |
| 数据根 | `<仓根>/data` 或 `<仓根>/miko_gis_data/data`(有 manifest 的那个) | 环境变量 `CARTOPY_FILE_DATA` |
| 数据清单 | `<数据根>/manifest.json` | 随数据根 |
| matplotlib 配置缓存 | `<仓根>/data/.mplcache` | 可自己先设 `MPLCONFIGDIR`(函数用 `setdefault`) |
| cartopy 下载缓存 | `<数据根>/cartopy` | 由 `configure_cartopy()` 重定向 |
| cartopy 旧缓存(只读复用) | 原 `~/.local/share/cartopy` 或 `CARTOPY_DATA_DIR` 指向的目录 | 环境变量 `CARTOPY_DATA_DIR` |
| 渲染仓根目录 | 由本文件位置推断(可编辑安装时上三级即仓库根) | 环境变量 `CARTOPY_FILE_ROOT` |
| 子项目名单 | 仓库根下有 `config.py` 的目录 | 目录结构本身 |

- 模块没有导入期副作用: 设环境变量,改 cartopy 配置只发生在显式调用函数时;
- `project_root()` 优先级: `CARTOPY_FILE_ROOT` > 由本文件位置推断(上三级有 `pyproject.toml`
  即仓库根) > 当前工作目录; 都失败时抛 `RuntimeError`;
- `data_root()` 是**三级回退**, 顺序固定:
  1. `CARTOPY_FILE_DATA`(指向别处或搬走数据项目后的唯一方式, 自动建目录);
  2. `<仓根>/data`(里面有 `manifest.json` 时);
  3. `<仓根>/miko_gis_data/data`(数据项目暂放在本仓内, 里面有 `manifest.json` 时);
  都没有清单时退回 `<仓根>/data` 并建目录, 让后续报错指向一个具体位置;
- 用"有没有 `manifest.json`"判定数据项目在哪: 空目录与真实数据根要能区分开, 否则会静默把
  缓存目录当成数据根;
- `local_data_dir()` 只建 `<仓根>/data`, 里面放 `.mplcache` 等本仓缓存; 它**不是**数据根,
  除非把清单也放进去;
- `prepare_matplotlib_env()` 用 `setdefault`, 已自己指定 `MPLCONFIGDIR` 的脚本保持原样;
  返回实际生效的缓存目录;
- `configure_cartopy()` 把 `cartopy.config["data_dir"]` 改成 `<数据根>/cartopy`, 并把改动前的
  旧缓存登记为 `pre_existing_data_dir`; 重复调用是安全的(idempotent);
- `natural_earth_paths()` 判断"是否已存在"只看 `.shp`(下载器把 shp/shx/dbf 一起解压),
  返回顺序故意让数据根里的项目缓存优先;
- `subproject_dirs()` 用"目录里有 `config.py`"当判定: 子项目名单只在目录结构里出现一次,
  新增子项目只要建目录 + `config.py`, 产物枚举就自动收录.

### 为什么缓存要重定向

本机 `/home` 是只读挂载, cartopy 默认的 `~/.local/share/cartopy` 与 matplotlib 默认的
`~/.config/matplotlib` 都不可写: 要素没有缓存时渲染会尝试下载并失败. 所以 matplotlib 的
`MPLCONFIGDIR` 指到 `<仓根>/data/.mplcache`, cartopy 缓存的写入位置指到 `<数据根>/cartopy`
(数据项目用同一个布局写入, 两边读到同一份共享底图).

`configure_cartopy()` 必须把旧缓存登记为 `pre_existing_data_dir`: cartopy 的 Downloader 先查
`pre_existing_data_dir` 再查 `data_dir`, 两者都没有才联网. 改 `data_dir` 后如果不登记旧缓存,
原先下在 HOME 里的文件会"看不见", 从而被重新下载一遍 -- 这正是要避免的. 渲染仓自己从不
下载, 读不到就是数据没备好, 由 [catalog.py](catalog.md) 与 `runner` 报错指向数据项目.

## 用法

```python
from cartopy_file.data import prepare_matplotlib_env

prepare_matplotlib_env()  # 必须在导入 matplotlib 之前调用

import matplotlib.pyplot as plt  # noqa: E402
import cartopy  # noqa: E402
from cartopy_file.data import (  # noqa: E402
    configure_cartopy,
    data_root,
    manifest_path,
    natural_earth_paths,
)

configure_cartopy()  # 必须在读取第一个 cartopy 要素之前; 可重复调用

# 只查缓存,不联网: (已存在的路径或 None, 下载会写入的目标路径)
existing, target = natural_earth_paths("10m", "physical", "coastline")

root = data_root()            # 数据根(不含 manifest 的读取, 那是 catalog 的事)
manifest = manifest_path()    # <数据根>/manifest.json
```

## 注意事项

- 数据根里没有 `manifest.json` 时, `catalog_for()` 会抛 `FileNotFoundError` 并提示到数据项目
  运行 `python main.py all`; 这时先检查 `CARTOPY_FILE_DATA` 是否指对;
- 本仓 `.gitignore` 忽略 `**/data`, 数据根与 `<仓根>/data` 都不入库; 换机器后到数据项目重跑
  准备命令即可恢复(清单见 [data-preparation.md](../data-preparation.md));
- `CARTOPY_DATA_DIR` 只被当作"旧缓存位置"登记为只读复用, 不是项目缓存的写入位置; 想让渲染
  仓使用另一个数据根, 设 `CARTOPY_FILE_DATA`;
- 渲染仓没有数据准备子命令: 数据缺失时不要在本仓找下载脚本, 去数据项目.
