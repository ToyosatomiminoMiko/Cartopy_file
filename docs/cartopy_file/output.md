# SVG 出图 (cartopy_file.output)

- 源码: [`src/cartopy_file/output.py`](../../src/cartopy_file/output.py)
- 用法: `from cartopy_file.output import apply_svg_output, save_svg`

## 是什么

项目统一的出图格式: 所有地图产物保存为**单个自包含的 SVG**, 不再输出 PNG.

- `apply_svg_output()`: 导入 matplotlib 之后调用一次, 固定 SVG 相关的 rcParams;
- `save_svg()`: 把 Figure 保存成单个 `.svg` 文件, 并强制后缀为 `.svg`(脚本漏改路径时
  直接报错, 而不是悄悄生成 PNG).

## 为什么统一用 SVG

1. 文字、国界/州界、河流、填色、经纬网都是矢量, 放大不糊; 文字宽度用 pt 定义, 与 dpi
   无关, 换输出尺寸不用重调字号.
2. 唯一无法矢量化的是山体晕渲: `relief.make_relief` 算出的 RGB 栅格没有边界可描,
   matplotlib 会把它编码成 PNG 并以 base64 内嵌(`svg.image_inline=True`), 所以产物仍是
   一个自包含的 `.svg`, 不会在旁边再掉一个 `_1.png`; `--dpi` 只影响这块内嵌栅格的分辨率.
3. `svg.fonttype="path"`: 汉字转成字形路径, 换台机器打开不缺字体、不变方框; 代价是 SVG
   里的文字不能选中和检索. 本项目要的是"换台机器打开也一模一样"的成品图.
4. `metadata={"Date": None}` + 固定 `svg.hashsalt`: 同一份数据重复出图内容相同, 提交 git
   时不会因为时间戳/随机 id 产生无意义改动.

## 用法

```python
from cartopy_file.data import prepare_matplotlib_env

prepare_matplotlib_env()  # 必须在导入 matplotlib 之前

import matplotlib.pyplot as plt
from cartopy_file.fonts import apply_matplotlib_fonts
from cartopy_file.output import apply_svg_output, save_svg

apply_matplotlib_fonts()
apply_svg_output()

fig = plt.figure(...)
...
save_svg(fig, "map.svg", dpi=300)
```

- `apply_svg_output()` 必须在导入 matplotlib 之后、创建 Figure 之前调用;
- `save_svg(fig, path, *, dpi=None, **kwargs)`: `path` 必须是 `.svg` 结尾; `dpi` 只影响
  内嵌晕渲栅格, 缺省用 Figure 自身的 dpi(各脚本统一显式传 `--dpi`, 默认 300); `kwargs`
  原样转给 `Figure.savefig`, 例如 `bbox_inches="tight"`.

## 警告

本模块不设置 `MPLCONFIGDIR`: 调用方仍必须在导入 matplotlib 之前调用
`cartopy_file.data.prepare_matplotlib_env()`, 否则本机只读的 `~/.config` 会让 matplotlib
每次重建字体缓存.
