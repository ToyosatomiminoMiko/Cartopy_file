# SVG 出图 (cartopy_file.output)

- 源码: [`src/cartopy_file/output.py`](../../src/cartopy_file/output.py)
- 实现细节: [`src/cartopy_file/svgtext.py`](../../src/cartopy_file/svgtext.py)
- 导入: `from cartopy_file.output import apply_svg_output, save_svg`

## 是什么

项目统一的出图格式: 所有地图产物保存为**单个自包含的 SVG**, 不再输出 PNG.

- `apply_svg_output()`: 导入 matplotlib 之后调用一次, 固定 SVG 相关的 rcParams;
- `save_svg()`: 把 Figure 保存成单个 `.svg` 文件, 并强制后缀为 `.svg`(脚本漏改路径时直接
  报错, 而不是悄悄生成 PNG). 默认把文字写成真 `<text>`, 并把本图用到的字体按字形裁剪成
  WOFF 内嵌进 `@font-face`.

## 关键行为

为什么统一用 SVG:

1. 文字、国界/州界、河流、填色、经纬网都是矢量, 放大不糊; 文字宽度用 pt 定义, 与 dpi 无关,
   换输出尺寸不用重调字号.
2. 唯一无法矢量化的是山体晕渲: `relief.make_relief` 算出的 RGB 栅格没有边界可描, matplotlib
   会把它编码成 PNG 并以 base64 内嵌(`svg.image_inline=True`), 所以产物仍是一个自包含的
   `.svg`, 不会在旁边再掉一个 `_1.png`; `--dpi` 只影响这块内嵌栅格的分辨率.
3. 文字外置 + 字体子集内嵌: 换台机器打开不缺字体、不变方框, 同时文字可以选中/复制/检索.
   - 保存前把文字上的白色描边(`pe.withStroke`)摘掉, 用 `svg.fonttype="none"` 写出 `<text>`;
   - 保存后从 SVG 里取出实际用到的字符与 `font-family`, 用 fontTools 把本机字体文件裁成
     只含这些字形的 WOFF, 以 base64 塞进顶层 `<defs>` 的 `@font-face`;
   - 描边改成 `<text>` 的 `stroke` + `paint-order: stroke`(描边必须画在字下面, 否则会吃细笔画).
   子集通常只有几十到一百多 KB, 而文字轮廓路径往往更大, 所以产物体积基本持平.
4. 风险: 不认 `@font-face` 的查看器(librsvg / ImageMagick / 部分 Office 导入 / 老软件)会
   回退系统字体, 缺字体时显示方框 —— 这是路径写法没有的风险. `save_svg(..., embed_text=False)`
   可以回到"文字转字形路径"的老行为; 外置流程任何一步抛异常时也会自动回退并打印警告.
5. `metadata={"Date": None}` + 固定 `svg.hashsalt`: 同一份数据重复出图内容相同, 提交 git 时
   不会因为时间戳/随机 id 产生无意义改动. 内嵌的字体子集也用 `recalcTimestamp=False` 生成:
   否则 fontTools 保存时会把 WOFF 里的 `head.modified` 改成"现在", 每次出图 base64 都不同.
6. 手工标签布局: `placements` 参数缺省 `"auto"`, 产物旁边存在同名的 `<name>.labels.json` 时
   自动读取并施加 —— 新增标注按 figure 坐标补画, 已有标签的位移/旋转以标签组 `transform`
   写进 SVG(与编辑器预览同构), 并把"实际施加的布局"写成 `<svg>` 开标签后的一行注释(编辑器
   据此判断布局是否已经烤进图里); 传 `None` 关闭, 传路径强制读取. 见
   [reference/labels.md](labels.md).

`apply_svg_output()` 必须在导入 matplotlib 之后、创建 Figure 之前调用; `save_svg(fig, path,
*, dpi=None, embed_text=True, placements="auto", **kwargs)` 的 `path` 必须是 `.svg` 结尾,
`dpi` 只影响内嵌晕渲栅格, 缺省用 Figure 自身的 dpi(各脚本统一显式传 `--dpi`, 默认 300),
`placements` 控制是否施加手工标签布局(见 `reference/labels.md`), `kwargs` 原样转给
`Figure.savefig`, 例如 `bbox_inches="tight"`.

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

## 注意事项

- 只处理项目在用的**单层** `pe.withStroke` 描边; 其它 path effect 原样保留, 该文字仍以轮廓
  路径写出(可正常显示, 但不可检索), 并打印警告;
- 字体名按 SVG 里写出的 `font-family` 反查 matplotlib 字体表; TTC(可变字体集合)按字体名匹配
  面序号. 本机缺字体时跳过内嵌, 文字退回查看器字体 —— matplotlib 本身也会用回退字体出图;
- 内嵌的是 OFL / Bitstream Vera 字体的子集, 产物里会写一行来源与许可声明(SVG `<style>` 注释);
- WOFF2 需要额外依赖 `brotli`, 项目没引入, 这里统一用 zlib 压缩的 WOFF;
- 本模块不设置 `MPLCONFIGDIR`: 调用方仍必须在导入 matplotlib 之前调用
  [`cartopy_file.data.prepare_matplotlib_env()`](data.md), 否则本机只读的 `~/.config` 会让
  matplotlib 每次重建字体缓存.
