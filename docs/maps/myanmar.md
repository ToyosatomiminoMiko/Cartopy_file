# 缅甸全境地形图 (Myanmar/myanmar.py)

- 源码: [`Myanmar/myanmar.py`](../../Myanmar/myanmar.py)
- 产物: `myanmar_topography_etopo2022_lambert_conformal.svg`(与脚本同目录)

## 是什么

读取本地的 NOAA ETOPO 2022 缅甸区域高程 NetCDF, 用兰勃特等角圆锥投影绘制缅甸联邦共和国
全境地形图, 叠加 Natural Earth 10m 国界(仅陆上段, 半透明红色)与邻国国界(灰色虚线), 标注
邻国、城市和海域. 海岸线不单独绘制, 海陆界线由地形配色在 0 m 处的跳变表达.

## 设计要点

### 1. 投影

兰勃特等角圆锥投影(Lambert Conformal Conic), 中央经线 96.5°E, 中央纬线 19.5°N, 标准纬线
10°N / 27°N. 缅甸南北狭长约 9.8~28.5°N: 等角圆锥比 Mercator 合适(Mercator 在 28°N 一带
明显夸大面积), 也比方位投影合适(方位投影适合圆形区域, 不适合狭长条带); 标准纬线贴近国土
南北缘, 全国比例误差远小于 1%.

### 2. 画布

南北约 26°、东西约 19°, 投影后宽高比约 3:4, 画布取 12×15 英寸, 手动画布加 `add_axes`,
地图与色标位置完全可控, 不依赖自动布局.

### 3. 底图: 0 m 处断开的海陆色带, 不画海岸线

先用 Natural Earth 陆地多边形在海洋色背景上铺一层真实海陆底色, 防止 ETOPO 子集边缘露白;
再叠 ETOPO 地形. 地形色带在 0 m 处断开(海水深蓝->浅蓝, 陆地浅绿->黄->棕->雪白), 海陆界线
直接由这条色界表达, 不再叠 cartopy 海岸线: 既少一条与国界争层级的线, 也避开 Natural Earth
国界与海岸线两套折线在岸边的偏差. 色带实现见 `make_relief_cmap`, 公共底图工具见
[`reference/relief.md`](../reference/relief.md).

国界同样只画陆上段: 先用 Natural Earth 海岸线缓冲把缅甸国界面里沿海岸闭合的那一段剪掉
(`COAST_CLIP_DEG`), 再以红色半透明实线(`#c62828`, alpha 0.62)画出; 邻国国界用灰色虚线,
并从缅甸国界走廊里剪掉, 免得与红线并行成双线. 红线在海岸收笔, 岸线交给 0 m 色界; 安达曼海
岛屿的边界整圈贴着海岸线, 会被一并剪掉, 岛上只剩地形色斑. 剪枝工具见
[`reference/overlap.md`](../reference/overlap.md).

## 数据

| 文件 | 内容 | 生成方式 |
| --- | --- | --- |
| `Myanmar/data/ETOPO_2022_v1_15s_myanmar_stride2.nc` | NOAA ETOPO 2022 高程子集 | `python Myanmar/download_etopo.py` |
| `Myanmar/data/ne_10m_admin_0_countries/` | Natural Earth 10m 国界 | 同上 |
| `data/cartopy/` | cartopy 缓存的 10m 海岸线/国界底图 | `python download_data.py` |

下载范围(85.3~107.7°E, 4.9~31.1°N)比地图画框(87~106°E, 5~31°N)大: 兰勃特投影的矩形画框
在北部向两侧张开, 只按画框下载会让四角露出没有高程数据的空白. 下载机制的共性见
[`data-preparation.md`](../data-preparation.md) 的 ETOPO 一节.

## 运行

```bash
python Myanmar/download_etopo.py   # 首次: ETOPO 子集 + NE 10m 国界(已存在则跳过)
python Myanmar/myanmar.py          # 出图, 产物写到脚本同目录
```

`myanmar.py` 的选项:

- `--stride`: 用 `Myanmar/data/` 下对应采样步长的高程文件, 缺省自动选步长最小的;
- `--dpi`: 内嵌晕渲栅格的像素密度, 默认 300(矢量部分与 dpi 无关);
- `--show`: 保存后弹出交互窗口(需要图形界面).

高程文件也可用环境变量 `MYANMAR_ETOPO_PATH` 指定; 数据缺失时脚本报错并提示先跑
`download_etopo.py`.

## 注意事项

- 出图不联网, 数据必须先准备(见上表);
- 海岸线不画, 岸线就是 0 m 处的水/陆色界; 国界也只画陆上段, 海岸与岛屿边缘不出现红线;
- `--stride 1` 的全分辨率高程约 135 MB, 只在需要放大细节时下载, 全境图用默认 `stride=2`
  足够;
- 同一份数据重复运行得到内容相同的 SVG(理由见 [`reference/output.md`](../reference/output.md)).
- 图上标注可用 `python tools/label_editor.py` 在浏览器里拖位置、加文字(先把
  `tools/label_editor.toml` 的 `svg` 指到这张图的产物), 布局存到产物旁边的 `.labels.json`,
  重跑脚本时自动施加(见 [label-editing.md](../label-editing.md)).
