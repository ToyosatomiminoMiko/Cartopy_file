# 伏尔加河流域地形图 (Volga/volga.py)

- 源码: [`Volga/volga.py`](../../Volga/volga.py); 数据准备
  [`Volga/download_data.py`](../../Volga/download_data.py)(下载/解压)与
  [`Volga/prepare_data.py`](../../Volga/prepare_data.py)(raw → 派生)
- 入口: [`Volga/main.py`](../../Volga/main.py)(子命令 download / prepare / render / all)
- 产物: `Volga/map/volga_basin_topography_etopo2022_lambert_conformal.svg`(流域图)、
  `Volga/map/volga_basin_republics_topography_etopo2022_lambert_conformal.svg`(周边共和国图);
  两张图的文字信息在 `Volga/text/` 下, 与地图同 stem 的 `.geo.json`

## 是什么

以 ETOPO 2022 地形晕渲为底图, 叠加 HydroSHEDS 伏尔加河流域、GADM 4.1 俄罗斯一级行政区、
Natural Earth 10m 河网与湖泊水面, 一次生成两张自包含 SVG:

- **流域图**: 只画流域一个主题, 不画联邦主体行政区. 画框沿用 30.3~62.3°E / 44.4~62.3°N,
  西到瓦尔代丘陵以西, 东到乌拉尔山西坡, 南到里海西北岸, 北到上卡马河源地.
- **周边共和国图**: 保留与流域直接覆盖/紧邻的六个联邦主体共和国, 科米与卡尔梅克不画;
  画框收窄到 40~60°E / 44.4~59°N, 北界足以放下卡马河中下游与六个共和国, 不再为科米留出
  60°N 以北的空白.

两图共用的图幅内容:

1. 伏尔加河流域(浅蓝填色 + 深蓝实线);
2. 俄罗斯国界(GADM 口径的陆地国界, 深灰实线);
3. 伏尔加河、卡马河、奥卡河、别拉亚河、维亚特卡河与支流河网;
4. 伏尔加—卡马梯级水库与其他湖泊水面;
5. 城市点(首都星形 / 共和国首府方块 / 一般城市圆点), 只画点位不写名称.

共和国图另有: 六国(半透明蓝紫填色 + 深紫描边)、其余联邦主体(灰色虚线界线).

地名、图例、配色、标题/注全部声明在 [`Volga/config.py`](../../Volga/config.py): 每条地名
同时给显示文案 `text`(中文/换行随图面走)与标识符 `name`(小写 ASCII slug, 拼成
`label-country-kazakhstan` 这类 id), 两张图各按自己的画框过滤成一份 `Sheet.labels`;
图例是 `Sheet.legend`/`legend_title`, 文案是 `Sheet.title`/`subtitle`/`notes`. 绘图模块
只画几何, 不拼 geo 字段.

## 设计要点

### 1. 投影与两张画框

兰勃特等角圆锥投影, 中央经线 46°E, 中央纬度 53°N, 标准纬线 47°N / 57°N. 流域主体在
45~62°N, 标准纬线夹住南北缘, 全图比例误差最小.

两张图共用投影与色带, 画框与版式写在 `Volga/config.py`(`EXTENT_BASIN` /
`EXTENT_REPUBLICS`、`LAYOUTS`), 由 `SHEETS` 里的两个 `Sheet` 驱动: 地图区高度固定
9.894 英寸, 宽度按画框投影包围盒的宽高比算, 画布宽度
随之为约 17.6 × 12.2 英寸(流域图)或 14.5 × 12.2 英寸(共和国图). 这样两种宽高比都能让
地图正好填满左侧地图区, 不靠留白对齐; 右侧面板宽度固定 4.23 英寸. 底图不再画文字但版面未重排,
右侧仍按原图例/色标/注的占位预留留白, 等前端排版接管; 地名只以 `role`/位置/字号写进同 stem
的 `.geo.json`(样式由前端 role 表统一决定). 图例条目、标题与右栏注是纯数据, 由
`layers.standard_collect` 从 `Sheet` 写进 geo.json, 绘图模块里没有手拼 geo 字段的代码.

### 2. 流域口径

