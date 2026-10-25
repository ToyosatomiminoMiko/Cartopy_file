# 项目文档

一个源码文件一页说明, 路径一一对应: 把 `.py` 换成 `.md`(前缀下划线去掉)。项目总览、
安装与出图流程见仓库根 [README.md](../README.md)。

| 源码 | 文档页 |
| --- | --- |
| `Myanmar/myanmar.py` | [`Myanmar/myanmar.md`](Myanmar/myanmar.md) |
| `Myanmar/myanmar_admin.py` | [`Myanmar/myanmar_admin.md`](Myanmar/myanmar_admin.md) |
| `Myanmar/northern_shan.py` | [`Myanmar/northern_shan.md`](Myanmar/northern_shan.md) |
| `Myanmar/download_etopo.py` | [`Myanmar/download_etopo.md`](Myanmar/download_etopo.md) |
| `Myanmar/download_regions.py` | [`Myanmar/download_regions.md`](Myanmar/download_regions.md) |
| `Myanmar/prepare_admin_data.py` | [`Myanmar/prepare_admin_data.md`](Myanmar/prepare_admin_data.md) |
| `Myanmar/map_lib.py` | [`Myanmar/map_lib.md`](Myanmar/map_lib.md) |
| `USSR/ussr.py` | [`USSR/ussr.md`](USSR/ussr.md) |
| `USSR/download_etopo.py` | [`USSR/download_etopo.md`](USSR/download_etopo.md) |
| `Ukraine/ukraine.py` | [`Ukraine/ukraine.md`](Ukraine/ukraine.md) |
| `Ukraine/download_data.py` | [`Ukraine/download_data.md`](Ukraine/download_data.md) |
| `src/cartopy_file/__init__.py` | [`cartopy_file/index.md`](cartopy_file/index.md) |
| `src/cartopy_file/data.py` | [`cartopy_file/data.md`](cartopy_file/data.md) |
| `src/cartopy_file/fonts.py` | [`cartopy_file/fonts.md`](cartopy_file/fonts.md) |
| `src/cartopy_file/output.py` | [`cartopy_file/output.md`](cartopy_file/output.md) |
| `src/cartopy_file/overlap.py` | [`cartopy_file/overlap.md`](cartopy_file/overlap.md) |
| `src/cartopy_file/relief.py` | [`cartopy_file/relief.md`](cartopy_file/relief.md) |
| `download_data.py` | [`download_data.md`](download_data.md) |
| `_stride1_chunked.py` | [`stride1_chunked.md`](stride1_chunked.md) |

`global.py` 与 `AmericaArmy/main.py` 是一次性演示脚本, 不设文档页.

## 约定

- 源码头部只保留版权行、一句话摘要和指向对应文档页的路径, 详细说明写在本目录;
- 文档页开头列出源码和用法(脚本页另有产物与运行方式), 正文按"是什么 / 设计要点 /
  数据 / 注意事项"组织, 不写空节, 只写代码里看不出来的东西: 设计取舍、投影参数、
  数据来源、踩过的坑;
- 改了实现就顺手改对应文档页; 新增脚本按同一路径规则补页并更新上表.
