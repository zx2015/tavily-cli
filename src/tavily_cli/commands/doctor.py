"""`doctor` → 分层探活：TCP → MCP 握手 → tools/list → 最小搜索（§4.1、§9 用例 8）。

四层永远各出一行；上层失败时下层标记跳过，这样"卡在哪一层"在输出结构上是稳定的。
没有 /health 可用（实测除 /mcp 外全部 404），所以最后一层是一次真实的 minimal search。
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from .. import __version__, schema
from ..classify import Classified, ErrorKind, classify, redact
from ..render import Envelope, build_envelope

_PROBE_QUERY = "ping"


class _Failure(Exception):
    """某一层失败，已归好类；用于把分层循环的异常路径收敛到一处。"""

    def __init__(self, classified: Classified) -> None:
        super().__init__(classified.message)
        self.classified = classified


def _check(name: str, status: str, detail: str = "", elapsed_ms: int | None = None) -> dict:
    return {"name": name, "status": status, "detail": detail, "elapsed_ms": elapsed_ms}


def _host_port(endpoint: str) -> tuple[str, int]:
    parts = urlsplit(endpoint)
    return parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80)


def run(client, *, endpoint: str, tcp_probe, timeout: float) -> Envelope:
    checks: list[dict] = []
    failure: Classified | None = None

    def tcp_layer() -> str:
        host, port = _host_port(endpoint)
        try:
            tcp_probe(host, port, timeout)
        except OSError as exc:
            # 裸 OSError 会被分类器保守判成 TOOL_ERROR，而这一层失败明确是 TRANSPORT。
            raise _Failure(classify(kind=ErrorKind.TRANSPORT, message=f"TCP {host}:{port} 不可达：{redact(str(exc))}")) from exc
        return f"{host}:{port}"

    def handshake_layer() -> str:
        client.initialize()
        return f"session {client.session.masked_id()} · 服务端 v{client.server_version}"

    def tools_layer() -> str:
        tools = client.list_tools()
        return f"{len(tools)} 个工具 · {schema.schema_hash(tools)[:19]}"

    def search_layer() -> str:
        result = client.call("tavily-search", {"query": _PROBE_QUERY, "max_results": 1})
        if result.is_error:
            raise _Failure(classify(result.text))
        items = (result.structured or {}).get("results") or []
        return f"{len(items)} 条结果 · {result.elapsed_ms}ms"

    layers = (
        ("TCP 连接", "可达", tcp_layer),
        ("MCP 握手", "成功", handshake_layer),
        ("tools/list schema", "成功", tools_layer),
        ("最小搜索", "成功", search_layer),
    )

    for name, ok_status, layer in layers:
        if failure is not None:
            checks.append(_check(name, "跳过", "上一层已失败，未执行"))
            continue
        started = time.monotonic()
        try:
            detail = layer()
        except _Failure as exc:
            failure = exc.classified
        except Exception as exc:  # noqa: BLE001 - 交给分类器决定 Kind 与退出码
            failure = classify(exc=exc)
        elapsed = int((time.monotonic() - started) * 1000)
        checks.append(_check(name, "失败" if failure else ok_status, failure.message if failure else detail, elapsed))

    env = build_envelope(
        "doctor",
        None,
        meta={
            "endpoint": endpoint,
            "cli_version": __version__,
            "server_version": client.server_version,
            "schema_hash": schema.schema_hash(),
            "elapsed_ms": sum(c["elapsed_ms"] or 0 for c in checks),
        },
        ok=failure is None,
        error=None if failure is None else {"kind": failure.kind.name, "message": failure.message, "hint": failure.hint},
    )
    env.results = checks
    return env
