# 纯几何 SVG 出图 (cartopy_file.output)

- 源码: [`src/cartopy_file/output.py`](../../src/cartopy_file/output.py)
- 导入: `from cartopy_file.output import apply_svg_output, save_svg`

## 是什么

项目统一的出图入口: 把 Figure 保存为**单个自包含的纯几何 SVG**, 不再输出 PNG. 本模块只做
三件事: 固定 SVG 相关的 rcParams、强制 `.svg` 后缀、把 Figure 写成一个文件.

- `apply_svg_output()`: 导入 matplotlib 之后调用一次, 固定 `svg.image_inline`、`svg.hashsalt`
  与 `savefig.format`;
- `save_svg()`: 把 Figure 保存为 `.svg`, 返回写入的路径; 后缀不是 `.svg` 时直接报错.

本模块**不再处理文字/字体/标签布局**: 文字外置、字体子集与 `@font-face` 内嵌、手工标签布局
(`labels.json`)与新增标注都已移除, 也不再读 `fonttools`. 产物里是否出现文字只取决于调用方,
项目脚本的约定是**不写任何文字**——地名、标题、图例、色标、刻度、注与来源由 `miko_svg_editor`
的前端排版接管(迁移中).

## 关键行为

1. **只写 SVG**: `save_svg()` 检查 `path` 的后缀, 不是 `.svg` 就抛 `ValueError`, 避免脚本漏改
   路径后又悄悄写出 PNG; `apply_svg_output()` 同时把 `savefig.format` 固定为 `svg`.
2. **栅格 base64 内联**: 矢量元素(边界、河流、填色等)按矢量写; 唯一无法矢量化的是山体晕渲
   栅格, matplotlib 把它编码成 PNG 并以 base64 内嵌(`svg.image_inline=True`), 所以产物始终是
   一个 `.svg` 文件, 不会在旁边再掉一个 `_1.png`.
3. **固定 hashsalt**: `svg.hashsalt` 固定为项目常量, SVG 内部生成的 id 稳定, 不会每次出图都变.
4. **`Date=None`**: `save_svg()` 缺省传 `metadata={"Date": None}`, 不写 `<dc:date>`; 否则每次
   出图内容都不同.
5. **字节级确定**: 同一份数据、同一环境下重复运行得到相同内容的 SVG, 提交 git 时不会因为
   时间戳/随机 id 产生无意义改动.
6. **`dpi` 只影响内嵌晕渲栅格**: 矢量部分与 dpi 无关; 缺省用 Figure 自身的 dpi, 各脚本统一显式
   传 `--dpi`(默认 300).
7. **`kwargs` 原样转给 `Figure.savefig`**: 例如 `bbox_inches="tight"`.

调用顺序: `apply_svg_output()` 必须在导入 matplotlib 之后、创建 Figure 之前调用;
`save_svg(fig, path, *, dpi=None, **kwargs)` 的 `path` 必须是 `.svg` 结尾.

## 用法

```python
from cartopy_file.data import prepare_matplotlib_env

prepare_matplotlib_env()  # 必须在导入 matplotlib 之前

import matplotlib.pyplot as plt  # noqa: E402
from cartopy_file.output import apply_svg_output, save_svg  # noqa: E402

apply_svg_output()

fig = plt.figure(...)
...
save_svg(fig, "map.svg", dpi=300)
```

## 注意事项

- 本模块不设置 `MPLCONFIGDIR`: 调用方仍必须在导入 matplotlib 之前调用
  [`cartopy_file.data.prepare_matplotlib_env()`](data.md), 否则本机只读的 `~/.config` 会让
  matplotlib 每次重建字体缓存;
- 产物不入库: `.gitignore` 忽略 `*.svg`, `save_svg()` 只负责写文件, 成品按需生成、不随仓库提交;
- 产物是纯几何地图是项目约定, 不是本模块自动剥离文字: 脚本不要调用 `ax.text()`, 也不要画
  图例、色标、标题、刻度文字、比例尺或指北针;
- `save_svg()` 不再接受文字/字体/标签布局相关的参数(如 `embed_text`、`placements`), 这些能力
  已随 `labels.py`、`svgtext.py`、`fonts.py` 一起删除;
- 确定性以同一环境为前提: 换 matplotlib 版本或改 rcParams 后, 同样的数据可能写出不同的字节.
