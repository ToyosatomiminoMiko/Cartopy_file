# 全局字体 (cartopy_file.fonts)

- 源码: [`src/cartopy_file/fonts.py`](../../src/cartopy_file/fonts.py)
- 导入: `from cartopy_file.fonts import apply_matplotlib_fonts`

## 是什么

项目全局字体: 汉字用 Noto Sans Mono CJK SC, 英文与数字用 JetBrainsMonoSlashed-Medium,
两者都缺字时回退 DejaVu Sans.

## 关键行为

### 字体文件名与 matplotlib 字体名

matplotlib 按字体名表里的 `family` 字段匹配, **不是按文件名**, 所以代码里不能直接写字体文件名:

| 字体文件 | matplotlib 字体名 | 常量 |
| --- | --- | --- |
| JetBrainsMonoSlashed-Medium | `JetBrains Mono Slashed Medium` | `LATIN_FONT` |
| Noto Sans Mono CJK SC | `Noto Sans Mono CJK SC` | `CJK_FONT` |
| (兜底) | `DejaVu Sans` | `FALLBACK_FONT` |

### 中英文如何各自生效

matplotlib >= 3.6 支持逐字符回退: 把 `font.family` 设成字体列表后, 渲染每个字符时依次查找,
拉丁字母/数字命中第一个字体, 汉字命中第二个.

坑: 不能写成 `font.family = "sans-serif"` + `font.sans-serif = [...]`. 通用族别名只会被解析成
单个字体, 不参与逐字符回退, 结果汉字报 `Glyph missing` 并画成方框.

### 其他行为

- 把项目字体写入 matplotlib 的全局 rcParams, 可重复调用;
- 每次调用都检查字体是否已安装: 缺 JetBrains 或 Noto 时打印警告并自动缩短字体链, 没装字体的
  机器上仍能出图(只是回退字体), 不抛异常;
- 同时设 `axes.unicode_minus = False`, 统一用 ASCII 负号, 避免不同字体的 U+2212 字宽不一致.

## 用法

```python
import matplotlib.pyplot as plt
from cartopy_file.fonts import apply_matplotlib_fonts

apply_matplotlib_fonts()  # 导入 matplotlib 之后、创建任何文字之前调用一次

fig, ax = plt.subplots()
ax.set_title("缅甸地形")
```

## 注意事项

- 必须在导入 matplotlib 之后调用; 缓存目录(`MPLCONFIGDIR`)要在导入 matplotlib 之前设好,
  见 [`data.md`](data.md) 的 `prepare_matplotlib_env()`;
- SVG 产物里文字会转成字形路径(见 [`output.md`](output.md)), 阅读器不需要装这两套字体.
