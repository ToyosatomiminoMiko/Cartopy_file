# 底图裁剪与 geo.json 出图 (cartopy_file.geo)

- 源码: [`src/cartopy_file/geo.py`](../../src/cartopy_file/geo.py)
- 导入: `from cartopy_file.geo import GeoDoc, figure_frame, save_map`

## 是什么

把「底图不画,前端排版要知道」的元数据收集成文字信息 `<stem>.geo.json`, 并把
Figure 保存成裁到地图框的纯几何底图. 地图与文字信息同 stem,分目录存放: 地图写到
`<子项目>/map/`, 文字信息写到 `<子项目>/text/`. 字段与取值口径沿用 `miko_svg_editor` 的
`mapdoc-geo` **v2** 契约(`docs/PAGE-EDITOR.md` §3): `base` / `graticule` / `labels` /
`relief` / `legend` / `suggestions`. 旧 **v1** 产物不再被接受, 编辑器会要求重新生成.

- `GeoDoc(frame)`: 收集器; 脚本按图层顺序调用 `add_label()` / `add_graticule()` /
  `set_relief()` / `set_legend()` / `set_suggestions()`;
- `figure_frame(fig, ax)`: 量出地图坐标区在 Figure 里的矩形, 换算成 SVG pt 坐标;
- `save_map(...)`: 保存 SVG -> 把根标签裁到地图框 -> 按最终字节算 `sha256` -> 写调用方传入的
  文字信息路径. 两个产物路径都显式给出, 本模块不在 SVG 旁边自动写 geo.json.

## 关键行为

1. **坐标只有一套**: 底图不重新变换几何, 只改根标签的 `viewBox` / `width` / `height`
   来裁到地图框, 因此 geo 里的 `x/y` 与底图坐标逐值一致(原点为原 Figure 左上角,
   y 向下, 单位 pt). `base.view_box` 与底图根标签由同一份 `Frame` 生成.
2. **labels 只描述语义与摆放, 不含样式**: 生成端输出 `id / role / text / x / y /
   anchor / order`, 字号/颜色/描边/斜体/字重/字距/行高/折行位置全部由前端
   `miko_svg_editor/src/config/text-style.ts` 的角色表与全局常量决定; 旋转也由前端
   处理(默认 0). v1 的 `kind / lines / color / italic / halo / rotation_deg` 已删除,
   `font_size_pt` 也不再输出(字号属于样式, 由前端 role 表决定).
   **导出文字一律单行**: `labels[].text`,`legend.entries[].label` 与 `suggestions` 里的
   标题/注/来源都不带换行符, 折行(按文本块宽度)全由前端负责; 生成端不写换行, 也不输出
   旧产物里的扩展字段 `label_lines`(v2 契约本身没有这个键). `geo.add_label` 与
   `tools/check_geo.py` 遇到换行直接报错.
3. **x 是文字块的水平锚点**: `anchor=start` 时 x 指文字块左端, `middle` 时指中心,
   `end` 时指右端(就是 matplotlib 的 `ha`). `anchor` 属于摆放数据, 不同角色/个别
   标签取值不同, 无法只由 role 推导, 所以保留.
4. **y 是文字块的垂直中心**(底图坐标), x 是水平锚点; 文案单行时它就是这段文字的中心.
   需要折行时由前端按文本块宽度决定断点并排版, 行高也由前端决定(旧成品用 `1.2 x 字号`);
   生成端不再自己算基线, 也不存行高/断点.
5. **role 枚举**与前端完全一致(唯一真源是 `src/config/text-style.ts` 的
   `MAP_LABEL_ROLES`; Python 只镜像校验, 不存样式值):

   ```text
   country  country-name  sea  city  city-reference  river  highland
   area  area-muted  area-accent-1  area-accent-2  area-accent-3
   area-accent-4  area-basin
   ```

6. **id 规则**: `label-<role 家族>-<name>[-<index>]`; 角色家族由 `_ID_PREFIX` 决定
   (`country-name -> country`, `city-reference -> city`, `area* -> area`, 其余 role 同名),
   `id_kind=` 可覆盖家族(如 `label-republic-tatarstan`). `<name>` **必须是小写 ASCII slug**
   (`spec.check_slug`): 字母数字, 用 `-` `_` `.` 连接, 例如 `label-country-belarus`;
   中文/双语后缀只放在 `labels[].text` 里(且必须单行). 为什么: id 是前端与布局文件引用的键,
   带中文时既是非法标识符, 也会随显示文案一起漂移; `tools/check_geo.py` 会拒绝不合规的
   id, 所以改名等于改产物, 必须重新出图.

   和排版编辑器的契约: 编辑器把 id 当**不透明键**, 对 `labels[].id` 只校验非空且唯一,
   不解析 `label-` 前缀或家族; 地名的样式按 `role` 查角色表, 与 id 无关(家族前缀仍保留
   在 id 里, 只作命名空间与人读分组). id 真正被引用的地方是排版块
   `page.items[].geo_label_id`(`miko_svg_editor` 的 `src/core/page.ts`): 打开已保存的
   排版时按 id 回查 `geo.labels`, 查不到就告警并回退默认版式. 所以 **改 id 是破坏性
   变更**(已存的排版失效), 改 `text` 不是; 一旦有人存过排版, id 就等于冻结.

   为什么用语义 slug 而不是序号: 地名表是手写的, 新增地名常插在中间; 语义 id 插入不
   影响其他标注, 按位置编号会让后面整体平移. 纯数字在规则上合法(`check_slug` 允许,
   如 `label-country-1`), 但编号若由顺序生成就会随插入平移, 若改成手工登记则与写 slug
   等价且更难读, 所以本仓统一用语义 slug.
