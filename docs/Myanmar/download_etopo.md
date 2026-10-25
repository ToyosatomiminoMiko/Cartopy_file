# 缅甸 ETOPO 高程与国界下载 (Myanmar/download_etopo.py)

- 源码: [`Myanmar/download_etopo.py`](../../Myanmar/download_etopo.py)
- 产物: `data/ETOPO_2022_v1_15s_<region>_stride<N>.nc` 与 `data/ne_10m_admin_0_countries/`
  (本地数据缓存, 不出图)
- 运行: `python Myanmar/download_etopo.py`(缅甸全境);
  `python Myanmar/download_etopo.py --region northern_shan --stride 1`(掸邦放大图)

## 是什么

下载 ETOPO 2022 15 弧秒缅甸区域子集与 Natural Earth 10m 国家边界, 缓存到 `data/`
供绘图脚本读取.

## 为什么走 ERDDAP

不直接用 xarray 打开 NOAA OPeNDAP 的几十个瓦片: 那需要在经度上跨瓦片拼接, 还要同时处理
0°/360° 与 -180°/180° 两套经度约定. 改为向 NOAA ERDDAP 请求一次已裁剪、重采样好的区域
NetCDF, 绘图时只读一个文件.

## 下载范围

默认区域(`myanmar`): 经度 85.3~107.7°E, 纬度 4.9~31.1°N. 比地图画框(87~106°E,
5~31°N)大, 是因为兰勃特投影的矩形画框在北部向两侧张开: 画框顶边对应约 85.4~107.6°E,
只下 87~106°E 时四角会露出没有高程数据的空白.

ERDDAP 经度是 0~360°, 该区域整体落在其中, 不存在跨 0°/360° 环绕问题, 不需要像 USSR
脚本那样把负经度 +360.

掸邦放大图(`--region northern_shan`): 经度 94.6~102.1°E, 纬度 18.8~25.2°N,
stride=1 约 11 MB. 南界从 20.9°N 下探到 18.8°N: 佤邦(南)延伸到 19.67°N, 画框南界定
19.0°N, 再留 0.2° 余量覆盖兰勃特投影矩形南缘的数值误差.

## 分辨率(`--stride`)

默认 `stride=2`(30 弧秒), 缅甸全境出图足够, 约 34 MB; 需要完整 15 弧秒网格时用
`--stride 1`(约 135 MB).

## 运行

```bash
python Myanmar/download_etopo.py                                   # 全境, 默认 stride=2
python Myanmar/download_etopo.py --region northern_shan --stride 1 # 掸邦放大图
python Myanmar/download_etopo.py --force                           # 强制重下(旧范围过期时)
```

## 注意事项

- **文件已存在就跳过**: 目标文件已存在且非空时不重下, 刷新时加 `--force`;
- **断点续传**: 中断留下 `.part` 文件, 再次运行尝试续传; ERDDAP 动态子集不一定支持
  Range, 若服务器忽略续传直接返回完整数据, 脚本会清空 `.part` 从头写, 避免拼出坏文件;
- **校验 NetCDF**: ERDDAP 在子集过大或参数非法时会返回 HTML 错误页, HTTP 状态码却仍是
  200; 脚本检查文件头(`CDF`/`HDF`), 不是 NetCDF 就删除并报错, 不会把 HTML 当缓存.
