# Cartopy_file

## 安装

依赖声明在 `pyproject.toml`，共享代码在 `src/cartopy_file/` 包里。用 uv 同步环境即可：

```bash
uv sync
```

如果已有可用的 `.venv`、只想把项目本身以可编辑模式装进去（不重建环境）：

```bash
uv pip install -e .
```

调试用的 ipykernel / debugpy 放在 `dev` 依赖组里，`uv sync` 默认会一并安装。

## 字体

所有图表的字体由 [src/cartopy_file/fonts.py](src/cartopy_file/fonts.py) 统一提供，
各绘图脚本不再单独设置 `rcParams`：

- 汉字: Noto Sans Mono CJK SC
- 英文/数字: JetBrainsMonoSlashed-Medium (matplotlib 字体名 `JetBrains Mono Slashed Medium`)

在导入 matplotlib 之后调用 `apply_matplotlib_fonts()` 即可；中英文如何按字符自动
切换、为什么不能用 `font.sans-serif` 等细节见该文件顶部说明。
