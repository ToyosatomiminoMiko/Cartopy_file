# 缅甸全境地形图 (Myanmar/myanmar.py)

- 源码: [`Myanmar/myanmar.py`](../../Myanmar/myanmar.py)
- 入口: [`Myanmar/main.py`](../../Myanmar/main.py)(子命令 download / prepare / render / all)
- 产物: `Myanmar/map/myanmar_topography_etopo2022_lambert_conformal.svg`(地图) 与
  `Myanmar/text/myanmar_topography_etopo2022_lambert_conformal.geo.json`(文字信息)

## 是什么

读取本地的 NOAA ETOPO 2022 缅甸区域高程 NetCDF, 用兰勃特等角圆锥投影绘制缅甸联邦共和国
全境地形图, 叠加 Natural Earth 10m 国界(仅陆上段, 半透明红色)与邻国国界(灰色虚线), 并画出主要
城市点(首都用星形标记、其余用空心圆, 不写名称). 海岸线不单独绘制, 海陆界线由地形配色在 0 m 处
的跳变表达. 地名(邻国/海域/国名/城名)不以文字画进底图, 只把 `role`/位置/字号/锚点登记进
`geo.labels`, 颜色与斜体等样式由前端 role 表统一决定. 标注 id 全是小写 ASCII slug
(如 `label-country-china`、`label-sea-andaman-sea`), 中文只出现在 `labels[].text`.

## 设计要点

### 1. 投影

兰勃特等角圆锥投影(Lambert Conformal Conic), 中央经线 96.5°E, 中央纬线 19.5°N, 标准纬线
10°N / 27°N. 缅甸南北狭长约 9.8~28.5°N: 等角圆锥比 Mercator 合适(Mercator 在 28°N 一带
明显夸大面积), 也比方位投影合适(方位投影适合圆形区域, 不适合狭长条带); 标准纬线贴近国土
南北缘, 全国比例误差远小于 1%.

### 2. 画布

南北约 26°、东西约 19°, 投影后宽高比约 3:4, 画布取 12×15 英寸, 手动画布加 `add_axes`,
地图位置完全可控, 不依赖自动布局.

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
[`reference/overlap.md`](../reference/overlap.md). 国界/邻国国界的颜色与线型是三个缅甸图种
共用的固定值, 写在 `Myanmar/config.py` 的 `COLOR_BORDER` / `BORDER_ALPHA` / `BORDER_WIDTH` /
`COLOR_NEIGHBOR`, 绘图模块只引用不再各写一份.

### 4. 地名与文案的归属

地名表 `MYANMAR_LABELS` 声明在 `Myanmar/config.py`: 每条 `Label` 的 `name` 是 id 的 ASCII
slug, `text` 才是图上显示的文案(中文), 两者分开是为了让前端按 id 引用的键不随文案漂移.
渲染模块只画陆地国界/邻国国界/城市点三层, `geo.json` 由 `runner` 缺省的
`layers.standard_collect` 按 `Sheet` 收集(地名 -> 经纬刻度 -> 色标 -> 文案), 模块里不再写
`collect` 回调, 地名/文案也不再手拼.

## 数据

| 文件 | 内容 | 生成方式 |
| --- | --- | --- |
| `Myanmar/data/raw/ETOPO_2022_v1_15s_myanmar_stride2.nc` | NOAA ETOPO 2022 高程子集(stride 2 = 30 弧秒) | `python Myanmar/main.py download --region myanmar` |
| `data/cartopy/` | 共享缓存的 Natural Earth 10m 国界/国界线/海岸线 | `python download_data.py` |

下载范围由 `Myanmar/config.py` 的画框推出来: `EXTENT_MYANMAR.padded(lon=1.7, lat=0.1)`
= 85.3~107.7°E / 4.9~31.1°N, 比地图画框(87~106°E, 5~31°N)大. 为什么不按画框直接下:
兰勃特投影的矩形画框在北部向两侧张开, 只按经纬度画框下载会让四角露出没有高程数据的空白.
这个数字只写在 `config.py` 一处, 下载脚本与绘图脚本共用; 出图时 `runner` 还会核对数据集
`bbox` 是否盖住投影后的画框. 下载机制的共性见 [`data-preparation.md`](../data-preparation.md)
的 ETOPO 一节.

## 运行

唯一入口是 `Myanmar/main.py`, 其余 `Myanmar/*.py` 都是模块(直接运行会报错并提示入口):

```bash
python download_data.py                            # 首次: 共享 Natural Earth 底图
python Myanmar/main.py download --region myanmar   # 首次: ETOPO + 行政区原始数据(已存在则跳过)
python Myanmar/main.py render --sheet myanmar      # 出图, 地图进 Myanmar/map/, 文字信息进 Myanmar/text/
```

画框、投影、色带、经纬网、地名与文案都在 [`Myanmar/config.py`](../../Myanmar/config.py);
渲染模块只画本图特有条图层(陆上国界、邻国国界、城市点), `geo.json` 由框架按 `Sheet` 收集.

`download` 的选项:

- `--region {all,myanmar,northern-shan}`: 下载区域, 缺省 `all` 两个 ETOPO 区域都下;
- `--stride`: 覆盖两个区域各自登记的默认步长(缅甸 2, 掸邦 1);
- `--force`: 覆盖已存在的下载文件;
- `--skip-regions`: 跳过掸邦特区边界/国界下载(本图不需要); 行政区原始数据仍会准备.

`render` 的选项(`--sheet myanmar`):

- `--sheet {all,myanmar,myanmar-admin,northern-shan}`: 只出其中一张; 缺省 `all` 按
  `config.SHEETS` 顺序出全部三张;
- `--stride`: 用 `Myanmar/data/raw/` 下对应采样步长的高程文件, 缺省自动选步长最小的;
- `--dpi`: 内嵌晕渲栅格的像素密度, 默认 300(矢量部分与 dpi 无关);
- `--show`: 保存后弹出交互窗口(需要图形界面).

高程文件也可用环境变量 `MYANMAR_ETOPO_PATH` 指定; 数据缺失时绘图报错并提示先跑
`python Myanmar/main.py download`.

## 注意事项

- 出图不联网, 数据必须先准备(见上表);
- 海岸线不画, 岸线就是 0 m 处的水/陆色界; 国界也只画陆上段, 海岸与岛屿边缘不出现红线;
- `--stride 1` 的全分辨率高程约 135 MB, 只在需要放大细节时下载, 全境图用默认 `stride=2`
  足够;
- 标注 id 是稳定的 ASCII slug, 前端/旧布局文件按 id 引用; 改显示文案只动 `text`,
  改 id 才算破坏兼容;
- 同一份数据重复运行得到内容相同的 SVG(理由见 [`reference/output.md`](../reference/output.md)).
