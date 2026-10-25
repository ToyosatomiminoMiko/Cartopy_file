# 缅甸 stride1 ETOPO 分块下载 (_stride1_chunked.py)

- 源码: [`_stride1_chunked.py`](../_stride1_chunked.py)
- 性质: 一次性临时脚本, 只用于补齐缅甸 15 弧秒(stride=1) ETOPO 数据; 日常出图不需要
- 产物: `Myanmar/data/ETOPO_2022_v1_15s_myanmar_stride1.nc`
- 运行: `.venv/bin/python _stride1_chunked.py`

## 是什么

把 ERDDAP 上 85.3~107.7°E、4.9~31.1°N 的缅甸子集拆成 8 个纬度带, 每块单独下载、单独
重试; 全部完成后用 xarray 沿纬度拼接成与原 `download_etopo.py` 完全一致的文件.

## 为什么分块

ERDDAP 对一次性 130 MB 动态子集响应极慢(实测单连接约 20 KiB/s, 约 2 小时), 而且
**不支持 Range 续传**(重连续传会退回 200 从头开始). 拆成 8 块(每块约 16 MB)并行请求,
单块失败可单独重试, 不会因为断线丢掉全部进度.

## 运行

```bash
.venv/bin/python _stride1_chunked.py
```

- 中间分块落在 `Myanmar/data/_stride1_bands/`, 最终文件写到
  `Myanmar/data/ETOPO_2022_v1_15s_myanmar_stride1.nc`;
- 可重复执行/断点续跑: 已存在且校验为 NetCDF 的分块直接跳过; 最终文件已存在时不再下载,
  只做自检;
- 并发 4, 单块最多重试 5 次(按次数退避), 单次请求超时 900 s. 这几项是为 ERDDAP 的慢响应
  与偶发 0 字节挂住调的: 并发太多反而会有请求挂住, 不要随手调大.

## 完成后的自检

脚本结束时(或最终文件已存在时)自动检查三项:

1. 形状与范围: 经度 85.3~107.7、纬度 4.9~31.1, 形状 `(6289, 5377)`(15 弧秒网格);
2. 有无 NaN: 合并后 `z` 的 NaN 数必须为 0, 否则说明分块边界没对齐并报错;
3. 与 stride2 对比: 在缅甸境内几个采样点(曼德勒附近平原、克钦山区、安达曼海)打印两者
   高程, 确认量级一致(海面为负值).

## 注意事项

- 这是临时脚本, 不属于常规出图流程; 常规数据准备仍用各图种的 `download_etopo.py`;
- 分块边界都落在 15 弧秒网格上(1/240 度), 相邻块共享一行纬度, 合并时后续块去掉第一行,
  避免重复行;
- 数据目录在 `.gitignore` 的 `**/data` 之内, 中间分块与最终产物都不提交;
- 高程数据的读取/使用见 [`cartopy_file.relief`](cartopy_file/relief.md).
