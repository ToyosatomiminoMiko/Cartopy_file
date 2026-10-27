# 苏联地形图 (USSR/ussr.py)

- 源码: [`USSR/ussr.py`](../../USSR/ussr.py)
- 产物: `ussr_topography_etopo2022_lambert_azimuthal.svg`(与脚本同目录)

## 是什么

用本地 ETOPO 2022 苏联区域地形绘制兰勃特等面积方位投影(Lambert Azimuthal Equal Area)地形图,
叠加 Natural Earth 前苏联加盟共和国合并边界.

## 设计要点

### 1. 投影与范围

- 投影: `ccrs.LambertAzimuthalEqualArea(central_longitude=105,
  central_latitude=55)`, 以苏联主体附近为投影中心, 减少边缘形变;
- 显示范围: `[15, 195, 15, 90]`, 即经度 15°E 向东跨过 180° 到 165°W、纬度 15°N~90°N;
  代码不接受"最小值大于最大值", 所以把 -165 展开成 195;
- 想换外观时, 代码注释给了两个替代: `ccrs.Orthographic` 与 `ccrs.AzimuthalEquidistant`
  (都以 90°E / 55°N 为中心).

### 2. 图幅内容

- 底图: ETOPO 2022 高程, `terrain` 色带, `vmin=-5000` / `vmax=5000`, `alpha=0.9`;
- 海岸线: cartopy 的 Natural Earth 海岸线(按图幅自动选分辨率), 黑色细线;
- 红色边界: 15 个前苏联加盟共和国的 Natural Earth 国界 `unary_union` 合并成一个整体, 只画
  外轮廓、不填充, 避免盖住地形;
- 经纬网: 纬度每 10°、经度每 15°, 只画网线, 不写刻度文字;
- 画布 16×12 英寸, 不画色标与标题.

## 数据

由 [`USSR/download_etopo.py`](../../USSR/download_etopo.py) 与根目录 `download_data.py` 准备:

| 文件 | 内容 | 生成方式 |
| --- | --- | --- |
| `USSR/data/ETOPO_2022_v1_15s_ussr_stride8.nc` | ETOPO 苏联区域高程(默认 2 弧分, 约 0.6 GB) | `python USSR/download_etopo.py` |
| `USSR/data/ne_110m_admin_0_countries/` | Natural Earth 110m 国界(下载脚本的产物) | 同上 |
| `data/ne_10m_admin_0_countries/` | Natural Earth 10m 国界(绘图实际读这份) | `python download_data.py` |
| `data/cartopy/` | cartopy 缓存的海岸线 | 同上 |

前苏联 15 国: Russia, Ukraine, Belarus, Moldova, Georgia, Armenia, Azerbaijan, Kazakhstan,
Uzbekistan, Turkmenistan, Kyrgyzstan, Tajikistan, Lithuania, Latvia, Estonia. 脚本按
`NAME`/`NAME_EN`/`ADMIN` 字段筛选, 主字段没匹配时遍历所有名称字段兜底.

ETOPO 子集范围: 经度 15°E 向东到 165°W(ERDDAP 的经度是 0~360, 脚本把 -165 展开成 195)、
纬度 20°N~90°N; 默认步长 8(2 弧分, 300 dpi 出图够用).

## 运行

```bash
python USSR/download_etopo.py              # 首次: ETOPO 子集(stride=8) + 110m 国界
python download_data.py                    # 首次: 共用 10m 国界与海岸线
python USSR/ussr.py                        # 出图, 产物写到脚本同目录
```

`ussr.py` 没有命令行参数: 高程优先用环境变量 `ETOPO_PATH` 指向任意文件, 否则在
`USSR/data/` 下找 `ETOPO_2022_v1_15s_ussr_stride*.nc` 并取排序后的第一个. 末尾会
`plt.show()` 弹窗, 无图形界面环境可注释掉.

## 注意事项

- 高程文件不存在时脚本抛 `FileNotFoundError` 并给出修复命令;
- 投影实际参数是 `central_longitude=105`, 不是 90°E(原始代码如此), 引用投影参数时以代码为准;
- `ussr.py` 读 10m 国界, 而 `download_etopo.py` 下载的是 110m 版本: 图上没有红色边界时先确认
  `data/ne_10m_admin_0_countries/` 存在(跑 `python download_data.py`);
- 地形色带直接用 matplotlib 的 `terrain`, 没有像乌克兰图那样为海陆分界定制色带;
- 下载细节(ERDDAP 范围、断点续传、退出码)见
  [`data-preparation.md`](../data-preparation.md) 的 ETOPO 一节;
- 本轮只出纯几何地图, 文字与版面(标题/图例/色标/刻度/注/来源)已移除, 等待前端排版接管
  (见 miko_svg_editor 的 `docs/CARTOPY-MIGRATION.md`).
