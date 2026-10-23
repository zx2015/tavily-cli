"""契约：真实上游最小成功调用（**消耗共享配额**）。

默认 skip，需要两道闸门同时打开：
    TAVILY_CONTRACT_QUOTA=1 .venv/bin/python -m pytest tests/ -q -m network
`tavily-crawl` / `tavily-map` 额外要 `TAVILY_CONTRACT_HEAVY=1`（一次 crawl 会抓多页，配额开销最大）。
上游调用次数是这里的设计目标之一：search/extract 各 **1 次**，由 module 级 fixture 共享给所有断言；
中文/英文同构性复用同一份响应，绝不为了断言再查一次。
"""

from __future__ import annotations

import json
import os

import pytest

from tavily_cli.render import FIELD_SECTIONS, KEY_MAP, build_envelope, render

SEARCH_QUERY = "Tavily API pricing"
EXTRACT_URL = "https://example.com"
# crawl/map 的目标必须**可爬**：example.com 实测返回 0 页，用它做闸门等于什么都没断。
CRAWL_URL = "https://docs.tavily.com"


def _meta(client, result) -> dict:
    structured = result.structured or {}
    return {
        "endpoint": client.session.endpoint,
        "request_id": structured.get("request_id"),
        "response_time": structured.get("response_time"),
        "elapsed_ms": result.elapsed_ms,
        "server_version": client.session.server_version,
    }


def _env_json(env, lang: str) -> dict:
    return json.loads(render(env, "json", lang=lang))


@pytest.fixture(scope="module")
def live_search(client, quota):
    quota.append("tavily-search")
    return client.call("tavily-search", {"query": SEARCH_QUERY, "max_results": 1, "search_depth": "basic"})


@pytest.fixture(scope="module")
def live_extract(client, quota):
    quota.append("tavily-extract")
    return client.call("tavily-extract", {"urls": [EXTRACT_URL], "extract_depth": "basic"})


def test_search_returns_the_documented_structured_fields(live_search):
    assert not live_search.is_error, live_search.text
    assert live_search.structured is not None, "structuredContent 缺失意味着 -f json 无键可渲染"
    # requirements §5.1：这些键必须存在（值可以为 null / 空）
    assert {"query", "results", "response_time", "request_id"} <= set(live_search.structured)
    assert len(live_search.structured["results"]) <= 1
    first = live_search.structured["results"][0]
    assert {"url", "title", "content", "score"} <= set(first), f"结果条目字段漂移：{sorted(first)}"
    assert first["url"].startswith(("http://", "https://"))
    assert isinstance(first["score"], (int, float))


def test_search_envelope_is_isomorphic_across_langs(client, live_search):
    """§9 用例 13 的**真机**版本：同一份线上响应，两套键名必须严格同构、取值相同。"""

    assert not live_search.is_error, live_search.text
    env = build_envelope(
        "tavily-search",
        live_search.structured,
        meta=_meta(client, live_search),
        query=SEARCH_QUERY,
        raw=live_search.structured,
    )
    zh = _env_json(env, "zh")
    en = _env_json(env, "en")

    assert _rename(zh, "zh") == en == _rename(en, "en")
    assert zh["成功"] is True and en["ok"] is True
    assert len(zh["结果"]) == len(en["results"]) == 1


def test_extract_returns_pages_and_failed_lists(live_extract):
    assert not live_extract.is_error, live_extract.text
    structured = live_extract.structured
    assert {"results", "failed_results", "response_time", "request_id"} <= set(structured)
    assert len(structured["results"]) + len(structured["failed_results"]) == 1, "每个 URL 必须恰好落在一侧"
    page = structured["results"][0]
    assert {"url", "title", "raw_content"} <= set(page), f"页面字段漂移：{sorted(page)}"
    assert page["url"] == EXTRACT_URL


