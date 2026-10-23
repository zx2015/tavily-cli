"""render：Envelope → 输出格式（D-2 中文键名单点映射 + 东亚宽字符列宽）。

断言的键名一律取自 docs/requirements.md §5.2/§5.3 与 §9 用例 13/14。
"""

from __future__ import annotations

import json
import re

import pytest

from tavily_cli.render import FIELD_SECTIONS, KEY_MAP, Envelope, display_width, render

META = {
    "request_id": "d0df3237-0fc3",
    "response_time": 1.02,
    "elapsed_ms": 1513,
    "endpoint": "http://127.0.0.1:18000/mcp",
    "cli_version": "0.1.0",
    "server_version": "4.1.0",
    "schema_hash": "sha256:abc",
}


def rename(doc, lang: str):
    """按 KEY_MAP 把某种语言的键名换回内部英文键名，用于同构性断言。"""

    inverse = {
        section: {names[0 if lang == "zh" else 1]: internal for internal, names in table.items()}
        for section, table in KEY_MAP.items()
    }

    def walk(value, section):
        if isinstance(value, list):
            return [walk(v, section) for v in value]
        if isinstance(value, dict):
            table = inverse.get(section)
            if table is None:
                return value
            out = {}
            for key, sub in value.items():
                internal = table.get(key, key)
                out[internal] = walk(sub, FIELD_SECTIONS.get(internal, section))
            return out
        return value

    return walk(doc, "envelope")


def search_env(**kwargs) -> Envelope:
    return Envelope(
        ok=True,
        tool="tavily-search",
        query="示例股份 2026 半年报 营收",
        results=[
            {"url": "https://a", "title": "海 康 视 讯", "content": "摘要甲", "score": "0.88", "id": "bcb923-00"},
            {"url": "https://b", "title": "Example Domain", "content": "摘要乙", "score": "0.71", "id": "bcb923-01"},
        ],
        meta=dict(META),
        raw={"query": "x", "results": [{"url": "https://a", "title": "海 康 视 讯", "score": "0.88"}]},
        **kwargs,
    )


# ------------------------------------------------------------------ JSON 信封


def test_json_defaults_to_chinese_keys():
    doc = json.loads(render(search_env(), "json"))
    assert doc == {
        "成功": True,
        "工具": "tavily-search",
        "查询": "示例股份 2026 半年报 营收",
        "结果": [
            {"网址": "https://a", "标题": "海 康 视 讯", "摘要": "摘要甲", "评分": "0.88", "编号": "bcb923-00"},
            {"网址": "https://b", "标题": "Example Domain", "摘要": "摘要乙", "评分": "0.71", "编号": "bcb923-01"},
        ],
        "简答": None,
        "图片": [],
        "页面": [],
        "失败": [],
        "节点": [],
        "元信息": {
            "请求编号": "d0df3237-0fc3",
            "服务端耗时": 1.02,
            "本地耗时毫秒": 1513,
            "端点": "http://127.0.0.1:18000/mcp",
            "CLI版本": "0.1.0",
            "服务端版本": "4.1.0",
            "schema指纹": "sha256:abc",
        },
        "错误": None,
    }


def test_keys_en_switches_only_key_names():
    en = json.loads(render(search_env(), "json", lang="en"))
    assert en["ok"] is True
    assert en["tool"] == "tavily-search"
    assert en["results"][0]["url"] == "https://a"
    assert en["meta"]["request_id"] == "d0df3237-0fc3"
    assert "结果" not in en


def test_zh_and_en_are_structurally_isomorphic(load_fixture):
    """§9 用例 13：同一 Envelope 下两种键名一一对应、值完全相同。"""

    raw = load_fixture("search_latest.json")["result"]["structuredContent"]
    env = Envelope(
        ok=True,
        tool="tavily-search",
        query=raw["query"],
        results=raw["results"],
        answer=raw.get("answer"),
        images=raw.get("images") or [],
        meta=dict(META),
        raw=raw,
    )
    zh = json.loads(render(env, "json"))
    en = json.loads(render(env, "json", lang="en"))
    assert rename(zh, "zh") == en == rename(en, "en")


def test_json_keeps_chinese_literals_and_indent():
    out = render(search_env(), "json")
    assert out.startswith("{\n  ")
    assert "示例股份" in out
    assert "\\u4f0a" not in out


