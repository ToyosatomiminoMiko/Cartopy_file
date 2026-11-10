# Cartopy_file 硬规矩

本文件只放**必须做 / 禁止做**的条款.项目怎么组成,文档怎么写, 看
[docs/index.md](docs/index.md) 的阅读路径与 [docs/conventions.md](docs/conventions.md);
这里不重复它们的内容.

## 开工前

1. **先定位再动手**: 读 [docs/index.md](docs/index.md) 的阅读路径, 找到本次任务对应的
   [docs/maps/](docs/maps) 或 [docs/reference/](docs/reference) 页; 不凭印象改代码.
2. **既定取舍不擅自推翻**: 页面"设计要点"与"注意事项"里的投影,范围,数据源,参数默认值
   都是已决定的事; 要改先问用户, 并把改动理由同时写进文档页.
3. **不读,不改,不提交仓库根的 `prompt.md`**(本地草稿, 已进 .gitignore).

## 收尾前(每次都必须)

1. 跑 `uv run python tools/check_all.py`(需要先 `export UV_CACHE_DIR="$PWD/data/uv-cache"`),
   把输出贴进回复; 不许用"应该没问题""看起来对"代替.
2. 检查失败必须修到过; 修不了就明确报告失败项与原因, **不许注释掉,跳过或放宽检查**.

## 改动必须配套

1. 改实现,参数或数据源 -> 同一个提交里同步改对应文档页(维护流程见
   [docs/conventions.md](docs/conventions.md)).
2. 新增图种或共享模块 -> 按 [docs/add-map.md](docs/add-map.md) 的清单逐项补, 不许挑着做.
3. 改产物相关代码 -> 重新生成 `.svg` 与同名 `.geo.json` 再自检; 产物不进 git, 但必须是
   当前代码生成的(否则 `geo.base.sha256` 会与底图不符).
4. 绘图脚本**不联网**: 数据一律由独立数据项目 `miko_gis_data` 准备; 新增/修改数据源要改
   数据项目的 `src/miko_gis_data/sources.py`, 并同步两边的数据说明页
   ([docs/data-preparation.md](docs/data-preparation.md) 与数据项目的 `docs/`).

## 脚本入口

1. 每个子项目**只有** `<子项目>/main.py` 可以执行, 且只有 `render` 子命令; 其余 `.py` 是
   模块, 只导出 `run()`, 直接运行会报错并指向入口. 数据下载/派生不在本仓, 统一走独立
   数据项目 `miko_gis_data/main.py`(`check` / `download` / `prepare` / `publish` / `all`).
2. 框架层脚本(`tools/*.py`,`global.py`)不受此限, 仍可独立运行.
3. `miko_gis_data/` 是独立项目(用户会整体移走), 本仓不跟踪它: 已在 .gitignore; 不要把它
   的文件混进本仓文档索引或检查脚本.

## 标点

1. 文档,注释与图面文案统一半角标点; 提交时 `.githooks/pre-commit` 会调用
   `tools/autorun.py` 自动改写暂存文件, 再把改过的文件重新 `git add`.
2. 每个 clone 各做一次 `git config --local core.hooksPath .githooks`(否则钩子不生效);
   映射表与部署原理见 [docs/conventions.md](docs/conventions.md) 的"标点与提交钩子"一节.

## 代码与注释

 1. 注释只写三类: 是什么 / 为什么 / 元信息; 跨文件的原理与取舍写进 docs, 代码里只留指针.
 2. 不提交 `.venv/`,`data/`,`miko_gis_data/`,`*.svg`,`*.geo.json`,`__pycache__/`(已在
   .gitignore, 不要用 `-f` 强加).
