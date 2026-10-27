# 底图裁剪与 geo.json 出图 (cartopy_file.geo)

- 源码: [`src/cartopy_file/geo.py`](../../src/cartopy_file/geo.py)
- 导入: `from cartopy_file.geo import GeoDoc, figure_frame, save_map`

## 是什么

把「底图不画、前端排版要知道」的元数据收集成与产物同名的 `<产物>.geo.json`, 并把
Figure 保存成裁到地图框的纯几何底图. 字段与取值口径沿用 `miko_svg_editor` 的
`mapdoc-geo` v1 契约(`docs/PAGE-EDITOR.md` §3): `base` / `graticule` / `labels` /
`relief` / `legend` / `suggestions`.

- `GeoDoc(frame)`: 收集器; 脚本按图层顺序调用 `add_label()` / `add_graticule()` /
  `set_relief()` / `set_legend()` / `set_suggestions()`;
- `figure_frame(fig, ax)`: 量出地图坐标区在 Figure 里的矩形, 换算成 SVG pt 坐标;
- `save_map(fig, svg_path, doc, dpi=...)`: 保存 SVG → 把根标签裁到地图框 → 按最终
  字节算 `sha256` → 写同名 `.geo.json`.

## 关键行为

1. **坐标只有一套**: 底图不重新变换几何, 只改根标签的 `viewBox` / `width` / `height`
   来裁到地图框, 因此 geo 里的 `x/y` 与底图坐标逐值一致(原点为原 Figure 左上角,
   y 向下, 单位 pt). `base.view_box` 与底图根标签由同一份 `Frame` 生成.
2. **labels 的 x/y 是第一行基线**, 不是文字 bbox 中心: 前端 `textLayout` 把 y 当基线,
   后续行按 `字号 x 行高` 往下排. `va="center"` 的锚点在这里换算成基线, 换算系数
   `BASELINE_RATIO = 0.36` 来自旧成品抽取出的 39 条 Volga 标签(中心到基线恒为
   0.36 x 字号); 多行再按行距把首行基线移到整块中心上方.
3. **rotation_deg 与 matplotlib 相反**: 输出的是 SVG 旋转角(顺时针为正), 传参用
   matplotlib 的 `rotation`(逆时针为正), 模块内部取反并归一到 (-180, 180].
4. **id 规则沿用旧 labels.json**: `label-<kind>-<name>[-<index>]`; `kind` 用契约枚举
   (`country|sea|highland|river|city|area|other`), 需要保留旧前缀时用 `id_kind=`
   (如 `label-republic-Tatarstan`), 方便旧布局迁移到 scene.
5. **经纬刻度只登记落在画框内的整倍数**, 坐标取网格线与地图框边线的交点: 沿边线反查
   经纬度再插值, 不对投影做任何直线假设; `side` 由脚本决定(现有图都只标底边/左边).
6. **色标 stops 从 colormap 等距采样 21 个**(与旧成品抽出的口径一致), 不导出
   matplotlib 内部锚点, 避免版本升级改变输出.
7. **确定性**: `save_svg` 已固定 hashsalt / 不写时间戳; 本模块只改根标签属性、JSON 用
   固定缩进和字段顺序, 同样数据重复出图得到相同字节(以同一环境为前提).

## 用法

```python
from cartopy_file.geo import GeoDoc, figure_frame, projected_angle, relief_from_cmap, save_map

fig, ax = build_map(...)               # 只画地理要素, 不自 ax.text()
frame = figure_frame(fig, ax)
doc = GeoDoc(frame)

doc.add_label(ax, 50.30, 54.85, "鞑靼斯坦\n共和国",
              kind="area", id_kind="republic", name="Tatarstan",
              font_size_pt=12.5, color="#4a2f6b", ha="center", va="center",
              halo={"color": "#ffffff", "width_pt": 3.0})
doc.add_graticule(ax, extent, lon_step=5, lat_step=2,
                  style={"stroke": "#808080", "width_pt": 0.5,
                         "dash": [0.5, 0.825], "opacity": 0.4})
doc.set_relief(relief_from_cmap(ELEV_CMAP, title="高程 / 水深", unit="m",
                                vmin=ELEV_VMIN, vmax=ELEV_VMAX,
                                ticks=(-2000, -1000, 0, 500, 1000, 1500, 2000)))
doc.set_legend("图例", [{"label": "国界", "shape": "line",
                        "stroke": "#4a4a4a", "width_pt": 1.4}])
doc.set_suggestions({"title": "…", "subtitle": "…", "notes": ["…"],
                     "source": "…", "legend_title": "图例",
                     "colorbar_title": "高程 / 水深"})

save_map(fig, OUT_SVG, doc, dpi=args.dpi)   # 写 OUT_SVG + OUT_SVG.with_suffix(".geo.json")
```

## 注意事项

- 脚本里**不要再用 `ax.text()` / 图例 / 色标 / 标题**: 文字只以 `doc.add_label` 的形式
  登记; 底图里出现 `<text>` 时 `save_map` 直接报错(契约 C2);
- 地图框位置只在 `set_extent()` 之后量, `figure_frame` 会先 `apply_aspect()`, 否则拿到
  的是 aspect 修正前的矩形;
- `title/subtitle/notes/source` 用纯文本(不带 `#` 等标记), 前端预填到 scene 的 text /
  legend / colorbar 组件; 图外面积注记放 `suggestions.area_annotation`, 图内区域名放
  `labels`(kind=`area`);
- 多行标注只输出第一行基线: 前端固定按 `1.2 x 字号` 排行, 而旧成品用 matplotlib 的
  `linespacing`(CJK 字体下实际行距更大); 因此两行以上标注的整块视觉中心可能与旧成品差
  1~3 pt, 这是「先由前端统一行距」的必然取舍, 不在 geo 里存行距;
- 契约 v2 的 `labels[].leader/lang`、`scale`、`north`、`area_labels` 尚未输出: 比例尺与
  指北针仍是非目标, 现有图种不产生这些信息(旧图的指引线端点保留在脚本数据表中);
- 产物不入库: `.gitignore` 忽略 `*.svg` 与 `*.geo.json`, 需要时按图种页跑脚本生成;
- 出图后跑 `python tools/check_geo.py <产物>.svg`(或直接无参检查全部产物): 定位「根标签没裁、
  残留 `<text>`、sha 没更新、字段/枚举不合法」这类结构错误; 它不做视觉判断, 前端标准校验仍以
  miko 的 `mapdoc-geo` 实现为准.