def test_values_are_not_reformatted(load_fixture):
    raw = load_fixture("search_latest.json")["result"]["structuredContent"]
    item = raw["results"][0]
    env = Envelope(ok=True, tool="tavily-search", query=raw["query"], results=raw["results"], meta=dict(META), raw=raw)
    doc = json.loads(render(env, "json"))
    assert doc["结果"][0] == {
        "网址": item["url"],
        "标题": item["title"],
        "摘要": item["content"],
        "评分": item["score"],
        "原文": item["raw_content"],
        "编号": item["id"],
    }


def test_unmapped_server_key_passes_through():
    """§5.2 的 1:1 优先于 §5.0 的键名翻译：未知字段不丢弃也不臆造中文名。"""

    env = Envelope(ok=True, tool="tavily-search", results=[{"url": "https://a", "video": "https://v"}], meta=dict(META))
    assert json.loads(render(env, "json"))["结果"][0]["video"] == "https://v"


# ------------------------------------------------------------------ 失败信封


def test_error_envelope_shape():
    env = Envelope(
        ok=False,
        tool="tavily-search",
        query="x",
        meta=dict(META),
        error={"kind": "POOL_DEAD", "message": "No active API keys available in the pool.", "hint": "需重启容器"},
    )
    doc = json.loads(render(env, "json"))
    assert doc["成功"] is False
    assert doc["结果"] == []
    assert doc["错误"] == {
        "类别": "密钥池已死亡",
        "消息": "No active API keys available in the pool.",
        "建议": "需重启容器",
    }


def test_error_kind_label_follows_lang():
    env = Envelope(ok=False, tool="tavily-search", meta=dict(META), error={"kind": "USAGE", "message": "m", "hint": "h"})
    assert json.loads(render(env, "json"))["错误"]["类别"] == "参数校验失败"
    assert json.loads(render(env, "json", lang="en"))["error"]["kind"] == "USAGE"


def test_error_envelope_is_isomorphic_across_langs():
    env = Envelope(ok=False, tool="tavily-search", meta=dict(META), error={"kind": "TIMEOUT", "message": "m", "hint": "h"})
    zh_doc = rename(json.loads(render(env, "json")), "zh")
    en_doc = json.loads(render(env, "json", lang="en"))
    # 唯一允许的差异是 类别 的取值本身（§6 规定它也本地化），其余必须逐字节相同
    assert json.loads(render(env, "json"))["错误"]["类别"] == "超时"
    zh_doc["error"]["kind"] = en_doc["error"]["kind"]
    assert zh_doc == en_doc


def test_missing_field_lists_become_empty_arrays():
    env = Envelope(ok=True, tool="tavily-search", meta=dict(META))
    doc = json.loads(render(env, "json"))
    assert doc["结果"] == [] and doc["失败"] == [] and doc["节点"] == []


# ------------------------------------------------------------------ raw 逃生通道


def test_raw_bypasses_key_map(search_result):
    raw_sc = search_result["structuredContent"]
    env = Envelope(ok=True, tool="tavily-search", query=raw_sc["query"], results=raw_sc["results"], meta=dict(META), raw=raw_sc)
    assert render(env, "raw") == json.dumps(raw_sc, ensure_ascii=False, indent=2)


def test_raw_ignores_keys_en():
    assert "url" in render(search_env(), "raw", lang="en")
    assert "网址" not in render(search_env(), "raw")


# ------------------------------------------------------------------ table


def test_table_header_and_summary():
    out = render(search_env(), "table")
    assert "序号" in out and "评分" in out and "标题" in out and "网址" in out
    assert "共 2 条" in out
    assert "d0df3237-0fc3" in out
    assert "1513" in out


def test_table_columns_stay_aligned_with_cjk(load_fixture):
    raw = load_fixture("search_latest.json")["result"]["structuredContent"]
    env = Envelope(ok=True, tool="tavily-search", query=raw["query"], results=raw["results"], meta=dict(META), raw=raw)
    lines = [line for line in render(env, "table", width=100).splitlines() if "|" in line]
    assert len({display_width(line) for line in lines}) == 1, lines


