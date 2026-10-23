"""MCP session 语义：握手状态、失效判定、脱敏（与 HTTP 机制解耦）。"""

from __future__ import annotations

from dataclasses import dataclass, field

PROTOCOL_VERSION = "2025-06-18"
SESSION_HEADER = "mcp-session-id"
MASK_PREFIX = 8

_SESSION_MISSING_MARKERS = ("missing session id", "missing session-id")


@dataclass
class Session:
    endpoint: str
    protocol_version: str = PROTOCOL_VERSION
    session_id: str | None = None
    server_version: str | None = None
    server_name: str | None = None
    failures: int = 0
    _observed: dict = field(default_factory=dict, repr=False)

    @property
    def ready(self) -> bool:
        return self.session_id is not None

    def adopt(self, session_id: str | None, server_info: dict | None, protocol_version: str | None) -> None:
        self.session_id = session_id
        info = server_info or {}
        self.server_version = info.get("version")
        self.server_name = info.get("name")
        if protocol_version:
            self.protocol_version = protocol_version

    def invalidate(self) -> None:
        self.session_id = None

    def masked_id(self) -> str:
        if not self.session_id:
            return "-"
        return self.session_id[:MASK_PREFIX] + "…"


def is_missing_session(status: int | None, detail: str) -> bool:
    """实测：缺 `mcp-session-id` 时服务端回 HTTP 400 `Bad Request: Missing session ID`。"""

    if status != 400:
        return False
    lowered = detail.lower()
    return any(marker in lowered for marker in _SESSION_MISSING_MARKERS)
