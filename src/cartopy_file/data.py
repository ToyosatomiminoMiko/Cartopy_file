# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Locate the data root, the manifest and cartopy's Natural Earth cache.

是什么: 渲染仓唯一的"数据在哪"入口. 数据由独立项目 miko_gis_data 准备, 本仓只读:
``CARTOPY_FILE_DATA`` 指向数据根(默认仓内 ``data/``, 其次仓内 ``miko_gis_data/data/``),
数据根里的 ``manifest.json`` 由 ``catalog.py`` 解析, ``cartopy/`` 是共享底图缓存.
本模块不下载任何东西; 数据根里没有清单时渲染会明确报错并指向数据项目.
完整说明(目录约定,环境变量,为什么缓存要落在可写磁盘)见 ``docs/reference/data.md``.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "DATA_ROOT_ENV",
    "ROOT_ENV",
    "configure_cartopy",
    "data_root",
    "local_data_dir",
    "manifest_path",
    "natural_earth_paths",
    "prepare_matplotlib_env",
    "project_root",
    "subproject_dirs",
]

# 与数据项目 miko_gis_data 共用的数据根环境变量: 两边读同一个值, 谁都不猜绝对路径.
DATA_ROOT_ENV = "CARTOPY_FILE_DATA"
# 手动指定渲染仓根目录(仅当无法由包安装路径推断时使用).
ROOT_ENV = "CARTOPY_FILE_ROOT"
# 数据项目暂放在本仓内时的默认位置(用户把 miko_gis_data 移走后不再适用).
_NESTED_DATA_PROJECT = "miko_gis_data"


