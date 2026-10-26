# 手工标签布局 (cartopy_file.labels)

- 源码: [`src/cartopy_file/labels.py`](../../src/cartopy_file/labels.py)
- 导入: `from cartopy_file.labels import label_id, load, dump, apply`

## 是什么

把"标签最终写在哪、转到什么角度"从绘图脚本里拆出来, 存成与产物同名的
`<产物>.labels.json`. 布局里有两类东西:

- `moved`: 脚本已经画出来的标注, 记它相对**脚本默认位置/角度**的位移与旋转增量. 位移单位是
  SVG 用户单位(= pt), y 轴向下(与 SVG 一致); 旋转单位是度, 正值顺时针(与 SVG 的 `rotate`
  一致, 与 matplotlib 的 `rotation` 反号);
- `added`: 编辑器里新加的文字标注, 记绝对锚点坐标、绝对角度与从图上某个标签抄来的样式.

`save_svg` 出图时自动读取并施加(见 [reference/output.md](output.md)), 所以手工微调不会被
重跑脚本冲掉. 交互用法见 [label-editing.md](../label-editing.md).

## 关键行为

### 1. 标签 id 就是 SVG 里的 gid

`label_id(kind, name, index=None)` 拼出 `label-<kind>-<name>[-<index>]`, 例如
`label-city-莫斯科`、`label-river-伏尔加河-2`. 绘图脚本把它传给 matplotlib 的文本:

```python
ax.text(lon, lat, "莫斯科", gid=label_id("city", "莫斯科"), ...)
```

matplotlib 会把 gid 写成 `<g id="...">` 包住这条文字; 编辑器靠 `label-` 前缀认出"这是可编辑
标签", 布局文件也用它当键. 因此 id 必须跨重跑稳定: 用数据里的名字/键, 不要用"第几个标注".

### 2. 布局文件格式

```json
{
  "format": "cartopy-file-labels",
  "version": 2,
  "figure": "volga_basin_topography_etopo2022_lambert_conformal.svg",
  "moved": {
    "label-city-莫斯科": { "dx": 8.5, "dy": -6.0, "rotation": -12.0, "text": "莫斯科" }
  },
  "added": [
    {
      "key": "label-custom-1",
      "text": "伏尔加格勒",
      "x": 512.25, "y": 640.5,
      "rotation": 0.0,
      "style": {
        "font_size": 9.3, "color": "#000000", "italic": false,
        "weight": "normal", "halo_color": "#ffffff", "halo_width": 2.5,
        "anchor": "start"
      }
    }
  ]
}
```

- 位移、角度与坐标保留 3 位小数, `moved` 按 id 排序写出: 布局文件是入库的纯文本, diff 要能读;
- `moved[*].rotation` 是 v2 新增的**可选**字段: 缺省(或 v1 文件)按 0 处理; 值为 0 时不写盘;
- `moved[*].text` 只是给人看的, 施加时不参与匹配;
- `added[*].x/y` 是**文字基线锚点**在整张 SVG 画布里的坐标(不是文本框中心, 也不是经纬度);
- `added[*].rotation` 用 SVG 约定: 正值表示顺时针, 与 matplotlib 的 `rotation` 反号;
- 版本: 写盘固定 `version: 2`; 读入接受 v1(纯位移)与 v2, 其它版本直接报错. 这样旧代码读到
  带旋转的新文件会明确失败, 而不是静默丢掉手工角度.
- `style.anchor` 取 `start` / `middle` / `end`, 分别对应 matplotlib 的 left / center / right.

读入走 `from_document()`(出图与编辑器保存共用同一套校验), 字段类型不对、版本不符都直接
报错, 不会静默退回默认位置; 写盘(`dump`)也会拒绝 NaN/Inf, 否则写出的是连自己都读不回的
非标准 JSON.

### 3. 施加方式: 在 SVG 标签组上补变换, 与编辑器预览同构

标准出图路径(文字外置成 `<text>` 成功时), 已有标签的位移/旋转**不在 Figure 上改文字**, 而是
`save_svg` 写完 SVG 之后, 给该标签的 `<g id="label-...">` 补一段
`transform="translate(dx dy) rotate(角度 锚点)"`:

- 锚点按组里第一条 `<text>` 自己的 transform/x/y 折算; 多行标签整组绕同一个锚点转;
- 编辑器给选中的标签加的也是同样一段包装层变换, 所以预览和产物是同一段矩阵, 不会
  "编辑器里对齐了, 出图又偏了";
- 布局里的数值与 dpi 无关: SVG 用户单位就是 pt, `--dpi` 只影响内嵌晕渲栅格.

`embed_text=False` 或字体外置失败回退时, SVG 里没有 `<text>` 可改, 仍回退到在 Figure 上
施加变换: 位置/角度是对的, 但大角度旋转会受 `rotation_mode` 重排影响, 可能与编辑器预览
差几 pt —— 这是降级路径, 正常出图不走它.

为什么不直接改 `Text` 的位移/角度:

