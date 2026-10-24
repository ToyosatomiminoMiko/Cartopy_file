# -*- coding: utf-8 -*-
# ============================================================
# data.py
# 项目共享数据目录与 cartopy 底图缓存的统一定位.
# 属于可安装的项目包 cartopy_file, 是所有绘图脚本唯一的缓存配置来源.
# (copyright) Kawaii Femboy Technology Co., Ltd.
# ============================================================
"""Locate the project-wide data directory and cartopy's download cache.

是什么:
    - ``shared_data_dir()``: 仓库级共享数据目录, 缺省为 ``<repo>/data``,
      可用环境变量 ``CARTOPY_FILE_DATA`` 覆盖;
    - ``prepare_matplotlib_env()``: 在导入 matplotlib 之前把 ``MPLCONFIGDIR``
      指到共享目录下可写的 ``.mplcache``;
    - ``configure_cartopy()``: 把 cartopy 的下载缓存重定向到共享目录下的
      ``cartopy/``, 并把已有缓存登记为 ``pre_existing_data_dir``(只读复用);
    - ``natural_earth_paths()``: 查某个 Natural Earth 要素已经落在哪个缓存
      里、下载会落到哪里, 不联网.

为什么:
    1. cartopy 默认把下载的 Natural Earth 数据放在 ``~/.local/share/cartopy``,
       matplotlib 默认把配置放在 ``~/.config/matplotlib``. 本机 ``/home`` 是
       只读挂载(btrfs ro), 这两个目录都不可写: 只要某个要素没有缓存(换机器、
       清缓存、升级 cartopy), 渲染时就会尝试下载并失败, 或者每次运行都重复
       下载同一份底图.
    2. 各脚本原先各管一段: ``northern_shan.py`` 自己把缓存改到
       ``Myanmar/data/cartopy``, 其余脚本仍用用户 HOME, 同一份底图可能在两处
       各下载一次.
    3. 缓存统一到仓库内 ``data/cartopy`` 后: 可写、随仓库走、只下载一次. 旧的
       HOME 缓存通过 ``pre_existing_data_dir`` 继续复用, 已经下载过的文件不会
       再下一遍; 新下载的则落在仓库里, 下次换脚本也能直接用.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "shared_data_dir",
    "project_root",
    "prepare_matplotlib_env",
    "configure_cartopy",
    "natural_earth_paths",
]

# 环境变量: 覆盖仓库级共享数据目录, 用于把缓存放到别的可写磁盘.
_DATA_ENV = "CARTOPY_FILE_DATA"
# 环境变量: 手动指定项目根目录(仅当无法由包安装路径推断时使用).
_ROOT_ENV = "CARTOPY_FILE_ROOT"


def project_root() -> Path:
    """返回仓库根目录.

    优先级: 环境变量 CARTOPY_FILE_ROOT > 由本文件位置推断 > 当前工作目录.
    导出安装(editable)时本文件位于 ``<repo>/src/cartopy_file/data.py``,
    上三级就是仓库根, 因此不需要猜路径.
    """
    override = os.environ.get(_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()

    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").is_file():
        return candidate

    # 非可编辑安装(或源码布局变了)时不能用包路径推断, 退回到"从仓库根运行".
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").is_file():
        return cwd

    raise RuntimeError(
        "无法定位项目根目录: 请用 `uv pip install -e .` 安装本项目, "
        f"或设置环境变量 {_ROOT_ENV} / {_DATA_ENV}."
    )


def shared_data_dir() -> Path:
    """返回全项目共享的数据目录(会自动建目录)."""
    override = os.environ.get(_DATA_ENV)
    base = Path(override).expanduser() if override else project_root() / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def prepare_matplotlib_env() -> Path:
    """在导入 matplotlib 之前调用: 把 MPLCONFIGDIR 指到可写目录.

    用 ``setdefault`` 而不是直接赋值: 已经在脚本顶部自己指定了 MPLCONFIGDIR
    的(例如 Myanmar 系列脚本指向 ``Myanmar/data/.mplcache``)保持原样.
    返回实际生效的缓存目录.
    """
    cache = shared_data_dir() / ".mplcache"
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
    """把 cartopy 的下载缓存定位到共享目录, 并复用已有缓存; 返回缓存目录.

    必须在第一个 cartopy 要素(cfeature.*)被读取之前调用, 一般在 import
    cartopy 之后立刻调用. 重复调用是安全的(idempotent).

    为什么还要设置 pre_existing_data_dir: cartopy 的 Downloader 先查
    ``pre_existing_data_dir`` 再查 ``data_dir``, 两者都没有才联网下载. 改
    ``data_dir`` 后如果不登记旧缓存, 原先下在 HOME 里的文件会"看不见",
    从而被重新下载一遍 —— 这正是要避免的.
    """
    import cartopy

    target = shared_data_dir() / "cartopy"
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


def natural_earth_paths(
    resolution: str,
    category: str,
    name: str,
) -> tuple[Path | None, Path]:
    """返回 (已存在的缓存路径或 None, 下载会写入的目标路径), 不联网.

    查路径的方式与 cartopy 内部一致: 用当前 config 里的缓存模板拼出
    ``pre_existing_data_dir`` 与 ``data_dir`` 两个位置. 判断"是否已存在"只看
    ``.shp``: NEShpDownloader 是把 shp/shx/dbf 一起解压的, shp 在即整套在.

    返回顺序上故意让 ``data_dir``(项目缓存)优先: 这样报告与"是否已自包含"的
    判断都以仓库为准; cartopy 自己读取时是 ``pre_existing_data_dir`` 优先,
    但两处内容相同, 不影响结果.
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
