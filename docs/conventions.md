# 文档与注释规范

本目录为什么这样分层,每一页写什么,路径和文风怎么统一.改文档前先读这一页, 改完跑
`uv run python tools/check_docs.py`.

## 三层结构

| 层 | 位置 | 回答的问题 | 写法 |
| --- | --- | --- | --- |
| 概念 | `docs/*.md` | 项目怎么组成,数据从哪来,怎么加图种 | 按主题组织, 不绑定源码文件 |
| 图种 | `docs/maps/<slug>.md` | 这张图为什么这么画,要哪些数据,怎么跑 | 一图种一页, 模板固定 |
| 参考 | `docs/reference/<module>.md` | 共享模块的 API,关键行为,坑 | 一导入模块一页, 模板固定 |

根 [README.md](../README.md) 只放安装与快速开始; 唯一全量索引是 [index.md](index.md).
目录布局与两仓边界见 [overview.md](overview.md); 数据来源,数据根与准备命令见
[data-preparation.md](data-preparation.md); `manifest.json` 契约见
[reference/manifest.md](reference/manifest.md).

`miko_gis_data/` 是独立数据项目, 它的文档在它自己的 `docs/` 下; 本仓文档只用文字提到它
(例如"到数据项目跑 `python main.py download`"), **不建相对链接**: 整体移走后链接会成死链.

## 图种页模板

```markdown
# 图名 (脚本路径)

- 源码: [`Myanmar/xxx.py`](../../Myanmar/xxx.py)
- 入口: [`Myanmar/main.py`](../../Myanmar/main.py)(子命令见"运行")
- 产物: `<子项目>/map/xxx.svg`(地图) 与 `<子项目>/text/xxx.geo.json`(文字信息);
  有派生数据时另写 `<子项目>/build/xxx.geojson`

## 是什么
## 设计要点
### 1. 主题
## 数据
## 运行
## 注意事项
```

- 元信息三行必填: `源码`(绘图模块, 有派生数据时也写 `prepare.py`),`入口`(子项目
  `main.py`),`产物`;
- 节序固定为 是什么 -> 设计要点 -> 数据 -> 运行 -> 注意事项, 整节可省略, 不可调换或自创;
- 设计要点内部用 `### 1. 主题` 编号, 便于正文里互相引用;
- "数据"写原始数据(`<数据根>/.../raw/...`)与本仓派生文件(`<子项目>/build/...`)的位置, 以及
  数据项目的 `download` 命令; "运行"写 `<子项目>/main.py prepare`(有派生数据时)与 `render`;
- 同一图种只写绘图模块与 `prepare.py` 两类源码小节; 数据项目侧的下载不在本仓文档里. 派生流程
  统一写 [reference/prepare.md](reference/prepare.md).

## 参考页模板

```markdown
# 功能名 (cartopy_file.module)

- 源码: [`src/cartopy_file/module.py`](../../src/cartopy_file/module.py)
- 导入: `from cartopy_file.module import ...`

## 是什么
## 关键行为
## 用法
## 注意事项
```

- 节序固定, 整节可省略; `关键行为` 按函数/参数逐条写, `用法` 给可直接复制的代码块;
- 跨模块的流程页(`reference/prepare.md`)也按这套模板写, `源码` 列相关文件, `导入` 写实际
  使用方式(如 `python <子项目>/main.py prepare`);
- 包入口(`__init__.py`)的说明并入 [overview.md](overview.md), 不单列页面;
- 只被某个图种使用的兼容 shim 不建页, 在对应参考页里用一段说明;
- 数据清单契约不是某个模块的 API, 单独一页 [reference/manifest.md](reference/manifest.md).

## 命名规则

- 图种页用图种名而不是脚本名, 小写连字符: `myanmar`,`myanmar-admin`,`northern-shan`,
  `ussr`,`ukraine`,`volga`; 同一图种多个脚本共用一页.
- 每个子项目的入口固定叫 `main.py`, 绘图模块用图种名: `Myanmar/myanmar.py`,
  `Volga/volga.py`.
- 参考页用导入模块名: `cartopy_file.relief` -> `reference/relief.md`;
  `cartopy_file.catalog` -> `reference/catalog.md`.
- 数据项目里一个区域一个目录, 目录名即 manifest 的 group 键, 也是本仓 `DATA_GROUP`: 小写
  连字符或下划线(`america_army`,`northern_shan` 是区域内部名, group 用 `myanmar` 等).
- 一次性脚本,临时脚本,兼容 shim 一律不单独建页: 内容并入所属图种页或
  [data-preparation.md](data-preparation.md), 源码 docstring 指过去即可.
- 不建"一源码文件一页"; 新脚本默认并进已有页面, 只有新图种或新共享模块才新增页面.
- 页面不放版本号,日期,作者; 变更看 git 历史.

## 路径写法

- 仓库内路径一律写成仓库根相对: `Myanmar/xxx.py`,`src/cartopy_file/...`,`docs/...`; 不写裸
  `data/`(容易和别的图种目录混淆).
- **原始数据写"数据根相对"**: `<数据根>/<region>/raw/...`, 共享 Natural Earth 图层写
  `<数据根>/cartopy/...`; 不写 `<子项目>/data/...`(子项目没有私有数据目录), 也不写
  任何绝对路径.
- 清单里的 `dest`/`files` 是相对 `<数据根>/<region>/` 的路径, 文档引用时补全到数据根口径.
- 派生数据写仓库根相对路径: 在 `<子项目>/build/`(由 `config.py` 的 `build_path(...)` 声明),
  不进数据根, 也不进清单.
