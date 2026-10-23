"""schema.py：静态契约副本 + 指纹 + 域名规则（全部离线）。"""

from __future__ import annotations

import copy

from tavily_cli import schema

SERVER_TOOL_NAMES = ["tavily-search", "tavily-extract", "tavily-crawl", "tavily-map"]


def test_builtin_tools_cover_four_server_tools(server_tools):
    assert [t["name"] for t in schema.BUILTIN_TOOLS] == SERVER_TOOL_NAMES
    assert [t["name"] for t in server_tools] == SERVER_TOOL_NAMES


def test_builtin_hash_matches_live_capture(server_tools):
    """内置副本必须与线上 tools/list 指纹一致，否则说明副本过期。"""

    assert schema.schema_hash() == schema.schema_hash(server_tools)


def test_schema_hash_prefix_and_stability(server_tools):
    first = schema.schema_hash(server_tools)
    shuffled = list(reversed(copy.deepcopy(server_tools)))
    assert first.startswith("sha256:")
    assert schema.schema_hash(server_tools) == first
    assert schema.schema_hash(shuffled) == first


def test_schema_hash_changes_on_param_drift(server_tools):
    mutated = copy.deepcopy(server_tools)
    mutated[0]["inputSchema"]["properties"]["new_flag"] = {"type": "boolean"}
    assert schema.schema_hash(mutated) != schema.schema_hash(server_tools)

    trimmed = copy.deepcopy(server_tools)
    trimmed[0]["inputSchema"]["required"] = []
    assert schema.schema_hash(trimmed) != schema.schema_hash(server_tools)


def test_schema_hash_ignores_description_only_change(server_tools):
    """描述文案变更不算契约漂移，不应触发告警。"""

    mutated = copy.deepcopy(server_tools)
    mutated[0]["description"] = "换了个说法"
    assert schema.schema_hash(mutated) == schema.schema_hash(server_tools)


def test_tool_schema_search_params_and_required():
    spec = schema.TOOL_SCHEMA["tavily-search"]
    assert spec.required == ("query",)
    assert spec.params["query"].max_length == 512
    assert spec.params["max_results"].minimum == 1
    assert spec.params["max_results"].maximum == 20
    assert spec.params["search_depth"].enum == ("basic", "advanced")
    assert spec.params["topic"].enum == ("general", "news", "finance")
    assert spec.params["days"].minimum == 1
    assert spec.params["days"].maximum == 365
    assert spec.params["time_range"].enum == ("day", "week", "month", "year")
    assert spec.params["time_range"].nullable is True
    assert "timeout" not in spec.params
    assert spec.params["include_domains"].kind == "array"
    assert spec.params["include_domains"].item_kind == "string"


def test_tool_schema_extract_and_others():
    assert schema.TOOL_SCHEMA["tavily-extract"].required == ("urls",)
    assert schema.TOOL_SCHEMA["tavily-extract"].params["extract_depth"].enum == (
        "basic",
        "advanced",
    )
    assert schema.TOOL_SCHEMA["tavily-map"].required == ("url",)
    assert schema.TOOL_SCHEMA["tavily-crawl"].required == ("url",)


def test_tool_schema_only_declares_server_known_names():
    """副本的参数集合必须与 schema 逐字相符，不得自创参数（4.1.0 的 timeout 就是这么被删掉的）。"""

    assert set(schema.TOOL_SCHEMA) == set(SERVER_TOOL_NAMES)
    for name, spec in schema.TOOL_SCHEMA.items():
        server_tool = next(t for t in schema.BUILTIN_TOOLS if t["name"] == name)
        assert set(spec.params) == set(server_tool["inputSchema"]["properties"])


def test_validate_domain_accepts_plain_hostnames():
    for good in ["tavily.com", "EXAMPLE.COM", "a.b.c.cn", "sub.domain.co.uk", "1.com"]:
        assert schema.validate_domain(good), good


def test_validate_domain_rejects_the_incident_input():
    """事故用例：!!bad 必须在校验层被拦下（研究文档 §5）。"""

    for bad in [
        "!!bad",
        "tavily",
        "http://tavily.com",
        "tavily.com/path",
        "tavily.com:8080",
        "sub tavily.com",
        "-bad.com",
        "bad-.com",
        ".tavily.com",
        "tavily..com",
        "tavily.c",
        "tavily..",
        "",
        "tävily.com",
        "tavily_und.com",
        "a" * 64 + ".com",
    ]:
        assert not schema.validate_domain(bad), bad
