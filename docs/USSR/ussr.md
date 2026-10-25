# 苏联地形图 (USSR/ussr.py)

- 源码: [`USSR/ussr.py`](../../USSR/ussr.py)
- 产物: `ussr_topography_etopo2022_lambert_azimuthal.svg`(与脚本同目录)
- 运行: `python USSR/download_etopo.py` 后 `python USSR/ussr.py`

## 是什么

用本地 ETOPO 2022 苏联区域地形绘制兰勃特等面积方位投影(Lambert Azimuthal Equal Area)
地形图, 叠加 Natural Earth 前苏联加盟共和国合并边界.

图幅内容:

- 底图: ETOPO 2022 高程, `terrain` 色带, `vmin=-5000` / `vmax=5000`, `alpha=0.9`;
- 海岸线: Natural Earth 海岸线(Cartopy 按图幅自动选分辨率), 黑色细线;
- 红色边界: 15 个前苏联加盟共和国的 Natural Earth 国界 `unary_union` 合并成一个整体,
  只画外轮廓、不填充, 避免盖住地形;
- 经纬网: 纬度每 10°、经度每 15°, 只显示左/下侧标签, 度分格式(`dms`);
- 色标 `Elevation (m)`; 标题注明数据来源与投影.

画布 16×12 英寸, 产物为单个 SVG(`save_svg`, 300 dpi, `bbox_inches="tight"`).

## 投影与范围

- 投影: `ccrs.LambertAzimuthalEqualArea(central_longitude=105, central_latitude=55)`,
  以苏联主体附近为投影中心, 减少边缘形变;
- 显示范围: `[15, 195, 15, 90]`, 即经度 15°E 向东跨过 180° 到 165°W、纬度 15°N~90°N;
  代码不接受"最小值大于最大值", 所以把 -165 展开成 195;
- 想换外观时, 代码注释给了两个替代: `ccrs.Orthographic(central_longitude=90,
  central_latitude=55)` 与 `ccrs.AzimuthalEquidistant(central_longitude=90,
  central_latitude=55)`.

## 数据

由 [`USSR/download_etopo.py`](download_etopo.md) 准备, 均放在 `USSR/data/` 下:

- **ETOPO 高程**: 优先用环境变量 `ETOPO_PATH` 指向任意已有文件; 否则在 `data/` 下查找
  `ETOPO_2022_v1_15s_ussr_stride*.nc`, 排序后取第一个; 都没有时回退到默认步长 8 的
  文件名;
- **Natural Earth 国界**: 读 `data/ne_10m_admin_0_countries/`(由根目录 `download_data.py`
  准备, 与缅甸/乌克兰共用); `USSR/download_etopo.py` 另会下载 110m 国界到
  `data/ne_110m_admin_0_countries/`. 脚本按 `NAME`/`NAME_EN`/`ADMIN` 字段筛选前苏联
  15 国, 主字段没匹配时遍历所有名称字段兜底.

前苏联 15 国: Russia, Ukraine, Belarus, Moldova, Georgia, Armenia, Azerbaijan, Kazakhstan,
Uzbekistan, Turkmenistan, Kyrgyzstan, Tajikistan, Lithuania, Latvia, Estonia.

## 注意事项

- 高程文件不存在时脚本直接抛 `FileNotFoundError` 并提示可操作的修复方式(先跑
  `download_etopo.py`, 或设 `ETOPO_PATH`);
- 脚本没有命令行参数; 末尾会 `plt.show()` 弹出窗口, 无图形界面环境可注释掉;
- 标题字符串写的是"中心 90°E, 55°N", 实际投影参数是 `central_longitude=105`(原始代码
  如此), 引用图题时以实际参数为准;
- `ussr.py` 读的是 `data/ne_10m_admin_0_countries/`, 而 `download_etopo.py` 下载的是
  110m 版本; 图上没有红色边界时先确认 10m 目录是否存在(`python download_data.py`);
- 地形色带直接用 matplotlib 的 `terrain`, 没有像乌克兰图那样为海陆分界定制色带.
