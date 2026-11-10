# 缅甸省/邦级行政区划图 (Myanmar/myanmar_admin.py)

- 源码: [`Myanmar/myanmar_admin.py`](../../Myanmar/myanmar_admin.py)
- 入口: [`Myanmar/main.py`](../../Myanmar/main.py)(唯一入口: `prepare` 派生 + `render` 出图)
- 产物: `Myanmar/map/myanmar_administrative_divisions_bilingual.svg`(地图) 与
  `Myanmar/text/myanmar_administrative_divisions_bilingual.geo.json`(文字信息)

## 是什么

绘制缅甸省/邦级行政区划图: 七邦冷色,七省暖色,内比都联邦区中性浅色加斜线, 并画出
各行政区中心点(联邦区/首都用星形,其余用空心圆), 叠加伊洛瓦底江,萨尔温江与 ETOPO 2022
地形晕渲. 国界用半透明红色,只画陆上段; 海岸线不单独绘制, 海陆界线由底色与行政区填色分界
表达. 地名(邻国/海域/行政区/行政中心/河名)的中英双语各登记成一条标注, 两条共用同一个
`role`(只有落点不同), 字号/颜色/描边等样式由前端 role 表统一决定. 标注 id 全是小写 ASCII
slug(如 `label-country-china`,`label-state-kachin`, 英文行加 `-en` 后缀), 中文只出现在
`labels[].text`; 图例/配色/标注落点与行政区属性表全部声明在 `Myanmar/config.py`.

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

### 4. 数据源为什么混用 GADM 与 OSM

GADM 4.1 的缅甸一级行政区只有 14 个单元正确: 其 "Naypyitaw Unionterritory" 只是约
1300 km² 的城市小块, 而官方联邦区面积约 7000 km². 所以 14 个邦/省取 GADM, 内比都联邦区
改用 OSM relation 5996482, 并从相邻的曼德勒省等单元中精确扣除, 避免重叠.

### 5. 为什么需要补缝

GADM 与 Natural Earth 10m 国界来自不同测绘成果, 直接按国界裁剪会在边境留下空隙或探出
国界的小块. 这里以 Natural Earth 国界为最终范围: 越界部分去掉, 空隙按"距离最近"并入相邻
行政区, 保证 15 个单元无重叠,无缝隙地铺满缅甸国土.

### 6. 国界与海岸线

国界取 15 个行政区合并后的**外环**, 与填色同源, 红线一定压在填色边缘上; 用半透明红
(`#c62828`, alpha 0.62)画, 让地形与下层填色透出来. 为什么只要外环: 相邻单元的公共边是两条
独立折线, 逐点浮点误差会在合并结果里留下零面积细缝(interior ring), 直接画 `boundary` 会把
这些细缝也当国界, 在掸邦-克钦邦,仰光省-勃固省等内部边界上留下一串红色短段(见
`country_exterior`). 沿海段再按 Natural Earth 海岸线缓冲剪掉, 只留与邻国接壤的陆上段 --
本图不画海岸线, 海陆界线由海洋底色与行政区填色分界表达, 若红线沿整圈海岸画就会变成一条
红色海岸线. 省/邦界里与国界,海岸重合的段落同样用走廊剪掉, 否则会在半透明红线下透出深灰线,
海岸上也会留一圈省界线. 邻国国界改用灰色虚线, 只作定位参照.

### 7. 图例与双语标注的声明位置

行政区属性表 `ADMIN_INFO`(GADM 名 -> key/中英文名/类型/行政中心中英文名与坐标)只在本仓
`Myanmar/config.py` 一份: 派生 `Myanmar/prepare.py` 用它生成行政区 GeoJSON 的名称/中心点
属性, 绘图模块,图例与双语标注也读它. 改行政中心名/坐标时改这一处, 再
`python Myanmar/main.py prepare` 重派生,重出图, 否则派生数据与图上的名称/落点会对不上.

图例是数据不是代码: 14 个行政区色块(7 邦冷色 + 7 省暖色) + 1 个联邦区(斜线) + 6 个符号/线型
条目, 按面板顺序声明在 `ADMIN_LEGEND`, 标题是 `ADMIN_LEGEND_TITLE`; `geo.legend` 由
`layers.standard_collect` 写入, 模块不手拼 `set_legend`. 填充色,描边色,国界/邻国国界线型
也都在 config(与 legend 共用同一份), 改色时图例与地图一起变.

