# 边界重合剪枝 (cartopy_file.overlap)

- 源码: [`src/cartopy_file/overlap.py`](../../src/cartopy_file/overlap.py)
- 依赖: 只依赖 shapely, 不导入 matplotlib/cartopy, 数据准备脚本也能用
- 用法: `from cartopy_file.overlap import overlap_mask, cut`

## 是什么

边界重合替代的几何工具: 剪掉低优先级边界里与高优先级边界重合的段落, 让同一条线在图上
只出现一次. 各图只用参数区分"哪条线胜出、缓冲半径多大、胜出线用什么线型", 算法共用.

- `overlap_mask(overlays, tol_deg)`: 把参考线按 `tol_deg` 膨胀后合并成裁剪蒙版. 参考线
  通常是"要保留的那条边界"; 传入面时会按整个面缓冲, 一般应先取 `.boundary`;
  `tol_deg` 只用于吸收两套数据的坐标偏差, 不是视觉留白, 必须 > 0(线做零宽缓冲得到空面,
  等于不剪);
- `cut(line, mask, *, min_length_deg=0.0)`: 从待剪线里剪掉蒙版覆盖的段落, 丢掉过短的
  碎段, 再用 `linemerge` 把差集切开的、端点相接的部分拼回连续折线. 整条线都被剪掉时
  返回 `None`(调用方据此跳过图层); 空蒙版会原样返回待剪线, 不必特判.

## 用法

```python
from cartopy_file.overlap import cut, overlap_mask

mask = overlap_mask([admin_line], tol_deg=0.01)  # 高优先级边界
rest = cut(low_priority_line, mask, min_length_deg=0.03)  # 低优先级边界剪掉重合段
if rest is not None:
    ax.add_geometries([rest], crs=ccrs.PlateCarree(), ...)
```

## 使用约束(都是实际踩过的坑)

1. 坐标必须重合, 或两套数据的最大偏差小于 `tol`. 公里级偏差(如 Natural Earth 国界 vs
   OSM 区域边界)剪不掉: 小 `tol` 无效, 大 `tol` 会把边界剪出可见缺口 —— 应先统一数据源,
   而不是调大 `tol`.
2. `tol` 必须大于坐标偏差、且不超过胜出线的半宽: 剪口落在胜出线中心线 `tol` 处, 只有
   `tol <= 半宽` 时剪口才被后画的胜出线盖住, 否则剪剩的线头会露出来.
3. 差集会把线切成多段; 对虚线/点划线, matplotlib 对每段重新起笔会让节距错乱, 所以统一
   `linemerge`. 被剪口隔开、端点不相接的段只能各自起笔, 不受影响.
4. `min_length_deg` 用于丢掉两条线小夹角相交留下的 1~2 km 碎段, 取值与线宽同量级.
5. 半透明胜出线, 或"虚线 + 白描边"的胜出线, 必须用本模块剪掉下层重合段, 不能靠 zorder
   叠压: 半透明线会透出下层颜色, 虚线间隙会露出下层线. 不透明且明显更粗的实线可以靠
   zorder 盖住.
