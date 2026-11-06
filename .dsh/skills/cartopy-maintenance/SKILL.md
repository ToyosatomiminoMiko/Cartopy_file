---
name: cartopy-maintenance
description: "Cartopy_file 仓库的维护流程: 改现成图种、新增图种、改共享模块、隔很久回来重跑体检。任何对 Cartopy_file 的代码/数据/文档改动都先按这里确定步骤与验证方式。"
whenToUse: 需要修改 Cartopy_file 的绘图脚本、共享模块、数据清单或文档; 新增一张地图; 接手这个仓库或隔很久回来继续维护; 出图/自检失败需要定位原因时。
---

# Cartopy_file 维护流程

所有路径相对仓库根 `Cartopy_file/`。先判断本次改动属于哪条路径, 按路径走, 最后统一做
「收尾」——**收尾不可跳过**。

## 0. 环境(每次会话第一次)

```bash
export UV_CACHE_DIR="$PWD/data/uv-cache"   # /home 只读, uv 缓存必须落在仓库内
uv sync                                     # 首次或依赖变更后
uv run python download_data.py --check      # 有缺失时退出码 1 并打印准备命令
```

## 1. 收尾(所有路径共用)

```bash
uv run python tools/check_all.py
```

一条命令跑 `check_docs` + `check_geo` + 全仓语法编译, 输出逐项 PASS/FAIL。

- 失败:按输出逐项修, 不许跳过或放宽检查(见 `AGENTS.md` 规则 5)。
- `check_geo` 对不存在的产物打印「跳过(不存在)」, 那是**未覆盖**, 不是通过。
- 有产物的改动再加一步:同一份数据连跑两次出图, 产物应**字节级一致**。项目保证不写时间戳、
  内部 id 固定; 不一致说明引入了不确定性(字典顺序、随机数、当前时间、绝对路径)。

## 2. 路径 A: 改一张现成的图

1. 读 `docs/maps/<slug>.md` 的「设计要点」与「注意事项」——投影、范围、数据源是既定取舍,
   不擅自改(`AGENTS.md` 规则 2)。
2. 改 `<Dir>/<name>.py`; 复用 `src/cartopy_file/` 的 `relief`/`overlap`/`geo`, 不复制实现。
3. 重新生成:`uv run python <Dir>/<name>.py`
4. `uv run python tools/check_geo.py <产物>.svg`
5. 文档页同步:设计要点、数据、注意事项哪条变了改哪条。
6. 收尾。

## 3. 路径 B: 新增图种

按 `docs/add-map.md` 的 5 节**逐项**做, 不许挑着做。额外三条容易漏的:

- 脚本顶部的导入顺序是硬约束(缓存目录必须设在导入 matplotlib 之前), 抄现有脚本的头部;
- 产物路径要加进 `tools/check_geo.py` 的 `PRODUCTS`, 否则无参自检覆盖不到它;
- 新页面必须被 `docs/index.md` 收录, 脚本 docstring 必须带 `docs/...` 指针——这两项
  `check_docs` 会各自报错。

## 4. 路径 C: 改共享模块

1. 读 `docs/reference/<module>.md`。
2. 改 `src/cartopy_file/`; 纯几何模块(如 `overlap`)不许 import matplotlib/cartopy, 数据准备
   脚本也要能用它。
3. 被多个图种调用的函数:先 grep 出**全部**调用点, 再逐个跑受影响的脚本验证, 不能只验证一个。
4. 同步 reference 页; 影响多个图种时还要看 `docs/overview.md` 的模块表。
5. 收尾。

## 5. 路径 D: 隔很久回来 / 换机器

1. `git log --oneline -20` 看这段时间改了什么; `git status` 必须干净再开工。
2. `uv sync` → `uv run python download_data.py --check`。
3. `uv run python tools/check_all.py`, 先拿到当前基线。
4. 需要重出全部图:按 `docs/index.md` 的出图表逐个跑, 再收尾。

## 6. 常见坑对照

| 现象 | 原因 |
| --- | --- |
| `geo.base.sha256 与底图字节不一致` | 改了代码没重新出图, 或手改了产物 |
| `源码指针不存在` | docstring 里的 `docs/...` 路径写错, 或页面被删 |
| `docs/index.md: 未收录 ...` | 新页面没加进索引表 |
| `没有指向 docs/ 的完整说明指针` | 新增 `.py` 少了 `完整说明: docs/...` 一行 |
| 两次出图不一致 | 引入了时间戳/随机数/未排序的字典或集合 |
