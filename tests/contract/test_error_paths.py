"""契约：真实服务端的错误形态必须落进 `classify()` 预期的那一类。

除 `test_destructive_400_*` 外，这些用例都停在 FastMCP 层、**不产生上游 Tavily 调用**
（实测依据：study/mcp-tavily-endpoint/README.md §5.5 —— 缺参/未声明键/工具名拼错均"不污染 Key 池"），
因此不消耗配额，可在 `pytest -m network` 下直接跑。
"""

from __future__ import annotations

import os

import pytest

from tavily_cli.classify import EMPTY_MESSAGE, ErrorKind, classify, retry_budget

BAD_DOMAINS = ["!!bad"]


def _resolved(result):
    assert result.is_error, f"服务端本应报错，却成功了：{result.raw}"
    assert result.text != EMPTY_MESSAGE, "错误文本为空 ⇒ classify 只能保守降级，红线判据丢失"
    return classify(result.text)


def test_unknown_tool_maps_to_protocol(client):
    resolved = _resolved(client.call("tavily-no-such-tool", {"query": "契约探测"}))

    assert resolved.kind is ErrorKind.PROTOCOL
    assert resolved.exit_code == 4
    assert retry_budget(resolved.kind, retries=3, retries_given=True) == 1, (
        "协议异常虽标为 retryable，但 ADR-0002 的重试矩阵只给传输/限流额外机会"
    )


def test_missing_required_argument_maps_to_client_gap(client):
    """缺必填 → FastMCP 校验失败 → 这是**客户端校验有遗漏**的信号，必须带补规则的建议。"""

    resolved = _resolved(client.call("tavily-search", {}))

    assert resolved.kind is ErrorKind.TOOL_ERROR
    assert resolved.exit_code == 5
    assert "客户端校验有遗漏" in resolved.hint, resolved.hint


def test_undeclared_key_maps_to_client_gap(client):
    """`additionalProperties:false`：这类错误同样证明"永不发未声明键/null"是必需的。"""

    resolved = _resolved(client.call("tavily-search", {"query": "契约探测", "bogus_key": 1}))

    assert resolved.kind is ErrorKind.TOOL_ERROR
    assert "unexpected_keyword_argument" in resolved.message or "validation error" in resolved.message
    assert "客户端校验有遗漏" in resolved.hint


def test_wrong_type_argument_is_rejected_before_upstream(client):
    resolved = _resolved(client.call("tavily-search", {"query": 123}))

    assert resolved.kind is ErrorKind.TOOL_ERROR
    assert "string_type" in resolved.message or "validation error" in resolved.message


def test_tool_error_never_enters_the_retry_matrix(client):
    resolved = _resolved(client.call("tavily-search", {}))

    assert resolved.kind is ErrorKind.TOOL_ERROR
    assert retry_budget(resolved.kind, retries=3, retries_given=True) == 1
    assert retry_budget(ErrorKind.POOL_DEAD, retries=3, retries_given=True) == 1


def test_session_recovery_is_transparent(client):
    """session 失效后必须能自动重握手，而不是把 400 抛给调用方（AGENTS §4"session 是强制的"）。"""

    from tavily_cli.transport import SessionExpired  # 仅确认导出存在，路径稳定

    assert SessionExpired is not None
    client.session.invalidate()
    assert not client.session.ready

    resolved = _resolved(client.call("tavily-no-such-tool", {"query": "契约探测"}))
    assert client.session.ready, "重握手后应重新持有 session"
    assert resolved.kind is ErrorKind.PROTOCOL


def test_pool_is_still_healthy_after_protocol_failures(client, quota):
    """上面这些坏请求都没走到 Tavily；这里用一次最小成功搜索证明 Key 池未被污染。"""

    quota.append("tavily-search")
    result = client.call("tavily-search", {"query": "契约探测", "max_results": 1, "search_depth": "basic"})

    assert not result.is_error, f"协议层坏请求污染了共享池：{result.text}"
    assert result.structured and result.structured["request_id"]


@pytest.mark.skipif(
    os.environ.get("TAVILY_ALLOW_DESTRUCTIVE") != "1",
    reason="会故意发出一个坏参数；服务端已修复该误判，但仍需显式授权（AGENTS §3 红线 1）",
)
def test_destructive_400_does_not_terminalise_the_key_pool(client, quota):
    """事故用例的永久回归防线：`!!bad` 只该让本次调用失败，不该让全池进 `ERROR` 终态。

    跑法（会消耗 2 次配额，且仅在确认服务端 400 防护在线时执行）：
        TAVILY_ALLOW_DESTRUCTIVE=1 TAVILY_CONTRACT_QUOTA=1 pytest tests/ -m network
    """

    quota.append("tavily-search(bad)")
    bad = client.call("tavily-search", {"query": "契约探测", "include_domains": BAD_DOMAINS})
    assert bad.is_error, "非法域名本应失败；若服务端校验变宽松，需回来更新红线文档"
    assert classify(bad.text).kind is not ErrorKind.POOL_DEAD, bad.text

    quota.append("tavily-search(after bad)")
    after = client.call("tavily-search", {"query": "契约探测", "max_results": 1, "search_depth": "basic"})
    assert not after.is_error, (
        "坏参数之后正常搜索仍失败 ⇒ 服务端 400→401 误判复发（见 docs/adr/0003-validate-before-send.md §6），"
        "需要 ssh mcp-host 'docker restart mcp-tavily' 并向使用者报告"
    )