HydroBASINS level 5 的伏尔加河主流域: 在入海口/三角洲窗口取 `UP_AREA` 最大的单元,
其 `MAIN_BAS=2050068680` 覆盖全流域; 同一 `MAIN_BAS` 的 41 个单元合并后面积约
141 万 km²(等积投影 EPSG:6933), 范围 31.97~60.47°E / 45.59~61.96°N, 含三角洲与卡马、奥卡、
伏尔加中游, 不含顿河、乌拉尔河、北德维纳河(三者的 `MAIN_BAS` 均不同, 与流域面只有边界
缝合级的 1e-5 平方度交集). HydroBASINS 的单元边界在里海西岸比 GADM 岸线略靠外, 出图时
再与 GADM 俄罗斯陆地并集、Natural Earth 10m 海洋面求差, 去掉岸线误差与伸进里海的尾巴,
所以图注面积按剪切后的面重算.

### 3. 行政区取舍

流域图 `draw_admin=False`: 八个共和国与其他联邦主体界一律不画, 只保留 GADM 俄罗斯国界;
`volga_subjects.geojson` 仍要读, 因为流域面要靠各州几何并集裁到陆地.

共和国图只高亮六个民族共和国: 鞑靼斯坦、巴什科尔托斯坦、楚瓦什、马里埃尔、莫尔多瓦、
乌德穆尔特. 科米与卡尔梅克在 `hidden_subjects` 里: 既不填色, 也不画自己的灰色虚线界
(与邻州的公共边仍会从邻州一侧画出). 画框内 GADM 的共和国共 14 个, 高加索诸共和国
(阿迪格、车臣、达吉斯坦、卡巴尔达-巴尔卡尔、卡拉恰伊-切尔克斯)与卡累利阿离流域主体
数百公里, 只保留灰色虚线界线, 不作主题; 这样"周边"的范围不会被读成"画框内所有共和国".

GADM 4.1 的 RUS 一级行政区不含克里米亚与塞瓦斯托波尔, 与仓库 Ukraine 图的 1991 法理口径
一致; 国界也直接用 GADM 83 个一级行政区并集的外边界, 与州界同源, 不会出现 Natural Earth
与 GADM 两套国界并行偏差.

### 4. 地形配色: 0 m 断开 + 里海低地修正

高程范围 -2196~2750 m. 色带在 0 m 处从浅蓝(水)跳到偏黄的浅绿(陆), 陆地锚点密集放在
0~500 m, 伏尔加平原上的高程差异才拉得开; 晕渲用"只压暗"的乘法因子
(`relief.make_relief` 的 `shade_strength`), 平原不会被压成灰底, 乌拉尔山与伏尔加高地
仍能看到山脊.

只按 z<0 判水会把里海沿岸低地(约 -28~0 m, 真实陆地)画成浅蓝水面, 在伏尔加下游连成
一片假海. 因此先用 Natural Earth 10m 的 ocean + lakes 判真正水域, 只有水域保留负高程
配色, 其余负高程陆地抬到 0.5 m 仍用陆地色(视觉抬升可忽略). 里海本身在 ocean 层而不是
lakes 层, 水深仍由 ETOPO 表达, 不会被等深浅蓝盖掉. 两张图共用同一份修正后的高程栅格,
流域图的画框完全覆盖共和国图, 不需要各算一次.

### 5. 河网分级

Natural Earth 10m `rivers_lake_centerlines` 按 `scalerank` 分三档: ≤3 为干流(伏尔加河,
1.9 pt + 白描边), 4~7 为较大支流(0.85 pt), ≥8 为次要河流(0.5 pt); 运河(`Canal`)不画.
画框约 1:770 万比例尺, 正是 Natural Earth 10m 的设计尺度, 不需要 HydroRIVERS 那种逐段
河网(几十 MB, 本图支流级细节用不上).

### 6. 湖泊与梯级水库

填画框内全部 Natural Earth 10m 湖泊: 伏尔加—卡马梯级水库面积小、水深浅, ETOPO 30″ 下
只是几像素宽的浅色带, 单独填色才能读出"上游窄河、下游宽水面"的沿程变化(与 Ukraine 图
处理第聂伯河梯级水库的理由一致); 咸海水面高出海平面约 29 m, 按高程配色会画成陆地, 也
只能靠湖泊面补上. 里海不填, 理由见设计要点 4.

### 7. 国界只画陆地段

