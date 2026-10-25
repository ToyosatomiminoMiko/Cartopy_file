# 苏联高程数据准备 (USSR/download_etopo.py)

- 源码: [`USSR/download_etopo.py`](../../USSR/download_etopo.py)
- 产物: `USSR/data/ETOPO_2022_v1_15s_ussr_stride8.nc`(默认 stride=8)与
  `USSR/data/ne_110m_admin_0_countries/`(本地数据, 不入库)
- 运行: `python USSR/download_etopo.py`(默认 stride=8; 全分辨率用 `--stride 1`)

## 是什么

下载 ETOPO 2022 15 弧秒的苏联区域子集与 Natural Earth 国界, 缓存到 `USSR/data/`, 供
[`USSR/ussr.py`](ussr.md) 离线读取.

不逐个打开 NOAA OPeNDAP 的约 66 个瓦片, 而是从 NOAA ERDDAP 下载**一个**已裁剪/重采样
好的区域 NetCDF. 默认 `stride=8`(2 弧分), 300 dpi 出图已经够用, 约 0.6 GB.

## 数据来源

- **ETOPO 2022**: NOAA ERDDAP 的 `ETOPO_2022_v1_15s.nc` 网格服务, 脚本按范围与步长拼
  `z[(lat):stride:(lat)][(lon):stride:(lon)]` 查询串;
  - 范围: 经度 15°E 向东到 165°W、纬度 20°N~90°N;
  - ERDDAP 经度是 0~360°, 脚本把 `-165` 展开成 `195`;
  - 步长: 1 = 完整 15 弧秒, 2 = 30 弧秒, 4 = 1 弧分, 8 = 2 弧分(默认);
- **Natural Earth 国界**: S3 上的 `ne_110m_admin_0_countries.zip`, 解压到
  `data/ne_110m_admin_0_countries/`.

## 输出

都在 `USSR/data/` 下:

| 文件 | 内容 |
| --- | --- |
| `ETOPO_2022_v1_15s_ussr_stride<N>.nc` | ETOPO 苏联区域高程(N 即 `--stride`) |
| `ne_110m_admin_0_countries.zip` | Natural Earth 110m 国界压缩包 |
| `ne_110m_admin_0_countries/` | 解压后的 shapefile 等文件 |

## 运行

```bash
python USSR/download_etopo.py             # 默认 stride=8, 约 0.6 GB
python USSR/download_etopo.py --stride 1  # 完整 15 弧秒网格(更大)
python USSR/download_etopo.py --force     # 覆盖已存在的下载文件
```

- 目标文件已存在且非空时跳过; 传输中的文件用 `.part` + HTTP `Range` 续传;
- 网络失败退避重试 3 次; 用户中断(Ctrl-C)时提示可续传, 退出码 130;
- 目标文件已存在时脚本会提示: 若是旧的 15~170°E 范围, 需要 `--force` 重下;
- 完成后提示"现在可运行: python ussr.py".

## 注意事项

- `ussr.py` 按文件名找 `ETOPO_2022_v1_15s_ussr_stride*.nc` 并取排序后的第一个, 手工放入
  别的步长文件时注意排序结果;
- 本脚本下载的国界是 110m, 而 `ussr.py` 读的是根目录 `download_data.py` 准备的 10m;
- 依赖 NOAA ERDDAP 与 Natural Earth S3 的可用性, 网络受限时需手动准备文件.
