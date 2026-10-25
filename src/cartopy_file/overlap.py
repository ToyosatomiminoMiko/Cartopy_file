# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Reusable geometry helpers for de-duplicating coincident boundary lines.

是什么: 剪掉低优先级边界里与高优先级边界重合的段落, 让同一条线在图上只出现一次.
完整说明(算法、为什么抽出、使用约束)见 ``docs/cartopy_file/overlap.md``.
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
            上界为胜出线的半宽. 必须大于 0: 线做零宽缓冲得到的是空面,
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
