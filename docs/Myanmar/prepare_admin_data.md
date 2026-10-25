# 缅甸省/邦级行政区数据准备 (Myanmar/prepare_admin_data.py)

- 源码: [`Myanmar/prepare_admin_data.py`](../../Myanmar/prepare_admin_data.py)
- 产物: `data/myanmar_admin1.geojson`(供 [`myanmar_admin.py`](myanmar_admin.md) 读取)
- 运行: `python Myanmar/prepare_admin_data.py`

## 是什么

准备缅甸省/邦级行政区划绘图数据: 下载 GADM 4.1 缅甸一级行政区、从 OSM 取内比都联邦区
边界, 做裁剪、补缝、拓扑检查, 输出 `data/myanmar_admin1.geojson`.

## 为什么混用 GADM 和 OSM

GADM 4.1 的缅甸一级行政区只有 15 个单元中的 14 个正确: 其 "Naypyitaw Unionterritory"
只是约 1300 km² 的城市小块, 而官方联邦区面积约 7000 km². 所以用 GADM 的 14 个邦/省,
再用 OSM relation 5996482 的内比都边界替换它, 并从相邻的曼德勒省等单元中精确扣除, 避免
重叠.

## 为什么需要补缝

GADM 与 Natural Earth 10m 国界来自不同测绘成果, 直接按国界裁剪会在边境留下空隙或探出
国界的小块. 这里以 Natural Earth 国界为最终范围: 越界部分去掉, 空隙按"距离最近"并入
相邻行政区, 保证 15 个单元无重叠、无缝隙地铺满缅甸国土.

## 数据

- GADM 4.1(gadm.org): 一级行政区;
- OpenStreetMap(ODbL 1.0): 内比都联邦区(relation 5996482);
- Natural Earth 10m: 国界(`ne_10m_admin_0_countries`).

## 注意事项

- 已下载的 GADM / OSM / Natural Earth 文件存在时跳过下载, 便于断点续跑;
- 生成前做拓扑自检: 15 个单元必须无重叠、无缝铺满国界, 否则报错退出.
