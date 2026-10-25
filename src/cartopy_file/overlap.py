# -*- coding: utf-8 -*-
# ============================================================
# overlap.py
# 边界重合替代的几何工具: 剪掉低优先级边界里与高优先级边界重合的段落,
# 让同一条线在图上只出现一次. 供各绘图脚本共用.
# 原先这段逻辑分别写在 Ukraine/ukraine.py 的函数与
# Myanmar/northern_shan.py 的内联 difference 里; 上移到共享包后只维护一份.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Reusable geometry helpers for de-duplicating coincident boundary lines.

是什么:
    - ``overlap_mask``: 把若干条参考线按给定缓冲半径膨胀后合并成一个
      裁剪蒙版; 参考线通常是"要保留的那条边界";
    - ``cut``: 从待绘制的边界线里剪掉蒙版覆盖的段落, 丢掉过短的碎段,
      再用 ``linemerge`` 把差集切开的、端点相接的部分拼回连续折线.

为什么抽出来:
    乌克兰全图与掸邦北部图都遇到"多条边界重合, 只画更重要的那一条".
    各图的差异只在三处: 哪条线胜出、缓冲半径取多大(取决于两套数据的
    坐标偏差)、胜出线用什么线型和透明度. 算法本身相同, 所以这里只抽
    算法, 上面三处仍由调用方决定.

使用约束(都是实际踩过的坑):
    1. 坐标必须重合, 或两套数据的最大偏差小于 tol. 若偏差是公里级
       (Natural Earth 国界 vs OSM 区域边界), 小 tol 剪不掉, 大 tol 又会
       把边界剪出可见缺口; 这种情况应先统一数据源, 或在数据准备阶段让
       公共段坐标一致, 而不是把 tol 调大.
    2. tol 必须大于坐标偏差、且不超过胜出线的半宽: 剪口落在胜出线
       中心线 tol 处, 只有 tol <= 半宽时剪口才被后画的胜出线盖住;
       否则剪剩的线头会露在胜出线外, 看起来是断开的.
    3. 差集会把线切成多段. 对虚线(点划线)而言, matplotlib 对每段重新
       起笔会让节距错乱, 所以这里统一 ``linemerge``; 被剪口隔开、端点
       不相接的段本来就只能各自起笔, 不受影响.
    4. ``min_length_deg`` 用来丢掉两条线以小夹角相交时留下的 1~2 km
       碎段. 取值与线宽同量级: 碎段比线宽还短时, 单独画出来只是一个
       孤立的小点, 不是有意义的边界.
    5. 半透明胜出线, 或"虚线 + 白描边"的胜出线, 必须用本模块剪掉下层
       重合段, 不能靠 zorder 叠压: 半透明线会透出下层颜色, 虚线的点划
       间隙会露出下层线. 不透明且明显更粗的实线可以靠 zorder 盖住,
       这时不需要本模块.

依赖:
    只依赖 shapely, 不导入 matplotlib/cartopy, 因此数据准备脚本也能用.
"""

from __future__ import annotations

from collections.abc import Iterable

from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, unary_union

__all__ = ["cut", "overlap_mask"]


def overlap_mask(overlays: Iterable[BaseGeometry], tol_deg: float) -> BaseGeometry:
    """把若干参考几何按 ``tol_deg``(度)缓冲后合并成裁剪蒙版.

    参数:
        overlays: 要保留的高优先级几何; 常用是线, 也可以是面(面会按整个
            面缓冲, 通常应先取 ``.boundary`` 只缓冲边线).
        tol_deg: 缓冲半径(度). 只用于吸收两套数据的坐标偏差, 不是视觉留白;
            上界见模块说明第 2 条. 必须大于 0: 线做零宽缓冲得到的是空面,
            传 0 等于不剪任何东西.

    返回:
        合并后的 (Multi)Polygon; 空输入返回空 GeometryCollection,
        ``Geometry.difference(空集)`` 会原样返回待剪线, 调用方不必特判.
    """
    return unary_union([geom.buffer(tol_deg) for geom in overlays])


def cut(
    line: BaseGeometry,
    mask: BaseGeometry,
    *,
    min_length_deg: float = 0.0,
) -> BaseGeometry | None:
    """从 ``line`` 里剪掉 ``mask`` 覆盖的段落, 过滤碎段并拼回连续折线.

    参数:
        line: 待绘制的低优先级边界; 面请先取 ``.boundary``.
        mask: ``overlap_mask`` 的结果, 或调用方自己构造的蒙版(多条参考线
            需要不同缓冲半径时, 在调用方分别膨胀后用 ``unary_union`` 拼).
        min_length_deg: 剪剩碎段的最小长度(度). 默认 0 表示不过滤; 需要丢掉
            接头碎段时按线宽量级传值, 例如 0.03(约 3 km).

    返回:
        剪剩的线(LineString / MultiLineString); 整条线都被剪掉时返回
        ``None``, 调用方据此跳过该图层.
    """
    rest = line.difference(mask)
    if rest.is_empty:
        return None
    parts = [
        part
        for part in getattr(rest, "geoms", [rest])
        if part.geom_type == "LineString" and part.length >= min_length_deg
    ]
    if not parts:
        return None
    return linemerge(parts)
