# 缅甸省/邦级行政区双语图 (Myanmar/myanmar_admin.py)

- 源码: [`Myanmar/myanmar_admin.py`](../../Myanmar/myanmar_admin.py)
- 产物: `myanmar_administrative_divisions_bilingual.svg`(与脚本同目录)

## 是什么

绘制缅甸省/邦级行政区划图: 七邦冷色、七省暖色、内比都联邦区中性浅色加斜线, 邦/省名与行政
中心均为中文 + English 双语标注, 叠加伊洛瓦底江、萨尔温江与 ETOPO 2022 地形晕渲.

## 设计要点

### 1. 颜色编码

7 个邦统一冷色系, 7 个省统一暖色系; 内比都联邦区既非邦也非省, 用中性浅色 + 斜线, 避免被
误读成第三类行政单位.

### 2. 投影

兰勃特等角圆锥投影, 标准纬线 10°N / 27°N, 全国比例误差最小; 等经纬度投影会把高纬的克钦邦
横向拉宽.

### 3. 地形只作底纹

ETOPO 2022 以低透明度铺底, 不抢行政区颜色的层级; 伊洛瓦底江与萨尔温江单独加深, 便于读
水系与行政中心的位置关系.

### 4. 文字

行政区名大号中文 + 小号英文, 行政中心小号双语; 全部加白色描边, 压在深色地形或彩色块上仍
可读.

### 5. 数据源为什么混用 GADM 与 OSM

GADM 4.1 的缅甸一级行政区只有 14 个单元正确: 其 "Naypyitaw Unionterritory" 只是约
1300 km² 的城市小块, 而官方联邦区面积约 7000 km². 所以 14 个邦/省取 GADM, 内比都联邦区
改用 OSM relation 5996482, 并从相邻的曼德勒省等单元中精确扣除, 避免重叠.

### 6. 为什么需要补缝

GADM 与 Natural Earth 10m 国界来自不同测绘成果, 直接按国界裁剪会在边境留下空隙或探出
国界的小块. 这里以 Natural Earth 国界为最终范围: 越界部分去掉, 空隙按"距离最近"并入相邻
行政区, 保证 15 个单元无重叠、无缝隙地铺满缅甸国土.

## 数据

| 文件 | 内容 | 生成方式 |
| --- | --- | --- |
| `Myanmar/data/myanmar_admin1.geojson` | 15 个一级行政区(含名称/中心点属性) | `python Myanmar/prepare_admin_data.py` |
| `Myanmar/data/gadm41_MMR/` | GADM 4.1 原始 JSON | 同上 |
| `Myanmar/data/ne_10m_admin_0_countries/` | Natural Earth 10m 国界 | 同上(`prepare_admin_data.py` 按需下载) |
| `Myanmar/data/ne_10m_rivers_lake_centerlines/` | Natural Earth 10m 河流 | 同上 |
| `Myanmar/data/ETOPO_2022_v1_15s_myanmar_stride2.nc` | NOAA ETOPO 2022 高程子集 | `python Myanmar/download_etopo.py` |

## 运行

```bash
python Myanmar/prepare_admin_data.py   # 首次: 行政区 GeoJSON + GADM/NE 原始数据
python Myanmar/download_etopo.py       # 首次: ETOPO 高程 + NE 国界
python Myanmar/myanmar_admin.py        # 出图
```

`myanmar_admin.py` 的选项与 `myanmar.py` 相同(`--stride` / `--dpi` / `--show`), 高程文件
也可用 `MYANMAR_ETOPO_PATH` 指定.

## 注意事项

- 已下载的 GADM / Natural Earth 文件存在时跳过下载, 便于断点续跑;
- `prepare_admin_data.py` 生成前做拓扑自检: 15 个单元必须无重叠、无缝铺满国界, 否则报错退出;
- 行政区 GeoJSON 缺失时绘图脚本报错并提示先跑 `prepare_admin_data.py`.