7. **经纬刻度只登记落在画框内的整倍数**, 坐标取网格线与地图框边线的交点: 沿边线反查
   经纬度再插值, 不对投影做任何直线假设; `side` 由脚本决定(现有图都只标底边/左边).
8. **色标 stops 从 colormap 等距采样 21 个**(与旧成品抽出的口径一致), 不导出
   matplotlib 内部锚点, 避免版本升级改变输出.
9. **确定性**: `save_svg` 已固定 hashsalt / 不写时间戳; 本模块只改根标签属性,JSON 用
   固定缩进和字段顺序, 同样数据重复出图得到相同字节(以同一环境为前提).

## 用法

```python
from cartopy_file.geo import GeoDoc, figure_frame, relief_from_cmap, save_map

fig, ax = build_map(...)               # 只画地理要素, 不自 ax.text()
frame = figure_frame(fig, ax)
doc = GeoDoc(frame)

# role 决定前端样式(含字号); 这里只给语义 + 位置 + 锚点.
doc.add_label(ax, 50.30, 54.85, "鞑靼斯坦共和国",
              role="area-accent-1", id_kind="republic", name="tatarstan",
              ha="center")
doc.add_graticule(ax, extent, lon_step=5, lat_step=2,
                  style={"stroke": "#808080", "width_pt": 0.5,
                         "dash": [0.5, 0.825], "opacity": 0.4})
doc.set_relief(relief_from_cmap(ELEV_CMAP, title="高程 / 水深", unit="m",
                                vmin=ELEV_VMIN, vmax=ELEV_VMAX,
                                ticks=(-2000, -1000, 0, 500, 1000, 1500, 2000)))
doc.set_legend("图例", [{"label": "国界", "shape": "line",
                        "stroke": "#4a4a4a", "width_pt": 1.4}])
doc.set_suggestions({"title": "...", "subtitle": "...", "notes": ["..."],
                     "legend_title": "图例",
                     "colorbar_title": "高程 / 水深"})
# 新图种不要手写 source: layers.suggestions(sheet, catalog) 会按数据集清单生成
# 「署名 + 发布页 URL」, 见 docs/reference/layers.md.

# 产物路径由 spec 的 map_path / text_path 拼: 地图进 <子项目>/map/, 文字信息进
# <子项目>/text/.
save_map(fig, MAP_PATH, doc, geo_path=TEXT_PATH, dpi=args.dpi)
```

## 注意事项

- 脚本里**不要再用 `ax.text()` / 图例 / 色标 / 标题**: 文字只以 `doc.add_label` 的形式
  登记; 底图里出现 `<text>` 时 `save_map` 直接报错(契约 C2);
- **不要写字号/颜色/描边/斜体/旋转**: 这些属于前端 `text-style.ts` 的单一真源, 生成端写
  了也会被忽略; 需要新样式时先在 `MAP_LABEL_ROLES` 里加一个语义角色, 不要在脚本里
  硬编码字号或颜色;
- 地图框位置只在 `set_extent()` 之后量, `figure_frame` 会先 `apply_aspect()`, 否则拿到
  的是 aspect 修正前的矩形;
- `suggestions.source` 由数据集清单自动生成(每个数据源一条, 带发布页 URL), 不要手写:
  手写的来源句容易混进投影参数之类的废话, 还会漏掉 ODbL 这类许可要求的署名;
- `title/subtitle/notes/source` 用纯文本且单行(不带 `#` 等标记), 前端预填到 scene 的 text /
  legend / colorbar 组件; 图外面积注记放 `suggestions.area_annotation`, 图内区域名放
  `labels`(用 `area`/`area-muted`/`area-accent-*` 等角色);
- 文字一律单行: `labels[].text`,`legend.entries[].label` 与 `suggestions` 的标题/注/来源
  都不写换行, 折行与行高全部由前端负责; 旧产物里手工分行的 `label_lines` 已删除,
  `suggestions.notes` 也不再按行拆开(一条注一个完整字符串);
- 契约里仍未定义的 `labels[].leader/lang`,`scale`,`north`,`area_labels` 不输出: 比例尺与
  指北针仍是非目标, 现有图种不产生这些信息(旧图的指引线端点保留在脚本数据表中);
- 布局只有一种: 地图必须在 `<子项目>/map/` 下,文字信息必须在 `<子项目>/text/` 下; 只拿到
  地图路径时用 `cartopy_file.spec.geo_path_for()` 反推 geo 路径, 地图不在 `map/` 下会直接
  报错, 不做「同级找同名 geo」的回退;
- 产物不入库: `.gitignore` 忽略 `*.svg` 与 `*.geo.json`, 需要时按图种页的命令生成;
- 出图后跑 `python tools/check_geo.py <子项目>/map/<产物>.svg`(或直接无参检查全部产物):
  定位「根标签没裁,残留 `<text>`,sha 没更新,字段/枚举不合法,v1 旧字段/`label_lines`/`font_size_pt`
  残留,文字带换行」这类结构错误;
  它不做视觉判断, 前端标准校验仍以 miko 的 `mapdoc-geo` 实现为准.
