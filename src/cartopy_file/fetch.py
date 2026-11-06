# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Download / resume / verify / extract helpers for the data-preparation scripts.

是什么: 数据准备脚本共用的下载层: 断点续传,多镜像重试,内容魔数校验,解压,sha256.
这里不 import matplotlib/cartopy, 也不认识任何具体数据集--「下什么,放哪」由各子项目
``config.py`` 的 ``DatasetSet`` 决定.
完整说明(续传与校验的坑,为什么先写 .part)见 ``docs/reference/datasets.md``.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .sources import USER_AGENT

__all__ = [
    "MAGIC_JSON",
    "MAGIC_NETCDF",
    "MAGIC_ZIP",
    "download",
    "extract_zip",
    "post",
    "sha256_of",
]

# 内容魔数: 服务器返回错误页时 HTTP 状态码仍可能是 200, 不看文件头就会把 HTML
# 当成数据缓存下来, 到出图时才报难懂的错.
MAGIC_NETCDF = (b"CDF", b"\x89HDF")
MAGIC_ZIP = (b"PK",)
MAGIC_JSON = (b"{", b"[")

# 分块大小; 1 MiB 在慢速下能及时打印进度, 又不会让循环次数过多.
_CHUNK = 1024 * 1024


def sha256_of(path: Path) -> str:
    """算文件 sha256(十六进制), 用于钉住「内容确实没换」."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _warn(message: str) -> None:
    """打印到 stderr: 下载层的提示不该混进脚本的正常输出."""
    import sys

    print(message, file=sys.stderr)


def _check_magic(path: Path, magic: tuple[bytes, ...], url: str) -> None:
    """校验文件头; 不符时删掉半成品并报错(否则下次会当作已下载)."""
    with open(path, "rb") as handle:
        head = handle.read(8)
    if magic and not any(head.startswith(prefix) for prefix in magic):
        path.unlink(missing_ok=True)
        preview = head.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"下载内容不是预期的二进制格式(可能是错误页): {url} 头部={preview!r}")


def download(
    url: str,
    dest: Path,
    *,
    description: str,
    force: bool = False,
    magic: tuple[bytes, ...] = (),
    expected_sha256: str | None = None,
    retries: int = 3,
    timeout: float = 600.0,
) -> Path:
    """把 url 下载到 dest; 已存在且非空时跳过, 中断过则续传.

    为什么先写 ``.part`` 再改名: 中途失败时目标文件不存在, 下次运行不会把半截文件
    当成已完成; 服务器忽略 Range(返回 200)时必须清空 ``.part`` 重写, 否则拼接出坏文件.
    """
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"已存在, 跳过 {description}: {dest}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    if force and part.exists():
        part.unlink()
    elif part.exists():
        print(f"发现未完成的下载, 续传: {part}")

    attempt = 0
    while attempt < retries:
        attempt += 1
        downloaded = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"

        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                # 服务器忽略 Range 时返回 200 和完整数据, 必须从零写.
                if downloaded and response.status == 200:
                    downloaded = 0
                    part.unlink(missing_ok=True)

                mode = "ab" if downloaded else "wb"
                total = response.headers.get("Content-Length")
                total = int(total) if total else None
                written = downloaded
                last_report = time.time()
                with open(part, mode) as out:
                    while True:
                        chunk = response.read(_CHUNK)
                        if not chunk:
                            break
                        out.write(chunk)
                        written += len(chunk)
                        now = time.time()
                        if now - last_report >= 3:
                            last_report = now
                            if total:
                                pct = written / (downloaded + total) * 100
                                print(
                                    f"  {description}: {written / 1048576:6.1f} MiB / "
                                    f"{total / 1048576:6.1f} MiB ({pct:5.1f}%)"
                                )
                            else:
                                print(f"  {description}: {written / 1048576:6.1f} MiB")
            _check_magic(part, magic, url)
            actual = sha256_of(part)
            if expected_sha256 is not None and actual != expected_sha256:
                part.unlink(missing_ok=True)
                raise RuntimeError(
                    f"sha256 不符: {url}\n  期望 {expected_sha256}\n  实际 {actual}\n"
                    "如果数据源确实换了版本, 请同步更新 Dataset 的版本口径与文档."
                )
            part.replace(dest)
            print(f"完成: {dest} ({dest.stat().st_size / 1048576:.1f} MiB)")
            return dest
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            _warn(f"  下载失败 ({attempt}/{retries}): {exc}")
            if attempt >= retries:
                raise
            time.sleep(5 * attempt)
    raise RuntimeError(f"下载失败: {url}")  # 逻辑上到不了这里, 仅供类型检查


def post(
    url: str,
    body: bytes,
    dest: Path,
    *,
    description: str,
    headers: dict[str, str] | None = None,
    force: bool = False,
    retries: int = 3,
    timeout: float = 180.0,
) -> Path:
    """POST 一段请求体并缓存响应(Overpass 这类「实时查询接口」用).

    与 ``download`` 的区别: 结果不是可直接比对的文件, 只能当快照缓存; 已经缓存过就
    不再请求(公共实例有限流, 重复请求既慢又容易被拒).
    """
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"已存在, 跳过 {description}: {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    request_headers = {"User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    attempt = 0
    while attempt < retries:
        attempt += 1
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
            if not payload:
                raise RuntimeError(f"响应为空: {url}")
            dest.write_bytes(payload)
            print(f"完成: {dest} ({dest.stat().st_size / 1024:.1f} KiB)")
            return dest
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            _warn(f"  请求失败 ({attempt}/{retries}): {exc}")
            if attempt >= retries:
                raise
            time.sleep(5 * attempt)
    raise RuntimeError(f"请求失败: {url}")


def extract_zip(archive: Path, dest_dir: Path, *, force: bool = False) -> Path:
    """把压缩包解压到 dest_dir, 返回解压目录.

    已经解压过就跳过(用 ``.unpacked`` 标记), 避免每次运行都重写几十 MB 的 shapefile;
    ``force`` 时重新解压, 用于压缩包被重新下载过的场景.
    """
    archive = Path(archive)
    dest_dir = Path(dest_dir)
    marker = dest_dir / ".unpacked"
    if marker.is_file() and not force:
        print(f"已解压, 跳过: {dest_dir}")
        return dest_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(dest_dir)
    marker.write_text(archive.name + "\n", encoding="utf-8")
    print(f"已解压: {dest_dir}")
    return dest_dir