GADM 各州并集的外边界同时是俄罗斯外轮廓, 含北冰洋/里海/黑海海岸和拉多加湖、奥涅加湖
湖岸. 若整条按国界样式画, 湖岸上会出现像国界的粗线, 拉多加湖西岸一个小岬角甚至会变成
一个显眼的污点. 因此用 Natural Earth 10m 海岸线与湖泊边界做蒙版, 剪掉重合段, 只留与邻国
接壤的陆地国界(与 Ukraine 图剪海岸段同一做法, 见
[`overlap`](../reference/overlap.md)).

## 数据

数据集清单(从哪下、下载范围、版本、本地路径)写在 `Volga/config.py` 的 `DATASETS` 里,
数据准备脚本与绘图脚本都只引用它; `volga.py` 只读 `Volga/data/` 下的本地文件与仓库
`data/cartopy/` 的共用底图. 数据准备拆成两步: `Volga/main.py download` 负责下载/解压,
`Volga/main.py prepare` 负责 raw → derived 派生.

| 文件 | 内容 | 准备子命令 |
| --- | --- | --- |
| `Volga/data/raw/ETOPO_2022_v1_15s_volga_stride2.nc` | NOAA ETOPO 2022 地形, 30 弧秒, 29.8~62.8°E / 43.9~62.8°N(画框四周外扩 0.5°) | `download` |
| `Volga/data/raw/gadm41_RUS_1.json` | GADM 4.1 俄罗斯一级行政区(原始) | `download` |
| `Volga/data/raw/hybas_eu_lev05_v1c.zip` | HydroBASINS level 5 欧洲区(原始压缩包) | `download` |
| `Volga/data/derived/hybas_eu_lev05_v1c/` | 解压后的 HydroBASINS shapefile | `download`(解压) |
| `Volga/data/derived/volga_subjects.geojson` | 55 个一级行政区裁到画框, 属性 name/engtype/type | `prepare` |
| `Volga/data/derived/volga_basin.geojson` | 伏尔加河流域面, 属性 area_km2 | `prepare` |
| `Volga/data/derived/russia_border.geojson` | GADM 口径俄罗斯国界(裁到画框) | `prepare` |
| `data/cartopy/.../ne_10m_rivers_lake_centerlines` | 仓库共用河网 | 仓库根 `download_data.py` |
| `data/cartopy/.../ne_10m_lakes` | 仓库共用湖泊 | 仓库根 `download_data.py` |
| `data/cartopy/.../ne_10m_ocean` | 仓库共用海洋面(里海低地判识 + 剪海岸段) | 仓库根 `download_data.py` |
| `data/cartopy/.../ne_10m_coastline` | 仓库共用海岸线(剪国界沿海段) | 仓库根 `download_data.py` |

`Volga/data/raw/` 只放下载原样, `Volga/data/derived/` 放解压目录与派生 GeoJSON. 下载走
`cartopy_file.fetch` 的共享下载层: 已有文件直接跳过, 中断的 `.part` 用 Range 续传, 下载
完成先校验文件头(NetCDF/zip/JSON). 派生每次都从 raw 重建, 不缓存中间结果. Natural Earth
10m 图层由仓库根 `download_data.py` 预取到 `data/cartopy/`, 本图种脚本不重复下载.

## 运行

唯一可执行入口是 `Volga/main.py`, 按子命令分工; 下面三个步骤也是 `all` 的顺序:

```bash
python Volga/main.py download   # 首次: 下载/解压 ETOPO、GADM、HydroBASINS 到 Volga/data/
python Volga/main.py prepare    # 从 raw 派生三个 GeoJSON 到 Volga/data/derived/
python Volga/main.py render     # 依次出两张图, 地图进 Volga/map/, 文字信息进 Volga/text/
python Volga/main.py all        # 依次执行 download → prepare → render
```

`Volga/download_data.py`、`Volga/prepare_data.py`、`Volga/volga.py` 是模块, 只导出 `run()`,
不能直接运行(直接执行会报错并指向入口); 命令行参数统一在 `main.py` 的子命令上解析.

`download` 的选项:

- `--check`: 只检查数据是否齐全(含派生文件), 不联网; 失败项按数据集类型提示该跑哪个脚本;
- `--force`: 强制重下原始数据与重新解压;
- `--skip-basin`: 跳过 HydroBASINS 下载(只准备 ETOPO/GADM).

`prepare` 的选项:

