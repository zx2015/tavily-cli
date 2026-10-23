"""错误分类器：原始信号 → ErrorKind → 退出码 / 重试策略 / 中文建议。

模式串全部取自服务端实测原文（study/mcp-tavily-endpoint/README.md、ADR-0002）。
未命中任何模式时**保守降级为 TOOL_ERROR（不重试）**，避免放大对共享 Key 池的损伤。
"""

from __future__ import annotations

import enum
import re
import socket
import urllib.error
from dataclasses import dataclass

from .transport import ClientTimeout, ProtocolError, TransportError

EMPTY_MESSAGE = "服务端未返回错误文本"


class ErrorKind(enum.Enum):
    OK = (0, False, "成功")
    USAGE = (2, False, "参数校验失败")
    TRANSPORT = (3, True, "网络不可达")
    PROTOCOL = (4, True, "协议异常")
    TOOL_ERROR = (5, False, "工具执行失败")
    POOL_DEAD = (6, False, "密钥池已死亡")
    TIMEOUT = (7, False, "超时")
    RATE_LIMITED = (8, True, "被限流")
    INTERRUPTED = (130, False, "已中断")

    def __init__(self, exit_code: int, retryable: bool, label: str) -> None:
        self.exit_code = exit_code
        self.retryable = retryable
        self.label = label


_POOL_DEAD = ("no active api keys", "all available keys failed")
_TIMEOUT = ("request timed out after",)
_RATE_LIMITED = ("rate limit", "too many requests", "status 429", "code 429", "error 429")
_PROTOCOL = ("unknown tool", "missing session id")
_FASTMCP_VALIDATION = ("validation error for call[", "unexpected_keyword_argument")

_HINTS = {
    ErrorKind.OK: "",
    ErrorKind.USAGE: "修正参数后重试；这类错误不会发出任何网络请求。",
    ErrorKind.TRANSPORT: "确认端点可达；必要时加 --tunnel on 走 SSH 隧道。",
    ErrorKind.PROTOCOL: "先跑 tavily-cli doctor 分层定位，再用 tavily-cli tools 检查 schema 漂移。",
    ErrorKind.TOOL_ERROR: "CLI 不会自动重试工具失败，请先看服务端原文。",
    ErrorKind.POOL_DEAD: (
        "服务端 Key 池已进入 ERROR 终态，客户端无法自愈；"
        "需 ssh mcp-host 'docker restart mcp-tavily' 恢复（根因见 "
        "docs/adr/0003-validate-before-send.md）。"
    ),
    ErrorKind.TIMEOUT: "增大 --timeout（search 默认 45s，crawl/map 默认 120s）；超时类永不重试。",
    ErrorKind.RATE_LIMITED: "上游限流；建议退避至少 5 秒后用 --retries 1 单次重试。",
    ErrorKind.INTERRUPTED: "已中断，未写出完整输出。",
}

_CLIENT_GAP_HINT = "这是服务端 FastMCP 校验失败，说明客户端校验有遗漏，应在 schema.py/validate.py 补规则。"

_KEY_PATTERN = re.compile(r"tvly-[A-Za-z0-9_\-]{6,}")


@dataclass(frozen=True)
class Classified:
    kind: ErrorKind
    message: str
    hint: str

    @property
    def exit_code(self) -> int:
        return self.kind.exit_code

    @property
    def retryable(self) -> bool:
        return self.kind.retryable


def redact(text: str) -> str:
    return _KEY_PATTERN.sub("tvly…<redacted>", text)


def retry_budget(kind: ErrorKind, *, retries: int, retries_given: bool) -> int:
    """ADR-0002 重试矩阵的唯一真相：返回**总尝试次数**（含首次）。"""

    if kind is ErrorKind.TRANSPORT:
        return 1 + max(0, retries)
    if kind is ErrorKind.RATE_LIMITED:
        return 2 if retries_given and retries > 0 else 1
    return 1


def classify(
    text: str | None = None,
    exc: BaseException | None = None,
    *,
    kind: ErrorKind | None = None,
    message: str | None = None,
) -> Classified:
    if kind is not None:
        raw = message if message is not None else str(exc or "")
        return Classified(kind, redact(raw or EMPTY_MESSAGE), _HINTS[kind])

    raw = text if text is not None else (str(exc) if exc is not None else "")
    resolved = _from_text(raw)
    if resolved is None:
        resolved = _from_exception(exc) if exc is not None else ErrorKind.TOOL_ERROR
    hint = _CLIENT_GAP_HINT if resolved is ErrorKind.TOOL_ERROR and _hits(raw, _FASTMCP_VALIDATION) else _HINTS[resolved]
    return Classified(resolved, redact(raw or EMPTY_MESSAGE), hint)


def _from_text(raw: str) -> ErrorKind | None:
    for markers, kind in (
        (_POOL_DEAD, ErrorKind.POOL_DEAD),
        (_TIMEOUT, ErrorKind.TIMEOUT),
        (_RATE_LIMITED, ErrorKind.RATE_LIMITED),
        (_PROTOCOL, ErrorKind.PROTOCOL),
    ):
        if _hits(raw, markers):
            return kind
    return None


def _from_exception(exc: BaseException) -> ErrorKind:
    if isinstance(exc, ClientTimeout):
        return ErrorKind.TIMEOUT
    if isinstance(exc, ProtocolError):
        return ErrorKind.PROTOCOL
    if isinstance(exc, TransportError):
        return ErrorKind.TRANSPORT
    if isinstance(exc, (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError)):
        return ErrorKind.TRANSPORT
    return ErrorKind.TOOL_ERROR


def _hits(raw: str, markers: tuple[str, ...]) -> bool:
    lowered = raw.lower()
    return any(marker in lowered for marker in markers)
