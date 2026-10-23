"""内置静态 schema：服务端 `tools/list` 的副本 + 指纹 + 域名规则。

副本 2026-10-22 抓取自 mcp-tavily 4.1.3 运行时 `tools/list`
（study/.../fixtures/tools_list.json，可用 study/.../probe_tools_list.py 刷新）。
它是**缓存**，权威永远是运行时 `tools/list`；两者指纹不一致时 CLI 必须告警而非静默。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

_BUILTIN_TOOLS_JSON = r"""[{"name":"tavily-search","title":"Tavily Search","inputSchema":{"properties":{"query":{"type":"string","description":"Search query text."},"search_depth":{"default":"basic","enum":["basic","advanced"],"type":"string","description":"Search quality preset, basic or advanced."},"topic":{"default":"general","enum":["general","news","finance"],"type":"string","description":"Search category: general, news, or finance."},"days":{"anyOf":[{"type":"integer"},{"type":"null"}],"default":null,"description":"News lookback window in days."},"max_results":{"default":5,"type":"integer","description":"Maximum number of returned results."},"include_images":{"default":false,"type":"boolean","description":"Include image results."},"include_answer":{"default":false,"type":"boolean","description":"Include a generated answer."},"include_raw_content":{"default":false,"type":"boolean","description":"Include raw page content."},"include_domains":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"default":null,"description":"Restrict results to these domains."},"exclude_domains":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"default":null,"description":"Exclude results from these domains."},"time_range":{"anyOf":[{"enum":["day","week","month","year"],"type":"string"},{"type":"null"}],"default":null,"description":"Restrict results to a calendar range."},"include_image_descriptions":{"default":false,"type":"boolean","description":"Include descriptions for image results."}},"required":["query"],"type":"object","additionalProperties":false}},{"name":"tavily-extract","title":"Tavily Extract","inputSchema":{"properties":{"urls":{"items":{"type":"string"},"type":"array","description":"URLs to extract."},"extract_depth":{"default":"basic","enum":["basic","advanced"],"type":"string","description":"Extraction detail preset, basic or advanced."},"include_images":{"default":false,"type":"boolean","description":"Include image URLs found on each page."}},"required":["urls"],"type":"object","additionalProperties":false}},{"name":"tavily-crawl","title":"Tavily Crawl","inputSchema":{"properties":{"url":{"type":"string","description":"Starting URL for the crawl."},"max_depth":{"anyOf":[{"type":"integer"},{"type":"null"}],"default":null,"description":"Maximum link depth."},"max_breadth":{"anyOf":[{"type":"integer"},{"type":"null"}],"default":null,"description":"Maximum links followed per page."},"limit":{"anyOf":[{"type":"integer"},{"type":"null"}],"default":null,"description":"Maximum total pages to process."},"instructions":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null,"description":"Natural-language crawl guidance."},"select_paths":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"default":null,"description":"Path patterns to include."},"exclude_paths":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"default":null,"description":"Path patterns to exclude."},"include_images":{"default":false,"type":"boolean","description":"Include images from crawled pages."},"allow_external":{"default":false,"type":"boolean","description":"Follow links outside the starting domain."}},"required":["url"],"type":"object","additionalProperties":false}},{"name":"tavily-map","title":"Tavily Map","inputSchema":{"properties":{"url":{"type":"string","description":"Starting URL for the site map."},"max_depth":{"anyOf":[{"type":"integer"},{"type":"null"}],"default":null,"description":"Maximum discovery depth."},"limit":{"anyOf":[{"type":"integer"},{"type":"null"}],"default":null,"description":"Maximum number of discovered URLs."},"select_paths":{"anyOf":[{"items":{"type":"string"},"type":"array"},{"type":"null"}],"default":null,"description":"Path patterns to include."}},"required":["url"],"type":"object","additionalProperties":false}}]"""

BUILTIN_TOOLS: list[dict] = json.loads(_BUILTIN_TOOLS_JSON)

DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})*\.[a-z]{2,}$")

# 只放 JSON schema 表达不了的约束（长度上限、更严的数值区间、语义检查）。
# 枚举与 required 一律从 schema 自身读取，避免副本与权威长期两张皮。
_RULES: dict[str, dict[str, dict]] = {
    "tavily-search": {
        "query": {"max_length": 512, "checks": ("nonempty", "no_control")},
        "max_results": {"minimum": 1, "maximum": 20},
        "days": {"minimum": 1, "maximum": 365, "checks": ("news_only",)},
        "include_domains": {"min_items": 1, "checks": ("domain_list",)},
        "exclude_domains": {"min_items": 1, "checks": ("domain_list",)},
    },
    "tavily-extract": {
        "urls": {"min_items": 1, "max_items": 20, "checks": ("http_url_list",)},
    },
    "tavily-crawl": {
        "url": {"checks": ("http_url",)},
        "max_depth": {"minimum": 0},
        "max_breadth": {"minimum": 1},
        "limit": {"minimum": 1},
        "select_paths": {"checks": ("regex_list",)},
        "exclude_paths": {"checks": ("regex_list",)},
    },
    "tavily-map": {
        "url": {"checks": ("http_url",)},
        "max_depth": {"minimum": 0},
        "limit": {"minimum": 1},
        "select_paths": {"checks": ("regex_list",)},
    },
}


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: str
    item_kind: str | None = None
    required: bool = False
    nullable: bool = False
    default: object = None
    enum: tuple[str, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    max_length: int | None = None
    min_items: int | None = None
    max_items: int | None = None
    checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    required: tuple[str, ...]
    params: dict[str, ParamSpec]


def _resolve_type(prop: dict) -> tuple[str, str | None, bool]:
    options = [prop] if "type" in prop else list(prop.get("anyOf", []))
    nullable = False
    kind: str | None = None
    item_kind: str | None = None
    for option in options:
        current = option.get("type")
        if current == "null":
            nullable = True
        elif current == "array":
            kind = "array"
            item_kind = (option.get("items") or {}).get("type")
        elif current:
            kind = current
    return kind or "string", item_kind, nullable


def _resolve_enum(prop: dict) -> tuple[str, ...] | None:
    options = [prop] if "type" in prop else list(prop.get("anyOf", []))
    for option in options:
        values = option.get("enum")
        if values:
            return tuple(values)
    return None


def _build() -> dict[str, ToolSpec]:
    built: dict[str, ToolSpec] = {}
    for tool in BUILTIN_TOOLS:
        schema = tool["inputSchema"]
        required = tuple(schema.get("required", []))
        rules = _RULES.get(tool["name"], {})
        params: dict[str, ParamSpec] = {}
        for name, prop in schema.get("properties", {}).items():
            kind, item_kind, nullable = _resolve_type(prop)
            extra = rules.get(name, {})
            params[name] = ParamSpec(
                name=name,
                kind=kind,
                item_kind=item_kind,
                required=name in required,
                nullable=nullable,
                default=prop.get("default"),
                enum=_resolve_enum(prop),
                minimum=extra.get("minimum"),
                maximum=extra.get("maximum"),
                max_length=extra.get("max_length"),
                min_items=extra.get("min_items"),
                max_items=extra.get("max_items"),
                checks=tuple(extra.get("checks", ())),
            )
        built[tool["name"]] = ToolSpec(
            name=tool["name"], title=tool["title"], required=required, params=params
        )
    return built


TOOL_SCHEMA: dict[str, ToolSpec] = _build()


def schema_hash(tools: list[dict] | None = None) -> str:
    """只哈希 name + inputSchema：描述文案变更不算契约漂移。"""

    items = BUILTIN_TOOLS if tools is None else tools
    canonical = sorted(
        ({"name": t.get("name"), "inputSchema": t.get("inputSchema")} for t in items),
        key=lambda entry: entry["name"] or "",
    )
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def validate_domain(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return bool(DOMAIN_RE.match(value.lower()))
