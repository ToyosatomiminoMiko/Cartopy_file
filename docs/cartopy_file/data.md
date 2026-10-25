# 数据与缓存定位 (cartopy_file.data)

- 源码: [`src/cartopy_file/data.py`](../../src/cartopy_file/data.py)
- 用法: `from cartopy_file.data import prepare_matplotlib_env, configure_cartopy`

## 是什么

统一定位项目数据目录与 cartopy/matplotlib 缓存, 让所有脚本读写同一处:

- `shared_data_dir()`: 仓库级共享数据目录, 缺省 `<repo>/data`, 可用环境变量
  `CARTOPY_FILE_DATA` 覆盖; 自动创建目录;
- `prepare_matplotlib_env()`: 在导入 matplotlib 之前把 `MPLCONFIGDIR` 指到共享目录下的
  `.mplcache`;
- `configure_cartopy()`: 把 cartopy 下载缓存重定向到共享目录下的 `cartopy/`, 并把已有
  缓存登记为 `pre_existing_data_dir`(只读复用);
- `natural_earth_paths()`: 查某个 Natural Earth 要素已落在哪个缓存、下载会落到哪里, 不联网;
- `project_root()`: 仓库根目录.

## 缓存位置

| 内容 | 位置 | 覆盖方式 |
| --- | --- | --- |
| 共享数据目录 | `<repo>/data`(缺省) | 环境变量 `CARTOPY_FILE_DATA` |
| matplotlib 配置缓存 | `<共享数据目录>/.mplcache` | 可自己先设 `MPLCONFIGDIR`(函数用 `setdefault`) |
| cartopy 下载缓存 | `<共享数据目录>/cartopy` | 由 `configure_cartopy()` 重定向 |
| cartopy 旧缓存(只读复用) | 原 `~/.local/share/cartopy` 或 `CARTOPY_DATA_DIR` 指向的目录 | 环境变量 `CARTOPY_DATA_DIR` |
| 仓库根目录(推断失败时) | — | 环境变量 `CARTOPY_FILE_ROOT` |

## 为什么

本机 `/home` 是只读挂载, cartopy 默认的 `~/.local/share/cartopy` 与 matplotlib 默认的
`~/.config/matplotlib` 都不可写: 要素没有缓存时渲染会尝试下载并失败. 缓存统一到仓库内
以后可写、随仓库走、只下载一次; 旧 HOME 缓存通过 `pre_existing_data_dir` 继续复用,
已经下载过的文件不会再下一遍.

## 用法

```python
from cartopy_file.data import prepare_matplotlib_env

prepare_matplotlib_env()  # 必须在导入 matplotlib 之前调用

import matplotlib.pyplot as plt  # noqa: E402
import cartopy  # noqa: E402
from cartopy_file.data import configure_cartopy, natural_earth_paths  # noqa: E402

configure_cartopy()  # 必须在读取第一个 cartopy 要素之前; 可重复调用

# 只查缓存、不联网: (已存在的路径或 None, 下载会写入的目标路径)
existing, target = natural_earth_paths("10m", "physical", "coastline")
```

## 行为与注意事项

- 模块没有导入期副作用: 设环境变量、改 cartopy 配置只发生在显式调用函数时;
- `prepare_matplotlib_env()` 用 `setdefault`, 已自己指定 `MPLCONFIGDIR` 的脚本保持原样;
  返回实际生效的缓存目录;
- `project_root()` 优先级: `CARTOPY_FILE_ROOT` > 由本文件位置推断(可编辑安装时上三级即
  仓库根) > 当前工作目录; 都失败时抛 `RuntimeError`;
- `configure_cartopy()` 必须把旧缓存登记为 `pre_existing_data_dir`: cartopy 先查
  `pre_existing_data_dir` 再查 `data_dir`, 两者都没有才联网; 不登记的话原先下在 HOME 里的
  文件会"看不见"而被重新下载;
- `natural_earth_paths()` 判断"是否已存在"只看 `.shp`(下载器把 shp/shx/dbf 一起解压),
  返回顺序故意让项目缓存优先;
- 下载内容不提交: `.gitignore` 忽略 `**/data`, 换机器后重跑各 `download_*.py` /
  `prepare_*.py` 即可恢复.
