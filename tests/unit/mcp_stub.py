"""CLI 层测试共用的 MCP 服务端替身（离线，注入为 `main(..., opener=...)`）。

从 `test_cli.py` 抽出，让 `test_batch.py` 之类的姊妹文件不必复制一份"够用就好"的假服务端。
"""

from __future__ import annotations

import json
import re

from tavily_cli.cli import main
from tavily_cli import schema

ENDPOINT = "http://127.0.0.1:1/mcp"
# 默认与内置副本同指纹：批量的 schema 漂移预检因此**不该**告警，除非测试专门传一份漂移的表。
SERVER_TOOLS = schema.BUILTIN_TOOLS


def frame(obj: dict) -> bytes:
    return b"event: message\r\ndata: " + json.dumps(obj, ensure_ascii=False).encode() + b"\r\n\r\n"


class Resp:
    def __init__(self, body=b"", status=200, headers=None):
        self._chunks = [body] if body else []
        self.status = status
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}

    def getheader(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def read(self, size=-1):
        return self._chunks.pop(0) if self._chunks else b""


class FakeOpener:
    """够用就好的 MCP 服务端替身：按方法应答，并把 tools/call 结果交给测试。

    `call` 可以是固定的一份 result，也可以是 `arguments -> result` 的可调用对象
    （批量场景下每条查询要给不同的东西）。
    """

    def __init__(self, call=None, tools=None, errors=(), fail_methods=None, session_id="sess-test1234"):
        self.call = call
        self.tools = SERVER_TOOLS if tools is None else tools
        self.errors = list(errors)
        self.fail_methods = dict(fail_methods or {})
        self.session_id = session_id
        self.requests: list[dict] = []
        self.urls: list[str] = []
        self.timeouts: list[float | None] = []

    def __call__(self, request, timeout=None):
        body = json.loads(request.data.decode())
        self.requests.append(body)
        self.urls.append(request.full_url)
        self.timeouts.append(timeout)
        if self.errors:
            raise self.errors.pop(0)
        method, rid = body["method"], body.get("id")
        if method in self.fail_methods:
            raise self.fail_methods[method]
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "mcp-tavily", "version": "4.1.0"}}
            return Resp(frame({"jsonrpc": "2.0", "id": rid, "result": result}), headers={"mcp-session-id": self.session_id, "content-type": "text/event-stream"})
        if method == "notifications/initialized":
            return Resp(status=202)
        if method == "tools/list":
            return Resp(frame({"jsonrpc": "2.0", "id": rid, "result": {"tools": self.tools}}), headers={"content-type": "text/event-stream"})
        result = self.call(body["params"]["arguments"]) if callable(self.call) else self.call
        return Resp(frame({"jsonrpc": "2.0", "id": rid, "result": result}), headers={"content-type": "text/event-stream"})

    @property
    def methods(self) -> list[str]:
        return [r["method"] for r in self.requests]

    def count(self, method: str) -> int:
        return self.methods.count(method)

    def calls(self) -> list[tuple[str, dict]]:
        """真正进入网络队列的 (工具名, arguments)，用来断言"坏行不进队列"。"""

        return [(r["params"]["name"], r["params"]["arguments"]) for r in self.requests if r["method"] == "tools/call"]

    def arguments_at(self, index: int) -> dict:
        return self.requests[index]["params"]["arguments"]


def ok_call(structured: dict, is_error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
        "isError": is_error,
        "structuredContent": structured,
    }


def run(argv, **kwargs) -> int:
    try:
        return main(argv, **kwargs)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2


def plain(text: str) -> str:
    """TTY 默认会着色；断言文本内容时先剥掉 SGR 转义。"""

    return re.sub(r"\x1b\[[0-9;]*m", "", text)
