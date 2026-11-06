# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Dataset config: what a subproject needs on disk, where it comes from, how to verify it.

是什么: 数据集规格 ``Dataset`` 与集合 ``DatasetSet``. 每个子项目在自己的 ``config.py``
里声明一份 ``DatasetSet``, 数据准备脚本据此下载/校验, 绘图脚本据此定位文件, 根目录的
``download_data.py --check`` 据此汇总整个仓库的数据清单.
完整说明(为什么集中到子项目配置,raw/derived 目录约定,版本怎么钉)见
``docs/reference/datasets.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .sources import Source, source
from .spec import Extent

__all__ = ["Dataset", "DatasetSet", "CheckLine"]

# 数据目录约定: 下载原样放 raw/, 由数据准备脚本生成的放 derived/.
# 分开的理由: raw 是一次下载,永不改写的原始资产; derived 可以随时重算, 删除也不会
# 触发重新联网下载(见 docs/reference/datasets.md).
RAW_DIR = "raw"
DERIVED_DIR = "derived"


@dataclass(frozen=True)
class Dataset:
    """一份数据集: 外在事实(来源/版本/许可) + 本地位置 + 校验方式.

    kind:
        ``file``        单个文件, 由 fetch 下载(dest 是文件).
        ``zip``         下载压缩包并解压到 dest 目录.
        ``cartopy-ne``  Natural Earth 图层, 由 cartopy 的下载器管理在共享缓存里,
                        只登记分辨率/类别/名称, 不自己下载.
        ``derived``     由本子项目的数据准备脚本生成(如边界 GeoJSON), 只做存在性检查.
        ``script``      由数据准备脚本自行抓取(如 Overpass 查询结果), 只做存在性检查.
        ``local``       仓库自带,不下载(如 AmericaArmy/data.geojson).
    bbox: 数据本身覆盖的经纬度范围. 有它才能让「下载范围必须盖住画框」变成机器可查的
        断言(runner 出图时会核对), 而不是靠两个文件里的注释维持一致.
    version: 覆盖 ``Source.version`` 的版本口径. 只有本机这份数据确实停在旧版本时才写,
        用来把版本钉在「磁盘上实际是什么」(自然地球换版会原地覆盖同名文件).
    version_file: 相对 data 根的 ``*.VERSION.txt``, 内容第一行即为版本号.
    files: 判定「已就位」的 glob(相对 data 根); 缺省用 dest.
    """

    id: str
    kind: str = "file"
    source_id: str | None = None
    url: str = ""
    dest: str = ""
    bbox: Extent | None = None
    stride: int | None = None
    version: str | None = None
    version_file: str = ""
    files: tuple[str, ...] = ()
    resolution: str = ""
    category: str = ""
    name: str = ""
    # 可选缓存: 缺了不影响出图, --check 不把它算作失败(如原始 GADM/OSM 中间产物).
    optional: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Dataset.id 不能为空")
        allowed = {"file", "zip", "cartopy-ne", "derived", "script", "local"}
        if self.kind not in allowed:
            raise ValueError(f"Dataset.kind 必须是 {sorted(allowed)}, 得到 {self.kind!r}")
        if self.kind in ("file", "zip") and not (self.url and self.dest):
            raise ValueError(f"Dataset({self.id}) 的 kind={self.kind} 需要 url 和 dest")
        if self.kind == "cartopy-ne" and not (self.resolution and self.category and self.name):
            raise ValueError(f"Dataset({self.id}) 的 kind=cartopy-ne 需要 resolution/category/name")

    # ------------------------------------------------------------------ 来源

    @property
    def source(self) -> Source | None:
        """登记在 sources.py 里的数据源; 项目自带数据没有."""
        return None if self.source_id is None else source(self.source_id)

    @property
    def version_label(self) -> str:
        """实际版本标签: 数据集覆盖值优先, 否则用数据源的版本."""
        if self.version:
            return self.version
        parent = self.source
        return "" if parent is None else parent.version

    @property
    def credit(self) -> str:
        """进图署名: 优先用数据源写好的署名短句, 版本被覆盖时改写版本号."""
        parent = self.source
        if parent is None:
            return ""
        if self.version and self.version != parent.version:
            return f"{parent.title} {self.version}"
        return parent.credit

    @property
    def citation(self) -> str:
        """产物「数据来源」里的一条: 署名 + 发布页 URL."""
        parent = self.source
        if parent is None:
            return ""
        return f"{self.credit} {parent.homepage}"


