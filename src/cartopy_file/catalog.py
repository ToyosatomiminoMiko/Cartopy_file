# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Read the data project's manifest and expose datasets to the render pipeline.

是什么: 数据清单(``<数据根>/manifest.json``)的只读视图. 提供 ``DatasetView``(一份数据集
的路径/覆盖范围/来源)与 ``Catalog``(一个区域的清单集合: 按 id 取路径, 判就位, 折署名).
为什么用 JSON 而不是 import 数据项目: 数据项目要能单独移走, 两个仓库只靠这份文件格式
耦合; 渲染仓不安装数据项目的 Python 包, 数据项目也不依赖绘图栈.
完整说明(manifest 字段与版本,渲染仓怎么读)见 ``docs/reference/manifest.md`` 与
``docs/reference/data.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .data import DATA_ROOT_ENV, data_root, manifest_path, natural_earth_paths
from .spec import Extent

__all__ = ["Catalog", "DatasetView", "SourceInfo", "catalog_for"]

# 与数据项目 miko_gis_data 约定的清单格式; 格式/版本不符时明确拒绝, 不猜.
MANIFEST_FORMAT = "miko-gis-data/manifest"
SUPPORTED_VERSION = 1


@dataclass(frozen=True)
class SourceInfo:
    """数据集来源的静态事实(从 manifest 读回), 用于复算「数据来源」署名."""

    id: str
    title: str
    version: str
    homepage: str
    credit: str


@dataclass(frozen=True)
class DatasetView:
    """一份数据集的只读视图; 字段与数据项目的 ``Dataset`` 一一对应(少了下下载参数)."""

    id: str
    kind: str
    note: str = ""
    optional: bool = False
    dest: str = ""
    files: tuple[str, ...] = ()
    version: str = ""
    stride: int | None = None
    bbox: Extent | None = None
    resolution: str = ""
    category: str = ""
    name: str = ""
    source: SourceInfo | None = None

    @property
    def version_label(self) -> str:
        """实际版本标签: 数据集覆盖值优先, 否则用数据源的版本."""
        if self.version:
            return self.version
        return "" if self.source is None else self.source.version

    @property
    def credit(self) -> str:
        """进图署名: 优先用数据源写好的署名短句, 版本被覆盖时改写版本号."""
        if self.source is None:
            return ""
        if self.version and self.version != self.source.version:
            return f"{self.source.title} {self.version}"
        return self.source.credit


class Catalog:
    """一个区域的清单集合; 是渲染侧"这个区域有哪些数据"的唯一入口."""

    def __init__(self, group: str, title: str, root: Path, items: tuple[DatasetView, ...]) -> None:
        self.group = group
        self.title = title
        self.root = root
        self.items = items

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def get(self, dataset_id: str) -> DatasetView:
        """按 id 取数据集; 写错时列出可用 id."""
        for item in self.items:
            if item.id == dataset_id:
                return item
        raise KeyError(
            f"{self.group}: manifest 里没有数据集 {dataset_id!r}; "
            f"已声明: {[item.id for item in self.items]}"
        )

    # ------------------------------------------------------------------ 路径

    @property
    def raw_dir(self) -> Path:
        """原始数据目录(下载原样); 渲染侧按文件名挑 ETOPO 步长时用."""
        return self.root / "raw"

    @property
    def derived_dir(self) -> Path:
        """派生数据目录(脚本生成物)."""
        return self.root / "derived"

    def patterns(self, dataset: DatasetView | str) -> tuple[str, ...]:
        """判定"已就位"用的 glob(相对区域数据目录)."""
        item = self.get(dataset) if isinstance(dataset, str) else dataset
        return item.files or (item.dest,)

    def path(self, dataset: DatasetView | str) -> Path:
        """数据集在本地的主路径(下载目标 / 解压目录 / 共享缓存里的图层)."""
        item = self.get(dataset) if isinstance(dataset, str) else dataset
        if item.kind == "cartopy-ne":
            found, target = natural_earth_paths(item.resolution, item.category, item.name)
            return found if found is not None else target
        if not item.dest:
            raise ValueError(f"{self.group}: 数据集 {item.id} 没有 dest, 无法定位文件")
        return self.root / item.dest

    def exists(self, dataset: DatasetView | str) -> bool:
        """数据是否就位; 不联网, 只查本地.

        ``Path.glob`` 返回生成器, 生成器对象本身恒为真: 必须真正取出一个匹配项再判断.
        """
        item = self.get(dataset) if isinstance(dataset, str) else dataset
        if item.kind == "cartopy-ne":
            return self.path(item).is_file()
        return any(
            next(iter(self.root.glob(pattern)), None) is not None
            for pattern in self.patterns(item)
        )

    # ------------------------------------------------------------------ 署名

    def citation(self, dataset_ids) -> str:
        """把用到的数据集折成产物「数据来源」一行: 每个数据源一条, 用 ` · ` 分隔.

        算法与数据项目的 ``DatasetSet.citation`` 完全一致(按来源去重, 版本不一致时并排
        写版本), 保证迁移前后产物字节不变. 改了这里要同步数据项目与 manifest 字段.
        """
        groups: dict[str, list[DatasetView]] = {}
        order: list[str] = []
        for dataset_id in dataset_ids:
            item = self.get(dataset_id)
            if item.source is None:
                continue
            if item.source.id not in groups:
                groups[item.source.id] = []
                order.append(item.source.id)
            groups[item.source.id].append(item)

        parts: list[str] = []
        for source_id in order:
            first = groups[source_id][0].source
            assert first is not None  # 上一步已过滤
            versions: list[str] = []
            for item in groups[source_id]:
                version = item.version_label
                if version and version not in versions:
                    versions.append(version)
            if versions == [first.version] or not versions:
                text = first.credit
            else:
                text = f"{first.title} {'/'.join(versions)}"
            parts.append(f"{text} {first.homepage}")
        return " · ".join(parts)


