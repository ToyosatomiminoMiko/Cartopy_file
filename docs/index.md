# 文档索引

文档分三层: 概念(项目怎么组成、数据从哪来、怎么扩展)、图种(每张图的设计与运行)、参考
(共享模块的 API). 安装与快速开始只在根 [README](../README.md); 写文档的规则见
[conventions.md](conventions.md).

## 阅读路径

- **第一次出图**: [README](../README.md) 安装 → [data-preparation.md](data-preparation.md) 准备
  数据 → [maps/](maps) 里对应图种的页面;
- **换机器 / 重新 clone**: [data-preparation.md](data-preparation.md), 再用
  `python download_data.py --check` 确认缺什么;
- **改某张图**: 对应图种页的"设计要点"与"注意事项" → 需要共用工具时查
  [reference/](reference);
- **新增图种或共享模块**: [add-map.md](add-map.md) 的清单;
- **查数据来源与许可**: [data-preparation.md](data-preparation.md).

## 概念

| 页面 | 内容 |
| --- | --- |
| [overview.md](overview.md) | 目录结构、三层结构、数据流、共享包为什么存在 |
| [data-preparation.md](data-preparation.md) | 数据放哪、从哪来、许可、准备命令、ETOPO 下载与 `--check` |
| [add-map.md](add-map.md) | 新增图种/共享模块的步骤与扩展点 |
| [conventions.md](conventions.md) | 文档模板、命名、路径、文风、注释规则 |

## 图种

| 页面 | 脚本 | 内容 |
| --- | --- | --- |
| [maps/myanmar.md](maps/myanmar.md) | `Myanmar/myanmar.py` | 缅甸全境地形图 |
| [maps/myanmar-admin.md](maps/myanmar-admin.md) | `Myanmar/myanmar_admin.py` | 缅甸省/邦级行政区划图 |
| [maps/northern-shan.md](maps/northern-shan.md) | `Myanmar/northern_shan.py` | 掸邦/特区地形图 |
| [maps/ussr.md](maps/ussr.md) | `USSR/ussr.py` | 苏联地形图 |
| [maps/ukraine.md](maps/ukraine.md) | `Ukraine/ukraine.py` | 乌克兰全图(1991/2014/2022 边界) |
| [maps/volga.md](maps/volga.md) | `Volga/volga.py` | 伏尔加河流域地形图 / 流域与周边六个共和国地形图 |

## 参考

| 页面 | 模块 |
| --- | --- |
| [reference/data.md](reference/data.md) | `cartopy_file.data`: 数据目录与缓存定位 |
| [reference/output.md](reference/output.md) | `cartopy_file.output`: 纯几何 SVG 出图 |
| [reference/relief.md](reference/relief.md) | `cartopy_file.relief`: 高程、晕渲、海陆底色 |
| [reference/overlap.md](reference/overlap.md) | `cartopy_file.overlap`: 边界重合剪枝 |

## 文档自身

- 改文档前读 [conventions.md](conventions.md);
- 提交前跑 `python tools/check_docs.py`: 检查死链、页面元信息与节序、索引覆盖、源码里的
  文档指针;
- 页面不放版本号/日期, 变更看 git 历史.
