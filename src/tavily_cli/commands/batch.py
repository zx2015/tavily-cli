"""`batch`：stdin NDJSON → "行 → 工具 + arguments"（§4.6）。

只做输入面的解析；校验、执行与逐行输出编排留在 `cli.py`，
这样坏行只失败自己那一行，而好行走的仍是与单命令**同一套**校验流水线。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .. import schema

ALIASES = {
    "search": "tavily-search",
    "extract": "tavily-extract",
    "crawl": "tavily-crawl",
    "map": "tavily-map",
}

INPUT_KEYS = ("id", "tool", "arguments")


@dataclass
class BatchLine:
    index: int
    id: object = None
    tool: str = ""
    arguments: dict = field(default_factory=dict)
    error: str = ""


def resolve_tool(name) -> tuple[str, str]:
    """返回 (规范工具名, 错误说明)；未知工具按"该行错误、零出网"处理。"""

    if not isinstance(name, str) or not name.strip():
        return "", "缺少 tool 键，或 tool 不是非空字符串"
    tool = ALIASES.get(name.lower(), name.lower())
    if tool not in schema.TOOL_SCHEMA:
        return "", f"未知工具 '{name}'，可用：{' / '.join(ALIASES)}"
    return tool, ""


def _json_kind(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "布尔"
    if isinstance(value, (int, float)):
        return "数字"
    if isinstance(value, str):
        return "字符串"
    if isinstance(value, list):
        return "数组"
    return "对象"


def parse_line(index: int, text: str) -> BatchLine | None:
    """一行 → BatchLine；空行返回 None（不占序号）。"""

    if not text.strip():
        return None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return BatchLine(index, error=f"不是合法 JSON：{exc.msg}（列 {exc.colno}）")
    if not isinstance(doc, dict):
        return BatchLine(index, error=f"这一行必须是 JSON 对象，实际是{_json_kind(doc)}")

    item_id = doc.get("id")
    extra = sorted(key for key in doc if key not in INPUT_KEYS)
    if extra:
        return BatchLine(
            index,
            item_id,
            error=f"含未声明的键 {'、'.join(map(str, extra))}，输入面只接受 {' / '.join(INPUT_KEYS)}",
        )

    tool, problem = resolve_tool(doc.get("tool"))
    if problem:
        given = doc.get("tool")
        return BatchLine(index, item_id, tool=given if isinstance(given, str) else "", error=problem)

    arguments = doc.get("arguments")
    if not isinstance(arguments, dict):
        return BatchLine(
            index, item_id, tool=tool, error=f"arguments 必须是 JSON 对象，实际是{_json_kind(arguments)}"
        )
    return BatchLine(index, item_id, tool=tool, arguments=arguments)


def read_lines(stream) -> list[BatchLine]:
    """读尽 stdin：空行忽略，序号只数有效行（§4.6）。上限由调用方按 len() 把关。"""

    lines: list[BatchLine] = []
    for text in stream:
        line = parse_line(len(lines) + 1, text)
        if line is not None:
            lines.append(line)
    return lines