def test_table_truncates_long_cells():
    env = Envelope(
        ok=True,
        tool="tavily-search",
        results=[{"url": "https://a" + "/x" * 60, "title": "标题" * 40, "score": "0.9"}],
        meta=dict(META),
    )
    out = render(env, "table", width=60)
    assert "…" in out
    for line in out.splitlines():
        assert display_width(line) <= 60


def test_table_for_extract_uses_pages_and_failed(load_fixture):
    raw = load_fixture("out_tavily-extract_sample.json")["result"]["structuredContent"]
    env = Envelope(ok=True, tool="tavily-extract", pages=raw["results"], failed=raw["failed_results"], meta=dict(META), raw=raw)
    out = render(env, "table", width=120)
    assert "example.com" in out
    assert "this-domain-really-does-not-exist-zzz.com" in out
    assert "Failed to fetch url" in out
    assert "共 1 页 · 1 失败" in out


def test_table_for_map_uses_nodes(load_fixture):
    raw = load_fixture("out_tavily-map_sample.json")["result"]["structuredContent"]
    env = Envelope(
        ok=True, tool="tavily-map", query=raw["base_url"], nodes=[{"url": "https://example.com/a"}], meta=dict(META), raw=raw
    )
    out = render(env, "table", width=120)
    assert "网址" in out
    assert "共 1 节点" in out


def test_table_on_empty_results_is_not_an_error():
    env = Envelope(ok=True, tool="tavily-search", query="zzz", results=[], meta=dict(META))
    assert "共 0 条" in render(env, "table")


# ------------------------------------------------------------------ ndjson / md


def test_ndjson_one_line_per_result():
    lines = render(search_env(), "ndjson").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["网址"] == "https://a"


def test_ndjson_with_meta_prepends_metadata_line():
    lines = render(search_env(), "ndjson", with_meta=True).splitlines()
    assert set(json.loads(lines[0])) == {"元信息"}
    assert len(lines) == 3


def test_ndjson_for_extract_and_map():
    env = Envelope(ok=True, tool="tavily-extract", pages=[{"url": "https://a"}, {"url": "https://b"}], meta=dict(META))
    assert len(render(env, "ndjson").splitlines()) == 2
    env = Envelope(ok=True, tool="tavily-map", nodes=[{"url": "https://a"}], meta=dict(META))
    assert len(render(env, "ndjson").splitlines()) == 1


def test_ndjson_on_error_envelope_emits_nothing():
    env = Envelope(ok=False, tool="tavily-search", meta=dict(META), error={"kind": "POOL_DEAD", "message": "m", "hint": "h"})
    assert render(env, "ndjson") == ""


def test_table_and_md_show_the_error_text():
    env = Envelope(
        ok=False,
        tool="tavily-search",
        meta=dict(META),
        error={"kind": "POOL_DEAD", "message": "No active API keys available in the pool.", "hint": "需重启"},
    )
    for fmt in ("table", "md"):
        out = render(env, fmt)
        assert "密钥池已死亡" in out
        assert "No active API keys available in the pool." in out
        assert "需重启" in out


def test_raw_without_server_payload_emits_nothing():
    env = Envelope(ok=False, tool="tavily-search", meta=dict(META), error={"kind": "USAGE", "message": "m", "hint": "h"})
    assert render(env, "raw") == ""


def test_md_blocks():
    out = render(search_env(), "md")
    assert "## 海 康 视 讯" in out
    assert "https://a" in out
    assert "摘要甲" in out
    assert "评分" in out


def test_md_reports_raw_body_length_without_inlining(load_fixture):
    raw = load_fixture("out_tavily-extract_sample.json")["result"]["structuredContent"]
    env = Envelope(ok=True, tool="tavily-extract", pages=raw["results"], meta=dict(META), raw=raw)
    out = render(env, "md")
    assert "This domain is for use in documentation" not in out
    assert "原文" in out and "字符" in out


# ------------------------------------------------------------------ 格式默认与工具面


def test_auto_format_depends_on_isatty():
    assert render(search_env(), "auto", isatty=False).startswith("{")
    assert "评分" in render(search_env(), "auto", isatty=True).splitlines()[0]


