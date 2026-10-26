#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Local web editor for hand-tuning label layout on a finished map SVG.

是什么: 起一个只监听本机 loopback 的标准库 HTTP 服务器, 把已生成的 SVG 与它旁边的布局
文件(``<name>.labels.json``)交给 ``tools/label_editor/`` 里的浏览器画布编辑器; 拖动、方向键
微调、新增标注都只改编辑器内存, 保存时原子写回布局文件, 用户重跑绘图脚本才生成最终 SVG.
因此微调一轮不再需要重跑几分钟的出图.
完整说明(启动方式、端点、状态模型、键盘、验证方法)见 ``docs/label-editing.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    from cartopy_file import labels
    from cartopy_file.data import project_root
except ImportError as exc:  # `--help` 与错误提示在没装包的解释器里也要能用
    labels = None  # type: ignore[assignment]
    project_root = None  # type: ignore[assignment]
    _IMPORT_ERROR: ImportError | None = exc
else:
    _IMPORT_ERROR = None

# 静态资源按本文件位置定位, 不依赖当前工作目录.
STATIC_DIR = Path(__file__).resolve().parent / "label_editor"
INDEX_FILE = STATIC_DIR / "index.html"
# 白名单: 只放行编辑器自己的两个静态文件, 避免把服务器变成任意文件读取器.
STATIC_TYPES = {
    "editor.js": "text/javascript; charset=utf-8",
    "editor.css": "text/css; charset=utf-8",
}
# POST /api/save 的体积上限. 正常布局是几 KB; 2MB 足够容纳大量新增标注,
# 同时挡住误把整张 SVG 当请求体发上来的情况.
MAX_BODY_BYTES = 2 * 1024 * 1024


def _normalized_document(placements, figure: str):
    """Placements -> 可序列化 JSON 对象; figure 统一成当前 SVG 文件名.

    为什么要统一 figure: 写进 SVG 的标记里不带 figure(标记属于那张图), 布局文件里却带;
    不归一化就会把"只有 figure 字段不同"误判成需要重跑脚本.
    """
    if placements is None:
        return None
    document = labels.to_document(placements)
    document["figure"] = figure
    return document


def _is_empty_document(document) -> bool:
    """没有任何位移与新增标注时视为空; 缺失(null)也算空."""
    return document is None or (
        not document.get("moved") and not document.get("added")
    )


def _render_hint(svg_path: Path) -> str | None:
    """在 SVG 所在目录找唯一引用该文件名的 *.py, 返回可复制的重跑命令.

    best effort: 0 个或多个候选都返回 None, 宁可不提示也不猜错脚本.
    """
    matches: list[Path] = []
    try:
        candidates = sorted(svg_path.parent.glob("*.py"))
    except OSError:
        candidates = []
    for script in candidates:
        try:
            text = script.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if svg_path.name in text:
            matches.append(script)
    if len(matches) != 1:
        return None
    script = matches[0]
    relative: str | Path = script
    if project_root is not None:
        try:
            relative = script.resolve().relative_to(project_root())
        except (ValueError, OSError):
            relative = script
    return f"python {relative}"


def _state_payload(svg_path: Path) -> dict:
    """GET /api/state 的响应: 把"已烤进 SVG 的布局"和"磁盘上的当前布局"并排交给前端."""
    figure = svg_path.name
    placements_path = labels.placement_path(svg_path)
    payload = {
        "figure": figure,
        "svg_path": str(svg_path),
        "placements_path": str(placements_path),
        "baked": None,
        "current": None,
        "needs_render": False,
        "render_hint": None,
        "error": None,
    }

    baked = None
    try:
        baked = labels.read_marker(svg_path)
    except OSError as exc:  # SVG 读不出来时仍然返回其余信息, 不让接口 500
        payload["error"] = f"读取 SVG 失败: {exc}"

    current = None
    if placements_path.is_file():
        try:
            current = labels.load(placements_path)
        except (ValueError, OSError) as exc:
            # 布局文件损坏是用户手改文件后的常见状态; 返回 200 + error,
            # 前端提示后仍可编辑, 保存即覆盖成合法文件.
            payload["error"] = f"布局文件损坏: {exc}"

    payload["baked"] = _normalized_document(baked, figure)
    payload["current"] = _normalized_document(current, figure)
    both_empty = _is_empty_document(payload["baked"]) and _is_empty_document(
        payload["current"]
    )
    payload["needs_render"] = (not both_empty) and (
        payload["baked"] != payload["current"]
    )
    payload["render_hint"] = _render_hint(svg_path)
    return payload


