"""validate.py：校验闸门真值表（requirements §4.2/§4.3 + design §6）。"""

from __future__ import annotations

import pytest

from tavily_cli import validate


def errs(tool: str, args: dict) -> set[str]:
    return {e.param for e in validate.validate(tool, args).errors}


def test_minimal_valid_search_passes():
    report = validate.validate("tavily-search", {"query": "示例股份 半年报"})
    assert report.ok, report.errors
    assert report.sanitize({"query": "示例股份 半年报"}) == {"query": "示例股份 半年报"}


def test_unknown_tool_is_rejected():
    report = validate.validate("tavily-nope", {"query": "x"})
    assert not report.ok
    assert "<tool>" in errs("tavily-nope", {"query": "x"})
    assert report.errors[0].message.startswith("未知工具")


def test_missing_required_query():
    assert errs("tavily-search", {}) == {"query"}


@pytest.mark.parametrize(
    "query",
    ["", "   ", "x" * 513, "带\n换行", "控制\x01字符", "尾部空白\x07"],
)
def test_query_shape(query):
    assert "query" in errs("tavily-search", {"query": query}), query


def test_query_at_512_chars_is_allowed():
    assert validate.validate("tavily-search", {"query": "x" * 512}).ok


@pytest.mark.parametrize(
    "bad",
    ["!!bad", "tavily", "http://tavily.com", "tavily.com/path", "a.com,b.com", "bad port.com:80"],
)
def test_include_domains_rejects_polluting_input(bad):
    """事故回归：这些值一旦出网会把共享 Key 池打进 ERROR 终态。"""

    report = validate.validate("tavily-search", {"query": "x", "include_domains": [bad]})
    assert not report.ok
    assert "include_domains" in errs("tavily-search", {"query": "x", "include_domains": [bad]})
    assert "后缀" in report.errors[0].message or "." in report.errors[0].hint


def test_exclude_domains_same_rule():
    assert "exclude_domains" in errs(
        "tavily-search", {"query": "x", "exclude_domains": ["!!bad"]}
    )


def test_domains_uppercase_ok_but_not_rewritten():
    args = {"query": "x", "include_domains": ["Example.COM"]}
    report = validate.validate("tavily-search", args)
    assert report.ok, report.errors
    assert report.sanitize(args)["include_domains"] == ["Example.COM"]


@pytest.mark.parametrize("depth", ["bogus", "Basic", "BASIC", "", "ultra"])
def test_search_depth_enum_lists_allowed_values(depth):
    report = validate.validate("tavily-search", {"query": "x", "search_depth": depth})
    assert not report.ok
    assert "basic" in report.errors[0].message
    assert "advanced" in report.errors[0].message


def test_search_depth_valid_values_pass():
    for depth in ["basic", "advanced"]:
        assert validate.validate("tavily-search", {"query": "x", "search_depth": depth}).ok


@pytest.mark.parametrize("topic", ["general", "news", "finance"])
def test_topic_valid(topic):
    assert validate.validate("tavily-search", {"query": "x", "topic": topic}).ok


def test_topic_invalid():
    assert "topic" in errs("tavily-search", {"query": "x", "topic": "crypto"})


@pytest.mark.parametrize("rng", ["day", "week", "month", "year"])
def test_time_range_valid(rng):
    assert validate.validate("tavily-search", {"query": "x", "time_range": rng}).ok


def test_time_range_invalid():
    assert "time_range" in errs("tavily-search", {"query": "x", "time_range": "decade"})


@pytest.mark.parametrize("n", [0, -1, 21, 100])
def test_max_results_out_of_range(n):
    assert "max_results" in errs("tavily-search", {"query": "x", "max_results": n})


@pytest.mark.parametrize("n", [1, 5, 20])
def test_max_results_in_range(n):
    assert validate.validate("tavily-search", {"query": "x", "max_results": n}).ok


@pytest.mark.parametrize("value", ["5", 1.5, True])
def test_max_results_wrong_type(value):
    assert "max_results" in errs("tavily-search", {"query": "x", "max_results": value})


@pytest.mark.parametrize("tool", ["tavily-search", "tavily-extract", "tavily-crawl", "tavily-map"])
def test_timeout_is_no_longer_a_server_param(tool):
    """4.1.3 起 timeout 由服务端 Depends 注入，客户端再发就是未声明键。"""

    args = {"tavily-search": {"query": "x"}, "tavily-extract": {"urls": ["https://a.com"]},
            "tavily-crawl": {"url": "https://a.com"}, "tavily-map": {"url": "https://a.com"}}[tool]
    args["timeout"] = 5.0
    assert "timeout" in errs(tool, args)