def test_crawl_maps_pages_and_base_url(client, quota):
    """M2 的渲染前提：crawl 的 `results` 落进 `页面` 槽位，`base_url` 必须回显。

    目标是 **可爬** 站点：实测 `example.com` 返回 0 页（`isError=false`、`results=[]`），
    而旧断言只判 `页面` 是列表，于是"空载荷"也能让这道闸门变绿 —— 现在要求非空并逐条看字段。
    """

    if os.environ.get("TAVILY_CONTRACT_HEAVY") != "1":
        pytest.skip("crawl/map 一次会抓多页，需额外设 TAVILY_CONTRACT_HEAVY=1")

    quota.append("tavily-crawl")
    result = client.call("tavily-crawl", {"url": CRAWL_URL, "max_depth": 1, "max_breadth": 2, "limit": 2})
    assert not result.is_error, result.text
    assert {"base_url", "results", "response_time", "request_id"} <= set(result.structured)
    assert result.structured["base_url"] == CRAWL_URL
    pages = result.structured["results"]
    assert pages, f"爬到了空集合，闸门失去意义（{result.text[:200]}）"
    for page in pages:
        assert isinstance(page, dict), f"页面条目不是对象：{page!r}"
        assert {"url", "raw_content"} <= set(page), f"页面字段漂移：{sorted(page)}"

    env = build_envelope("tavily-crawl", result.structured, meta=_meta(client, result))
    doc = _env_json(env, "zh")
    assert doc["工具"] == "tavily-crawl"
    assert len(doc["页面"]) == len(pages)
    for fmt in ("table", "md"):  # 渲染崩过一次的现场：缺 title 的页面必须还能排版
        assert render(env, fmt, isatty=True, width=100)


def test_map_returns_nodes(client, quota):
    """M2 的渲染前提：map 的 `results` 落进 `节点` 槽位。

    实测（2026-10-23）：服务端给的是**裸 URL 字符串数组**，不是 `{url,title}`；
    `build_envelope` 必须归一化成记录，否则 table/md 会 `AttributeError`。
    """

    if os.environ.get("TAVILY_CONTRACT_HEAVY") != "1":
        pytest.skip("map 会枚举整站，需额外设 TAVILY_CONTRACT_HEAVY=1")

    quota.append("tavily-map")
    result = client.call("tavily-map", {"url": CRAWL_URL, "max_depth": 1, "limit": 5})
    assert not result.is_error, result.text
    assert {"base_url", "results", "response_time", "request_id"} <= set(result.structured)
    assert result.structured["base_url"] == CRAWL_URL
    raw_nodes = result.structured["results"]
    assert raw_nodes, "map 返回空数组，断不出节点形状"
    assert len(raw_nodes) <= 5

    env = build_envelope("tavily-map", result.structured, meta=_meta(client, result))
    assert all(isinstance(node, dict) and node.get("url") for node in env.nodes), env.nodes
    doc = _env_json(env, "zh")
    assert len(doc["节点"]) == len(raw_nodes)
    for node in doc["节点"]:
        assert node["网址"].startswith(("http://", "https://"))
        assert "标题" not in node, "服务端没给标题，不许凭空补"
    for fmt in ("table", "md"):
        assert render(env, fmt, isatty=True, width=100)


_INVERSE = {
    lang: {
        section: {names[0 if lang == "zh" else 1]: internal for internal, names in table.items()}
        for section, table in KEY_MAP.items()
    }
    for lang in ("zh", "en")
}


def _rename(value, lang: str, section: str = "envelope"):
    """按 KEY_MAP 把对外键名换回内部英文标识符，用于逐字节同构断言。"""

    if isinstance(value, list):
        return [_rename(item, lang, section) for item in value]
    if not isinstance(value, dict):
        return value
    table = _INVERSE[lang].get(section)
    if table is None:
        return value
    out = {}
    for key, sub in value.items():
        internal = table.get(key, key)
        out[internal] = _rename(sub, lang, FIELD_SECTIONS.get(internal, section))
    return out
