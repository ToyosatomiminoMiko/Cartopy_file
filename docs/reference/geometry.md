# 几何与 GeoJSON 工具 (cartopy_file.geometry)

- 源码: [`src/cartopy_file/geometry.py`](../../src/cartopy_file/geometry.py)
- 导入: `from cartopy_file.geometry import valid_geometry, feature, write_geojson`

## 是什么

数据准备脚本共用的纯几何工具: 修失效几何,拆面/线,删小孔,按确定性格式写 GeoJSON,量面积与
长度,清洗属性文本. 只依赖 shapely/pyproj/pandas, 不 import matplotlib/cartopy, 所以
`prepare_*.py` 与 `download_*.py` 都能直接导入.

这些函数原先在 Ukraine 与 Volga 的 `prepare_data.py` 里各有一份, 且已经漂移(坐标精度
6 位 vs 5 位,面积一个用椭球一个用等积投影,写文件一个手写 JSON 一个走 GDAL). 上移到框架层
后只有一份实现; **与图有关的阈值和精度仍留在各子项目**, 以参数传入.

## 关键行为

### 几何修复

- `valid_geometry(geom)`: 失效几何用 `make_valid` 修; `None` 与空几何返回 `None`, 调用方
  可以直接 `if geom is None: continue`;
- `extract_polygons(geom)` / `extract_lines(geom)`: 从可能嵌套的 `GeometryCollection` 里
  取出面/线并合并, 没有有效部件返回 `None`;
- `drop_small_holes(geom, min_hole_area)`: 删面积小于阈值的内部环(单位平方度). 阈值由子项目
  按图幅传(乌克兰 `1e-4`, 伏尔加 `1e-3`), 不是全局常数.

### 写 GeoJSON

- `feature(geom, props, *, precision=6, min_hole_area=None)`: 把 shapely 几何包成
  `{"type": "Feature", "properties", "geometry"}`; 给 `min_hole_area` 时先删小孔; 坐标按
  `precision` 位小数舍入. 不支持 `GeometryCollection`, 先用 `extract_*` 拆;
- `write_geojson(path, features, *, name=None)`: 写紧凑分隔符,键序固定,不写时间戳的
  FeatureCollection(带 CRS84 的 `crs` 成员). 为什么不用 GIS 库写: 同一份数据要逐字节一致,
  库的写出顺序与浮点格式化会随版本变;
- `round_coords(obj, nd)`: 递归舍入坐标, 一般由 `feature` 内部调用.

### 量算

- `geodesic_area_km2(geom)`: WGS84 椭球面积(km²). 经纬度上直接取 `area` 在高纬会严重偏小,
  不要用;
- `geodesic_length_km(geom)`: WGS84 椭球线长(km);
- `n_vertices(geom)`: 顶点数, 用于核对简化前后细节有没有丢;
- `clean_text(value)`: `None`/`NaN` 统一成空串, 避免写出 `null` 属性.

## 用法

```python
import config
from cartopy_file.geometry import (
    drop_small_holes,
    feature,
    geodesic_area_km2,
    valid_geometry,
    write_geojson,
)

MIN_HOLE_AREA_DEG = 1e-4  # 本图幅下针孔的量级; 换尺度的图要重新定

geom = valid_geometry(row.geometry)
features = [
    feature(
        geom,
        {"gid": row["GID_1"], "name_zh": name_zh, "area_km2": round(geodesic_area_km2(geom), 1)},
        precision=6,
        min_hole_area=MIN_HOLE_AREA_DEG,
    )
]
write_geojson(config.DATASETS.path("ukraine-oblasts"), features)
```

## 注意事项

- 改这里的函数会影响所有子项目的派生数据; 改完必须重跑受影响的 `prepare_*.py`, 并确认派生
  数据与出图产物符合预期(必要时逐字节比对);
- `precision` 不是全局常数: 乌克兰用 6 位(约 0.11 m), 伏尔加用 5 位(约 1.1 m), 都是远小于
  出图精度的取值, 改动会让派生文件与产物重新生成;
- 面积有两种历史口径: 本模块只留椭球面积; 伏尔加图注里的面积在绘图脚本内用等积投影
  (EPSG:6933) 单独计算, 与图注口径一致, 不要混用;
- 模块名是 `geometry`, 与 `geo.py`(底图裁剪与 geo.json 契约)不是一回事, 后者会导入
  matplotlib.
