# Cartopy_file

## 字体

所有图表的字体由根目录的 [fonts.py](fonts.py) 统一提供, 各绘图脚本不再单独设置
`rcParams`:

- 汉字: Noto Sans Mono CJK SC
- 英文/数字: JetBrainsMonoSlashed-Medium (matplotlib 字体名 `JetBrains Mono Slashed Medium`)

在导入 matplotlib 之后调用 `apply_matplotlib_fonts()` 即可; 中英文如何按字符自动
切换、为什么不能用 `font.sans-serif` 等细节见 [fonts.py](fonts.py) 顶部说明.
