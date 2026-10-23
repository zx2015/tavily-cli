"""`tools` → `tools/list`：打印服务端权威 schema，并与内置副本比对指纹（§4.4）。"""

from __future__ import annotations

from .. import schema
from ..render import Envelope, build_envelope

TOOL = "tools/list"


def to_envelope(tools: list[dict], meta: dict) -> Envelope:
    return build_envelope(TOOL, {"tools": tools}, meta={**meta, "schema_hash": schema.schema_hash(tools)}, raw={"tools": tools})


def drift_warning(tools: list[dict]) -> str | None:
    """指纹不一致即服务端参数表已漂移；内置副本仅作缓存，权威是运行时 tools/list。"""

    server = schema.schema_hash(tools)
    builtin = schema.schema_hash()
    if server == builtin:
        return None
    return (
        f"schema 漂移：服务端指纹 {server[:19]}… 与内置副本 {builtin[:19]}… 不一致，"
        "参数表可能已增删；内置校验规则可能过严或过松，请以 tavily-cli tools 的输出为准。"
    )