- `--skip-basin`: 跳过流域派生, 只重建行政区与国界.

`render` 的选项:

- `--sheet {all,basin,republics}`: 只出其中一张图; 缺省 all 两张都出;
- `--stride`: 用 `Volga/data/raw/` 下对应采样步长的 ETOPO 文件; 缺省自动选分辨率最高
  (步长最小)的一个;
- `--dpi`: 内嵌晕渲栅格的像素密度, 默认 300(矢量部分与 dpi 无关);
- `--show`: 保存后弹出交互窗口(需要图形界面).

数据已就位时 `download` 不联网: 三个原始文件逐项跳过, 解压目录存在也不再解压
(`--check` 会列出每一项的本地路径). `prepare` 每次运行都重建三个派生文件, 不做增量判断.

高程文件也可用环境变量 `VOLGA_ETOPO_PATH` 指定; 数据缺失时脚本直接报错. 两张图在同一次
运行里顺序生成, ETOPO、行政区与 Natural Earth 图层只读一次(图层用 `lru_cache` 缓存).

## 注意事项

- 数据必须先准备, 本图脚本不联网; 缺 raw 文件会报错并提示运行 `python Volga/main.py
  download`, 缺派生文件则提示 `python Volga/main.py prepare`.
- 派生 GeoJSON 由 `cartopy_file.geometry` 统一写: 坐标 5 位小数、紧凑分隔符、不写时间戳.
  流域面在写文件前先用 1e-5° 的 GEOS 精度网格压一次坐标(旧产物的 GDAL 写出路径就是这个
  网格); 这会让舍入后重合的顶点被删掉并重排环起点, 换写法产物就不再逐字节一致. 改派生
  写法后必须重跑 `prepare` 与 `render` 并核对产物.
- 流域面积按 HydroBASINS 口径约 141 万 km², 略高于常引用的 138 万 km²; 引用面积时标明口径,
  不与其他来源混用. 共和国图画框虽然裁掉了流域西北/北缘, 但流域面积仍是全流域口径, 不要按
  画面内面积重算.
- GADM 4.1 的俄罗斯国界不含克里米亚; 本图沿用该口径, 图上克里米亚一带没有俄罗斯一级
  行政区界与国界(与 Ukraine 图一致).
- 里海低地的负高程陆地靠 Natural Earth 海洋/湖泊面判识, 依赖仓库 `data/cartopy/` 的 10m
  ocean 层; 缺这一层时脚本会退回"z<0 全部按水面"并在终端告警.
- 湖泊填色用 Natural Earth 10m 面, 与 ETOPO 岸线有几百米级偏差; 图面 1:770 万下不可见.
- 新增第三张图时只加一个 `Sheet` 到 `Volga/config.py` 的 `SHEETS`, 并登记 `THEMES`、
  `LAYOUTS`, 再按画框过滤生成一份地名表; 画框外的城市点仍由模块自动跳过, 画布宽度按投影
  宽高比自动算;
- 图例条目、配色、标题与右栏注都在 `config.py` 里声明(图例走 `Sheet.legend`/
  `legend_title`, 文案走 `Sheet.title`/`subtitle`/`notes`), 改图例只改 config; `volga.py`
  没有 `collect` 回调, geo.json 由 `layers.standard_collect` 统一写;
- 流域面积是出图时才知道的值: 地名/图注里的 `{area_wan:.0f}` 占位符由
  `runner.render(label_vars={"area_wan": ...})` 填充, config 不读数据; 图外面板的面积注记
  (`geo.suggestions.area_annotation`)只给流域图; 共和国图把同一块文字画在图内, 传空元组
  以保留空的 `area_annotation: []`(缺键与空数组对下游是两种情况);
- label id 是 ASCII slug(`label-country-kazakhstan`、`label-river-volga-1`), 中文只进
  `labels[].text`; 同一条河标两段时序号并进 slug(volga-1 / volga-2), 共和国名用 GADM
  NAME_1 的小写形式(tatarstan、mariy-el); 改显示文案不改变 id, 改 id 等于改产物, 需要重新
  出图并由前端重新对齐布局;
- 不用 `tight_layout` / `bbox_inches="tight"`: cartopy 0.25 在非矩形投影上绘制经纬网时,
  提前绘制会触发 gridliner 的 GEOSException, tight bbox 还会把地图边缘裁掉(项目已踩过).
