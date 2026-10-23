"""MCP Streamable HTTP 传输层：仅标准库（ADR-0001）。

实测事实（study/mcp-tavily-endpoint/README.md）：
· 响应总是 text/event-stream，帧分隔符 \\r\\n，须按 `data:` 行取 JSON
· session 强制：initialize → 取响应头 mcp-session-id → notifications/initialized(202)
· 除 /mcp 外没有别的端点，探活只能靠 initialize + tools/list
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from .session import SESSION_HEADER, Session, is_missing_session

ACCEPT = "application/json, text/event-stream"
READ_SIZE = 65536


class TransportError(Exception):
    """TCP/DNS/连接被拒/HTTP 5xx：可重试（矩阵见 classify）。"""


class ProtocolError(Exception):
    """协议层异常：握手失败、无响应帧、JSON-RPC error 对象、意外 4xx。"""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class SessionExpired(ProtocolError):
    """HTTP 400 Missing session ID，允许重握手一次。"""


class ClientTimeout(Exception):
    """客户端总超时。"""


@dataclass
class CallResult:
    is_error: bool
    text: str
    structured: dict | None
    elapsed_ms: int
    raw: dict


@dataclass
class _Reply:
    body: dict | None
    status: int
    header: Callable[[str], str | None]


class SSEFramer:
    """把任意切分的字节流还原成 JSON 对象；容忍 \\r\\n / \\n / \\r、心跳与未完成尾帧。"""

    def __init__(self) -> None:
        self._buf = b""
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> list[dict]:
        objects: list[dict] = []
        self._buf += chunk
        while True:
            found = self._take_line()
            if found is None:
                return objects
            objects.extend(self._handle(*found))
        return objects  # pragma: no cover - 由 _take_line 的 None 退出

    def close(self) -> list[dict]:
        out: list[dict] = []
        line = self._buf.rstrip(b"\r")
        self._buf = b""
        if line:
            out.extend(self._handle(line.decode("utf-8", "replace"), 0))
        out.extend(self._dispatch())
        return out

    def _take_line(self) -> tuple[str, int] | None:
        for index, byte in enumerate(self._buf):
            if byte == 0x0A:
                return self._pop(index, 1)
            if byte == 0x0D:
                if index + 1 == len(self._buf):
                    return None  # 可能是 \r\n 的前半，等下一块
                return self._pop(index, 2 if self._buf[index + 1] == 0x0A else 1)
        return None

    def _pop(self, index: int, terminator: int) -> tuple[str, int]:
        line = self._buf[:index]
        self._buf = self._buf[index + terminator :]
        return line.decode("utf-8", "replace"), terminator

    def _handle(self, line: str, _terminator: int) -> list[dict]:
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return []
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            self._data.append(value)
        return []

    def _dispatch(self) -> list[dict]:
        if not self._data:
            return []
        text = "\n".join(self._data)
        self._data = []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        return [parsed] if isinstance(parsed, dict) else []


def build_tool_request(tool: str, arguments: dict, request_id: int) -> dict:
    """tools/call 请求体的唯一构造点：--dry-run 打印它与真实发送它共用同一段代码。"""

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }


class McHttp:
    def __init__(
        self,
        endpoint: str,
        timeout: float = 45.0,
        opener: Callable = urllib.request.urlopen,
        client_name: str = "tavily-cli",
        client_version: str = "0",
        verbose: bool = False,
    ) -> None:
        self._raw_opener = opener
        self._client_name = client_name
        self._client_version = client_version
        self.verbose = verbose
        self.session = Session(endpoint=endpoint)
        self.session_id: str | None = None
        self.server_version: str | None = None
        self.timeout = timeout
        self._next_id = 0
        self._session_lock = threading.Lock()

    # ------------------------------------------------------------- 基础设施

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[tavily-cli] {message}", file=sys.stderr)

    def _request_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _send(self, payload: dict, *, want_id: int | None) -> _Reply:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.session.endpoint, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", ACCEPT)
        if self.session.session_id:
            request.add_header(SESSION_HEADER, self.session.session_id)
        method = payload.get("method", "?")
        started = time.monotonic()
        deadline = started + self.timeout

        try:
            response = self._raw_opener(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = _drain(exc)
            self._log(f"{method} → HTTP {exc.code} ({_ms(started)}ms)")
            if is_missing_session(exc.code, detail):
                raise SessionExpired(f"HTTP 400 Missing session ID: {detail[:200]}") from exc
            if 500 <= exc.code < 600:
                raise TransportError(f"HTTP {exc.code}: {detail[:200]}") from exc
            raise ProtocolError(f"HTTP {exc.code}: {detail[:200]}", code=exc.code) from exc
        except socket.timeout as exc:
            raise ClientTimeout(f"{method} 连接超时 {self.timeout}s") from exc
        except urllib.error.URLError as exc:
            raise TransportError(f"无法连接 {self.session.endpoint}：{exc.reason}") from exc
        except (OSError, ValueError) as exc:
            raise TransportError(f"传输层异常：{exc}") from exc

        status = getattr(response, "status", None) or getattr(response, "code", 200)
        header = _header_reader(response)
        self._log(f"{method} → HTTP {status} ({_ms(started)}ms) session={self.session.masked_id()}")
        if want_id is None:
            return _Reply(None, status, header)
        return _Reply(self._read_response(response, want_id, deadline), status, header)

    def _read_response(self, response, want_id: int, deadline: float) -> dict:
        content_type = (_header_reader(response)("Content-Type") or "").lower()
        framer = SSEFramer()

        if "text/event-stream" not in content_type:
            raw = _read_all(response, deadline)
            try:
                parsed = json.loads(raw.decode("utf-8", "replace") or "null")
            except json.JSONDecodeError as exc:
                raise ProtocolError(f"响应不是合法 JSON：{raw[:200]!r}") from exc
            if isinstance(parsed, dict) and parsed.get("id") == want_id:
                return self._unwrap(parsed, want_id)
            raise ProtocolError(f"响应 id 不匹配：期望 {want_id}，实际 {parsed!r:.200}")

        while True:
            if time.monotonic() > deadline:
                raise ClientTimeout(f"读取响应超时（{self.timeout}s）")
            try:
                chunk = response.read(READ_SIZE)
            except socket.timeout as exc:
                raise ClientTimeout(f"读取响应超时（{self.timeout}s）") from exc
            except (OSError, ValueError) as exc:
                raise TransportError(f"读取响应失败：{exc}") from exc
            if not chunk:
                break
            for obj in framer.feed(chunk):
                if obj.get("id") == want_id:
                    return self._unwrap(obj, want_id)

        for obj in framer.close():
            if obj.get("id") == want_id:
                return self._unwrap(obj, want_id)
        raise ProtocolError(f"未找到 id={want_id} 的响应帧")

    @staticmethod
    def _unwrap(obj: dict, want_id: int) -> dict:
        error = obj.get("error")
        if isinstance(error, dict):
            raise ProtocolError(
                f"JSON-RPC error {error.get('code')}: {error.get('message', '')}",
                code=error.get("code"),
            )
        if obj.get("id") != want_id:
            raise ProtocolError(f"响应 id 不匹配：期望 {want_id}")
        return obj

    # ---------------------------------------------------------------- 协议面

    def initialize(self) -> str:
        self._handshake()
        assert self.session.session_id is not None
        return self.session.session_id

    def _handshake(self) -> None:
        with self._session_lock:
            self._handshake_locked()

    def _handshake_locked(self) -> None:
        self.session.invalidate()
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": self.session.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": self._client_name, "version": self._client_version},
            },
        }
        reply = self._send(payload, want_id=payload["id"])
        body = reply.body or {}
        result = body.get("result") or {}
        session_id = reply.header(SESSION_HEADER) or reply.header("Mcp-Session-Id")
        if not session_id:
            raise ProtocolError("initialize 成功但响应头没有 mcp-session-id")
        self.session.adopt(session_id, result.get("serverInfo"), result.get("protocolVersion"))
        self.session_id = self.session.session_id
        self.server_version = self.session.server_version

        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, want_id=None)

    def _ensure_session(self) -> None:
        with self._session_lock:
            if not self.session.ready:
                self._handshake_locked()

    def call(self, tool: str, arguments: dict) -> CallResult:
        self._ensure_session()
        started = time.monotonic()
        try:
            body = self._tool_request(tool, arguments)
        except SessionExpired:
            self._log("session 失效，重握手 1 次后重发")
            self._handshake()
            body = self._tool_request(tool, arguments)
        result = body.get("result") or {}
        text = "\n".join(
            block.get("text", "")
            for block in result.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        structured = result.get("structuredContent")
        if structured is None and text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            structured = parsed if isinstance(parsed, dict) else None
        return CallResult(
            is_error=bool(result.get("isError")),
            text=text,
            structured=structured,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            raw=body,
        )

    def _tool_request(self, tool: str, arguments: dict) -> dict:
        payload = build_tool_request(tool, arguments, self._request_id())
        reply = self._send(payload, want_id=payload["id"])
        return reply.body or {}

    def list_tools(self) -> list[dict]:
        self._ensure_session()
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id(),
            "method": "tools/list",
            "params": {},
        }
        reply = self._send(payload, want_id=payload["id"])
        body = reply.body or {}
        return (body.get("result") or {}).get("tools", [])


def _header_reader(response) -> Callable[[str], str | None]:
    def read(name: str) -> str | None:
        getter = getattr(response, "getheader", None)
        if callable(getter):
            return getter(name)
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        for key, value in headers.items():
            if key.lower() == name.lower():
                return value
        return None

    return read


def _read_all(response, deadline: float) -> bytes:
    out = bytearray()
    while True:
        if time.monotonic() > deadline:
            raise ClientTimeout("读取响应超时")
        try:
            chunk = response.read(READ_SIZE)
        except socket.timeout as exc:
            raise ClientTimeout("读取响应超时") from exc
        if not chunk:
            return bytes(out)
        out += chunk


def _drain(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return str(exc)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
