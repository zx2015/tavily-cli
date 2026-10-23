"""classify：错误信号 → ErrorKind → 退出码/重试策略（ADR-0002 是判定唯一真相）。

判定信号文本全部来自 study/mcp-tavily-endpoint/README.md 的实测原文。
"""

from __future__ import annotations

import urllib.error

import pytest

from tavily_cli import classify as C
from tavily_cli import constants as K
from tavily_cli.transport import ClientTimeout, ProtocolError, SessionExpired, TransportError

POOL_DEAD_TEXT = "Error calling tool 'tavily-map': No active API keys available in the pool."
ALL_KEYS_FAILED = "All available keys failed for tavily-search"
FASTMCP_VALIDATION = "1 validation error for call[tavily_search] query Missing required argument"
UNKNOWN_TOOL = "Unknown tool: 'nope'"
SERVER_TIMEOUT = "Request timed out after 0.001 seconds"


# ------------------------------------------------------------------ 退出码表


@pytest.mark.parametrize(
    ("kind", "exit_code", "label"),
    [
        (C.ErrorKind.OK, 0, "成功"),
        (C.ErrorKind.USAGE, 2, "参数校验失败"),
        (C.ErrorKind.TRANSPORT, 3, "网络不可达"),
        (C.ErrorKind.PROTOCOL, 4, "协议异常"),
        (C.ErrorKind.TOOL_ERROR, 5, "工具执行失败"),
        (C.ErrorKind.POOL_DEAD, 6, "密钥池已死亡"),
        (C.ErrorKind.TIMEOUT, 7, "超时"),
        (C.ErrorKind.RATE_LIMITED, 8, "被限流"),
        (C.ErrorKind.INTERRUPTED, 130, "已中断"),
    ],
)
def test_kind_exit_code_and_chinese_label(kind, exit_code, label):
    assert kind.exit_code == exit_code
    assert kind.label == label


def test_exit_code_constants_agree_with_kinds():
    assert (
        K.EXIT_OK,
        K.EXIT_USAGE,
        K.EXIT_TRANSPORT,
        K.EXIT_PROTOCOL,
        K.EXIT_TOOL_ERROR,
        K.EXIT_POOL_DEAD,
        K.EXIT_TIMEOUT,
        K.EXIT_RATE_LIMITED,
        K.EXIT_INTERRUPTED,
    ) == (0, 2, 3, 4, 5, 6, 7, 8, 130)


def test_retry_flags_are_decoupled_from_is_error():
    """可重试仅限传输层/协议/限流；池死亡与工具失败绝不自愈重试。"""

    assert C.ErrorKind.TRANSPORT.retryable is True
    assert C.ErrorKind.RATE_LIMITED.retryable is True
    assert C.ErrorKind.PROTOCOL.retryable is True
    for kind in (C.ErrorKind.POOL_DEAD, C.ErrorKind.TOOL_ERROR, C.ErrorKind.USAGE, C.ErrorKind.TIMEOUT):
        assert kind.retryable is False


# ------------------------------------------------------------------ 文本模式


def test_pool_dead_marker_wins_over_everything():
    got = C.classify(text=POOL_DEAD_TEXT)
    assert got.kind is C.ErrorKind.POOL_DEAD
    assert got.kind.exit_code == 6
    assert "docker restart mcp-tavily" in got.hint
    assert "客户端无法自愈" in got.hint


def test_all_keys_failed_is_also_pool_dead():
    assert C.classify(text=ALL_KEYS_FAILED).kind is C.ErrorKind.POOL_DEAD


def test_pool_dead_detected_from_exception_text_too():
    got = C.classify(exc=TransportError(POOL_DEAD_TEXT))
    assert got.kind is C.ErrorKind.POOL_DEAD


def test_server_side_validation_error_hints_at_client_gap():
    got = C.classify(text=FASTMCP_VALIDATION)
    assert got.kind is C.ErrorKind.TOOL_ERROR
    assert "客户端校验" in got.hint


