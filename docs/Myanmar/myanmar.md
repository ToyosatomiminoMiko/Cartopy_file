# 缅甸全境地形图 (Myanmar/myanmar.py)

- 源码: [`Myanmar/myanmar.py`](../../Myanmar/myanmar.py)
- 产物: `myanmar_topography_etopo2022_lambert_conformal.svg`(与脚本同目录)
- 运行: `python Myanmar/download_etopo.py`, 再 `python Myanmar/myanmar.py`

## 是什么

读取本地 NOAA ETOPO 2022 缅甸区域高程 NetCDF, 用兰勃特等角圆锥投影绘制缅甸联邦共和国
全境地形图, 叠加 Natural Earth 10m 海岸线与国界, 标注邻国、城市和海域.

## 设计要点

投影: 兰勃特等角圆锥投影(Lambert Conformal Conic), 中央经线 96.5°E, 中央纬线
19.5°N, 标准纬线 10°N / 27°N. 缅甸南北狭长(约 9.8~28.5°N), 等角圆锥比 Mercator
更合适(Mercator 在 28°N 一带夸大面积), 也比方位投影合适(方位投影适合圆形区域, 而非
狭长条带); 标准纬线贴近南北缘, 全国比例误差远小于 1%.

## 数据

- NOAA ETOPO 2022 15 弧秒地形, NOAA ERDDAP 子集, 由
  [`download_etopo.py`](download_etopo.md) 下载;
- Natural Earth 10m 国界.
