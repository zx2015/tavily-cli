"""契约：握手与 `tools/list`。

这些用例**不产生上游 Tavily 调用**（`initialize` / `tools/list` 只走 MCP 层），
因此不消耗共享配额，可在 `pytest -m network` 下直接跑。
它守的是两件事：session 语义没变、内置 schema 没与服务端漂移。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from tavily_cli import schema
from tavily_cli.session import PROTOCOL_VERSION, SESSION_HEADER
from tavily_cli.transport import ACCEPT, McHttp

EXPECTED_TOOLS = {"tavily-search", "tavily-extract", "tavily-crawl", "tavily-map"}


def test_initialize_yields_a_session_id_and_server_info(endpoint):
    transport = McHttp(endpoint, timeout=30.0, client_version="contract")
    session_id = transport.initialize()

    assert session_id, "服务端必须回 mcp-session-id，否则后续请求一律 400"
    assert transport.session.ready
    assert transport.session.server_name, "serverInfo.name 必须存在"
    assert transport.session.server_version, "serverInfo.version 必须存在"


def test_negotiated_protocol_version_is_accepted(client):
    assert client.session.protocol_version == PROTOCOL_VERSION


def test_tools_list_names_are_what_the_cli_ships(client):
    names = {tool["name"] for tool in client.list_tools()}
    assert names == EXPECTED_TOOLS, f"服务端工具集变化：{sorted(names)}"


def test_live_schema_hash_matches_builtin(client):
    """漂移即失败：失败意味着要刷新 schema._BUILTIN_TOOLS_JSON 与 fixtures（AGENTS.md §6.3）。"""

    live = client.list_tools()
    assert schema.schema_hash(live) == schema.schema_hash(), (
        "内置 schema 与服务端不一致；请刷新 schema.py 与 study/.../fixtures/tools_list.json"
    )


def test_no_tool_accepts_a_client_timeout(client):
    """4.1.3 起 `timeout` 由服务端 Depends 注入：客户端再发会被 additionalProperties:false 拒。
    这正是 CLI 把 --request-timeout 退化为"纯本地读超时"的原因。"""

    for tool in client.list_tools():
        assert "timeout" not in tool["inputSchema"]["properties"], tool["name"]


def test_required_arguments_match_cli_assumptions(client):
    required = {
        tool["name"]: tuple(tool["inputSchema"].get("required", [])) for tool in client.list_tools()
    }
    assert required == {
        "tavily-search": ("query",),
        "tavily-extract": ("urls",),
        "tavily-crawl": ("url",),
        "tavily-map": ("url",),
    }


def test_sending_an_undeclared_key_is_rejected(client):
    """`additionalProperties:false` 仍在：这是"永不发 null / 只发用户显式给的键"的前提（AGENTS §4）。"""

    result = client.call("tavily-search", {"query": "契约探测", "bogus": 1})
    assert result.is_error
    assert "unexpected_keyword_argument" in result.text or "validation error" in result.text


def test_missing_required_argument_is_rejected(client):
    result = client.call("tavily-search", {})
    assert result.is_error
    assert "query" in result.text


def test_request_without_session_header_is_refused(endpoint):
    """实测：不带 mcp-session-id ⇒ HTTP 400 `Missing session ID`；CLI 靠它判定"该重握手"。"""

    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", ACCEPT)
    assert SESSION_HEADER.lower() not in str(request.headers).lower()

    try:
        urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        assert "missing session id" in exc.read().decode("utf-8", "replace").lower()
    else:
        raise AssertionError("不带 session 头的请求本应被拒，却成功了")


def test_unknown_tool_is_reported_as_error_not_crash(client):
    result = client.call("tavily-does-not-exist", {"query": "契约探测"})
    assert result.is_error
    assert "unknown tool" in result.text.lower()


def test_protocol_error_carries_http_status(client):
    """协议层异常必须能被分类器映射成退出码 4，而不是被吞成通用工具失败。"""

    from tavily_cli.classify import ErrorKind, classify

    result = client.call("tavily-does-not-exist", {})
    resolved = classify(result.text)
    assert resolved.kind is ErrorKind.PROTOCOL
    assert resolved.exit_code == 4