def test_unknown_tool_is_protocol():
    assert C.classify(text=UNKNOWN_TOOL).kind is C.ErrorKind.PROTOCOL


def test_server_timeout_text_is_timeout():
    got = C.classify(text=SERVER_TIMEOUT)
    assert got.kind is C.ErrorKind.TIMEOUT
    assert "--timeout" in got.hint


@pytest.mark.parametrize("text", ["Rate limit exceeded, retry in 12 seconds", "HTTP 429 Too Many Requests"])
def test_rate_limit_semantics(text):
    got = C.classify(text=text)
    assert got.kind is C.ErrorKind.RATE_LIMITED
    assert "5" in got.hint


def test_unmatched_text_is_conservative_tool_error():
    got = C.classify(text="Something unexpected happened upstream")
    assert got.kind is C.ErrorKind.TOOL_ERROR
    assert got.kind.retryable is False


def test_empty_text_still_yields_a_classified_kind():
    got = C.classify(text="")
    assert got.kind is C.ErrorKind.TOOL_ERROR
    assert got.message == "服务端未返回错误文本"


# ------------------------------------------------------------------ 异常类型


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (ClientTimeout("读取响应超时（45s）"), C.ErrorKind.TIMEOUT),
        (TransportError("无法连接：[Errno 111] Connection refused"), C.ErrorKind.TRANSPORT),
        (urllib.error.URLError("connection refused"), C.ErrorKind.TRANSPORT),
        (ConnectionRefusedError("refused"), C.ErrorKind.TRANSPORT),
        (SessionExpired("HTTP 400 Missing session ID"), C.ErrorKind.PROTOCOL),
        (ProtocolError("响应不是合法 JSON"), C.ErrorKind.PROTOCOL),
    ],
)
def test_exception_types_map_to_kinds(exc, kind):
    assert C.classify(exc=exc).kind is kind


def test_transport_hint_mentions_tunnel_and_endpoint():
    got = C.classify(exc=TransportError("无法连接 http://203.0.113.10:18000/mcp"))
    assert "--tunnel" in got.hint
    assert "203.0.113.10" in got.message


def test_usage_and_interrupted_are_producible_without_signals():
    assert C.classify(kind=C.ErrorKind.USAGE, message="域名格式不对").kind.exit_code == 2
    assert C.classify(kind=C.ErrorKind.INTERRUPTED).kind.exit_code == 130


# ------------------------------------------------------------------ 脱敏


def test_api_key_like_text_is_redacted():
    fake_key = "tvly-" + "aB3xY9qK2m"  # 故意拼接，避免仓库里出现可被 grep 命中的疑似 Key
    got = C.classify(text=f"upstream rejected key {fake_key}")
    assert fake_key not in got.message
    assert "tvly…" in got.message


def test_redact_leaves_plain_text_alone():
    assert C.redact("nothing sensitive here") == "nothing sensitive here"


# ------------------------------------------------------------------ 重试预算


def test_transport_gets_one_attempt_per_retries():
    assert C.retry_budget(C.ErrorKind.TRANSPORT, retries=2, retries_given=True) == 3
    assert C.retry_budget(C.ErrorKind.TRANSPORT, retries=0, retries_given=False) == 1


def test_rate_limited_only_backs_off_when_user_asked_for_retries():
    assert C.retry_budget(C.ErrorKind.RATE_LIMITED, retries=1, retries_given=True) == 2
    assert C.retry_budget(C.ErrorKind.RATE_LIMITED, retries=1, retries_given=False) == 1


@pytest.mark.parametrize("kind", [C.ErrorKind.POOL_DEAD, C.ErrorKind.TOOL_ERROR, C.ErrorKind.USAGE, C.ErrorKind.TIMEOUT])
def test_never_retryable_kinds_stay_at_one_attempt(kind):
    assert C.retry_budget(kind, retries=3, retries_given=True) == 1


def test_protocol_rehandshake_is_already_inside_transport():
    assert C.retry_budget(C.ErrorKind.PROTOCOL, retries=3, retries_given=True) == 1