双语标注的**落点**是坐标不是偏移: `geo.labels` 只认经纬度, 中文行与英文行各登记一条标注,
两条共用同一个 `role` 与 `id_kind`, 只有落点不同(行距体现在两条落点的坐标差里). 兰勃特投影
在画框各处的比例不同, 不存在统一点到度的换算系数, 所以 `ADMIN_LABEL_POSITIONS` /
`CAPITAL_LABEL_POSITIONS` / `NEIGHBOUR_LABELS` / `SEA_LABELS` / `RIVER_LABELS` 里写的是
**换算后的经纬度落点**(已含两行的相对偏移). 换投影,改画幅或 `SHEET_ADMIN.axes/figsize` 时
必须重新换算, 否则标注会偏离预期的图上位置. 行政中心的水平对齐由
`CAPITAL_LABEL_POSITIONS` 的 `ha` 给出, 叠放顺序是:
邻国/海域 -> 行政区名 -> 行政中心 -> 河名.

## 数据

原始数据由独立数据项目 `miko_gis_data` 下载, 派生文件由本仓 `prepare` 生成; 数据根定位见
[data-preparation.md](../data-preparation.md), 派生流程见 [reference/prepare.md](../reference/prepare.md):

| 文件 | 内容 | 准备方式 |
| --- | --- | --- |
| `Myanmar/build/myanmar_admin1.geojson` | 15 个一级行政区(含名称/中心点属性, 属性表是 `Myanmar/config.py` 的 `ADMIN_INFO`) | 本仓 `python Myanmar/main.py prepare` |
| `<数据根>/myanmar/raw/gadm41_MMR/gadm41_MMR_1.json` | GADM 4.1 原始 JSON | 数据项目 `python main.py download --group myanmar` |
| `<数据根>/myanmar/raw/osm_naypyidaw_union_territory.json` | OSM 内比都联邦区 relation 原始响应 | 数据项目 `python main.py download --group myanmar` |
| `<数据根>/myanmar/raw/ne_10m_rivers_lake_centerlines/` | Natural Earth 10m 河流(固定 5.0.0 版本) | 数据项目 `python main.py download --group myanmar` |
| `<数据根>/cartopy/shapefiles/natural_earth/...` | 共享缓存的 Natural Earth 10m 国界(底图)/海岸线(剪国界用)/国界线 | 数据项目 `python main.py download` 统一预取 |
| `<数据根>/myanmar/raw/ETOPO_2022_v1_15s_myanmar_stride2.nc` | NOAA ETOPO 2022 高程子集 | 数据项目 `python main.py download --group myanmar --region myanmar` |

## 运行

唯一入口是 `Myanmar/main.py`, 其余 `Myanmar/*.py` 都是模块(直接运行会报错并提示入口):

```bash
# 数据项目根(与本仓平级时: ../miko_gis_data): 下载原始数据 + 发布清单
(cd ../miko_gis_data && python main.py download --group myanmar --region myanmar)
(cd ../miko_gis_data && python main.py publish)

# 渲染仓: 派生行政区 GeoJSON, 再出图
python Myanmar/main.py prepare
python Myanmar/main.py render --sheet myanmar-admin
```

本仓的 `prepare` 不联网: 只读 manifest 指向的原始数据, 派生行政区 GeoJSON 每次全量重建并做
拓扑自检; 缺原始数据时报错并提示先到数据项目跑 `download`. `render` 的选项与其它图种相同
(`--stride` / `--dpi` / `--show`), 高程文件也可用 `MYANMAR_ETOPO_PATH` 指定.

## 注意事项

- 数据项目的 `download` 对已存在的 GADM / Natural Earth 文件跳过下载, 便于断点续跑;
- 本仓 `prepare` 生成前做拓扑自检: 15 个单元必须无重叠,无缝铺满国界, 否则报错退出;
- 国界只画陆上段, 海岸线不画; 省/邦界贴着国界/海岸的那一段会被走廊剪掉, 所以图上
  海岸处没有深灰轮廓, 由填色与海洋底色分界;
- 行政区 GeoJSON 缺失时绘图报错并提示先跑 `python Myanmar/main.py prepare`(原始数据缺失则
  提示到数据项目 `download`);
- 双语标注落点是按当前画框/投影折算的经纬度(见设计要点 7), 改投影或画幅要重算, 不要只改
  文案;
- 标注 id 是稳定的 ASCII slug, 前端按 id 引用; 改显示文案只动 `text`.