class LabelEditorServer(ThreadingHTTPServer):
    """带 SVG 目标的线程化服务器: 10MB 的 /map.svg 传输不会挡住 /api/save."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, handler_class, svg_path: Path):
        super().__init__(server_address, handler_class)
        self.svg_path = svg_path
        self.placements_path = labels.placement_path(svg_path)


class LabelEditorHandler(BaseHTTPRequestHandler):
    """编辑器的全部端点; 路径解析严格白名单, 不做目录服务."""

    server: LabelEditorServer
    server_version = "CartopyFileLabelEditor/1.0"

    # 日志克制: 启动与保存各一行, 其余请求不刷屏.
    def log_message(self, format, *args):  # noqa: A002 - 覆盖标准库签名
        return

    def do_GET(self) -> None:  # noqa: N802 - 标准库要求的方法名
        path = urlparse(self.path).path
        if path == "/":
            self._serve_index()
        elif path.startswith("/static/"):
            self._serve_static(path[len("/static/") :])
        elif path == "/api/state":
            self._serve_state()
        elif path == "/map.svg":
            self._serve_map()
        elif path == "/api/save":
            self._method_not_allowed()
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/save":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._save()

    def do_PUT(self) -> None:  # noqa: N802
        self._reject_other_method()

    def do_PATCH(self) -> None:  # noqa: N802
        self._reject_other_method()

    def do_DELETE(self) -> None:  # noqa: N802
        self._reject_other_method()

    def do_HEAD(self) -> None:  # noqa: N802
        self._reject_other_method()

    # -- 响应辅助 ---------------------------------------------------------

    def _send_bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # 浏览器关闭标签页时的正常竞态, 不当作服务器错误.
            pass

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(
            status,
            body,
            "application/json; charset=utf-8",
            extra_headers=extra_headers,
        )

    def _method_not_allowed(self) -> None:
        self._send_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": "只支持 POST"},
            extra_headers={"Allow": "POST"},
        )

    def _reject_other_method(self) -> None:
        if urlparse(self.path).path == "/api/save":
            self._method_not_allowed()
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    # -- 各端点 -----------------------------------------------------------

    def _serve_index(self) -> None:
        try:
            body = INDEX_FILE.read_bytes()
        except OSError as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"找不到前端文件: {INDEX_FILE}: {exc}"},
            )
            return
        self._send_bytes(HTTPStatus.OK, body, "text/html; charset=utf-8")

    def _serve_static(self, name: str) -> None:
        content_type = STATIC_TYPES.get(name)
        if content_type is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            body = (STATIC_DIR / name).read_bytes()
        except OSError as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"找不到静态文件: {name}: {exc}"},
            )
            return
        self._send_bytes(HTTPStatus.OK, body, content_type)

    def _serve_state(self) -> None:
        self._send_json(HTTPStatus.OK, _state_payload(self.server.svg_path))

    def _serve_map(self) -> None:
        try:
            body = self.server.svg_path.read_bytes()
        except OSError as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"读取 SVG 失败: {exc}"},
            )
            return
        self._send_bytes(HTTPStatus.OK, body, "image/svg+xml")

    def _save(self) -> None:
        length_header = self.headers.get("Content-Length")
        try:
            length = int(length_header) if length_header is not None else -1
        except ValueError:
            length = -1
        if length < 0:
            self._send_json(
                HTTPStatus.LENGTH_REQUIRED, {"error": "缺少 Content-Length"}
            )
            return
        if length > MAX_BODY_BYTES:
            # 不读超大请求体, 直接拒绝并关闭连接, 免得把 10MB 的 SVG 留在缓冲区里.
            self.close_connection = True
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": f"请求体超过 {MAX_BODY_BYTES} 字节上限"},
            )
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST, {"error": f"请求体不是合法 JSON: {exc}"}
            )
            return
        if not isinstance(payload, dict):
            self._send_json(
                HTTPStatus.BAD_REQUEST, {"error": "请求体顶层必须是 JSON 对象"}
            )
            return

        figure = self.server.svg_path.name
        document = {
            "format": labels.FORMAT,
            "version": labels.VERSION,
            "figure": figure,
            "moved": payload.get("moved", {}),
            "added": payload.get("added", []),
        }
        try:
            placements = labels.from_document(document)
        except (ValueError, TypeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        try:
            written = labels.dump(
                placements, self.server.placements_path, figure=figure
            )
        except OSError as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"写入布局文件失败: {exc}"},
            )
            return

        print(
            f"已保存布局: {written} (位移 {len(placements.moved)}, "
            f"新增 {len(placements.added)})",
            flush=True,
        )
        self._send_json(
            HTTPStatus.OK,
            {
                "path": str(written),
                "moved": len(placements.moved),
                "added": len(placements.added),
            },
        )


def _print_url(host: str, port: int) -> str:
    """把监听地址转成能点开的 URL; 通配地址显示成本机回环, 否则浏览器打不开."""
    display = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    if ":" in display:  # IPv6 字面量
        display = f"[{display}]"
    return f"http://{display}:{port}/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="在浏览器里拖动标签, 保存为 <svg>.labels.json, 不重跑绘图脚本",
    )
    parser.add_argument("svg", type=Path, help="已生成的地图 SVG")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="监听端口, 默认 0(由系统分配空闲端口)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址, 默认只监听本机回环 127.0.0.1",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="启动后不自动打开浏览器",
    )
    args = parser.parse_args(argv)

    if _IMPORT_ERROR is not None:
        print(
            f"错误: 无法导入 cartopy_file(用项目虚拟环境运行: "
            f".venv/bin/python tools/label_editor.py ...): {_IMPORT_ERROR}",
            file=sys.stderr,
        )
        return 1

    svg_path = args.svg.expanduser()
    if not svg_path.is_file():
        print(f"错误: SVG 文件不存在: {svg_path}", file=sys.stderr)
        return 2
    svg_path = svg_path.resolve()
    if not 0 <= args.port <= 65535:
        print(f"错误: --port 超出范围: {args.port}", file=sys.stderr)
        return 2

    try:
        server = LabelEditorServer(
            (args.host, args.port), LabelEditorHandler, svg_path
        )
    except OSError as exc:
        print(f"错误: 无法监听 {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1

    port = server.server_address[1]
    url = _print_url(args.host, port)
    placements_path = labels.placement_path(svg_path)
    print(f"标签编辑器已就绪: {url} (SVG: {svg_path}; 布局: {placements_path})", flush=True)
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001 - 打不开浏览器不该拖垮服务器
            print(f"提示: 无法自动打开浏览器({exc}), 请手动访问 {url}", flush=True)

    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("已停止", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
