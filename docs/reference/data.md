# 数据与缓存定位 (cartopy_file.data)

- 源码: [`src/cartopy_file/data.py`](../../src/cartopy_file/data.py)
- 导入: `from cartopy_file.data import prepare_matplotlib_env, configure_cartopy`

## 是什么

渲染仓唯一的"数据在哪,缓存放哪"入口. 数据由独立数据项目 `miko_gis_data` 准备, 本模块只定位,
不下载:

- `project_root()`: 渲染仓根目录;
- `local_data_dir()`: 渲染仓自己的可写缓存目录(`<仓根>/data`, 自动创建);
- `data_root()`: 数据根目录, 取自仓根 `config.toml` 的 `data_root`, 是数据项目发布
  `manifest.json` 与各区域数据的那个目录;
- `manifest_path()`: 数据清单的固定位置(`<数据根>/manifest.json`);
- `prepare_matplotlib_env()`: 在导入 matplotlib 之前把 `MPLCONFIGDIR` 指到可写目录;
- `configure_cartopy()`: 把 cartopy 的下载缓存定位到 `<数据根>/cartopy/`, 并把 HOME 下已有的
  缓存登记为只读复用来源;
- `natural_earth_paths()`: 查某个 Natural Earth 要素落在哪个缓存, 目标路径是哪, 不联网;
- `subproject_dirs()`: 渲染仓里的子项目目录名(判定标准是目录里有 `config.py`), 供
  `tools/check_geo.py` 自动枚举产物.

`data.py` 不解析 `manifest.json`; 清单的读取在 [`catalog.py`](catalog.md), 契约在
[`manifest.md`](manifest.md).

## 关键行为

| 内容 | 位置(缺省) | 说明 |
| --- | --- | --- |
| 数据根 | 仓根 `config.toml` 的 `data_root` | 本机配置, 不进 git; 没有它 `data_root()` 直接报错 |
| 数据清单 | `<数据根>/manifest.json` | 随数据根 |
| matplotlib 配置缓存 | `<仓根>/data/.mplcache` | 由 `prepare_matplotlib_env()` 在导入 matplotlib 前设好 |
| cartopy 下载缓存 | `<数据根>/cartopy` | 由 `configure_cartopy()` 重定向 |
| cartopy 已有缓存(只读复用) | `~/.local/share/cartopy` | 只登记为 `pre_existing_data_dir`, 不写入 |
| 渲染仓根目录 | 由本文件位置推断(可编辑安装时上三级即仓库根) | 推断失败退回当前工作目录 |
| 子项目名单 | 仓库根下有 `config.py` 的目录 | 目录结构本身 |

- 模块没有导入期副作用: 改 cartopy 配置只发生在显式调用函数时;
- `project_root()` 只按本文件位置推断(上三级有 `pyproject.toml` 即仓库根), 失败退回当前工作
  目录, 再失败抛 `RuntimeError`; 不读环境变量;
- `data_root()` 的**唯一来源**是仓根 `config.toml` 的 `data_root`(相对路径按仓根解析);
  配置缺失或非法时抛 `RuntimeError`, 并在错误信息里给出该写什么. 不读环境变量, 也不设隐式
  默认路径: 数据根换位置后宁可报错, 也不静默读到别处的数据;
- `config.toml` 是本机文件(`.gitignore` 已忽略), 内容:

  ```toml
  data_root = "<数据项目>/data"
  ```

- 本模块只认`数据根`这一个概念, 不认识数据项目放在哪,目录叫什么; 两个仓之间只靠
  `manifest.json` 与本机的 `config.toml` 耦合;
- `local_data_dir()` 只建 `<仓根>/data`, 里面放 `.mplcache` 等本仓缓存; 它**不是**数据根;
- `prepare_matplotlib_env()` 用 `setdefault`, 已自己指定 `MPLCONFIGDIR` 的脚本保持原样;
  返回实际生效的缓存目录;
- `configure_cartopy()` 把 `cartopy.config["data_dir"]` 改成 `<数据根>/cartopy`, 并把 HOME 下
  已有的缓存登记为 `pre_existing_data_dir`; 重复调用是安全的(idempotent);
- `natural_earth_paths()` 判断"是否已存在"只看 `.shp`(下载器把 shp/shx/dbf 一起解压),
  返回顺序故意让数据根里的项目缓存优先;
- `subproject_dirs()` 用"目录里有 `config.py`"当判定: 子项目名单只在目录结构里出现一次,
  新增子项目只要建目录 + `config.py`, 产物枚举就自动收录.

### 为什么缓存要重定向

缓存默认落在 HOME 下(`~/.local/share/cartopy`, `~/.config/matplotlib`), 机器一换就没了,
HOME 只读时还会直接失败. 所以本模块把两类缓存都固定到仓库/数据根里: matplotlib 的
`MPLCONFIGDIR` 指到 `<仓根>/data/.mplcache`, cartopy 缓存的写入位置指到 `<数据根>/cartopy`
(数据项目用同一个布局写入, 两边读到同一份共享底图).

`configure_cartopy()` 必须把 HOME 下已有的缓存登记为 `pre_existing_data_dir`: cartopy 的
Downloader 先查 `pre_existing_data_dir` 再查 `data_dir`, 两者都没有才联网. 不登记时 HOME 下
已有的缓存文件会"看不见", 从而被重新下载一遍 -- 这正是要避免的. 渲染仓自己从不下载, 读不到
就是数据没备好, 由 [catalog.py](catalog.md) 与 `runner` 报错指向数据项目.

## 用法

本机一次性配置(路径按实际情况改, 不进 git):

```toml
# <仓根>/config.toml
data_root = "<数据项目>/data"
```

脚本里照常调用:

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
  运行 `python main.py all`; 这时先检查仓根 `config.toml` 的 `data_root` 是否指对;
- `config.toml` 是本机文件, 换机器要重新写; `.gitignore` 已忽略它, 不要提交;
- 本仓 `.gitignore` 也忽略 `**/data`, 本仓自己的缓存与数据根都不入库; 换机器后到数据项目
  重跑准备命令即可恢复(清单见 [data-preparation.md](../data-preparation.md));
- cartopy 已有缓存(`~/.local/share/cartopy`)只被当作只读复用来源, 不是项目缓存的写入位置;
- 渲染仓没有下载/解压子命令: 原始数据缺失时去数据项目 `download`; 派生数据缺失时跑本仓
  `<子项目>/main.py prepare`(见 [prepare.md](prepare.md)), 不要在本仓找下载脚本.