@dataclass(frozen=True)
class CheckLine:
    """一条数据检查结果, 供 ``download_data.py --check`` 打印."""

    dataset_id: str
    group: str
    label: str
    state: str  # ok | missing | drifted
    detail: str

    @property
    def failed(self) -> bool:
        """missing 与 drifted 都算失败: 版本漂移会让产物与文档不一致.

        optional(可选缓存缺失)不算失败, 但会原样打印出来, 便于知道哪些中间产物可以重建.
        """
        return self.state in ("missing", "drifted")


@dataclass(frozen=True)
class DatasetSet:
    """一个子项目的数据集集合; 是「这个子项目要哪些数据」的唯一真源."""

    group: str
    root: Path
    items: tuple[Dataset, ...]

    def __post_init__(self) -> None:
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Dataset.id 重复: {ids}")
        if not self.group:
            raise ValueError("DatasetSet.group 不能为空(用于 --check 分组显示)")

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def get(self, dataset_id: str) -> Dataset:
        """按 id 取数据集; 写错时列出可用 id."""
        for item in self.items:
            if item.id == dataset_id:
                return item
        raise KeyError(
            f"{self.group}: 未声明数据集 {dataset_id!r}; 已声明: {[i.id for i in self.items]}"
        )

    # ------------------------------------------------------------------ 路径

    @property
    def raw_dir(self) -> Path:
        """下载原样的存放目录."""
        return self.root / RAW_DIR

    @property
    def derived_dir(self) -> Path:
        """派生数据(解压目录,生成文件)的存放目录."""
        return self.root / DERIVED_DIR

    def ne_paths(self, dataset: Dataset | str) -> tuple[Path | None, Path]:
        """Natural Earth 图层: (已存在的那份或 None, 项目缓存里的目标路径)."""
        item = self.get(dataset) if isinstance(dataset, str) else dataset
        # 先 configure, 否则 cartopy 会去 HOME 的旧缓存里找.
        from .data import configure_cartopy, natural_earth_paths

        configure_cartopy()
        return natural_earth_paths(item.resolution, item.category, item.name)

    def path(self, dataset: Dataset | str) -> Path:
        """数据集在本地的主路径(下载目标 / 解压目录 / 仓库自带文件)."""
        item = self.get(dataset) if isinstance(dataset, str) else dataset
        if item.kind == "cartopy-ne":
            found, target = self.ne_paths(item)
            return found if found is not None else target
        return self.root / item.dest

    def patterns(self, dataset: Dataset | str) -> tuple[str, ...]:
        """判定「已就位」用的 glob(相对 data 根)."""
        item = self.get(dataset) if isinstance(dataset, str) else dataset
        return item.files or (item.dest,)

    def exists(self, dataset: Dataset | str) -> bool:
        """数据是否已就位; 不联网, 只查本地.

        注意 ``Path.glob`` 返回生成器, 生成器对象本身恒为真: 必须真正取出一个匹配项
        再判断, 否则 ``--check`` 会对任何数据集都报「已存在」(历史 bug).
        """
        item = self.get(dataset) if isinstance(dataset, str) else dataset
        if item.kind == "cartopy-ne":
            return self.path(item).is_file()
        return any(
            next(iter(self.root.glob(pattern)), None) is not None
            for pattern in self.patterns(item)
        )

    # ------------------------------------------------------------------ 校验

    def version_of(self, dataset: Dataset | str) -> str:
        """读 ``version_file`` 第一行; 没有版本文件时返回空串."""
        item = self.get(dataset) if isinstance(dataset, str) else dataset
        if not item.version_file:
            return ""
        path = self.root / item.version_file
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
        except (OSError, IndexError):
            return ""

    def check(self) -> list[CheckLine]:
        """逐条检查本子项目的数据; 返回结果行(空列表 = 全部就位).

        为什么版本漂移也算失败: Natural Earth 的下载地址不带版本号, 重下会拿到新版;
        产物是「当前代码 + 当前数据」生成的, 数据换版后底图就会与文档不符, 必须显式
        确认(更新 Dataset.version 与文档)才能继续.
        """
        lines: list[CheckLine] = []
        for item in self.items:
            if item.kind == "cartopy-ne":
                found, target = self.ne_paths(item)
                if found is None:
                    lines.append(
                        CheckLine(item.id, self.group, item.note or item.name, "missing", str(target))
                    )
                    continue
                if found.resolve() != target.resolve():
                    # 只在 HOME 旧缓存里: 能出图, 但换机器就没了, 不算自包含.
                    lines.append(
                        CheckLine(
                            item.id,
                            self.group,
                            item.note or item.name,
                            "drifted",
                            f"只在旧缓存 {found}, 项目缓存缺 {target}",
                        )
                    )
                    continue
            present = self.exists(item)
            if not present:
                lines.append(
                    CheckLine(
                        dataset_id=item.id,
                        group=self.group,
                        label=item.note or item.dest or item.name,
                        state="missing",
                        detail=", ".join(self.patterns(item)),
                    )
                )
                continue
            found = self.version_of(item)
            expected = item.version_label
            if found and expected and found != expected:
                lines.append(
                    CheckLine(
                        dataset_id=item.id,
                        group=self.group,
                        label=item.note or item.dest or item.name,
                        state="drifted",
                        detail=f"本地版本 {found} != 期望 {expected}",
                    )
                )
                continue
            lines.append(
                CheckLine(
                    dataset_id=item.id,
                    group=self.group,
                    label=item.note or item.dest or item.name,
                    state="optional" if item.optional and not present else "ok",
                    detail=str(self.path(item)),
                )
            )
        return lines

    # ------------------------------------------------------------------ 署名

    def citation(self, dataset_ids) -> str:
        """把用到的数据集折成产物「数据来源」一行: 每个数据源一条, 用 ` · ` 分隔.

        为什么按数据源(而不是按数据集)去重: 一张图常常同时用到同一来源的多个图层
        (国界,海岸线,河流), 逐条列出会把来源行撑成一串重复的名字. 同一来源下版本
        不一致时(例如老图钉住 Natural Earth 5.0.0 的河网)把版本并排写出来, 而不是
        假装只有一个版本.
        """
        groups: dict[str, list[Dataset]] = {}
        order: list[str] = []
        for dataset_id in dataset_ids:
            item = self.get(dataset_id)
            if item.source is None:
                continue
            if item.source_id not in groups:
                groups[item.source_id] = []
                order.append(item.source_id)
            groups[item.source_id].append(item)

        parts: list[str] = []
        for source_id in order:
            parent = source(source_id)
            versions: list[str] = []
            for item in groups[source_id]:
                version = item.version_label
                if version and version not in versions:
                    versions.append(version)
            if versions == [parent.version] or not versions:
                # 版本与数据源登记的一致(或该源没有版本概念): 直接用登记好的署名短句,
                # 它会带上许可要求出现的文字(如 ODbL 的 © OpenStreetMap contributors).
                text = parent.credit
            else:
                text = f"{parent.title} {'/'.join(versions)}"
            parts.append(f"{text} {parent.homepage}")
        return " · ".join(parts)


def dataset_set(group: str, root: Path, items) -> DatasetSet:
    """写法糖: ``DATASETS = dataset_set("缅甸", Path(__file__).parent / "data", [...])``."""
    return DatasetSet(group=group, root=Path(root), items=tuple(items))
