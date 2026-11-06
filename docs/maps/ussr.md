# 苏联地形图 (USSR/ussr.py)

- 源码: [`USSR/ussr.py`](../../USSR/ussr.py)
- 入口: [`USSR/main.py`](../../USSR/main.py)(子命令 download / prepare / render / all)
- 产物: `USSR/map/ussr_topography_etopo2022_lambert_azimuthal.svg`(地图) 与
  `USSR/text/ussr_topography_etopo2022_lambert_azimuthal.geo.json`(文字信息)

## 是什么

用本地 ETOPO 2022 苏联区域地形绘制兰勃特等面积方位投影(Lambert Azimuthal Equal Area)地形图,
叠加 Natural Earth 前苏联加盟共和国合并边界.

## 设计要点

### 1. 投影与范围

- 投影: `ccrs.LambertAzimuthalEqualArea(central_longitude=105,
  central_latitude=55)`, 以苏联主体附近为投影中心, 减少边缘形变;
- 显示范围: `[15, 195, 15, 90]`, 即经度 15°E 向东跨过 180° 到 165°W,纬度 15°N~90°N;
  代码不接受"最小值大于最大值", 所以把 -165 展开成 195;
- 想换外观时, 代码注释给了两个替代: `ccrs.Orthographic` 与 `ccrs.AzimuthalEquidistant`
  (都以 90°E / 55°N 为中心).

### 2. 图幅内容

- 底图: ETOPO 2022 高程, `terrain` 色带, `vmin=-5000` / `vmax=5000`, `alpha=0.9`;
- 海岸线: cartopy 的 Natural Earth 海岸线(按图幅自动选分辨率), 黑色细线;
- 红色边界: 15 个前苏联加盟共和国的 Natural Earth 国界 `unary_union` 合并成一个整体, 只画
  外轮廓,不填充, 避免盖住地形;
- 经纬网: 纬度每 10°,经度每 15°, 只画网线, 不写刻度文字;
- 画布 16×12 英寸, 不画色标与标题.

## 数据

由 [`USSR/download_etopo.py`](../../USSR/download_etopo.py) 与根目录 `download_data.py` 准备;
数据目录按「下载原样 / 生成物」分成 `raw/` 与 `derived/`:

| 文件 | 内容 | 生成方式 |
| --- | --- | --- |
| `USSR/data/raw/ETOPO_2022_v1_15s_ussr_stride8.nc` | ETOPO 苏联区域高程(默认 2 弧分, 约 45 MB) | `python USSR/main.py download` |
| `data/cartopy/shapefiles/natural_earth/cultural/ne_10m_admin_0_countries.shp` | Natural Earth 10m 国界(全项目共用一份) | `python download_data.py` |
| `data/cartopy/shapefiles/natural_earth/physical/ne_110m_coastline.shp` | Natural Earth 110m 海岸线 | `python download_data.py` |

前苏联 15 国: Russia, Ukraine, Belarus, Moldova, Georgia, Armenia, Azerbaijan, Kazakhstan,
Uzbekistan, Turkmenistan, Kyrgyzstan, Tajikistan, Lithuania, Latvia, Estonia. 脚本按
`NAME`/`NAME_EN`/`ADMIN` 字段筛选, 主字段没匹配时遍历所有名称字段兜底.

ETOPO 子集范围: 经度 15°E 向东到 165°W(ERDDAP 的经度是 0~360, 右端写 195 = -165 + 360),
纬度 20°N~90°N; 默认步长 8(2 弧分, 300 dpi 出图够用). 这个范围就是 `USSR/config.py` 里的
`ETOPO_BBOX_USSR`, 下载范围与「这份数据覆盖多大」是同一个对象, 下载脚本不再另写一份--
旧版下载脚本写的是 20~90°N,绘图脚本写 15~90°N, 两处分叉正是本次迁移修掉的 bug.
画框底边到 15°N, 15~20°N 一带本来就没有高程数据(改前成品如此, 靠留白), 要扩到 15°N
属于换数据,会改变底图字节, 需要单独评审. 下载机制见
[`data-preparation.md`](../data-preparation.md) 的 ETOPO 一节.

## 运行

`USSR/` 只有一个可执行入口 `USSR/main.py`, 数据准备与出图都是它的子命令:

```bash
python USSR/main.py download              # 首次: ETOPO 子集(stride=8), 已存在则跳过
python download_data.py                    # 首次: 共用 Natural Earth 底图(110m 海岸线等)
python USSR/main.py render                # 出图, 地图进 USSR/map/, 文字信息进 USSR/text/
python USSR/main.py all                   # 两步合一: 先 download, 再 render
```

`download` 子命令的选项:

- `--stride`: ERDDAP 采样步长, 默认 8(2 弧分); 文件名带步长, 不同步长可共存;
- `--force`: 覆盖已存在的下载文件.

`render` 子命令的选项:

- `--stride`: 用 `USSR/data/raw/` 下对应步长的高程文件, 缺省自动选步长最小的;
- `--dpi`: 内嵌晕渲栅格的像素密度, 默认 300(矢量部分与 dpi 无关);
- `--show`: 保存后弹出交互窗口(需要图形界面).

`all` 子命令依次跑 `download` 与 `render`, `--stride` 同时用于下载和挑文件, 另有
`--force` / `--dpi` / `--show`. 高程文件也可用环境变量 `ETOPO_PATH` 指向任意文件; 数据缺失
时脚本报错, 先跑 `python USSR/main.py download` 补齐. 出图走共享的 `runner.render`, 地图框
在 `tight_layout` 之后才量, 所以底图与 geo.json 的坐标对齐.

## 注意事项

- 旧成品只有经纬**网线**, 没有刻度文字: 这一点由 `Sheet.graticule_ticks=False` 声明,
  `standard_collect` 会退化成只登记网线线型; 改成 True 会多出一圈旧图没有的刻度文字;
- 高程文件不存在时 `load_elevation` 抛 `FileNotFoundError`(不带命令提示), 先跑
  `python USSR/main.py download` 补齐;
- 投影实际参数是 `central_longitude=105`, 不是 90°E(原始代码如此), 引用投影参数时以代码为准;
- 红色苏联轮廓读共享缓存的 Natural Earth 10m 国界(`data/cartopy/`, 由根
  `download_data.py` 预取; `USSR/data/derived/` 不存这份数据), 海岸线读同一缓存的 110m
  海岸线; 10m 国界缺失时 `countries_frame()` 返回 `None`, 红色轮廓静默跳过;
- 地形色带直接用 matplotlib 的 `terrain`, 没有像乌克兰图那样为海陆分界定制色带;
- 下载细节(ERDDAP 范围,断点续传,退出码)见
  [`data-preparation.md`](../data-preparation.md) 的 ETOPO 一节.
