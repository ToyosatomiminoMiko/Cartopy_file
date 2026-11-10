# Cartopy_file 维护流程

所有路径相对渲染仓根 `Cartopy_file/`. 先判断本次改动属于哪条路径, 按路径走, 最后统一做
「收尾」--**收尾不可跳过**.

本仓做**派生 + 渲染**: 原始数据的下载/入库/解压在独立数据项目 `miko_gis_data`(可整体移走),
本仓各子项目的 `prepare` 负责清洗/派生/裁剪(产物在 `<子项目>/build/`), `render` 出图. 两个
仓库只靠 `<数据根>/manifest.json` 耦合, 互不 import; 契约见 `docs/reference/manifest.md`,
派生流程见 `docs/reference/prepare.md`.

## 0. 环境(每次会话第一次)

```bash
uv sync                                     # 渲染仓
(cd ../miko_gis_data && uv sync)            # 数据项目(放在别处就换成实际路径)
```

确认数据就位(不联网):

```bash
(cd ../miko_gis_data && uv run python main.py check)
```

有缺失时按输出跑数据项目: `python main.py download` -> `publish`(或一条
`python main.py all`).

派生数据不在数据根里: 首次出图前在本仓跑 `<子项目>/main.py prepare`(苏联/美军基地演示没有
派生数据, 不用跑). `build/` 删掉后重跑 `prepare` 即可重建, 不触发下载.

## 1. 收尾(所有路径共用)

```bash
uv run python tools/check_all.py
```

一条命令跑 `check_docs` + `check_geo` + 全仓语法编译, 输出逐项 PASS/FAIL.

- 失败: 按输出逐项修, 不许跳过或放宽检查(见 `AGENTS.md` 规则 5).
- `check_geo` 对不存在的产物打印「跳过(不存在)」, 那是**未覆盖**, 不是通过.
- 有产物的改动再加一步: 同一份数据连跑两次出图, 产物应**字节级一致**. 项目保证不写时间戳,
  内部 id 固定; 不一致说明引入了不确定性(字典顺序,随机数,当前时间,绝对路径).

## 2. 路径 A: 改一张现成的图

1. 读 `docs/maps/<slug>.md` 的「设计要点」与「注意事项」--投影,范围,数据源是既定取舍,
   不擅自改(`AGENTS.md` 规则 2).
2. 改 `<Dir>/<name>.py`(绘图模块); 参数与选项在 `<Dir>/main.py` 里加, 复用
   `src/cartopy_file/` 的 `relief`/`overlap`/`layers`/`geo`, 不复制实现.
3. 派生改动(阈值/裁剪/拼装)改 `<Dir>/prepare.py`, 然后 `uv run python <Dir>/main.py prepare`
   重建 `build/`; 只改绘图时跳过这步.
4. 重新生成: `uv run python <Dir>/main.py render`(多图子项目用 `--sheet`); 地图落到
   `<Dir>/map/`, 文字信息落到 `<Dir>/text/`.
5. `uv run python tools/check_geo.py <Dir>/map/<产物>.svg`.
6. 文档页同步: 设计要点,数据,注意事项哪条变了改哪条. 原始数据源/范围/版本变了要改**数据项目**
   的区域配置并重新 `download`/`publish`, 两边文档一起改; 派生口径变了同步
   `docs/reference/prepare.md` 与图种页.
7. 收尾.

## 3. 路径 B: 新增图种

按 `docs/add-map.md` 的 6 节**逐项**做, 不许挑着做. 工作分两边:

1. 数据项目: 建 `src/miko_gis_data/regions/<region>/config.py` 声明 `DATASETS`, 写
   `download_*.py`(只下载/解压), 跑 `download` -> `publish` -> `check`; 新数据源先登记
   `src/miko_gis_data/sources.py`, 两边数据说明页一起改.
2. 渲染侧: 建 `<Dir>/config.py`(`DATA_GROUP` = 区域名 + `build_path(...)` 派生路径 +
   `SHEETS`),`<Dir>/main.py`(`prepare` + `render` 子命令); 需要派生时再写
   `<Dir>/prepare.py`. 绘图模块用 `catalog_for(config.DATA_GROUP)` 拿 `Catalog`, 原始数据路径
   只从 `Catalog.raw_dir` / `Catalog.path(id)` 取, 派生数据路径只从 `config.py` 的
   `build_path(...)` 取.
