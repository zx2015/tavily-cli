"""渲染层：Envelope → 五种输出格式。

内部数据模型是英文的，中文只发生在这一层（D-2）：`KEY_MAP` 是键名的唯一来源，
`--format raw` 完全绕过它直通服务端 `structuredContent`。
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field, fields

KEY_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "envelope": {
        "ok": ("成功", "ok"),
        "tool": ("工具", "tool"),
        "query": ("查询", "query"),
        "results": ("结果", "results"),
        "answer": ("简答", "answer"),
        "images": ("图片", "images"),
        "pages": ("页面", "pages"),
        "failed": ("失败", "failed"),
        "nodes": ("节点", "nodes"),
        "meta": ("元信息", "meta"),
        "error": ("错误", "error"),
    },
    "result": {
        "url": ("网址", "url"),
        "title": ("标题", "title"),
        "content": ("摘要", "content"),
        "score": ("评分", "score"),
        "id": ("编号", "id"),
        "raw_content": ("原文", "raw_content"),
    },
    "page": {
        "url": ("网址", "url"),
        "title": ("标题", "title"),
        "raw_content": ("原文", "raw_content"),
    },
    "failed": {"url": ("网址", "url"), "error": ("错误", "error")},
    "node": {"url": ("网址", "url"), "title": ("标题", "title")},
    "image": {"url": ("网址", "url"), "description": ("描述", "description")},
    "tool_spec": {
        "name": ("名称", "name"),
        "title": ("标题", "title"),
        "description": ("描述", "description"),
        "inputSchema": ("入参schema", "inputSchema"),
    },
    "check": {
        "name": ("检查项", "name"),
        "status": ("状态", "status"),
        "detail": ("细节", "detail"),
        "elapsed_ms": ("耗时毫秒", "elapsed_ms"),
    },
    "meta": {
        "request_id": ("请求编号", "request_id"),
        "response_time": ("服务端耗时", "response_time"),
        "elapsed_ms": ("本地耗时毫秒", "elapsed_ms"),
        "endpoint": ("端点", "endpoint"),
        "cli_version": ("CLI版本", "cli_version"),
        "server_version": ("服务端版本", "server_version"),
        "schema_hash": ("schema指纹", "schema_hash"),
    },
    "error": {"kind": ("类别", "kind"), "message": ("消息", "message"), "hint": ("建议", "hint")},
    # batch 的逐行信封在 §5.2 信封之前多两个批处理字段（§5.4）；请求体只在 --dry-run 出现
    "batch": {"line": ("行", "line"), "id": ("关联编号", "id"), "request": ("请求", "request")},
}

FIELD_SECTIONS = {
    "results": "result",
    "pages": "page",
    "failed": "failed",
    "nodes": "node",
    "images": "image",
    "meta": "meta",
    "error": "error",
}

_WIDE = {"W", "F"}
_UNIT = {"result": "条", "page": "页", "node": "节点", "tool_spec": "工具", "check": "项"}


@dataclass
class Envelope:
    ok: bool
    tool: str
    query: str | None = None
    results: list = field(default_factory=list)
    answer: str | None = None
    images: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    nodes: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    error: dict | None = None
    raw: dict | None = None


# 服务端列表字段 → Envelope 槽位（search 用 results，extract/crawl 落 pages，map 落 nodes）。
_TOOL_FIELDS = {
    "tavily-search": ("results", "results"),
    "tavily-extract": ("results", "pages"),
    "tavily-crawl": ("results", "pages"),
    "tavily-map": ("results", "nodes"),
    "tools/list": ("tools", "results"),
}

# 实测（2026-10-23）：tavily-map 的 results 是裸 URL 字符串数组，不是 {url,title}。
# 渲染层按 dict 取键，所以这里给该槽位指定收纳字符串的键名；其余槽位保持原样。
_BARE_STRING_KEY = {"nodes": "url"}


def build_envelope(
    tool: str,
    structured: dict | None,
    *,
    meta: dict | None = None,
    ok: bool = True,
    error: dict | None = None,
    query: str | None = None,
    raw: dict | None = None,
) -> Envelope:
    env = Envelope(
        ok=ok,
        tool=tool,
        query=query,
        meta=dict(meta or {}),
        error=error,
        raw=structured if raw is None else raw,
    )
    if not isinstance(structured, dict):
        return env

    source, target = _TOOL_FIELDS.get(tool, ("results", "results"))
    items = structured.get(source) or []
    string_key = _BARE_STRING_KEY.get(target)
    records: list = []
    for item in items:
        if isinstance(item, dict):
            records.append(dict(item))
        elif string_key is not None and isinstance(item, str):
            records.append({string_key: item})
        else:
            records.append(item)
    setattr(env, target, records)
    env.failed = [dict(item) for item in structured.get("failed_results") or []]
    env.images = list(structured.get("images") or [])
    env.answer = structured.get("answer")
    if env.query is None:
        env.query = structured.get("query") or structured.get("base_url")
    for key in ("request_id", "response_time"):
        if key in structured:
            env.meta.setdefault(key, structured[key])
    return env


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in _WIDE else 1 for ch in text)


# 只用前景与加粗/暗淡：SGR 30-37 与 1/2，不用背景色（浅色终端上背景色常不可读）。
_PALETTE = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33"}


def _paint(text: str, style: str | None, color: bool) -> str:
    if not (color and style and text):
        return text
    return f"\x1b[{_PALETTE[style]}m{text}\x1b[0m"


def render(
    env: Envelope,
    fmt: str = "json",
    isatty: bool = False,
    *,
    lang: str = "zh",
    with_meta: bool = False,
    width: int = 80,
    color: bool = False,
) -> str:
    if fmt == "auto":
        fmt = "table" if isatty else "json"
    if fmt == "raw":
        return "" if env.raw is None else json.dumps(env.raw, ensure_ascii=False, indent=2)
    if fmt == "ndjson":
        return _ndjson(env, lang, with_meta)
    if fmt == "table":
        return _table(env, width, color)
    if fmt == "md":
        return _md(env, color)
    return json.dumps(_doc(env, lang), ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ 机读


def _name(section: str | None, key: str, lang: str) -> str:
    table = KEY_MAP.get(section or "", {})
    entry = table.get(key)
    if entry is None:
        return key
    return entry[0] if lang == "zh" else entry[1]


def _translate(value, section: str | None, lang: str):
    if isinstance(value, list):
        return [_translate(v, section, lang) for v in value]
    if isinstance(value, dict):
        return {
            _name(section, k, lang): _translate(v, FIELD_SECTIONS.get(k, section), lang)
            for k, v in value.items()
        }
    return value


def _section_for(field_name: str, tool: str) -> str | None:
    if field_name == "results":
        if tool == "tools/list":
            return "tool_spec"
        if tool == "doctor":
            return "check"
    return FIELD_SECTIONS.get(field_name)


def _doc(env: Envelope, lang: str) -> dict:
    doc: dict = {}
    for f in fields(Envelope):
        if f.name == "raw":
            continue
        value = getattr(env, f.name)
        if f.name == "error" and isinstance(value, dict):
            value = _error_value(value, lang)
        doc[_name("envelope", f.name, lang)] = _translate(value, _section_for(f.name, env.tool), lang)
    return doc


def _error_value(error: dict, lang: str) -> dict:
    from .classify import ErrorKind

    kind = error.get("kind")
    if isinstance(kind, str) and kind in ErrorKind.__members__:
        error = {**error, "kind": kind if lang == "en" else ErrorKind[kind].label}
    return error


def meta_doc(meta: dict, lang: str = "zh") -> dict:
    return {_name("envelope", "meta", lang): _translate(meta, "meta", lang)}


def _batch_head(line: int, item_id, lang: str) -> dict:
    return {_name("batch", "line", lang): line, _name("batch", "id", lang): item_id}


def batch_line_doc(line: int, item_id, env: Envelope, lang: str = "zh") -> dict:
    return {**_batch_head(line, item_id, lang), **_doc(env, lang)}


def batch_request_doc(line: int, item_id, request: dict, lang: str = "zh") -> dict:
    """--dry-run 的逐行形状。请求体本身是协议面，键名不经过 KEY_MAP（§5.0）。"""

    return {**_batch_head(line, item_id, lang), _name("batch", "request", lang): request}


def is_empty(env: Envelope) -> bool:
    """成功但主列表为空：空结果不是错误（§9 用例 12），仅用于 stderr 提示。"""

    return env.ok and not _primary(env)[1]


def _primary(env: Envelope) -> tuple[str, list]:
    for name in ("results", "pages", "nodes"):
        items = getattr(env, name)
        if items:
            return _section_for(name, env.tool), items
    return ("result" if env.ok else "", [])


def _ndjson(env: Envelope, lang: str, with_meta: bool) -> str:
    if not env.ok:
        return ""
    section, items = _primary(env)
    lines = [json.dumps(_translate(item, section, lang), ensure_ascii=False) for item in items]
    if with_meta:
        lines.insert(0, json.dumps({_name("envelope", "meta", lang): _translate(env.meta, "meta", lang)}, ensure_ascii=False))
    return "\n".join(lines)


# ------------------------------------------------------------------ 人读


def _clip(text: str, width: int) -> str:
    if display_width(text) <= width:
        return text
    if width <= 1:
        return "…" if width == 1 else ""
    kept: list[str] = []
    used = 0
    for ch in text:
        cost = 2 if unicodedata.east_asian_width(ch) in _WIDE else 1
        if used + cost > width - 1:
            break
        kept.append(ch)
        used += cost
    return "".join(kept) + "…"


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def _fit(natural: list[int], available: int, minimum: int = 4) -> list[int]:
    widths = list(natural)
    while sum(widths) > available:
        if all(w <= minimum for w in widths):
            break
        index = max(range(len(widths)), key=lambda k: widths[k])
        if widths[index] > minimum:
            widths[index] -= 1
    return widths


_COLUMNS = {
    "result": [("评分", "score"), ("标题", "title"), ("网址", "url")],
    "page": [("标题", "title"), ("网址", "url"), ("原文", "raw_content")],
    "node": [("标题", "title"), ("网址", "url")],
    "tool_spec": [("名称", "name"), ("标题", "title")],
    "failed": [("网址", "url"), ("错误", "error")],
}

_COLUMN_STYLE = {
    "result": {"title": "bold", "url": "dim"},
    "page": {"title": "bold", "url": "dim"},
    "node": {"title": "bold", "url": "dim"},
    "tool_spec": {"name": "bold", "title": "dim"},
    "failed": {"error": "red"},
}

_DOCTOR_STYLE = {"失败": "red", "跳过": "yellow"}


def _cell(item: dict, key: str) -> str:
    value = item.get(key)
    if key == "raw_content":
        return f"{len(str(value))} 字符" if value else ""
    return str(value or "")


def _block(name: str, items: list, width: int, color: bool) -> list[str]:
    columns = [(label, key) for label, key in _COLUMNS[name] if any(_cell(item, key) for item in items)]
    headers = ["序号"] + [label for label, _ in columns]
    styles = [None] + [_COLUMN_STYLE[name].get(key) for _, key in columns]
    rows = [[str(index)] + [_cell(item, key) for _, key in columns] for index, item in enumerate(items, 1)]
    natural = [max(display_width(headers[i]), *(display_width(row[i]) for row in rows)) for i in range(len(headers))]
    widths = _fit(natural, width - 3 * (len(headers) - 1))
    header_line = _row(headers, widths, ["bold"] * len(headers), color)
    return [header_line, *(_row(row, widths, styles, color) for row in rows)]


def _row(cells: list[str], widths: list[int], styles: list[str | None] | None = None, color: bool = False) -> str:
    # 先剪贴、再填充、最后上色：转义序列不进 display_width，列位置因此与无色输出完全一致。
    padded = [_pad(_clip(cell, w), w) for cell, w in zip(cells, widths)]
    return " | ".join(_paint(cell, (styles or [None] * len(cells))[i], color) for i, cell in enumerate(padded))


def _elapsed(item: dict) -> str:
    value = item.get("elapsed_ms")
    return f"{value}ms" if value is not None else ""


def _doctor_table(env: Envelope, width: int, color: bool) -> str:
    """§9 用例 8：一检查项一行，状态与耗时同行，不套表头与汇总。"""

    rows = [
        [str(item.get("name") or ""), str(item.get("status") or ""), _elapsed(item), str(item.get("detail") or "")]
        for item in env.results
    ]
    natural = [max((display_width(row[i]) for row in rows), default=0) for i in range(4)]
    widths = _fit(natural, width - 3 * 3)
    return "\n".join(
        _row(row, widths, [None, _DOCTOR_STYLE.get(row[1], "green"), None, None], color) for row in rows
    )


def _error_block(env: Envelope, width: int | None = None, color: bool = False) -> list[str]:
    error = env.error or {}
    from .classify import ErrorKind

    kind = error.get("kind", "TOOL_ERROR")
    label = kind if kind not in ErrorKind.__members__ else ErrorKind[kind].label
    rows = [
        ("成功", "否", None),
        ("工具", env.tool, None),
        ("类别", label, "red"),
        ("消息", error.get("message", ""), None),
        ("建议", error.get("hint", ""), None),
    ]
    return [_paint(_clip(f"{k}：{v}", width) if width else f"{k}：{v}", style, color) for k, v, style in rows]


def _summary(env: Envelope) -> str:
    section, items = _primary(env)
    parts = []
    if section:
        parts.append(f"共 {len(items)} {_UNIT[section]}")
    if env.failed:
        parts.append(f"{len(env.failed)} 失败")
    meta = env.meta
    if "elapsed_ms" in meta:
        parts.append(f"耗时 {meta['elapsed_ms']}ms")
    if meta.get("request_id"):
        parts.append(f"请求编号 {meta['request_id']}")
    return " · ".join(parts)


def _table(env: Envelope, width: int, color: bool) -> str:
    if env.tool == "doctor":
        return _doctor_table(env, width, color)
    if not env.ok:
        return "\n".join(_error_block(env, width, color))
    lines: list[str] = []
    section, items = _primary(env)
    if section and items:
        lines.extend(_block(section, items, width, color))
    if env.failed:
        if lines:
            lines.append("")
        lines.extend(_block("failed", env.failed, width, color))
    lines.append(_paint(_clip(_summary(env), width), "dim", color))
    return "\n".join(lines)


def _md(env: Envelope, color: bool) -> str:
    if not env.ok:
        return "\n\n".join(_error_block(env, color=color))
    section, items = _primary(env)
    chunks: list[str] = []
    for item in items:
        heading = f"## {item.get('title') or item.get('url') or ''}".rstrip()
        blocks = [
            _paint(heading, "bold", color),
            _paint(str(item.get("url") or ""), "dim", color),
        ]
        if item.get("content"):
            blocks.append(str(item["content"]))
        if item.get("raw_content"):
            blocks.append(f"原文：{len(str(item['raw_content']))} 字符（未展开，取全文请用 -f json 或 -f raw）")
        if item.get("score"):
            blocks.append(f"评分：{item['score']}")
        chunks.append("\n\n".join(block for block in blocks if block))
    if env.failed:
        chunks.append(
            _paint("## 失败", "red", color) + "\n\n" + "\n".join(f"- {f.get('url')}：{f.get('error')}" for f in env.failed)
        )
    summary = _summary(env)
    if summary:
        chunks.append(_paint(summary, "dim", color))
    return "\n\n".join(chunks)
