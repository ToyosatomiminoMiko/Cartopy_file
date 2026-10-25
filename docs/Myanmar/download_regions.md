# 掸邦特区/国界下载 (Myanmar/download_regions.py)

- 源码: [`Myanmar/download_regions.py`](../../Myanmar/download_regions.py)
- 产物: `data/regions/shan_north_boundaries.geojson`(特区/自治区域多边形)与
  `data/regions/osm_country_borders.geojson`(画框附近国界线)
- 运行: `python Myanmar/download_regions.py`

## 是什么

下载掸邦各武装/自治区域的 OpenStreetMap 行政边界关系与画框附近国界(`admin_level=2`),
拼装成多边形/折线后缓存为 GeoJSON, 供 [`northern_shan.py`](northern_shan.md) 离线绘图.

## 数据来源与拼装

- **为什么用 OSM**: 缅甸各特区没有官方测绘成果可下载; OSM 社区已按 relation 绘出 2024 年
  以后的第一特区(1 市 4 县)、佤邦(5 县 1 特区)、掸邦东部第四特区(3 县)、德昂邦的行政
  边界, 范围与各特区自己公布的图基本一致, 比手工描点精确得多;
- **国界也从 OSM 取**: Natural Earth 10m 国界在画框内只有几百个顶点, 与 OSM 区域边界沿
  国界平均偏差约 1.5 km、最大约 5 km, 叠加会画成两条线; OSM 的国界与区域边界共享同一批
  way/节点, 严丝合缝, 绘图时重合段只按国界样式画;
- **在本地拼装**: Overpass 只返回 relation + 成员 way, 一个多边形往往由几十段 way 首尾
  相接; 脚本用 shapely 把所有 way 拼成线段后 `polygonize`, 再按 outer/inner 挖洞得到标准
  GeoJSON 多边形; 国界按 way 缓存成 MultiLineString.

数据来源: OpenStreetMap 贡献者, ODbL 1.0.

## 运行

```bash
python Myanmar/download_regions.py           # 下载并缓存两个 GeoJSON
python Myanmar/download_regions.py --force   # 缓存过期时覆盖重下
```

## 注意事项

- **文件已存在就跳过**: 两个 GeoJSON 分别判断, `--force` 才覆盖;
- **分批请求**: Overpass 响应体积随成员 way 数增长, 脚本把关系分组避免超时; 佤邦整体
  单独一组, 否则与 5 个县关系合在一起请求容易 504;
- **镜像轮换**: 公共 Overpass 实例常满负荷(502), 脚本在多个镜像间轮换重试.
