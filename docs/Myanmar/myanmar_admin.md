# 缅甸省/邦级行政区双语图 (Myanmar/myanmar_admin.py)

- 源码: [`Myanmar/myanmar_admin.py`](../../Myanmar/myanmar_admin.py)
- 产物: `myanmar_administrative_divisions_bilingual.svg`(与脚本同目录)
- 运行: `python Myanmar/prepare_admin_data.py`, 再 `python Myanmar/myanmar_admin.py`

## 是什么

绘制缅甸省/邦级行政区划图: 七邦冷色、七省暖色、内比都联邦区中性浅色 + 斜线, 邦/省名与
行政中心均为中文 + English 双语标注, 叠加伊洛瓦底江、萨尔温江与 ETOPO 2022 地形晕渲.

## 设计要点

1. **颜色编码**: 7 个邦统一冷色系, 7 个省统一暖色系; 内比都联邦区既非邦也非省, 用中性
   浅色 + 斜线, 避免被误读.
2. **投影**: 兰勃特等角圆锥投影, 标准纬线 10°N / 27°N, 全国比例误差最小; 等经纬度投影
   会把高纬的克钦邦横向拉宽.
3. **地形**: ETOPO 2022 只作低透明度底纹, 不抢行政区颜色的层级; 河流单独加深.
4. **文字**: 行政区名大号中文 + 小号英文, 行政中心小号双语; 全部加白色描边, 压在深色
   地形或彩色块上仍可读.

## 数据

- `data/myanmar_admin1.geojson`: 由 [`prepare_admin_data.py`](prepare_admin_data.md) 生成;
- `data/ne_10m_admin_0_countries`: Natural Earth 10m 国界;
- `data/ne_10m_rivers_lake_centerlines`: Natural Earth 10m 河流;
- `data/ETOPO_2022_v1_15s_myanmar_stride2.nc`: NOAA ETOPO 2022 地形.
