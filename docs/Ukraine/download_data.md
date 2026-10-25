# 乌克兰数据准备 (Ukraine/download_data.py)

- 源码: [`Ukraine/download_data.py`](../../Ukraine/download_data.py)
- 产物: `Ukraine/data/` 下的原始数据与派生 GeoJSON(在 `.gitignore` 内, 不入库), 供
  [`Ukraine/ukraine.py`](../../Ukraine/ukraine.py) 离线读取
- 运行: `python Ukraine/download_data.py`(常用选项 `--check` / `--force`)

## 是什么

准备乌克兰全图所需的全部本地数据, 分两步:

1. 下载原始数据: NOAA ETOPO 2022 乌克兰高程子集、Natural Earth 10m 国界、GADM 4.1
   乌克兰一级行政区、OCHA HDX 2021 HNO GCA/NGCA 分区、OSM 第聂伯河与梯级水库、OSM
   德涅斯特河与德左(PMR)边界、OSM 南布格河/顿河下游补段;
2. 加工成绘图脚本直接读取的 GeoJSON: 1991 年边界、各州边界、2014 年克里米亚陆上控制线、
   顿巴斯控制区/接触线、2022 年宣称四州全境、德左区域面、第聂伯河/德涅斯特河中心线与
   水库水面、南布格河/顿河中心线.

下载都是"文件已存在就跳过", 派生 GeoJSON 每次重新生成.

## 为什么用这些数据源

1. **地形**: NOAA NCEI ETOPO 2022(15 弧秒), 与缅甸/苏联图一致; 向 ERDDAP 请求已裁剪/
   重采样的区域子集, 只下一个文件, 绘图时完全离线.
2. **1991 年国际承认边界**: 用 GADM 4.1 的乌克兰一级行政区合并. Natural Earth 的
   `admin_0` 把克里米亚划给俄罗斯(事实控制口径), 无法表达"1991 年边界含克里米亚"; GADM
   4.1 的 `UKR` 把克里米亚和塞瓦斯托波尔都算作乌克兰, 合并即法理国界.
3. **2014 年实际控制线**: 克里米亚与赫尔松州的行政边界就是 2014 年 3 月以后的陆上控制线
   (彼列科普地峡/锡瓦什湖一带); 顿巴斯用 OCHA/HDX 2021 HNO 的 GCA/NGCA 两套面, 二者
   分界即接触线 —— 明斯克协议(2015-02)之后的线, 2015–2022 基本稳定, 作为"2014 年接触
   线"的近似(项目需求允许大致范围).
4. **2022 年边界**: 俄方 2022-09 单方面宣称四州"全境", 实际并未全部控制; 这里只取四州
   完整的 GADM 州界, 明确标注为"宣称"而非控制线.
5. **第聂伯河**: NE 10m 河道中心线只有约 600 个顶点, 叠在 1:330 万图上几乎看不见, 位置
   中位差约 0.8 km(个别水库段 10 km 以上). 改用 OSM `waterway=river` relation: 干流乌克兰
   段上万个顶点, 精度到几十米; 五个梯级水库另有 `natural=water` 多边形, 按实际水面填充.
   卡霍夫卡水库 2023-06 溃坝后被放空, OSM 已删除其水面, 本图讲 2022 年, 这一座用 NE 10m
   的溃坝前水库面补上.
6. **南布格河/顿河下游**: NE 10m 河网在入海前提前收笔 —— 南布格河止于 (31.75, 47.26),
   离河口约 35 km; 顿河止于 (39.38, 47.11), 还在三角洲里, 离亚速海约 10 km. 这两处用 OSM
   `waterway=river` 下游一小段补上, 并与 NE 上段在交点附近拼成一条连续中心线(见
   `build_river_extension`).