- 产物写仓库根相对路径: 地图在 `<子项目>/map/`, 文字信息在 `<子项目>/text/`(同 stem).
- 页间链接用相对路径; 外部链接只出现在 [data-preparation.md](data-preparation.md) 的数据
  来源处.

## 文风

- 中文配半角逗号,句号,括号, 标点后一个空格; 中英文与数字之间加空格. 这条由提交钩子
  强制, 见下一节.
- 只写代码里看不出来的东西: 设计取舍,投影与范围参数的取值理由,数据来源,踩过的坑;
  不复述函数签名和显而易见的流程.
- 不写空节, 不写"本节介绍......"式的空话.

## 标点与提交钩子

- 唯一执行者: `tools/autorun.py`, 映射表是它模块级的 `CHAR_MAP`(全角标点 -> ASCII,
  键一律写成 `\uXXXX` 转义). 用法:
  - 手动: `python tools/autorun.py <file> [<file>...]` 原地改写, 二进制文件跳过;
  - 管道: `python tools/autorun.py < in > out`;
  - 提交流程: `.githooks/pre-commit` 对本次暂存的每个文本文件调用文件模式, 再把改过的
    文件重新 `git add`, 所以漏改也会在提交前被修正.
- 每个 clone 各做一次: `git config --local core.hooksPath .githooks`;
  临时跳过某次提交用 `git commit --no-verify`; 卸载用 `git config --unset core.hooksPath`.
- 钩子放在版本库而不是 `.git/hooks`: 后者不进版本库, 换机器或重新 clone 后会静默失效;
  钩子跟随仓库提交, 谁 clone 下来执行一次上面那条命令就生效.
- 文件模式会改磁盘内容(不只是暂存区), 所以 `git status` 可能看不到差异但工作区已经变了.
- 工具只替换标点字符, 不补空格, 也不动全角汉字与全角空格(U+3000): "标点后一个空格"
  仍靠手写时遵守, 钩子只兜底字符层面.
- 图面文案(config.py 里的标题/图例/注释, 最终写进 `.geo.json`)也在修正范围内: 改完文案
  要重出图, 否则产物与代码不一致(见 [AGENTS.md](../AGENTS.md) 的"改动必须配套").
- 本文件自己也被扫: 它和 `.githooks/pre-commit` 的注释只写半角标点, 转换幂等, 不会每次
  提交都产生无意义的 diff.

## 注释规则(源码)

规则与 `~/.dsh/AGENTS.md` 一致, 这里只补本文档体系下的写法:

- 注释只有三类: 是什么 / 为什么 / 元信息;
- 模块 docstring: 一行英文摘要 + `是什么:` 一到两行 + `完整说明: ``docs/...`` `;
- 代码内只留本文件局部的 why,约束和数值出处; 跨文件的原理与取舍写在对应文档页,
  注释里只留指针;
- 不复述文档页的设计段落: 同一段理由只写在文档页, 代码注释写"见 docs/...";
- 改实现时如果理由变了, 文档页与注释一起改;
- 绘图模块的指针指向图种页; 派生模块(`prepare.py`)与共享几何工具指向
  [reference/prepare.md](reference/prepare.md) / [reference/geometry.md](reference/geometry.md)
  与图种页; 数据下载相关代码**不在本仓**, 要改数据源就改数据项目并同步两边的数据说明页.

## 文档指针

`tools/check_docs.py` 要求每个 `.py`(少数一次性脚本除外)的 docstring 里至少有一处
`docs/...md` 指针, 且该页面必须存在; 指针写错或页面被删都会让检查失败. 指向规则:

- 绘图模块与子项目 `main.py` -> 对应的 `docs/maps/<slug>.md`;
- `prepare.py` -> `docs/reference/prepare.md` + 对应图种页;
- 共享模块 -> 对应的 `docs/reference/<module>.md`(几何工具见 `geometry.md`);
- 数据下载/清单**写出侧**在数据项目, 相关代码指针指向数据项目自己的 `docs/`;
- 一个模块只留一处"完整说明: `docs/...`"式完整指针, 其余引用写短路径或只写文件名.

## 脚本入口

- 每个子项目**只有一个可执行文件** `<子项目>/main.py`: 有派生数据的子项目有 `prepare` 与
  `render` 两个子命令, 没有派生数据的(苏联/美军基地演示)只有 `render`; 文档里的派生/出图
  命令一律从这个入口写, 不写模块文件名;
- 其余 `.py` 都是模块: 只导出 `run(...)`, 不写 argparse/main; 直接执行时报错并指向入口;
- 数据下载/入库/解压与发布清单不在本仓: 统一走独立数据项目 `miko_gis_data/main.py` 的
  `check` / `download` / `publish` / `all`; 清洗/派生/裁剪在本仓各子项目的 `prepare.py`;
- 框架层脚本(`tools/*.py`,`global.py`)不受此约束, 仍可独立运行;
- 新增子命令时同步本页与该图种页的"运行"节.

## 维护流程

1. 改实现,参数或数据源 -> 同步改对应页, 同一个 commit 或紧邻 commit;
2. 改原始数据源/版本/下载范围 -> 同时改数据项目的 `sources.py` / 区域 `config.py`, 重新
   `publish`, 并同步两边的数据说明页(本仓 [data-preparation.md](data-preparation.md) 与数据
   项目的 `docs/`); 改派生逻辑 -> 重跑本仓 `<子项目>/main.py prepare` 再重出图;
3. 新增图种或共享模块 -> 按 [add-map.md](add-map.md) 的清单逐项补;
4. 提交前跑 `uv run python tools/check_all.py`(含 `check_docs`): 死链,元信息,节序,索引
   覆盖,源码指针五类全绿再提交.
