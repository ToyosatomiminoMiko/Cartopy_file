# 预取共享底图与数据清单 (download_data.py)

- 源码: [`download_data.py`](../download_data.py)
- 用途: 预取全项目共用的 cartopy Natural Earth 底图; `--check` 检查全项目数据清单
- 运行: `python download_data.py`(预取) / `python download_data.py --check`(只检查)
- 前提: 项目已装进当前环境(`uv pip install -e .`), 用 `.venv/bin/python` 运行

## 是什么

- 默认: 把各绘图脚本会用到的 Natural Earth 要素下载到仓库 `data/cartopy`; 要素已存在
  (包括旧 `~/.local/share/cartopy` 缓存)就跳过, 不联网;
- `--check`: 只检查所有图种需要的本地数据是否就位, 不联网; 有缺失时退出码 1.

清单包括三部分: cartopy 共用底图(10m / 110m 的海岸线、国界、河流、湖泊、陆地、海洋)、
各图种自己的本地数据(ETOPO、国界/河流、行政区 GeoJSON、OSM 边界)、几项缺失也不影响出图
的可选缓存.

## 为什么

绘图脚本不负责下载, 只读缓存: 要素缺失时 cartopy 会在渲染中临时联网. 本机 HOME 只读,
默认缓存目录不可写, 于是要么下载失败, 要么每次运行都重试同一份底图. 共用底图集中预取
一次后, 出图流程完全离线. 各图种自己的数据仍由各自的 `download_*.py` / `prepare_*.py`
负责, 同样是"文件已存在就跳过".

## 用法

```bash
python download_data.py           # 预取共用底图(已存在的跳过), 结束后打印清单
python download_data.py --check   # 只检查, 不联网; 有缺失时退出码 1
```

- 缓存位置: 仓库 `data/cartopy`, 由
  [`cartopy_file.data.configure_cartopy()`](cartopy_file/data.md) 统一重定向; 旧 HOME
  缓存里已有的要素会复制进项目缓存, 让仓库数据自包含;
- 输出: 逐项打印 `[已存在]` / `[缺失]` / `下载:` / `复制到项目缓存:`; 预取结束汇总本次
  下载/失败数, `--check` 末尾按缺失项给出准备命令;
- 退出码: 预取模式有下载失败为 1; `--check` 有缺失为 1, 全部就位为 0.

## 注意事项

- 重复执行安全, 已就位的要素不会重新联网;
- 共用底图清单写在脚本顶部的 `NE_FEATURES`(分辨率/类别/名称/使用位置); 新增图种用到新
  要素时同步补一行, 名称必须与 `cartopy.feature` 里的一致;
- 数据目录在 `.gitignore` 的 `**/data` 之内, 不随仓库提交; 换机器后重跑本脚本与各图种的
  数据准备脚本即可恢复.