@dataclass(frozen=True)
class _Manifest:
    """解析后的清单; 只在 ``_load`` 里构造一次."""

    groups: dict[str, tuple[str, tuple[DatasetView, ...]]]


_CACHE: dict[str, Catalog] = {}


def _parse_bbox(payload) -> Extent | None:
    """manifest 的 bbox 对象 -> ``cartopy_file.spec.Extent``."""
    if payload is None:
        return None
    return Extent(
        float(payload["lon_min"]),
        float(payload["lon_max"]),
        float(payload["lat_min"]),
        float(payload["lat_max"]),
    )


def _parse_source(payload) -> SourceInfo | None:
    """manifest 的 source 对象 -> ``SourceInfo``."""
    if payload is None:
        return None
    return SourceInfo(
        id=str(payload["id"]),
        title=str(payload["title"]),
        version=str(payload["version"]),
        homepage=str(payload["homepage"]),
        credit=str(payload["credit"]),
    )


def _parse_item(payload: dict) -> DatasetView:
    """一条 manifest 数据集 -> ``DatasetView``."""
    return DatasetView(
        id=str(payload["id"]),
        kind=str(payload["kind"]),
        note=str(payload.get("note", "")),
        optional=bool(payload.get("optional", False)),
        dest=str(payload.get("dest", "")),
        files=tuple(str(pattern) for pattern in payload.get("files", ())),
        version=str(payload.get("version", "")),
        stride=payload.get("stride"),
        bbox=_parse_bbox(payload.get("bbox")),
        resolution=str(payload.get("resolution", "")),
        category=str(payload.get("category", "")),
        name=str(payload.get("name", "")),
        source=_parse_source(payload.get("source")),
    )


def _load() -> _Manifest:
    """读并校验清单; 文件缺失/格式不符/版本不支持时给出可执行的提示."""
    path = manifest_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"数据清单不存在: {path}\n"
            "请先准备数据: 到数据项目 miko_gis_data 运行 `python main.py all`, "
            f"或把环境变量 {DATA_ROOT_ENV} 指向已就绪的数据根."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != MANIFEST_FORMAT:
        raise RuntimeError(
            f"数据清单格式不符: {path} 的 format={payload.get('format')!r}, "
            f"期望 {MANIFEST_FORMAT!r}; 请用当前版本的 miko_gis_data 重新 publish."
        )
    version = payload.get("version")
    if version != SUPPORTED_VERSION:
        raise RuntimeError(
            f"数据清单版本 {version!r} 不受支持(本仓只读 {SUPPORTED_VERSION}); "
            "请同步升级/降级两边的 miko_gis_data 与 Cartopy_file."
        )
    groups: dict[str, tuple[str, tuple[DatasetView, ...]]] = {}
    for group, group_payload in payload.get("groups", {}).items():
        groups[group] = (
            str(group_payload.get("title", group)),
            tuple(_parse_item(item) for item in group_payload.get("items", ())),
        )
    return _Manifest(groups)


def catalog_for(group: str) -> Catalog:
    """按 manifest 键(区域名)取清单; 结果缓存在进程内."""
    if group not in _CACHE:
        manifest = _load()
        if group not in manifest.groups:
            raise KeyError(
                f"manifest 里没有区域 {group!r}; 已发布: {sorted(manifest.groups)}"
            )
        title, items = manifest.groups[group]
        _CACHE[group] = Catalog(group, title, data_root() / group, items)
    return _CACHE[group]
