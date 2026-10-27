# 文档与注释规范

本目录为什么这样分层、每一页写什么、路径和文风怎么统一。改文档前先读这一页, 改完跑
`python tools/check_docs.py`。

## 三层结构

| 层 | 位置 | 回答的问题 | 写法 |
| --- | --- | --- | --- |
| 概念 | `docs/*.md` | 项目怎么组成、数据从哪来、怎么加图种 | 按主题组织, 不绑定源码文件 |
| 图种 | `docs/maps/<slug>.md` | 这张图为什么这么画、要哪些数据、怎么跑 | 一图种一页, 模板固定 |
| 参考 | `docs/reference/<module>.md` | 共享模块的 API、关键行为、坑 | 一导入模块一页, 模板固定 |

根 [README.md](../README.md) 只放安装与快速开始; 唯一全量索引是 [index.md](index.md)。
目录布局与数据流见 [overview.md](overview.md), 数据来源与准备命令见
[data-preparation.md](data-preparation.md)。

## 图种页模板

```markdown
# 图名 (脚本路径)

- 源码: [`Myanmar/xxx.py`](../../Myanmar/xxx.py)
- 产物: `xxx.svg`(与脚本同目录)

## 是什么
## 设计要点
### 1. 主题
## 数据
## 运行
## 注意事项
```

- 元信息两行必填: `源码`、`产物`;
- 节序固定为 是什么 → 设计要点 → 数据 → 运行 → 注意事项, 整节可省略, 不可调换或自创;
- 设计要点内部用 `### 1. 主题` 编号, 便于正文里互相引用;
- 同一图种的绘制脚本与它的数据准备脚本共用一页, 不再为 `download_*.py` /
  `prepare_*.py` 单独建页。

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
- 包入口(`__init__.py`)的说明并入 [overview.md](overview.md), 不单列页面;
- 只被某个图种使用的兼容 shim 不建页, 在对应参考页里用一段说明。

## 命名规则

- 图种页用图种名而不是脚本名, 小写连字符: `myanmar`、`myanmar-admin`、`northern-shan`、
  `ussr`、`ukraine`、`volga`; 同一图种多个脚本共用一页。
- 参考页用导入模块名: `cartopy_file.relief` → `reference/relief.md`。
- 一次性脚本、临时脚本、兼容 shim 一律不单独建页: 内容并入所属图种页或
  [data-preparation.md](data-preparation.md), 源码 docstring 指过去即可。
- 不建"一源码文件一页"; 新脚本默认并进已有页面, 只有新图种或新共享模块才新增页面。
- 页面不放版本号、日期、作者; 变更看 git 历史。

## 路径写法

- 仓库内路径一律写成仓库根相对: `Myanmar/data/...`、`data/cartopy/...`、
  `src/cartopy_file/...`; 不写裸 `data/`(容易和别的图种目录混淆)。
- 产物写文件名并注明"(与脚本同目录)"。
- 页间链接用相对路径; 外部链接只出现在 [data-preparation.md](data-preparation.md) 的数据
  来源处。

## 文风

- 中文配半角逗号、句号、括号, 标点后一个空格; 中英文与数字之间加空格。
- 只写代码里看不出来的东西: 设计取舍、投影与范围参数的取值理由、数据来源、踩过的坑;
  不复述函数签名和显而易见的流程。
- 不写空节, 不写"本节介绍……"式的空话。

## 注释规则(源码)

规则与 `~/.dsh/AGENTS.md` 一致, 这里只补本文档体系下的写法:

- 注释只有三类: 是什么 / 为什么 / 元信息;
- 模块 docstring: 一行英文摘要 + `是什么:` 一到两行 + `完整说明: ``docs/...`` `;
- 代码内只留本文件局部的 why、约束和数值出处; 跨文件的原理与取舍写在对应文档页,
  注释里只留指针;
- 不复述文档页的设计段落: 同一段理由只写在文档页, 代码注释写"见 docs/...";
- 改实现时如果理由变了, 文档页与注释一起改。

## 维护流程

1. 改实现、参数或数据源 → 同步改对应页, 同一个 commit 或紧邻 commit;
2. 新增图种或共享模块 → 按 [add-map.md](add-map.md) 的清单逐项补;
3. 提交前跑 `python tools/check_docs.py`: 死链、元信息、节序、索引覆盖、源码指针五项
   全绿再提交。