3. 容易漏的: 模块顶部的导入顺序是硬约束(`MPLCONFIGDIR` 必须设在导入 matplotlib 之前);
   唯一的可执行文件是 `<Dir>/main.py`, 其余模块只导出 `run()`; 产物路径不用手写,
   `tools/check_geo.py` 从 `config.py` 的 `SHEETS` 自动派生 `map/` 与 `text/`; 新页面必须被
   `docs/index.md` 收录, 每个 `.py` docstring 必须带 `docs/...` 指针--这两项 `check_docs`
   会各自报错.

## 4. 路径 C: 改共享模块

1. 读 `docs/reference/<module>.md`.
2. 改 `src/cartopy_file/`; 纯几何/纯数据模块(如 `overlap`,`spec`,`catalog`)不许 import
   matplotlib/cartopy.
3. 被多个图种调用的函数: 先 grep 出**全部**调用点, 再逐个跑受影响的脚本验证, 不能只验证一个.
4. 同步 reference 页; 影响多个图种时还要看 `docs/overview.md` 的模块表.
5. 改的是数据清单契约(`catalog.py` / manifest 字段): 同时改数据项目的 `manifest.py` 与
   `docs/reference/manifest.md` 两侧版本号, 重新 `publish` 并重出受影响的图.
6. 收尾.

## 5. 路径 D: 隔很久回来 / 换机器

1. `git log --oneline -20` 看这段时间改了什么; `git status` 必须干净再开工.
2. `uv sync` -> `(cd ../miko_gis_data && uv sync && uv run python main.py check)`; 有缺失就从
   缺失那步开始补, 最后 `python main.py publish`(数据或配置变过就要重新发布清单).
3. 在本仓补派生数据: 按 `docs/index.md` 的图种页逐个跑 `<子项目>/main.py prepare`(苏联/美军
   基地演示没有派生数据, 跳过).
4. `uv run python tools/check_all.py`, 先拿到当前基线.
5. 需要重出全部图: 按 `docs/index.md` 的出图表逐个跑 `<子项目>/main.py render`, 再收尾.

## 6. 常见坑对照

| 现象 | 原因 |
| --- | --- |
| `本文件是模块, 不能直接运行` | 直接跑了子项目里的模块; 统一走 `<子项目>/main.py render` |
| `geo.base.sha256 与底图字节不一致` | 改了代码没重新出图, 或手改了产物 |
| 产物还写在脚本目录 | 保存路径没走 `spec`; 产物布局是 `<子项目>/map/` + `<子项目>/text/` |
| `源码指针不存在` | docstring 里的 `docs/...` 路径写错, 或页面被删 |
| `docs/index.md: 未收录 ...` | 新页面没加进索引表 |
| `没有指向 docs/ 的完整说明指针` | 新增 `.py` 少了 `完整说明: docs/...` 一行 |
| 两次出图不一致 | 引入了时间戳/随机数/未排序的字典或集合 |
| `数据清单不存在: .../manifest.json` | 数据项目还没 `publish`; 或仓根 `config.toml` 的 `data_root` 指错 |
| 缺 `build/*.geojson` / 派生文件报错 | 还没跑 `<子项目>/main.py prepare`; `build/` 删掉后要重建 |
| `manifest 里没有区域 '...'` | 渲染仓 `DATA_GROUP` 与数据项目 `regions/<region>/` 目录名不一致 |
| `数据清单版本 ... 不受支持` | 两个仓库版本不同步; 一起升级/降级后重新 `publish` |
| `缺少共享 Natural Earth 图层` | 到数据项目跑 `python main.py download` |
| 数据项目报 `invalid choice: 'prepare'` | 数据项目没有派生; 跑本仓 `<子项目>/main.py prepare` |
| 图上数据或署名与实际不符 | 改完数据只改了清单没重出图, 或只改了一边没 `publish` |