- 位移用 `ScaledTranslation(dx/72, -dy/72, fig.dpi_scale_trans)` 表达是准的(先投影到画布,
  再在画布上平移 pt; 不需要反演投影, 也不会把 pt 当成经纬度), 但旋转用
  `Text.set_rotation` 时 matplotlib 会按 `rotation_mode` 重新排字 —— `default` 或垂直居中
  的标签改角度后文字锚点会挪几 pt, 与编辑器绕固定锚点转的结果对不上;
- 直接调用 `labels.apply(fig, ...)` 仍用上面这套 matplotlib 变换(方便自己渲染 PNG 或看
  交互窗口), 精度不如 SVG 路径; 出图请走 `save_svg`.

新增标注按 `x/72/fig_width_in` 换成 figure 分数, 用 `fig.text(va="baseline", rotation_mode="anchor")`
补画, 因此与 SVG 里 `<text y=...>`(y 是基线)和 `rotate(a x y)`(a 顺时针)的语义一致.

`ax.annotate()` 画的标签在 SVG 路径上不特殊处理: gid 组整体加变换, 组里是哪种对齐都不影响.
只有 **Figure 路径**(直接调用 `apply()`、`--show` 同步、字形路径回退)才要单独处理 ——
`Annotation` 每次绘制时自己把 `xytext` 换算成显示坐标并把自己的 transform 换成单位阵,
所以只支持 `textcoords="offset points"` 的注释(本项目所有可编辑标注都是这种), 直接给
`xyann` 加 pt; 其它 textcoords 会打警告并跳过 —— 这条限制只影响 Figure 路径和 `--show`,
标准 SVG 路径照样按组变换施加.

带引线的标注: 标准 SVG 路径下引线在标签组外, 不会跟着文字转; Figure 路径会平移
offset-points 注释的 `xyann`, 引线端点也会跟着文字走.

### 4. SVG 里的布局标记

出图时若施加了布局, `save_svg` 会在 `<svg>` 开标签后写一行注释:

```
<!-- cartopy-file-labels:<base64 的规范化 JSON> -->
```

作用是让编辑器区分"这份布局已经烤进图里"和"布局比 SVG 新(还没重跑脚本)". 没有这层信息,
重开编辑器会把同一段位移/旋转叠加两遍. 注释对查看器没有影响, 手删也无害, 只是编辑器会当成
"这张图没有烤进布局".

### 5. 坏数据与过期数据的处理

- 布局文件不是合法 JSON / 版本不符 → 出图直接抛 `ValueError`(宁可失败也不静默丢手工调整);
- `moved` 里的 id 在图里找不到(脚本删了标注或改了 id) → 打印一条汇总警告并跳过;
- 同一 id 在图里出现多次 → 警告, 且位移与旋转会同时作用在它们身上(说明脚本的 id 分配有 bug);
- 空布局(`moved` 与 `added` 都空)不写标记, 也不会改变画面.

## 用法

绘图脚本侧只需要两件事:

```python
from cartopy_file.labels import label_id

ax.text(lon, lat, "莫斯科", gid=label_id("city", "莫斯科"), transform=ccrs.PlateCarree())

# 产物旁边存在 <产物>.labels.json 时自动施加
save_svg(fig, out_svg, dpi=args.dpi)
save_svg(fig, out_svg, dpi=args.dpi, placements=None)           # 出纯默认位置
save_svg(fig, out_svg, dpi=args.dpi, placements="x.labels.json")  # 指定布局文件
```

代码里读写布局:

```python
from cartopy_file import labels

document = labels.load("Volga/x.labels.json")
document.moved["label-city-莫斯科"] = {
    "dx": 12.0, "dy": -4.0, "rotation": -8.0, "text": "莫斯科"
}
labels.dump(document, "Volga/x.labels.json", figure="x.svg")

baked = labels.read_marker("Volga/x.svg")  # 没标记时返回 None
```

## 注意事项

- 新增标注的坐标以"SVG 画布 = Figure 画布"为基准: 脚本不要用 `bbox_inches="tight"`,
  否则画布尺寸变了, 坐标会整体错位(有 `added` 时 `save_svg` 会直接拒绝);
- 位移与旋转分别**叠加在脚本默认位置/角度上**: 改了脚本里的经纬度或自动算出的河名角度,
  手工调整仍然跟着那个新位置/新角度走;
- 新增标注的多行间距用 matplotlib 默认 `linespacing`, 与抄样式的原标签可能差一点;
- 新增文字用到的字形不在当前字体子集里: 编辑器预览会回退到系统字体, 重新出图后才内嵌正确字形;
- 布局文件与产物一起入库; 换投影/画框等版式大改时, 旧的 `added` 绝对坐标可能不再合适,
  需要重调;
- 带引线的标注(缅甸行政区图里有几条)在标准 SVG 产物里移动或旋转文字时**引线不跟着走**:
  引线是独立画师, 画的是地理位置到另一个点的连线, 不属于可编辑标签; 小幅移动通常看不出
  问题, 大改位置/角度要回脚本调. 字形路径回退(`embed_text=False` 或字体外置失败)时引线
  端点会跟着平移, 属于另一种降级表现.