def test_days_without_news_is_warning_and_dropped():
    report = validate.validate("tavily-search", {"query": "x", "days": 7})
    assert report.ok
    assert not report.warnings == []
    assert "days" in report.dropped
    assert report.sanitize({"query": "x", "days": 7}) == {"query": "x"}


def test_days_with_news_kept():
    args = {"query": "x", "topic": "news", "days": 7}
    report = validate.validate("tavily-search", args)
    assert report.ok
    assert report.dropped == ()
    assert report.sanitize(args) == args


@pytest.mark.parametrize("n", [0, 366, -5])
def test_days_out_of_range(n):
    assert "days" in errs("tavily-search", {"query": "x", "topic": "news", "days": n})


def test_undeclared_key_blocked():
    """additionalProperties:false：未声明键会被 FastMCP 拒绝，必须本地拦下。"""

    report = validate.validate("tavily-search", {"query": "x", "bogus": 1})
    assert not report.ok
    assert "bogus" in errs("tavily-search", {"query": "x", "bogus": 1})
    assert "未声明" in report.errors[0].message


def test_null_valued_key_blocked():
    """省略 ≠ 传 null：值为 null 的可选键一律不得发出。"""

    assert "include_domains" in errs(
        "tavily-search", {"query": "x", "include_domains": None}
    )


def test_extract_urls_valid_including_idn():
    """§9 用例 5：不存在的中文域名也要通过本地校验，由服务端返回 failed_results。"""

    args = {"urls": ["https://example.com", "https://不存在.invalid"]}
    assert validate.validate("tavily-extract", args).ok


@pytest.mark.parametrize(
    "bad",
    ["example.com", "ftp://example.com", "", "https://", "not a url", "javascript:alert(1)"],
)
def test_extract_urls_rejects_non_http(bad):
    assert "urls" in errs("tavily-extract", {"urls": [bad]})


def test_extract_urls_count_bounds():
    assert "urls" in errs("tavily-extract", {"urls": []})
    assert "urls" in errs("tavily-extract", {"urls": ["https://a.com"] * 21})
    assert validate.validate("tavily-extract", {"urls": ["https://a.com"] * 20}).ok


def test_extract_depth_enum():
    assert "extract_depth" in errs("tavily-extract", {"urls": ["https://a.com"], "extract_depth": "deep"})


def test_crawl_url_must_be_http_url():
    assert "url" in errs("tavily-crawl", {"url": "docs.foo.com"})
    assert validate.validate("tavily-crawl", {"url": "https://docs.foo.com"}).ok


def test_select_paths_must_compile():
    args = {"url": "https://docs.foo.com", "select_paths": ["(("]}
    assert "select_paths" in errs("tavily-map", args) | errs("tavily-crawl", args)
    assert validate.validate("tavily-map", {"url": "https://a.com", "select_paths": ["^/docs"]}).ok


@pytest.mark.parametrize(
    "tool,args",
    [
        ("tavily-crawl", {"url": "https://a.com", "max_depth": -1}),
        ("tavily-crawl", {"url": "https://a.com", "max_breadth": 0}),
        ("tavily-crawl", {"url": "https://a.com", "limit": 0}),
        ("tavily-map", {"url": "https://a.com", "max_depth": -1}),
        ("tavily-map", {"url": "https://a.com", "limit": -5}),
    ],
)
def test_crawl_and_map_counters_must_be_non_negative(tool, args):
    """0 页 / 负层深对上游没有意义，却照样要打一次 Tavily：本地拦住，省下一次共享配额。"""

    assert set(args) - {"url"} <= errs(tool, args)


def test_zero_depth_is_legal():
    """只抓起点页是合法意图，不能把 0 当成"没给"。"""

    assert validate.validate("tavily-crawl", {"url": "https://a.com", "max_depth": 0}).ok
    assert validate.validate("tavily-map", {"url": "https://a.com", "max_depth": 0}).ok


def test_instructions_is_plain_string_not_regex():
    """服务端 instructions 是 string（自然语言指引），不做正则编译。"""

    args = {"url": "https://a.com", "instructions": "只要财经页面 ( ("}
    assert validate.validate("tavily-crawl", args).ok


def test_boolean_flags_must_be_bool():
    assert "include_answer" in errs("tavily-search", {"query": "x", "include_answer": "yes"})


def test_report_field_error_carries_hint():
    report = validate.validate("tavily-search", {"query": "x", "include_domains": ["!!bad"]})
    error = report.errors[0]
    assert error.param == "include_domains"
    assert error.value == ["!!bad"]
    assert error.hint