def project_root() -> Path:
    """返回渲染仓根目录.

    优先级: 环境变量 ``CARTOPY_FILE_ROOT`` > 由本文件位置推断 > 当前工作目录.
    可编辑安装时本文件位于 ``<repo>/src/cartopy_file/data.py``, 上三级就是仓库根.
    """
    override = os.environ.get(ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()

    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").is_file():
        return candidate

    cwd = Path.cwd()
    if (cwd / "pyproject.toml").is_file():
        return cwd

    raise RuntimeError(
        "无法定位项目根目录: 请用 `uv pip install -e .` 安装本项目, "
        f"或设置环境变量 {ROOT_ENV} / {DATA_ROOT_ENV}."
    )


def local_data_dir() -> Path:
    """返回渲染仓自己的可写缓存目录(不进数据项目): matplotlib 缓存等."""
    base = project_root() / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _has_manifest(path: Path) -> bool:
    """数据根是否已经发布过清单(用来区分"数据项目在哪")."""
    return (path / "manifest.json").is_file()


def data_root() -> Path:
    """返回数据根目录(会自动建目录).

    优先级:
    1. ``CARTOPY_FILE_DATA`` -- 数据项目被移出本仓后的唯一方式;
    2. ``<仓根>/data`` -- 数据根就放在渲染仓里;
    3. ``<仓根>/miko_gis_data/data`` -- 数据项目暂放在本仓内(未移走)时的默认位置.
    """
    override = os.environ.get(DATA_ROOT_ENV)
    if override:
        base = Path(override).expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base

    repo = project_root()
    candidates = (repo / "data", repo / _NESTED_DATA_PROJECT / "data")
    for candidate in candidates:
        if _has_manifest(candidate):
            return candidate
    # 都还没发布清单时退回仓内 data/, 让后续报错信息指向一个具体位置.
    base = candidates[0]
    base.mkdir(parents=True, exist_ok=True)
    return base


def manifest_path() -> Path:
    """数据清单的固定位置: 数据根根目录."""
    return data_root() / "manifest.json"


def prepare_matplotlib_env() -> Path:
    """在导入 matplotlib 之前调用: 把 MPLCONFIGDIR 指到可写目录.

    用 ``setdefault`` 而不是直接赋值: 已经在脚本顶部自己指定了 MPLCONFIGDIR 的
    (例如各子项目 ``main.py`` 指向 ``<子项目>/data/.mplcache``)保持原样.
    返回实际生效的缓存目录.
    """
    cache = local_data_dir() / ".mplcache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    return Path(os.environ["MPLCONFIGDIR"])


def _existing_dirs(*candidates: object) -> list[Path]:
    """把候选值里真实存在且不是 "." 的目录挑出来(去重, 保持优先级)."""
    found: list[Path] = []
    for value in candidates:
        if not isinstance(value, (str, Path)):
            continue
        text = str(value)
        if text in ("", "."):
            # cartopy 没设置 CARTOPY_DATA_DIR 时 pre_existing_data_dir 就是
            # Path(''), 它表示相对当前目录, 不能当缓存来源.
            continue
        path = Path(text).expanduser()
        if not path.is_dir():
            continue
        resolved = path.resolve()
        if resolved not in found:
            found.append(resolved)
    return found


def configure_cartopy() -> Path:
    """把 cartopy 的下载缓存定位到数据根, 并复用已有缓存; 返回缓存目录.

    必须在第一个 cartopy 要素(cfeature.*)被读取之前调用, 一般在 import
    cartopy 之后立刻调用. 重复调用是安全的(idempotent).

    为什么还要设置 pre_existing_data_dir: cartopy 的 Downloader 先查
    ``pre_existing_data_dir`` 再查 ``data_dir``, 两者都没有才联网. 改
    ``data_dir`` 后如果不登记旧缓存, 原先下在 HOME 里的文件会"看不见",
    从而被重新下载一遍 -- 这正是要避免的. 渲染仓自己从不下载, 读不到就是数据没备好.
    """
    import cartopy

    target = data_root() / "cartopy"
    target.mkdir(parents=True, exist_ok=True)

    # 记下改动前的两个位置: 旧 data_dir(通常是 ~/.local/share/cartopy)与
    # 用户显式设置的 CARTOPY_DATA_DIR(它在 config 里是 pre_existing_data_dir).
    legacy = _existing_dirs(
        cartopy.config.get("pre_existing_data_dir"),
        cartopy.config.get("data_dir"),
    )

    cartopy.config["data_dir"] = target
    for path in legacy:
        if path != target.resolve():
            cartopy.config["pre_existing_data_dir"] = path
            break
    return target


def subproject_dirs() -> tuple[str, ...]:
    """返回渲染仓里的子项目目录名(按名字排序), 判定标准是目录里有 ``config.py``.

    为什么用"有 config.py"而不是硬编码列表: 名单只该在目录结构里出现一次, 新增
    子项目只要建目录 + config.py, 产物枚举就自动收录, 不用再改工具.
    """
    root = project_root()
    return tuple(sorted(path.parent.name for path in root.glob("*/config.py")))


def natural_earth_paths(
    resolution: str,
    category: str,
    name: str,
) -> tuple[Path | None, Path]:
    """返回 (已存在的缓存路径或 None, 下载会写入的目标路径), 不联网.

    查路径的方式与 cartopy 内部一致: 用当前 config 里的缓存模板拼出
    ``pre_existing_data_dir`` 与 ``data_dir`` 两个位置. 判断"是否已存在"只看
    ``.shp``: NEShpDownloader 是把 shp/shx/dbf 一起解压的, shp 在即整套在.

    返回顺序上故意让 ``data_dir``(数据根里的项目缓存)优先: 这样报告与"是否自包含"的
    判断都以数据根为准.
    """
    import cartopy
    from cartopy.io import shapereader

    downloader = shapereader.NEShpDownloader.default_downloader()
    format_dict = {
        "config": cartopy.config,
        "resolution": resolution,
        "category": category,
        "name": name,
    }
    pre_downloaded = downloader.pre_downloaded_path(format_dict)
    target = downloader.target_path(format_dict)
    if target.exists():
        return target, target
    if pre_downloaded is not None and pre_downloaded.exists():
        return pre_downloaded, target
    return None, target