def test_tools_list_envelope_renders_server_payload():
    tools = [{"name": "tavily-search", "title": "Search"}]
    env = Envelope(ok=True, tool="tools/list", meta=dict(META), raw={"tools": tools})
    doc = json.loads(render(env, "json"))
    assert doc["工具"] == "tools/list"
    assert '"tools"' in render(env, "raw")


def test_tools_list_rows_use_tool_spec_keys_and_unit():
    env = Envelope(
        ok=True,
        tool="tools/list",
        results=[{"name": "tavily-search", "title": "Search", "inputSchema": {"type": "object"}}],
        meta=dict(META),
    )
    assert json.loads(render(env, "json"))["结果"][0] == {
        "名称": "tavily-search",
        "标题": "Search",
        "入参schema": {"type": "object"},
    }
    assert "共 1 工具" in render(env, "table")
    assert json.loads(render(env, "ndjson").splitlines()[0])["名称"] == "tavily-search"


def test_doctor_check_rows():
    env = Envelope(
        ok=True,
        tool="doctor",
        results=[{"name": "TCP 连接", "status": "可达", "detail": "203.0.113.10:18000", "elapsed_ms": 3}],
        meta=dict(META),
    )
    doc = json.loads(render(env, "json"))
    assert doc["结果"][0] == {"检查项": "TCP 连接", "状态": "可达", "细节": "203.0.113.10:18000", "耗时毫秒": 3}
    # §9 用例 8：一检查项一行，无表头无汇总，状态与耗时同行可见。
    line = render(env, "table")
    assert line.splitlines() == [line]
    assert "TCP 连接" in line and "可达" in line and "3ms" in line and "203.0.113.10:18000" in line


# ------------------------------------------------------------------ Envelope 构造


def test_build_envelope_for_search(search_result):
    from tavily_cli.render import build_envelope

    env = build_envelope("tavily-search", search_result["structuredContent"], meta=dict(META))
    assert env.ok is True
    assert env.tool == "tavily-search"
    assert len(env.results) == 2
    assert env.query == search_result["structuredContent"]["query"]


def test_build_envelope_for_extract_keeps_failed_results(extract_result):
    from tavily_cli.render import build_envelope

    sc = extract_result["structuredContent"]
    env = build_envelope("tavily-extract", sc, meta=dict(META))
    assert len(env.pages) == len(sc["results"])
    assert len(env.failed) == len(sc["failed_results"])
    assert env.results == []


def test_build_envelope_for_map_uses_nodes(load_fixture):
    from tavily_cli.render import build_envelope

    sc = load_fixture("out_tavily-map_sample.json")["result"]["structuredContent"]
    env = build_envelope("tavily-map", sc, meta=dict(META))
    assert env.query == sc["base_url"]
    assert env.nodes == sc["results"]


def test_build_envelope_normalizes_bare_string_nodes():
    """实测：tavily-map 的 results 是裸 URL 字符串（存下来的 fixture 恰好是空数组，证不了形状）。"""

    from tavily_cli.render import build_envelope

    env = build_envelope("tavily-map", {"base_url": "https://a", "results": ["https://a/x"]}, meta=dict(META))
    assert env.nodes == [{"url": "https://a/x"}], "内部模型必须是记录，渲染层才不必各自判类型"
    assert json.loads(render(env, "json"))["节点"] == [{"网址": "https://a/x"}]
    assert json.loads(render(env, "json", lang="en"))["nodes"] == [{"url": "https://a/x"}]


def test_build_envelope_for_tools_list(server_tools):
    from tavily_cli.render import build_envelope

    env = build_envelope("tools/list", {"tools": server_tools}, meta=dict(META))
    assert [row["name"] for row in env.results] == [t["name"] for t in server_tools]


def test_build_envelope_on_error_keeps_empty_arrays():
    from tavily_cli.render import build_envelope

    env = build_envelope(
        "tavily-search", None, meta=dict(META), ok=False, query="x", error={"kind": "POOL_DEAD", "message": "m", "hint": "h"}
    )
    doc = json.loads(render(env, "json"))
    assert doc["结果"] == [] and doc["错误"]["类别"] == "密钥池已死亡"


# ------------------------------------------------------------------ 映射表单点


