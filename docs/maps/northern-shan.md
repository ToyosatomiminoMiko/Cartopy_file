# 掸邦/特区地形图 (Myanmar/northern_shan.py)

- 源码: [`Myanmar/northern_shan.py`](../../Myanmar/northern_shan.py)
- 产物: `northern_shan_topography_etopo2022_lambert_conformal.svg`(与脚本同目录)

## 是什么

以掸邦为中心, 绘制缅甸联邦第一特区(MNDAA 实控区)、德昂邦(TNLA)、佤邦(UWSA)、掸邦东部
第四特区(NDAA)及周边直到曼德勒/克耶邦的地形图, 并在第一特区内标出其前身"原果敢自治区"
的范围.

## 设计要点

### 1. 图幅与投影

- 范围 95.3~101.5°E, 19.0~24.75°N: 北到果敢/勐古的中缅边界, 东到湄公河(老挝边界),
  西到曼德勒省/勃固省一带;
- 南界取 19.0°N: 佤邦(南)最南到 19.67°N, 原先的 21.0°N 会把它拦腰截断; 19.0°N 还能
  带出克耶邦北部与南掸邦军活动区的一部分;
- 投影: 兰勃特等角圆锥投影, 中央经线 98.4°E, 标准纬线 20.0°N / 24.0°N. 区域东西约
  6.2°、南北约 5.75°, 投影后约 653 × 636 km, 接近正方形, 画布也接近方形.

### 2. 果敢与原果敢自治区

果敢西临萨尔温江, 北、东两面与中国接壤, 南面大致以南定河(南汀河)与佤邦为界.

2010–2023 年的果敢自治区由老街、拱掌两个镇区组成; 2024 年第一特区扩编为 1 市 4 县后,
这两个镇区对应老街市与果敢县, 二者合并即原自治区范围(约 2000 km²), 是第一特区的真子集.

图上用同一紫色系加深填充表示"含于第一特区", 不描内边界: 南定河纵贯果敢, 2.4 pt 的内边界
会把河压住; 也不加第二层底纹, 因为第一特区上已有 MNDAA 的"///"斜线, 两种纹理叠加会看不清.

### 3. 国界处理(本图的关键点)

Natural Earth 10m 国界在画框内只有几百个顶点(同范围 OSM 约两万个), 与 OSM 区域边界沿国界
的平均偏差约 1.5 km、最大约 5 km, 直接叠加会画成两条线. 因此国界改用 OSM
`admin_level=2` 关系(与区域边界同源、共享节点), 并把落在国界上的那一段从区域边界描边里
裁掉, 让重合段只按国界样式出现一次. 国界画成红色半透明实线(`#c62828`, alpha 0.62), 与
Ukraine 图一致: 下面的地形与区域填色透出来, 与它重合的区域边界也不会被压成一块死色. 裁剪用
[`reference/overlap.md`](../reference/overlap.md) 的 `overlap_mask` / `cut`.

### 4. 数据来源为什么用 OSM

- 缅甸各特区没有官方测绘成果可下载; OSM 社区已按 relation 绘出 2024 年以后的第一特区
  (1 市 4 县)、佤邦(5 县 1 特区)、掸邦东部第四特区(3 县)、德昂邦的行政边界, 范围与各特区
  自己公布的图基本一致, 比手工描点精确得多;
- 国界也从 OSM 取, 与区域边界共享同一批 way/节点, 严丝合缝(理由见上一条);
- 在本地拼装: Overpass 只返回 relation + 成员 way, 一个多边形往往由几十段 way 首尾相接;
  脚本用 shapely 拼成线段后 `polygonize`, 再按 outer/inner 挖洞得到标准 GeoJSON 多边形,
  国界按 way 缓存成 MultiLineString.

数据来源: OpenStreetMap 贡献者, ODbL 1.0(许可见 [`data-preparation.md`](../data-preparation.md)).

### 5. 伊洛瓦底江与萨尔温江

两条干流是本图最主要的自然地理参照, 从一般河流图层里单独强调: 先用 4.2 pt 浅色描边、再用
1.9 pt 深蓝画线, 颜色与行政图同源; 一般河流保持 0.7 pt, 不抢层级. Natural Earth 10m 把两条
江拆成多段(Salween 上游 `Nu` + 下游 `Salween`, Irrawaddy 另有三角洲段), 按 `name_en` 全部
选出再画, 河线才不会在 20.95°N 的分段点断开. 河名用与干流同色的 10.5 pt 文字加白描边,
放在河道东/西侧空地上, 不压河线、城市点和特区名. 数据仍取自共享的 cartopy Natural Earth
缓存, 不需要额外准备.

## 数据

| 文件 | 内容 | 生成方式 |
| --- | --- | --- |
| `Myanmar/data/ETOPO_2022_v1_15s_northern_shan_stride1.nc` | 15 弧秒高程子集 | `python Myanmar/download_etopo.py --region northern_shan --stride 1` |
| `Myanmar/data/regions/shan_north_boundaries.geojson` | 特区/自治区域多边形 | `python Myanmar/download_regions.py` |
| `Myanmar/data/regions/osm_country_borders.geojson` | 画框附近 OSM 国界线 | 同上 |
| `Myanmar/data/ne_10m_admin_0_countries/` | Natural Earth 10m 国界(邻国参照) | `python Myanmar/download_etopo.py` |
| `data/cartopy/` | cartopy 缓存的 10m 河流/湖泊/海陆底图 | `python download_data.py` |

`_stride1_chunked.py` 是一次性脚本: 早期用来把缅甸 15 弧秒高程分 8 个纬度带下载再拼接,
现在 `download_etopo.py --region northern_shan --stride 1` 已能一次拿到所需子集, 日常不再
需要它.

ETOPO 子集范围 94.6~102.1°E, 18.8~25.2°N: 画框南界是 19.0°N, 子集下探到 18.8°N 并留 0.2°
余量, 用来覆盖兰勃特投影矩形南缘的数值误差.

## 运行

```bash
python Myanmar/download_etopo.py --region northern_shan --stride 1   # 高程子集
python Myanmar/download_regions.py                                   # OSM 区域/国界
python Myanmar/northern_shan.py                                      # 出图
```

`northern_shan.py` 的选项: `--stride`(指定 `Myanmar/data/` 下的采样步长)、`--dpi`(内嵌
晕渲像素密度, 默认 300)、`--show`(保存后弹窗).

## 注意事项

- 两个数据准备脚本都要先跑, 缺文件时绘图脚本报错并提示对应命令;
- 下载都是"文件已存在就跳过", 刷新加 `--force`;
- Overpass 公共实例常满负荷(502): 脚本分批请求(佤邦整体单独一组, 否则与 5 个县关系合在一
  起容易 504), 并在多个镜像间轮换重试;
- 国界线与区域边界必须同源(都来自 OSM), 换成 NE 国界会重新出现双线问题.
- 图上标注可用 `python tools/label_editor.py <产物>.svg` 在浏览器里拖位置、加文字, 布局存到
  产物旁边的 `.labels.json`, 重跑脚本时自动施加(见 [label-editing.md](../label-editing.md)).
