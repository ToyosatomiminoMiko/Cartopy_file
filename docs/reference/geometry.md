# 几何工具 (cartopy_file.geometry)

- 源码: [`src/cartopy_file/geometry.py`](../../src/cartopy_file/geometry.py)
- 导入: `from cartopy_file.geometry import feature, write_geojson, ...`

## 是什么

各子项目 `prepare.py` 共用的几何与 GeoJSON 工具: 把失效几何修到能画, 从任意几何里取出面/线,
去掉接缝处的针状小孔, 按确定性格式写 GeoJSON, 按 WGS84 椭球量面积/长度/顶点数. 只依赖
shapely/pyproj/pandas, 不 import matplotlib/cartopy, 所以 `prepare` 与 `tools/` 都能用.

为什么统一收在一处: 这些操作只实现一份, 避免各子项目各写一份导致坐标精度,面积算法,写
文件方式不一致. 与图种相关的数值阈值(小孔面积等)仍由各子项目按自己的图传参, 不在这里
写死.

## 关键行为

### 几何修复与拆解

- `valid_geometry(geom)`: 自相交/失效几何用 shapely 的 `make_valid` 修成合法几何; `None`
  与空几何返回 `None`;
- `extract_geometries(geom, kinds)`: 从(可能嵌套的)`GeometryCollection` 里按类型取出部件;
- `extract_polygons(geom)`: 把任意几何裁成面(`MultiPolygon` 拆平后合并), 没有面积返回
  `None`. 伏尔加只保留与画框相交的行政区时用它;
- `extract_lines(geom)`: 把任意几何裁成线, 空则返回 `None`; 国界只取 `boundary` 的交集时用它;
- `drop_small_holes(geom, min_hole_area=1e-3)`: 删掉面积小于阈值的内部环(单位: 平方度).
  为什么需要: 相邻行政区边界不严格共线, `union` 成一个大面时接缝处会留下针状小孔(实测面积
  `< 2e-6` 平方度, 但周长可达 0.2°), 画成边界线就是一串黑点; 真正的内部环(如被包围的直辖市,
  0.1 平方度量级)远大于阈值, 会保留. 阈值与图幅尺度有关, 由各子项目传:
  乌克兰 `1e-4`, 伏尔加 `1e-3`.

### 写 GeoJSON

- `round_coords(obj, nd=6)`: 递归把坐标四舍五入到 `nd` 位小数; 缺省 6 位(`1e-6°` 约
  0.11 m), 控制体积;
- `feature(geom, props, *, precision=6, min_hole_area=None)`: 把 shapely 几何包成 GeoJSON
  `Feature`; 给 `min_hole_area` 时先删小孔, 不给则保留原始内部环; 不支持
  `GeometryCollection`, 调用前先用 `extract_polygons`/`extract_lines` 拆成面或线;
- `write_geojson(path, features, *, name=None)`: 写确定性的 RFC 7946 GeoJSON -- 紧凑分隔符,
  固定键序,`crs` 写 CRS84,不写时间戳, 打印文件体积与要素数. 为什么不用 GIS 库写: 同一份
  数据必须每次逐字节一致, 而库的写出顺序与浮点格式化会随版本变; 这里由本仓控制格式,
  内容只来自调用方给的 Feature 列表.

### 量算与文本

- `geodesic_area_km2(geom)` / `geodesic_length_km(geom)`: 用 `pyproj.Geod(ellps="WGS84")`
  算椭球面积/长度; 经纬度上直接算平面 `area`/`length` 在高纬会严重偏小, 图注面积/长度一律
  用这两个函数;
- `n_vertices(geom)`: 几何顶点数, 用于核对简化后没有丢掉细节; 各图种把值写进派生属性;
- `clean_text(value)`: 把 GADM 等数据里的 NaN/None 属性统一成空串, 以免写出 `null`.

## 用法

```python
from cartopy_file.geometry import (
    clean_text, extract_polygons, feature, geodesic_area_km2, valid_geometry, write_geojson,
)

geom = valid_geometry(row.geometry)
clipped = extract_polygons(geom.intersection(bbox))
if clipped is None:
    continue
write_geojson(
    build_path(ROOT, "volga_subjects.geojson"),
    [
        feature(
            clipped,
            {"name": clean_text(row.get("NAME_1"))},
            precision=5,             # 本图坐标取 1e-5° 网格
        )
    ],
)
print(geodesic_area_km2(clipped))
```

## 注意事项

- **坐标精度是产物契约**: 缺省 6 位是框架默认; 伏尔加用 5 位, 并在写流域面之前用
  `shapely.set_precision(1e-5)` 与 GDAL 网格几何对齐(精度 1e-5). 改精度会改变产物字节,
  属于要单独评审的改动;
- **小孔阈值不能做成全局常数**: 它跟图幅尺度与原始数据精度有关, 由子项目各自给; 改阈值会
  改变派生几何, 必须重出图;
- **不要 import 绘图栈**: 本模块被 `prepare` 与 `tools/` 使用, import matplotlib/cartopy 会
  让只做派生或只做检查的进程拖起整套绘图依赖;
- **`feature()` 不接 `GeometryCollection`**: 先 `extract_polygons`/`extract_lines`, 否则写出
  的 GeoJSON 类型不被下游接受;
- **确定性**: 调用方要保证 Feature 顺序与属性键序固定; `write_geojson` 只负责格式, 不负责
  给集合排序.
