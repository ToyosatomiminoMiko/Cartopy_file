#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Local web editor for hand-tuning label layout on a finished map SVG.

是什么: 起一个只监听本机回环(127.0.0.1)的标准库 HTTP 服务器, 把 ``tools/label_editor.toml``
指向的 SVG 与它旁边的布局文件(``<name>.labels.json``)交给 ``tools/label_editor/`` 里的浏览器
画布编辑器; 拖动、方向键微调、新增标注都只改编辑器内存, 保存时原子写回布局文件, 用户重跑绘图
脚本才生成最终 SVG. 因此微调一轮不再需要重跑几分钟的出图.
没有命令行参数: 目标图、端口、是否自动打开浏览器全部读 TOML, 监听地址固定 127.0.0.1.
完整说明(配置项、端点、状态模型、键盘、验证方法)见 ``docs/label-editing.md``.
"""

from __future__ import annotations

import json
import sys
import tomllib
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    from cartopy_file import labels
    from cartopy_file.data import project_root
except ImportError as exc:  # 错误提示在没装包的解释器里也要能用
    labels = None  # type: ignore[assignment]
    project_root = None  # type: ignore[assignment]
    _IMPORT_ERROR: ImportError | None = exc
else:
    _IMPORT_ERROR = None

# 本文件所在目录: TOML 配置与前端静态文件都按它定位, 不依赖当前工作目录.
TOOL_DIR = Path(__file__).resolve().parent
CONFIG_FILE = TOOL_DIR / "label_editor.toml"
STATIC_DIR = TOOL_DIR / "label_editor"
INDEX_FILE = STATIC_DIR / "index.html"
# 监听地址固定回环: 编辑器没有鉴权, 只靠 127.0.0.1 隔离, 所以不提供改地址的配置项.
HOST = "127.0.0.1"
# 配置缺省值: 端口 0 = 由系统分配空闲端口, 免得多个编辑器实例抢端口.
DEFAULT_PORT = 0
DEFAULT_OPEN_BROWSER = True
# 白名单: 只放行编辑器自己的两个静态文件, 避免把服务器变成任意文件读取器.
STATIC_TYPES = {
    "editor.js": "text/javascript; charset=utf-8",
    "editor.css": "text/css; charset=utf-8",
}
# POST /api/save 的体积上限. 正常布局是几 KB; 2MB 足够容纳大量新增标注,
# 同时挡住误把整张 SVG 当请求体发上来的情况.
MAX_BODY_BYTES = 2 * 1024 * 1024

# 配置文件缺失时给用户的样例, 与仓库里的 label_editor.toml 保持一致.
_EXAMPLE_CONFIG = """\
svg = "Volga/volga_basin_topography_etopo2022_lambert_conformal.svg"
port = 0
open_browser = true
"""


class _ConfigError(Exception):
    """TOML 配置缺失或取值不合法; 消息文案直接面向用户, 由 main 打印后退出."""


@dataclass(frozen=True)
class EditorConfig:
    """一次编辑会话需要的三项配置: 目标 SVG、监听端口、是否自动打开浏览器."""

    svg: Path
    port: int
    open_browser: bool


def _repo_root() -> Path:
    """返回配置里相对路径的解析基准(仓库根目录).

    为什么不在模块顶层直接算: 正常情况用 ``cartopy_file.data.project_root()``, 它支持
    ``CARTOPY_FILE_ROOT`` 覆盖, 但要求包可导入; 工具脱离包直接跑时退回本文件上两级,
    这样配置里的 ``Volga/xxx.svg`` 永远按仓库根解释, 与从哪个目录启动无关.
    """
    if project_root is not None:
        try:
            return project_root()
        except RuntimeError:
            pass
    return TOOL_DIR.parent


def _load_config(path: Path = CONFIG_FILE) -> EditorConfig:
    """读并校验 TOML 配置; 任何问题都转成带配置文件路径的 _ConfigError."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise _ConfigError(
            f"找不到配置文件: {path}\n请创建它, 内容示例:\n{_EXAMPLE_CONFIG}"
        ) from None
    except OSError as exc:
        raise _ConfigError(f"读取配置文件失败: {path}: {exc}") from exc

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise _ConfigError(f"配置文件不是合法 TOML: {path}: {exc}") from exc

    # 拒绝未知键: 拼错键名(如 opne_browser)时不能悄悄按默认值跑.
    unknown = sorted(set(data) - {"svg", "port", "open_browser"})
    if unknown:
        raise _ConfigError(
            f"配置文件里有不认识的键 {', '.join(unknown)}: {path}"
            "(只支持 svg / port / open_browser)"
        )

    svg_value = data.get("svg")
    if not isinstance(svg_value, str) or not svg_value.strip():
        raise _ConfigError(f"配置项 svg 必须是非空字符串(路径以仓库根为准): {path}")
    svg = Path(svg_value.strip()).expanduser()
    if not svg.is_absolute():
        svg = _repo_root() / svg
    svg = svg.resolve()
    if not svg.is_file():
        raise _ConfigError(f"svg 指向的文件不存在: {svg}(配置: {path})")

    # bool 是 int 的子类, 必须先排除, 否则 port = true 会被当成 1.
    port_value = data.get("port", DEFAULT_PORT)
    if isinstance(port_value, bool) or not isinstance(port_value, int):
        raise _ConfigError(f"配置项 port 必须是整数(0 表示由系统分配): {path}")
    if not 0 <= port_value <= 65535:
        raise _ConfigError(f"配置项 port 超出 0..65535: {port_value}")

    open_value = data.get("open_browser", DEFAULT_OPEN_BROWSER)
    if not isinstance(open_value, bool):
        raise _ConfigError(f"配置项 open_browser 必须是 true 或 false: {path}")

    return EditorConfig(svg=svg, port=port_value, open_browser=open_value)


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


def main() -> int:
    # 故意不接受命令行参数: 参数写死在 TOML 里, 传参数只会让人以为生效了.
    if len(sys.argv) > 1:
        print(
            "错误: 这个工具不接受命令行参数, 目标图/端口写在 "
            f"{CONFIG_FILE} 里, 直接运行 .venv/bin/python tools/label_editor.py",
            file=sys.stderr,
        )
        return 2

    if _IMPORT_ERROR is not None:
        print(
            f"错误: 无法导入 cartopy_file(用项目虚拟环境运行: "
            f".venv/bin/python tools/label_editor.py): {_IMPORT_ERROR}",
            file=sys.stderr,
        )
        return 1

    try:
        config = _load_config()
    except _ConfigError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    try:
        server = LabelEditorServer(
            (HOST, config.port), LabelEditorHandler, config.svg
        )
    except OSError as exc:
        print(f"错误: 无法监听 {HOST}:{config.port}: {exc}", file=sys.stderr)
        return 1

    port = server.server_address[1]
    url = f"http://{HOST}:{port}/"
    placements_path = labels.placement_path(config.svg)
    print(
        f"标签编辑器已就绪: {url} (SVG: {config.svg}; 布局: {placements_path})",
        flush=True,
    )
    if config.open_browser:
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
