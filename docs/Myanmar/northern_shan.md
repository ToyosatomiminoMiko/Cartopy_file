# 掸邦/特区地形图 (Myanmar/northern_shan.py)

- 源码: [`Myanmar/northern_shan.py`](../../Myanmar/northern_shan.py)
- 产物: `northern_shan_topography_etopo2022_lambert_conformal.svg`(与脚本同目录)
- 运行(两条数据准备都要先跑):
  `python Myanmar/download_etopo.py --region northern_shan --stride 1`,
  `python Myanmar/download_regions.py`, 再 `python Myanmar/northern_shan.py`

## 是什么

以掸邦为中心, 绘制缅甸联邦第一特区(MNDAA 实控区)、德昂邦(TNLA)、佤邦(UWSA)、掸邦东部
第四特区(NDAA)及周边直到曼德勒/克耶邦的地形图, 并在第一特区内标出其前身"原果敢自治区"
的范围.

## 图幅与投影

- 范围 95.3~101.5°E, 19.0~24.75°N: 北到果敢/勐古的中缅边界, 东到湄公河(老挝边界),
  西到曼德勒省/勃固省一带;
- 南界取 19.0°N: 佤邦(南)最南到 19.67°N, 原先的 21.0°N 会把它拦腰截断; 19.0°N 还能
  带出克耶邦北部与南掸邦军活动区的一部分;
- 投影: 兰勃特等角圆锥投影, 中央经线 98.4°E, 标准纬线 20.0°N / 24.0°N. 区域投影后约
  653 × 636 km, 接近正方形, 画布也接近方形.

## 果敢与原果敢自治区

果敢西临萨尔温江, 北、东两面与中国接壤, 南面大致以南定河(南汀河)与佤邦为界.

2010–2023 年的果敢自治区由老街、拱掌两个镇区组成; 2024 年第一特区扩编为 1 市 4 县后,
这两个镇区对应老街市与果敢县, 二者合并即原自治区范围(约 2000 km²), 是第一特区的真子集.

图上用同一紫色系加深填充表示"含于第一特区", 不描内边界: 南定河纵贯果敢, 2.4 pt 的内
边界会把河压住; 也不加第二层底纹, 因为第一特区上已有 MNDAA 的"///"斜线, 两种纹理叠加
会看不清.

## 国界处理(本文件的关键点)

Natural Earth 10m 国界在画框内只有几百个顶点(同范围 OSM 约两万个), 与 OSM 区域边界沿
国界的平均偏差约 1.5 km、最大约 5 km, 直接叠加会画成两条线. 因此国界改用 OSM
`admin_level=2` 关系(与区域边界同源、共享节点), 并把落在国界上的那一段从区域边界描边里
裁掉, 让重合段只按国界样式出现一次.

## 数据

- 地形: ETOPO 2022 15 弧秒缅甸区域子集(`download_etopo.py --region northern_shan
  --stride 1` 下载);
- 区域/国界: OpenStreetMap(`download_regions.py` 下载并缓存为 GeoJSON).
