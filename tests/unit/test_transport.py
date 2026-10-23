"""transport/session：SSE 分帧与 MCP Streamable HTTP 语义（全部离线，注入假 opener）。

依据 study/mcp-tavily-endpoint/README.md 的实测事实：响应总是 text/event-stream、
帧分隔符 \\r\\n、session 强制、无 /health。
"""

from __future__ import annotations

import io
import json
import socket
import threading
import time
import urllib.error

import pytest

from tavily_cli import transport
from tavily_cli.transport import CallResult, McHttp, SSEFramer

ENDPOINT = "http://127.0.0.1:1/mcp"  # 永不真连：opener 被注入


ID_TOKEN = b'"__ID__"'


def frame(payload: dict) -> bytes:
    return b"event: message\r\ndata: " + json.dumps(payload).encode() + b"\r\n\r\n"


def rpc(payload: dict) -> bytes:
    return frame({"jsonrpc": "2.0", "id": "__ID__", "result": payload})


def rpc_error(code: int, message: str) -> bytes:
    return frame({"jsonrpc": "2.0", "id": "__ID__", "error": {"code": code, "message": message}})


class FakeResponse:
    def __init__(self, chunks=(), status=200, headers=None):
        self._chunks = list(chunks)
        self.status = status
        defaults = {"content-type": "text/event-stream"} if self._chunks else {}
        self.headers = {**defaults, **{k.lower(): v for k, v in (headers or {}).items()}}

    def bind(self, request_id) -> None:
        self._chunks = [c.replace(ID_TOKEN, json.dumps(request_id).encode()) for c in self._chunks]

    def getheader(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def read(self, size=-1):
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    def close(self):
        pass


def http_error(code: int, body: bytes | str = b"", headers=None) -> urllib.error.HTTPError:
    text = body.encode() if isinstance(body, str) else body
    return urllib.error.HTTPError(
        ENDPOINT,
        code,
        f"HTTP {code}",
        {k.lower(): v for k, v in (headers or {}).items()},
        io.BytesIO(text),
    )


class Recorder:
    """替身 opener：按队列返回响应，同时记录发出的每个请求。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[dict] = []

    def __call__(self, request, timeout=None):
        self.requests.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "body": json.loads(request.data.decode()) if request.data else None,
                "headers": {k.lower(): v for k, v in request.header_items()},
                "timeout": timeout,
            }
        )
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, FakeResponse):
            body = self.requests[-1]["body"]
            if body and "id" in body:
                item.bind(body["id"])
        return item

    @property
    def bodies(self) -> list[dict]:
        return [r["body"] for r in self.requests]

    def method_at(self, index: int) -> str:
        return self.requests[index]["body"]["method"]


def init_ok() -> FakeResponse:
    return FakeResponse(
        [
            rpc(
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mcp-tavily", "version": "4.1.0"},
                }
            )
        ],
        headers={"mcp-session-id": "sess-abcdef123456"},
    )


def notify_accepted() -> FakeResponse:
    return FakeResponse([], status=202)


def make_client(responses, **kwargs) -> tuple[McHttp, Recorder]:
    recorder = Recorder(responses)
    client = McHttp(ENDPOINT, timeout=5.0, opener=recorder, client_version="9.9.9", **kwargs)
    return client, recorder


# ---------------------------------------------------------------- SSE 分帧


def test_framer_reads_complete_crlf_frame():
    objs = SSEFramer().feed(frame({"jsonrpc": "2.0", "id": 1, "result": {}}))
    assert objs == [{"jsonrpc": "2.0", "id": 1, "result": {}}]


def test_framer_ignores_heartbeat_and_event_lines():
    data = b": keep-alive\r\nevent: message\r\nid: 42\r\ndata: {\"a\": 1}\r\n\r\n"
    assert SSEFramer().feed(data) == [{"a": 1}]


def test_framer_accepts_data_prefix_without_space():
    assert SSEFramer().feed(b'data:{"a":1}\n\n') == [{"a": 1}]


def test_framer_buffers_lines_split_across_chunks():
    framer = SSEFramer()
    payload = frame({"jsonrpc": "2.0", "id": 7, "result": {"ok": True}})
    collected = []
    for i in range(len(payload)):
        collected.extend(framer.feed(payload[i : i + 1]))
    assert collected == [{"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}]


def test_framer_handles_crlf_split_between_chunks():
    framer = SSEFramer()
    assert framer.feed(b'data: {"a":1}\r') == []
    assert framer.feed(b"\n\r\n") == [{"a": 1}]


def test_framer_yields_every_frame_in_one_chunk():
    chunk = frame({"id": 1}) + frame({"id": 2})
    assert [o["id"] for o in SSEFramer().feed(chunk)] == [1, 2]


def test_framer_flushes_unterminated_frame_on_close():
    framer = SSEFramer()
    assert framer.feed(b'data: {"a":1}\r\n') == []
    assert framer.close() == [{"a": 1}]


def test_framer_survives_large_frame_in_small_chunks():
    big = {"result": {"blob": "x" * 200_000}}
    payload = frame(big)
    framer = SSEFramer()
    out = []
    for i in range(0, len(payload), 4096):
        out.extend(framer.feed(payload[i : i + 4096]))
    assert len(out) == 1
    assert out[0]["result"]["blob"] == "x" * 200_000


def test_framer_skips_undecodable_frame():
    assert SSEFramer().feed(b"data: not-json\r\n\r\n") == []


# ---------------------------------------------------------------- 握手


def test_initialize_params_and_headers():
    client, rec = make_client([init_ok(), notify_accepted()])
    assert client.initialize() == "sess-abcdef123456"
    first = rec.requests[0]
    assert first["body"]["method"] == "initialize"
    assert first["body"]["params"]["protocolVersion"] == "2025-06-18"
    assert first["body"]["params"]["clientInfo"] == {"name": "tavily-cli", "version": "9.9.9"}
    assert "text/event-stream" in first["headers"]["accept"]
    assert "application/json" in first["headers"]["accept"]
    assert first["headers"]["content-type"] == "application/json"
    assert "mcp-session-id" not in first["headers"]


def test_initialized_notification_uses_session_and_expects_202():
    client, rec = make_client([init_ok(), notify_accepted()])
    client.initialize()
    notify = rec.requests[1]
    assert notify["body"]["method"] == "notifications/initialized"
    assert "id" not in notify["body"]
    assert notify["headers"]["mcp-session-id"] == "sess-abcdef123456"
    assert client.server_version == "4.1.0"


def test_timeout_passed_to_opener():
    client, rec = make_client([init_ok(), notify_accepted()])
    client.initialize()
    assert rec.requests[0]["timeout"] == 5.0


# ---------------------------------------------------------------- tools/call


def search_frames(is_error=False):
    return FakeResponse(
        [
            rpc(
                {
                    "content": [{"type": "text", "text": json.dumps({"query": "x", "results": []})}],
                    "isError": is_error,
                    "structuredContent": {"query": "x", "results": [{"url": "https://a"}]},
                }
            )
        ]
    )


def test_call_returns_structured_content():
    client, rec = make_client([init_ok(), notify_accepted(), search_frames()])
    result = client.call("tavily-search", {"query": "x"})
    assert isinstance(result, CallResult)
    assert result.is_error is False
    assert result.structured == {"query": "x", "results": [{"url": "https://a"}]}
    assert result.text == json.dumps({"query": "x", "results": []})
    assert result.elapsed_ms >= 0
    call = rec.requests[2]["body"]
    assert call["method"] == "tools/call"
    assert call["params"] == {"name": "tavily-search", "arguments": {"query": "x"}}


def test_call_arguments_are_forwarded_verbatim():
    client, rec = make_client([init_ok(), notify_accepted(), search_frames()])
    client.call("tavily-search", {"query": "x", "max_results": 3})
    assert rec.requests[2]["body"]["params"]["arguments"] == {"query": "x", "max_results": 3}


def test_call_lazy_initializes_once():
    client, rec = make_client([init_ok(), notify_accepted(), search_frames(), search_frames()])
    client.call("tavily-search", {"query": "a"})
    client.call("tavily-search", {"query": "b"})
    assert [rec.method_at(i) for i in range(4)] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
        "tools/call",
    ]


def test_call_ignores_interleaved_notification_frames():
    noise = frame({"jsonrpc": "2.0", "method": "notifications/progress", "params": {}})
    answer = rpc({"content": [{"type": "text", "text": "{}"}], "isError": False,
                "structuredContent": {"query": "x"}})
    client, _ = make_client(
        [init_ok(), notify_accepted(), FakeResponse([noise + answer])]
    )
    assert client.call("tavily-search", {"query": "x"}).structured == {"query": "x"}


def test_is_error_does_not_raise():
    """isError=true 只是"工具没成功"，重试决策交给 classify（ADR-0002）。"""

    client, _ = make_client([init_ok(), notify_accepted(), search_frames(is_error=True)])
    result = client.call("tavily-search", {"query": "x"})
    assert result.is_error is True


def test_structured_falls_back_to_content_text_json():
    payload = {
        "content": [{"type": "text", "text": json.dumps({"query": "x", "results": []})}],
        "isError": False,
    }
    client, _ = make_client(
        [init_ok(), notify_accepted(), FakeResponse([rpc(payload)])]
    )
    assert client.call("tavily-search", {"query": "x"}).structured == {"query": "x", "results": []}


def test_list_tools_returns_tools():
    tools = [{"name": "tavily-search", "inputSchema": {"type": "object"}}]
    client, rec = make_client([init_ok(), notify_accepted(), FakeResponse([rpc({"tools": tools})])])
    assert client.list_tools() == tools
    assert rec.requests[2]["body"]["method"] == "tools/list"


# ---------------------------------------------------------------- 错误路径


def test_jsonrpc_error_object_is_protocol_error():
    client, _ = make_client(
        [
            init_ok(),
            notify_accepted(),
            FakeResponse([rpc_error(-32601, "Method not found")]),
        ]
    )
    with pytest.raises(transport.ProtocolError) as exc:
        client.call("tavily-search", {"query": "x"})
    assert "Method not found" in str(exc.value)
    assert exc.value.code == -32601


def test_response_with_foreign_id_is_rejected():
    client, _ = make_client(
        [init_ok(), notify_accepted(), FakeResponse([frame({"jsonrpc": "2.0", "id": 999, "result": {}})])]
    )
    with pytest.raises(transport.ProtocolError) as exc:
        client.call("tavily-search", {"query": "x"})
    assert "未找到 id=2" in str(exc.value)  # tools/call 的 id 是 2，无关帧不得当结果


def expired_session() -> urllib.error.HTTPError:
    body = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Bad Request: Missing session ID"}}
    return http_error(400, json.dumps(body))


def test_missing_session_id_triggers_exactly_one_rehandshake():
    client, rec = make_client(
        [init_ok(), notify_accepted(), expired_session(), init_ok(), notify_accepted(), search_frames()]
    )
    assert client.call("tavily-search", {"query": "x"}).is_error is False
    assert [rec.method_at(i) for i in range(6)] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]


def test_missing_session_twice_raises_protocol():
    client, rec = make_client(
        [init_ok(), notify_accepted(), expired_session(), init_ok(), notify_accepted(), expired_session()]
    )
    with pytest.raises(transport.SessionExpired):
        client.call("tavily-search", {"query": "x"})
    assert len(rec.requests) == 6


def test_initialize_without_session_header_is_protocol_error():
    client, _ = make_client([FakeResponse([rpc({"serverInfo": {}})]), notify_accepted()])
    with pytest.raises(transport.ProtocolError):
        client.initialize()


def test_url_error_is_transport_error():
    client, _ = make_client([urllib.error.URLError("connection refused")])
    with pytest.raises(transport.TransportError):
        client.initialize()


def test_http_5xx_is_transport_error():
    client, _ = make_client([http_error(503, b"unavailable")])
    with pytest.raises(transport.TransportError):
        client.initialize()


def test_http_4xx_other_is_protocol_error():
    client, _ = make_client([http_error(404, b'{"error":"not found"}')])
    with pytest.raises(transport.ProtocolError):
        client.initialize()


def test_read_timeout_is_client_timeout():
    class TimeoutResponse(FakeResponse):
        def read(self, size=-1):
            raise socket.timeout("timed out")

    client, _ = make_client([TimeoutResponse([b"event: message\r\n"])])
    with pytest.raises(transport.ClientTimeout):
        client.initialize()


def test_json_body_response_also_supported():
    """Accept 同时允许 application/json；服务端若返回裸 JSON 也要能解。"""

    body = json.dumps({"jsonrpc": "2.0", "id": "__ID__", "result": {"serverInfo": {"version": "4.1.0"}}}).encode()
    client, _ = make_client(
        [FakeResponse([body], headers={"content-type": "application/json", "mcp-session-id": "s1"}), notify_accepted()]
    )
    assert client.initialize() == "s1"


def test_verbose_logs_method_and_masked_session(capsys):
    client, _ = make_client([init_ok(), notify_accepted(), search_frames()], verbose=True)
    client.call("tavily-search", {"query": "x"})
    err = capsys.readouterr().err
    assert "initialize" in err and "tools/call" in err
    assert "sess-abcdef123456" not in err
    assert "sess-abc…" in err


# --------------------------------------------------- 并发（NFR-11：batch 多路共用一个 client）


class ScriptedOpener:
    """按方法应答的替身：每种请求返回其应有的响应，并可卡在 `initialize` 里等测试放行。

    卡住的用途是把两次握手**强制重叠**——不靠线程时序碰运气。
    """

    def __init__(self, *, stuck_on_initialize: threading.Event | None = None, release: threading.Event | None = None):
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        self._stuck = stuck_on_initialize
        self._release = release

    def __call__(self, request, timeout=None):
        body = json.loads(request.data.decode()) if request.data else None
        method = (body or {}).get("method", "")
        with self._lock:
            self.requests.append({"method": method, "body": body})
        if method == "initialize":
            response = init_ok()
            if self._stuck is not None:
                self._stuck.set()
                if not self._release.wait(5):
                    raise AssertionError("测试没有放行 initialize")
        elif method == "notifications/initialized":
            return notify_accepted()
        else:
            response = search_frames()
        if body and "id" in body:
            response.bind(body["id"])
        return response

    def count(self, method: str) -> int:
        with self._lock:
            return sum(1 for item in self.requests if item["method"] == method)

    def call_ids(self) -> list[int]:
        with self._lock:
            return [item["body"]["id"] for item in self.requests if item["method"] == "tools/call"]


def test_concurrent_first_calls_handshake_only_once():
    """`batch` 的多路线程会同时首次进入 `call()`；握手必须合流成**一次** initialize。

    各握各的后果：后一次 adopt 覆盖了 session id，仍在途的前一份请求带着已作废的 id。
    """

    started = threading.Event()
    release = threading.Event()
    opener = ScriptedOpener(stuck_on_initialize=started, release=release)
    client = McHttp(ENDPOINT, timeout=5.0, opener=opener)

    results: dict[str, CallResult] = {}
    errors: list[BaseException] = []

    def run(name: str) -> None:
        try:
            results[name] = client.call("tavily-search", {"query": name})
        except BaseException as exc:  # noqa: BLE001 - 线程里的异常要在主线程如实看到
            errors.append(exc)

    threads: list[threading.Thread] = []
    try:
        first = threading.Thread(target=run, args=("a",))
        first.start()
        threads.append(first)
        assert started.wait(5), "第一次握手没有开始"
        for name in ("b", "c", "d"):
            thread = threading.Thread(target=run, args=(name,))
            thread.start()
            threads.append(thread)
        time.sleep(0.2)  # 让后三条都走到"是否已有 session"的判定点
    finally:
        release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert not [thread for thread in threads if thread.is_alive()], "有线程卡在锁上没出来"
    assert not errors
    assert sorted(results) == ["a", "b", "c", "d"]
    assert opener.count("initialize") == 1, f"并发触发了 {opener.count('initialize')} 次握手"
    assert len(set(opener.call_ids())) == len(opener.call_ids()) == 4, "tools/call 的 JSON-RPC id 重号"