@pytest.mark.parametrize("section", sorted(KEY_MAP))
def test_every_section_maps_the_same_fields_in_both_languages(section):
    table = KEY_MAP[section]
    pairs = list(table.values())
    assert all(zh and en for zh, en in pairs)
    assert len({zh for zh, _ in pairs}) == len(pairs)
    assert len({en for _, en in pairs}) == len(pairs)


def test_envelope_section_covers_every_dataclass_field():
    from dataclasses import fields

    declared = {f.name for f in fields(Envelope)} - {"raw"}
    assert declared == set(KEY_MAP["envelope"])


def test_field_sections_only_reference_known_sections():
    assert set(FIELD_SECTIONS.values()) <= set(KEY_MAP)


# ------------------------------------------------------------------ 宽度函数


@pytest.mark.parametrize(
    ("text", "expected"),
    [("abc", 3), ("中", 2), ("中文", 4), ("中a文b", 6), ("…", 1), ("，", 2), ("ｆｕｌｌ", 8)],
)
def test_display_width(text, expected):
    assert display_width(text) == expected


# ------------------------------------------------------------------ 着色（M2）


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.mark.parametrize("fmt", ["json", "ndjson", "raw"])
def test_machine_readable_formats_never_carry_ansi(fmt):
    """机读格式是 agent 的消费面，任何情况下都不掺转义序列。"""

    assert "\x1b" not in render(search_env(), fmt, isatty=True, lang="zh", width=120, color=True)


@pytest.mark.parametrize("fmt", ["table", "md"])
def test_colour_only_when_asked_and_never_moves_a_column(fmt):
    plain = render(search_env(), fmt, isatty=True, lang="zh", width=120)
    painted = render(search_env(), fmt, isatty=True, lang="zh", width=120, color=True)
    assert "\x1b" not in plain, "默认（非 TTY 或未开启）必须干净"
    assert "\x1b" in painted
    assert strip_ansi(painted) == plain, "着色只加转义，不得改动一个字符、一个空格"


def test_coloured_cjk_table_stays_aligned(load_fixture):
    raw = load_fixture("search_latest.json")["result"]["structuredContent"]
    env = Envelope(ok=True, tool="tavily-search", query=raw["query"], results=raw["results"], meta=dict(META), raw=raw)
    lines = [strip_ansi(line) for line in render(env, "table", width=100, color=True).splitlines() if "|" in line]
    assert len({display_width(line) for line in lines}) == 1, lines


def test_doctor_status_is_colour_coded():
    env = Envelope(
        ok=False,
        tool="doctor",
        results=[
            {"name": "TCP 连接", "status": "可达", "detail": "h:1", "elapsed_ms": 1},
            {"name": "MCP 握手", "status": "成功", "detail": "s", "elapsed_ms": 2},
            {"name": "tools/list schema", "status": "失败", "detail": "boom", "elapsed_ms": 3},
            {"name": "最小搜索", "status": "跳过", "detail": "上一层已失败，未执行", "elapsed_ms": None},
        ],
        error={"kind": "TRANSPORT", "message": "boom", "hint": ""},
        meta=dict(META),
    )
    lines = render(env, "table", isatty=True, width=120, color=True).splitlines()
    assert "\x1b[32m" in lines[0] and "\x1b[32m" in lines[1], "通过项绿色"
    assert "\x1b[31m" in lines[2], "失败项红色"
    assert "\x1b[33m" in lines[3], "跳过项黄色"


def test_failed_and_error_blocks_use_red():
    env = Envelope(
        ok=True,
        tool="tavily-extract",
        query="https://a",
        pages=[{"url": "https://a", "title": "甲", "raw_content": "x" * 10}],
        failed=[{"url": "https://不存在.invalid", "error": "404"}],
        meta=dict(META),
    )
    painted = render(env, "table", isatty=True, width=120, color=True)
    assert any("\x1b[31m" in line and "404" in strip_ansi(line) for line in painted.splitlines())

    err = Envelope(
        ok=False, tool="tavily-search", query="x", error={"kind": "POOL_DEAD", "message": "m", "hint": "h"}, meta=dict(META)
    )
    for fmt in ("table", "md"):
        lines = render(err, fmt, isatty=True, width=120, color=True).splitlines()
        assert any("\x1b[31m" in line and "密钥池已死亡" in strip_ansi(line) for line in lines), fmt
