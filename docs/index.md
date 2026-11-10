# 文档索引

文档分三层: 概念(项目怎么组成,数据从哪来,怎么扩展),图种(每张图的设计与运行),参考
(共享模块的 API 与数据清单契约). 安装与快速开始只在根 [README](../README.md); 写文档的规则
见 [conventions.md](conventions.md).

## 阅读路径

- **第一次出图**: 准备数据项目(到 `miko_gis_data` 跑 `python main.py all`, 细节见
  [data-preparation.md](data-preparation.md)) -> [README](../README.md) 安装本仓 -> 按
  [maps/](maps) 里对应图种页的"运行"节出图;
- **换机器 / 重新 clone**: 先装数据项目, 用 `python main.py check`(在数据项目里跑)确认缺
  什么, 再 `python main.py download` / `prepare` / `publish`; 数据根位置与命令见
  [data-preparation.md](data-preparation.md);
- **改某张图**: 对应图种页的"设计要点"与"注意事项" -> 需要共用工具时查
  [reference/](reference);
- **新增图种或共享模块**: [add-map.md](add-map.md) 的清单(先看 `AmericaArmy/` 这个最小例子);
- **查数据来源与许可**: [data-preparation.md](data-preparation.md);
- **改数据清单/数据源**: 读 [reference/manifest.md](reference/manifest.md) 与数据项目的
  `docs/`, 两个仓库要一起改.

## 概念

| 页面 | 内容 |
| --- | --- |
| [overview.md](overview.md) | 目录结构,四层结构,数据流,与数据项目的边界,共享包模块 |
| [data-preparation.md](data-preparation.md) | 数据根布局,数据项目命令,数据源与许可,ETOPO 下载 |
| [add-map.md](add-map.md) | 新增图种(渲染侧 + 数据项目)/共享模块的步骤与扩展点 |
| [conventions.md](conventions.md) | 文档模板,命名,路径,文风,注释规则,维护流程 |

## 图种

每个子项目只有一个可执行入口 `<子项目>/main.py`, 只有 `render` 子命令; 下表的"入口"列就是
出图命令. 数据一律由独立数据项目准备.

| 页面 | 入口 | 内容 |
| --- | --- | --- |
| [maps/myanmar.md](maps/myanmar.md) | `Myanmar/main.py render --sheet myanmar` | 缅甸全境地形图 |
| [maps/myanmar-admin.md](maps/myanmar-admin.md) | `Myanmar/main.py render --sheet myanmar-admin` | 缅甸省/邦级行政区划图 |
| [maps/northern-shan.md](maps/northern-shan.md) | `Myanmar/main.py render --sheet northern-shan` | 掸邦/特区地形图 |
| [maps/ussr.md](maps/ussr.md) | `USSR/main.py render` | 苏联地形图 |
| [maps/ukraine.md](maps/ukraine.md) | `Ukraine/main.py render` | 乌克兰全图(1991/2014/2022 边界) |
| [maps/volga.md](maps/volga.md) | `Volga/main.py render` | 伏尔加河流域地形图 / 流域与周边六个共和国地形图 |

## 参考

| 页面 | 模块 |
| --- | --- |
| [reference/data.md](reference/data.md) | `cartopy_file.data`: 数据根与 manifest 定位,cartopy/matplotlib 缓存,子项目枚举 |
| [reference/catalog.md](reference/catalog.md) | `cartopy_file.catalog`: 读 manifest,按数据集 id 取路径/判断就位/折署名 |
| [reference/manifest.md](reference/manifest.md) | `manifest.json` 契约: 字段,版本,两仓分工 |
| [reference/spec.md](reference/spec.md) | `cartopy_file.spec`: 实例规格(画框/投影/色带/经纬网/地名/文案) |
| [reference/layers.md](reference/layers.md) | `cartopy_file.layers`: 图层原语(底图/晕渲/经纬网/城市点/geo 收集) |
| [reference/runner.md](reference/runner.md) | `cartopy_file.runner`: 统一出图流程与回调契约 |
| [reference/geo.md](reference/geo.md) | `cartopy_file.geo`: 底图裁剪,geo.json 与前端契约 |
| [reference/output.md](reference/output.md) | `cartopy_file.output`: 纯几何 SVG 出图 |
| [reference/relief.md](reference/relief.md) | `cartopy_file.relief`: 高程,晕渲,海陆底色 |
| [reference/overlap.md](reference/overlap.md) | `cartopy_file.overlap`: 边界重合剪枝 |

## 文档自身

- 改文档前读 [conventions.md](conventions.md);
- 提交前跑 `uv run python tools/check_all.py`(含 `tools/check_docs.py`): 检查死链,页面元信息
  与节序,索引覆盖,源码里的文档指针;
- 页面不放版本号/日期, 变更看 git 历史.
