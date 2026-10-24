# Cartopy_file

## 安装

共享代码放在 `src/cartopy_file/` 包里。首次使用（或换新环境）时，把本仓库以可编辑
模式装进当前环境，各脚本即可正常 `import cartopy_file`：

```bash
uv pip install -e .
```

绘图依赖目前直接装在 `.venv` 里，`pyproject.toml` 的依赖列表尚未声明。

## 字体

所有图表的字体由 [src/cartopy_file/fonts.py](src/cartopy_file/fonts.py) 统一提供，
各绘图脚本不再单独设置 `rcParams`：

- 汉字: Noto Sans Mono CJK SC
- 英文/数字: JetBrainsMonoSlashed-Medium (matplotlib 字体名 `JetBrains Mono Slashed Medium`)

在导入 matplotlib 之后调用 `apply_matplotlib_fonts()` 即可；中英文如何按字符自动
切换、为什么不能用 `font.sans-serif` 等细节见该文件顶部说明。