7. **德左**: 图幅西南角的摩尔多瓦境内. 用 OSM 的 PMR relation(`admin_level=3`, 见
   `TRANSNISTRIA_RELATION`), 再按图上已画出的两条线裁切: 西缘 = 德涅斯特河中心线(OSM),
   东缘 = 1991 年乌克兰国界(GADM), 这样填色边缘与河/红线是同一条几何.
   - 不用 GADM 4.1 摩尔多瓦一级单元: 其 Transnistria 单元只有 546 个顶点(平均 1.3 km
     一个), 西缘与德涅斯特河河心线中位差 5.6 km、最远约 30 km, 图上是明显大锯齿; OSM 的
     PMR 边界面与 OSM 河网同源(沿河段直接共用河线顶点), 精度到几十米.
   - 仍要裁切: PMR 面包含 Bender(宾杰里, 河右岸)与部分右岸村庄, 直接填会跨过河; 东缘再与
     1991 国界求差, 避免 OSM/GADM 国界数字化差异(~0.3~0.6 km)造成灰区尖角戳出红线.
   - PMR 关系的内环一起填: 内环是摩尔多瓦控制的左岸村庄(杜伯萨里区飞地), 本图填色只作
     位置参照、不区分实际控制, 保持一条连续地带(见 `build_transnistria`).

## 输出

都在 `Ukraine/data/` 下(已在 `.gitignore` 里):

| 文件 | 内容 |
| --- | --- |
| `ETOPO_2022_v1_15s_ukraine_stride2.nc` | ETOPO 高程 |
| `ne_10m_admin_0_countries/` | NE 10m 国界 |
| `gadm41_UKR/gadm41_UKR_1.json` | GADM 乌克兰一级行政区 |
| `ocha_gca_ngca/` | OCHA GCA/NGCA shapefile |
| `osm_dniester_river.json` | OSM 德涅斯特河干流原始关系(缓存) |
| `osm_transnistria_boundary.json` | OSM 德左(PMR)边界原始关系(缓存) |
| `ukraine_oblasts.geojson` | 27 个一级行政区(含克里米亚/塞瓦斯托波尔) |
| `ukraine_1991.geojson` | 1991 年国际承认边界(含克里米亚) |
| `crimea_2014_line.geojson` | 2014 年克里米亚陆上控制线 |
| `occupied_2014.geojson` | 2014 年顿巴斯分离武装控制区(顿/卢两州) |
| `contact_line_2014.geojson` | 2014 年顿巴斯接触线(近似) |
| `claimed_2022.geojson` | 2022 年俄方宣称的四州全境(面) |
| `transnistria.geojson` | 德左区域面(OSM PMR 按河心线/1991 国界裁切) |
| `dnieper_river_osm.geojson` | 第聂伯河干流中心线(OSM) |
| `dnieper_water_osm.geojson` | 第聂伯河梯级水库水面(OSM + NE 卡霍夫卡) |
| `dniester_river_osm.geojson` | 德涅斯特河干流中心线(OSM) |
| `southern_bug_river_osm.geojson` | 南布格河中心线(NE 上段 + OSM 下段) |
| `don_river_osm.geojson` | 顿河中心线(NE 上段 + OSM 下段) |

## 运行

```bash
python Ukraine/download_data.py           # 下载 + 加工 + 自检
python Ukraine/download_data.py --check   # 只检查数据是否齐全, 不联网
python Ukraine/download_data.py --force   # 强制重下原始数据(派生文件总是重建)
```

- 原始数据文件存在时跳过, `--force` 才覆盖; 中断后可重跑, 未完成的下载与原始 JSON 缓存
  会复用;
- OSM 数据通过公共 Overpass API 获取, 首次运行请求 relation 并缓存原始 JSON;
- 完成后做一次数据自检, 并提示下一步运行 `python Ukraine/ukraine.py`.

## 数据许可

OpenStreetMap 数据: 贡献者, ODbL 1.0. 其余来源: ETOPO 2022 / Natural Earth / GADM 4.1 /
OCHA HDX.
