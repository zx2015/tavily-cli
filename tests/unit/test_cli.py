"""cli 装配：argv → 校验 → 传输 → 分类 → 渲染 → 退出码（§9 可离线验证的用例）。"""

from __future__ import annotations

import json
import urllib.error

import pytest

from mcp_stub import FakeOpener, ok_call, plain, run

def search_structured(load_fixture) -> dict:
    return load_fixture("search_latest.json")["result"]["structuredContent"]


# ------------------------------------------------------------------ dry-run


def test_dry_run_sends_nothing_and_has_no_null_arguments(load_fixture, capsys):
    fake = FakeOpener(call=ok_call(search_structured(load_fixture)))
    code = run(["search", "Tavily", "--dry-run"], opener=fake)
    assert code == 0
    assert fake.requests == []
    request = json.loads(capsys.readouterr().out)
    assert request["method"] == "tools/call"
    assert request["params"]["name"] == "tavily-search"
    assert request["params"]["arguments"] == {"query": "Tavily"}


def test_dry_run_includes_explicit_options_only(capsys):
    run(["search", "x", "--depth", "advanced", "--max-results", "3", "--include-answer", "--dry-run"])
    arguments = json.loads(capsys.readouterr().out)["params"]["arguments"]
    assert arguments == {"query": "x", "search_depth": "advanced", "max_results": 3, "include_answer": True}


def test_dry_run_rejects_bad_input_before_network(capsys):
    fake = FakeOpener(call=ok_call({"results": []}))
    assert run(["search", "x", "--include-domain", "!!bad", "--dry-run"], opener=fake) == 2
    assert fake.requests == []


# ------------------------------------------------------------------ 请求级超时（4.1.3 起只作用于本地）


def test_request_timeout_is_the_local_read_timeout(load_fixture):
    """4.1.3 服务端删掉了 `timeout` 入参：本选项只改本次调用的客户端 HTTP 读超时。"""

    fake = FakeOpener(call=ok_call(search_structured(load_fixture)))
    assert run(["search", "x", "--request-timeout", "7", "-f", "json"], opener=fake) == 0
    assert fake.timeouts == [7.0, 7.0, 7.0], fake.timeouts
    assert "timeout" not in fake.arguments_at(2)


def test_request_timeout_absent_keeps_global_timeout(load_fixture):
    fake = FakeOpener(call=ok_call(search_structured(load_fixture)))
    assert run(["search", "x", "-f", "json"], opener=fake) == 0
    assert set(fake.timeouts) == {45.0}


def test_global_timeout_still_applies(load_fixture):
    fake = FakeOpener(call=ok_call(search_structured(load_fixture)))
    assert run(["search", "x", "--timeout", "12", "-f", "json"], opener=fake) == 0
    assert set(fake.timeouts) == {12.0}


def test_request_timeout_out_of_range_is_usage_error(capsys):
    fake = FakeOpener()
    assert run(["search", "x", "--request-timeout", "0.5"], opener=fake) == 2
    assert fake.requests == []
    err = capsys.readouterr().err
    assert "--request-timeout" in err and "1.0" in err and "60.0" in err


# ------------------------------------------------------------------ 成功路径


def test_search_success_json_envelope(load_fixture, capsys):
    structured = search_structured(load_fixture)
    fake = FakeOpener(call=ok_call(structured))
    assert run(["search", "示例", "-f", "json"], opener=fake) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["成功"] is True
    assert len(doc["结果"]) == len(structured["results"])
    assert doc["元信息"]["请求编号"] == structured["request_id"]
    assert doc["元信息"]["服务端版本"] == "4.1.0"
    assert fake.methods == ["initialize", "notifications/initialized", "tools/call"]


def test_search_uses_table_when_tty(load_fixture, capsys):
    fake = FakeOpener(call=ok_call(search_structured(load_fixture)))
    assert run(["search", "示例"], opener=fake, isatty=True) == 0
    out = capsys.readouterr().out
    assert "评分" in out.splitlines()[0]
    assert not out.lstrip().startswith("{")


def test_keys_en_end_to_end(load_fixture, capsys):
    structured = search_structured(load_fixture)
    run(["search", "示例", "-f", "json", "--keys-en"], opener=FakeOpener(call=ok_call(structured)))
    en = json.loads(capsys.readouterr().out)
    assert en["ok"] is True and en["results"][0]["url"] == structured["results"][0]["url"]


def test_raw_format_passes_server_payload_through(load_fixture, capsys):
    structured = search_structured(load_fixture)
    run(["search", "示例", "-f", "raw"], opener=FakeOpener(call=ok_call(structured)))
    assert json.loads(capsys.readouterr().out) == structured


def test_empty_result_is_success(capsys):
    fake = FakeOpener(call=ok_call({"query": "zzz", "results": [], "request_id": "r1", "response_time": 0.5}))
    assert run(["search", "zzz", "-f", "json"], opener=fake) == 0
    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    assert doc["成功"] is True and doc["结果"] == []
    assert "无结果" in captured.err


def test_extract_keeps_failed_pages(load_fixture, capsys):
    sc = load_fixture("out_tavily-extract_sample.json")["result"]["structuredContent"]
    fake = FakeOpener(call=ok_call(sc))
    argv = ["extract", "https://example.com", "https://不存在.invalid", "-f", "json"]
    assert run(argv, opener=fake) == 0
    doc = json.loads(capsys.readouterr().out)
    assert len(doc["页面"]) == 1
    assert len(doc["失败"]) == 1
    assert fake.arguments_at(len(fake.requests) - 1)["urls"] == ["https://example.com", "https://不存在.invalid"]


def test_output_flag_writes_file(tmp_path, capsys):
    target = tmp_path / "out.json"
    fake = FakeOpener(call=ok_call({"query": "x", "results": [{"url": "https://a"}], "request_id": "r"}))
    assert run(["search", "x", "-f", "json", "-o", str(target)], opener=fake) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["成功"] is True
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------------ 失败路径


def test_pool_dead_maps_to_six(load_fixture, capsys):
    fake = FakeOpener(call=ok_call({"error": "Error calling tool 'tavily-search': No active API keys available in the pool."}, is_error=True))
    assert run(["search", "x", "-f", "json"], opener=fake) == 6
    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    assert doc["成功"] is False
    assert doc["错误"]["类别"] == "密钥池已死亡"
    assert "docker restart mcp-tavily" in captured.err
    assert fake.methods.count("tools/call") == 1, "池死亡绝不重试"


def test_tool_error_maps_to_five(capsys):
    fake = FakeOpener(call=ok_call({"error": "Something odd"}, is_error=True))
    assert run(["search", "x"], opener=fake) == 5
    assert "工具执行失败" in capsys.readouterr().err


def test_transport_failure_maps_to_three_and_mentions_tunnel(capsys):
    fake = FakeOpener(errors=[urllib.error.URLError("connection refused"), urllib.error.URLError("connection refused")])
    assert run(["search", "x", "--tunnel", "off", "-f", "json"], opener=fake) == 3
    captured = capsys.readouterr()
    assert "--tunnel" in captured.err
    assert json.loads(captured.out)["错误"]["类别"] == "网络不可达"


def test_transport_failure_retries_only_transport(capsys, monkeypatch):
    from tavily_cli import cli

    slept: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", slept.append)
    fake = FakeOpener(
        call=ok_call({"query": "x", "results": [{"url": "https://a"}], "request_id": "r"}),
        errors=[urllib.error.URLError("connection refused")],
    )
    assert run(["search", "x", "--retries", "1", "-f", "json"], opener=fake) == 0
    assert slept and slept[0] < 1.0
    assert fake.methods.count("initialize") == 2


def test_timeout_maps_to_seven(capsys):
    fake = FakeOpener(call=ok_call({"error": "Request timed out after 45 seconds"}, is_error=True))
    assert run(["search", "x"], opener=fake) == 7
    assert "--timeout" in capsys.readouterr().err


# ------------------------------------------------------------------ M2：crawl / map

MAP_STRUCTURED = {
    # 实测（2026-10-23，docs.tavily.com --limit 5）：tavily-map 的 results 是**裸 URL 字符串**，不是 {url,title}。
    "base_url": "https://example.com",
    "results": ["https://example.com/a", "https://example.com/b"],
    "response_time": 1.2,
    "request_id": "r-map",
}
CRAWL_STRUCTURED = {
    "base_url": "https://example.com",
    "results": [
        {"url": "https://example.com/a", "title": "页面 A", "raw_content": "x" * 120},
        {"url": "https://example.com/b", "title": "页面 B", "raw_content": "y" * 30},
    ],
    "response_time": 3.4,
    "request_id": "r-crawl",
}


def test_crawl_dry_run_sends_only_explicit_options(capsys):
    argv = [
        "crawl", "https://docs.example.com", "--max-depth", "2", "--max-breadth", "10",
        "--limit", "20", "--select-path", "^/api", "--select-path", "^/guides",
        "--exclude-path", "/tag/", "--instructions", "只取接口文档", "--allow-external", "--dry-run",
    ]
    assert run(argv) == 0
    request = json.loads(capsys.readouterr().out)
    assert request["params"]["name"] == "tavily-crawl"
    assert request["params"]["arguments"] == {
        "url": "https://docs.example.com",
        "max_depth": 2,
        "max_breadth": 10,
        "limit": 20,
        "select_paths": ["^/api", "^/guides"],
        "exclude_paths": ["/tag/"],
        "instructions": "只取接口文档",
        "allow_external": True,
    }


def test_map_dry_run_omits_untouched_options(capsys):
    assert run(["map", "https://docs.example.com", "--limit", "50", "--dry-run"]) == 0
    request = json.loads(capsys.readouterr().out)
    assert request["params"]["name"] == "tavily-map"
    assert request["params"]["arguments"] == {"url": "https://docs.example.com", "limit": 50}


def test_crawl_success_renders_pages(load_fixture, capsys):
    sample = load_fixture("out_tavily-crawl_sample.json")["result"]["structuredContent"]
    structured = {**sample, "results": CRAWL_STRUCTURED["results"]}
    fake = FakeOpener(call=ok_call(structured))
    assert run(["crawl", "https://example.com", "-f", "json"], opener=fake) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["工具"] == "tavily-crawl"
    assert [p["网址"] for p in doc["页面"]] == ["https://example.com/a", "https://example.com/b"]
    assert doc["查询"] == structured["base_url"], "crawl 没有 query，信封回落到 base_url"
    assert doc["元信息"]["请求编号"] == structured["request_id"]


def test_map_success_renders_nodes(capsys):
    assert run(["map", "https://example.com", "-f", "json"], opener=FakeOpener(call=ok_call(MAP_STRUCTURED))) == 0
    doc = json.loads(capsys.readouterr().out)
    assert len(doc["节点"]) == 2
    assert doc["节点"][0] == {"网址": "https://example.com/a"}
    assert "标题" not in doc["节点"][0], "服务端只给 URL，不许编造标题"


def test_map_nodes_keep_titles_when_the_server_provides_them(capsys):
    """裸字符串与 {url,title} 混着返回时，两者都不能崩，且标题照常翻译。"""

    mixed = {**MAP_STRUCTURED, "results": ["https://example.com/a", {"url": "https://example.com/b", "title": "B"}]}
    assert run(["map", "https://example.com", "-f", "json"], opener=FakeOpener(call=ok_call(mixed))) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["节点"] == [{"网址": "https://example.com/a"}, {"网址": "https://example.com/b", "标题": "B"}]


def test_crawl_empty_result_is_success(capsys):
    empty = {**MAP_STRUCTURED, "results": []}
    fake = FakeOpener(call=ok_call(empty))
    assert run(["crawl", "https://example.com", "-f", "json"], opener=fake) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["页面"] == []
    assert "无结果" in captured.err


def test_crawl_table_lists_pages_with_char_count(capsys):
    fake = FakeOpener(call=ok_call(CRAWL_STRUCTURED))
    assert run(["crawl", "https://example.com"], opener=fake, isatty=True) == 0
    out = capsys.readouterr().out
    assert "原文" in out.splitlines()[0]
    assert "共 2 页" in out


def test_map_table_counts_nodes(capsys):
    assert run(["map", "https://example.com"], opener=FakeOpener(call=ok_call(MAP_STRUCTURED)), isatty=True) == 0
    out = plain(capsys.readouterr().out)
    header = out.splitlines()[0].split()
    assert header == ["序号", "|", "网址"], "标题列全空时应按其他块一样整列删掉"
    assert "共 2 节点" in out


def test_map_md_and_ndjson_survive_bare_string_nodes(capsys):
    assert run(["map", "https://example.com", "-f", "md"], opener=FakeOpener(call=ok_call(MAP_STRUCTURED))) == 0
    assert "https://example.com/a" in capsys.readouterr().out
    assert run(["map", "https://example.com", "-f", "ndjson"], opener=FakeOpener(call=ok_call(MAP_STRUCTURED))) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["网址"] for line in lines] == ["https://example.com/a", "https://example.com/b"]


def test_crawl_table_drops_the_title_column_when_the_server_gives_no_titles(capsys):
    """实测（2026-10-23，crawl docs.tavily.com）：页面只有 url + raw_content，标题列必须整列消失。"""

    no_title = {**CRAWL_STRUCTURED, "results": [{"url": "https://example.com/a", "raw_content": "x" * 50}]}
    assert run(["crawl", "https://example.com"], opener=FakeOpener(call=ok_call(no_title)), isatty=True) == 0
    out = plain(capsys.readouterr().out)
    assert out.splitlines()[0].split() == ["序号", "|", "网址", "|", "原文"]


def test_crawl_and_map_default_to_the_long_timeout(capsys):
    """§4.5：crawl/map 实测显著更久，默认 120s 而不是 45s。"""

    for argv, structured in ((["crawl", "https://example.com"], CRAWL_STRUCTURED), (["map", "https://example.com"], MAP_STRUCTURED)):
        fake = FakeOpener(call=ok_call(structured))
        assert run(argv + ["-f", "json"], opener=fake) == 0, argv
        assert set(fake.timeouts) == {120.0}, argv


def test_explicit_timeout_overrides_the_command_default():
    fake = FakeOpener(call=ok_call(MAP_STRUCTURED))
    assert run(["map", "https://example.com", "--timeout", "30", "-f", "json"], opener=fake) == 0
    assert set(fake.timeouts) == {30.0}


def test_timeout_before_subcommand_still_wins():
    """§4 陷阱：子命令之前的全局选项不得被命令默认值（120）覆盖回去。"""

    fake = FakeOpener(call=ok_call(MAP_STRUCTURED))
    assert run(["--timeout", "30", "map", "https://example.com", "-f", "json"], opener=fake) == 0
    assert set(fake.timeouts) == {30.0}


# ------------------------------------------------------------------ 隧道降级（--tunnel）

LAN = "http://203.0.113.10:18000/mcp"
LOCAL = "http://127.0.0.1:18000/mcp"


class HostRouter:
    """按请求 URL 的主机名分流：直连口一路、隧道口另一路。"""

    def __init__(self, **by_host):
        self.by_host = by_host

    def __call__(self, request, timeout=None):
        host = request.full_url.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]
        return self.by_host[host](request, timeout=timeout)


def _stub_tunnel(monkeypatch, endpoint=LOCAL, error=None):
    from tavily_cli import cli

    seen: list[str] = []

    def fake_ensure(current, ssh_host, **kwargs):
        seen.append(current)
        if error is not None:
            raise error
        return endpoint

    monkeypatch.setattr(cli, "ensure_tunnel", fake_ensure)
    return seen


def test_auto_tunnel_falls_back_after_transport_failure(monkeypatch, capsys):
    seen = _stub_tunnel(monkeypatch)
    direct = FakeOpener(errors=[urllib.error.URLError("No route to host")] * 3)
    tunnelled = FakeOpener(call=ok_call(MAP_STRUCTURED))
    argv = ["map", "https://example.com", "--endpoint", LAN, "-f", "json"]
    assert run(argv, opener=HostRouter(**{"203.0.113.10": direct, "127.0.0.1": tunnelled})) == 0
    assert seen == [LAN]
    assert tunnelled.methods == ["initialize", "notifications/initialized", "tools/call"]
    captured = capsys.readouterr()
    assert "已降级走 SSH 隧道" in captured.err
    assert json.loads(captured.out)["元信息"]["端点"] == LOCAL


def test_tunnel_off_never_touches_ssh(monkeypatch, capsys):
    seen = _stub_tunnel(monkeypatch)
    direct = FakeOpener(errors=[urllib.error.URLError("No route to host")] * 2)
    argv = ["map", "https://example.com", "--endpoint", LAN, "--tunnel", "off", "-f", "json"]
    assert run(argv, opener=direct) == 3
    assert seen == []
    assert "--tunnel" in capsys.readouterr().err


def test_tunnel_on_skips_the_direct_attempt(monkeypatch):
    seen = _stub_tunnel(monkeypatch)
    direct = FakeOpener(errors=[urllib.error.URLError("不该被用到")] * 3)
    tunnelled = FakeOpener(call=ok_call(MAP_STRUCTURED))
    argv = ["map", "https://example.com", "--endpoint", LAN, "--tunnel", "on", "-f", "json"]
    assert run(argv, opener=HostRouter(**{"203.0.113.10": direct, "127.0.0.1": tunnelled})) == 0
    assert seen == [LAN]
    assert direct.requests == []


def test_tunnel_on_applies_to_tools(monkeypatch, capsys):
    seen = _stub_tunnel(monkeypatch)
    tunnelled = FakeOpener()
    direct = FakeOpener(errors=[urllib.error.URLError("不该被用到")] * 3)
    argv = ["tools", "--endpoint", LAN, "--tunnel", "on", "-f", "json"]
    assert run(argv, opener=HostRouter(**{"203.0.113.10": direct, "127.0.0.1": tunnelled})) == 0
    assert seen == [LAN]
    assert json.loads(capsys.readouterr().out)["元信息"]["端点"] == LOCAL


def test_tunnel_on_applies_to_doctor(monkeypatch, capsys):
    seen = _stub_tunnel(monkeypatch)
    tunnelled = FakeOpener(call=ok_call({"results": [{"url": "u", "title": "t", "content": "c"}]}))
    argv = ["doctor", "--endpoint", LAN, "--tunnel", "on", "-f", "json"]
    assert run(argv, opener=HostRouter(**{"127.0.0.1": tunnelled}), tcp_probe=lambda *a, **k: None) == 0
    assert seen == [LAN]
    assert "已按 --tunnel on 走 SSH 隧道" in capsys.readouterr().err


def test_tools_transport_failure_maps_to_three_without_traceback(monkeypatch, capsys):
    _stub_tunnel(monkeypatch, error=AssertionError("auto 不该在 tools 之外自行 spawn"))
    fake = FakeOpener(errors=[urllib.error.URLError("No route to host")] * 3)
    assert run(["tools", "--endpoint", LAN, "--tunnel", "off", "-f", "json"], opener=fake) == 3
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert json.loads(captured.out)["错误"]["类别"] == "网络不可达"


def test_tools_auto_falls_back_to_the_tunnel(monkeypatch, capsys):
    seen = _stub_tunnel(monkeypatch)
    direct = FakeOpener(errors=[urllib.error.HTTPError(LAN, 502, "Bad Gateway", {}, None)] * 3)
    tunnelled = FakeOpener()
    argv = ["tools", "--endpoint", LAN, "-f", "json"]
    assert run(argv, opener=HostRouter(**{"203.0.113.10": direct, "127.0.0.1": tunnelled})) == 0
    assert seen == [LAN]
    assert "已降级走 SSH 隧道" in capsys.readouterr().err


def test_doctor_does_not_spawn_ssh_by_itself(monkeypatch, capsys):
    from tavily_cli.tunnel import TunnelError

    seen = _stub_tunnel(monkeypatch, error=TunnelError("不该被调用"))
    fake = FakeOpener(errors=[urllib.error.URLError("No route to host")] * 3)
    argv = ["doctor", "--endpoint", LAN, "-f", "json"]
    assert run(argv, opener=fake, tcp_probe=lambda *a, **k: None) == 3
    assert seen == []


def test_dry_run_and_usage_errors_never_touch_ssh(monkeypatch, capsys):
    seen = _stub_tunnel(monkeypatch)
    assert run(["tools", "--endpoint", LAN, "--tunnel", "on", "--dry-run"], opener=FakeOpener()) == 0
    assert json.loads(capsys.readouterr().out)["method"] == "tools/list"
    assert run(["search", "x", "--endpoint", LAN, "--tunnel", "on", "--dry-run"], opener=FakeOpener()) == 0
    assert run(["search", "x", "--endpoint", LAN, "--tunnel", "on", "--include-domain", "!!bad"], opener=FakeOpener()) == 2
    assert seen == []


def test_pool_dead_does_not_trigger_the_tunnel(monkeypatch):
    from tavily_cli.tunnel import TunnelError

    seen = _stub_tunnel(monkeypatch, error=TunnelError("不该被调用"))
    fake = FakeOpener(call=ok_call({"error": "No active API keys available in the pool."}, is_error=True))
    assert run(["map", "https://example.com", "--endpoint", LAN, "-f", "json"], opener=fake) == 6
    assert seen == []


def test_tunnel_failure_still_reports_transport(monkeypatch, capsys):
    from tavily_cli.tunnel import TunnelError

    _stub_tunnel(monkeypatch, error=TunnelError("ssh 隧道建立失败（退出码 255）"))
    direct = FakeOpener(errors=[urllib.error.URLError("No route to host")] * 2)
    argv = ["map", "https://example.com", "--endpoint", LAN, "-f", "json"]
    assert run(argv, opener=direct) == 3
    err = capsys.readouterr().err
    assert "隧道" in err and "255" in err


def test_api_key_in_server_text_is_redacted(capsys):
    fake_key = "tvly-" + "Zx9qK2mLp7"
    fake = FakeOpener(call=ok_call({"error": f"invalid api key {fake_key}"}, is_error=True))
    assert run(["search", "x", "-f", "json"], opener=fake) == 5
    captured = capsys.readouterr()
    assert fake_key not in captured.out
    assert fake_key not in captured.err


def test_keyboard_interrupt_exits_130(capsys):
    fake = FakeOpener(errors=[KeyboardInterrupt()])
    assert run(["search", "x", "-f", "json"], opener=fake) == 130
    captured = capsys.readouterr()
    assert "已中断" in captured.err
    assert not captured.out.strip().startswith("{"), "中断不得留下半截 JSON"


# ------------------------------------------------------------------ tools / doctor


def test_tools_lists_names_and_schema_hash(server_tools, capsys):
    fake = FakeOpener(tools=server_tools)
    assert run(["tools", "-f", "json"], opener=fake) == 0
    doc = json.loads(capsys.readouterr().out)
    assert [row["名称"] for row in doc["结果"]] == [t["name"] for t in server_tools]
    assert doc["元信息"]["schema指纹"].startswith("sha256:")


def test_tools_warns_when_server_schema_drifts_from_builtin(capsys):
    drifted = [{"name": "tavily-search", "inputSchema": {"type": "object", "properties": {"newest": {"type": "string"}}}}]
    assert run(["tools", "-f", "json"], opener=FakeOpener(tools=drifted)) == 0
    assert "漂移" in capsys.readouterr().err


def test_doctor_reports_four_layers(capsys):
    fake = FakeOpener(call=ok_call({"query": "ping", "results": [{"url": "https://a"}], "request_id": "r"}))
    code = run(["doctor"], opener=fake, isatty=True, tcp_probe=lambda *a, **k: None)
    assert code == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 4, lines
    assert "TCP" in lines[0] and "握手" in lines[1] and "tools" in lines[2] and "搜索" in lines[3]


def test_doctor_fails_with_three_when_tcp_is_dead(capsys):
    fake = FakeOpener()
    code = run(["doctor"], opener=fake, tcp_probe=lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
    assert code == 3
    captured = capsys.readouterr()
    assert "不可达" in captured.out
    doc = json.loads(captured.out)
    assert "refused" in doc["错误"]["消息"], "§6：错误说明必须带上失败原因，不能只有状态词"
    assert "refused" in doc["结果"][0]["细节"]


# ------------------------------------------------------------------ 参数面与配置


def test_help_is_chinese_and_lists_every_search_option(capsys):
    assert run(["search", "--help"]) == 0
    out = capsys.readouterr().out
    for flag in (
        "--depth", "--topic", "--days", "--max-results", "--time-range", "--include-answer",
        "--include-images", "--include-image-descriptions", "--include-raw-content",
        "--include-domain", "--exclude-domain", "--request-timeout",
    ):
        assert flag in out, flag
    for chinese in ("搜索", "域名", "输出格式"):
        assert chinese in out
    assert "usage:" not in out, "§9 用例 10：帮助文本不得留英文样板"


def test_top_level_help_is_chinese(capsys):
    assert run(["--help"]) == 0
    out = capsys.readouterr().out
    assert "用法" in out and "选项" in out
    assert "usage:" not in out and "options:" not in out
    for name in ("search", "extract", "tools", "doctor"):
        assert name in out


def test_subcommand_usage_line_has_a_single_prefix(capsys):
    assert run(["search", "--help"]) == 0
    out = capsys.readouterr().out
    assert "用法：用法：" not in out
    assert out.startswith("用法：tavily-cli search ")


def test_argparse_boilerplate_help_is_chinese(capsys):
    for argv in (["--help"], ["search", "--help"], ["doctor", "--help"]):
        assert run(argv) == 0
        out = capsys.readouterr().out
        assert "show this help message and exit" not in out, argv
        assert "show program's version number and exit" not in out, argv


def test_global_options_render_in_their_own_section(capsys):
    assert run(["search", "--help"]) == 0
    out = capsys.readouterr().out
    assert "全局选项:" in out


def test_global_options_work_before_and_after_subcommand(capsys):
    fake = FakeOpener(call=ok_call({"query": "x", "results": [{"url": "https://a"}], "request_id": "r"}))
    assert run(["--keys-en", "-f", "raw", "search", "x"], opener=fake) == 0
    assert "url" in capsys.readouterr().out
    assert run(["search", "x", "-f", "raw"], opener=fake) == 0


def test_endpoint_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("TAVILY_MCP_ENDPOINT", "http://10.0.0.1:9/mcp")
    fake = FakeOpener(call=ok_call({"query": "x", "results": [{"url": "https://a"}], "request_id": "r"}))
    assert run(["search", "x", "--endpoint", "http://10.0.0.2:8/mcp", "-f", "json"], opener=fake) == 0
    assert fake.urls[0] == "http://10.0.0.2:8/mcp"


def test_endpoint_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("TAVILY_MCP_ENDPOINT", "http://10.0.0.1:9/mcp")
    fake = FakeOpener(call=ok_call({"query": "x", "results": [{"url": "https://a"}], "request_id": "r"}))
    assert run(["search", "x", "-f", "json"], opener=fake) == 0
    assert fake.urls[0] == "http://10.0.0.1:9/mcp"


def test_version_flag(capsys):
    assert run(["--version"]) == 0
    assert "tavily-cli" in capsys.readouterr().out


def test_no_subcommand_is_a_usage_error(capsys):
    assert run([]) == 2
    captured = capsys.readouterr()
    assert "用法" in captured.out + captured.err


# ------------------------------------------------------------------ 着色（M2）

_COLOURED = {"query": "x", "results": [{"url": "https://a", "title": "海康视讯", "score": "0.9"}], "request_id": "r"}


@pytest.fixture
def no_leaked_no_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)


def test_table_on_a_tty_is_coloured(no_leaked_no_color, capsys):
    fake = FakeOpener(call=ok_call(_COLOURED))
    assert run(["search", "x", "-f", "table"], opener=fake, isatty=True) == 0
    assert "\x1b[" in capsys.readouterr().out


def test_piped_table_carries_no_ansi(no_leaked_no_color, capsys):
    fake = FakeOpener(call=ok_call(_COLOURED))
    assert run(["search", "x", "-f", "table"], opener=fake, isatty=False) == 0
    assert "\x1b" not in capsys.readouterr().out


def test_no_color_flag_and_env_var_both_switch_it_off(no_leaked_no_color, capsys, monkeypatch):
    fake = FakeOpener(call=ok_call(_COLOURED))
    assert run(["search", "x", "-f", "table", "--no-color"], opener=fake, isatty=True) == 0
    assert "\x1b" not in capsys.readouterr().out
    monkeypatch.setenv("NO_COLOR", "1")
    assert run(["search", "x", "-f", "table"], opener=fake, isatty=True) == 0
    assert "\x1b" not in capsys.readouterr().out


def test_machine_readable_stdout_is_never_coloured(no_leaked_no_color, capsys):
    fake = FakeOpener(call=ok_call(_COLOURED))
    for fmt in ("json", "ndjson", "raw"):
        assert run(["search", "x", "-f", fmt], opener=fake, isatty=True) == 0
        assert "\x1b" not in capsys.readouterr().out, fmt


def test_output_file_never_receives_escape_sequences(no_leaked_no_color, tmp_path, capsys):
    target = tmp_path / "out.txt"
    fake = FakeOpener(call=ok_call(_COLOURED))
    assert run(["search", "x", "-f", "table", "-o", str(target)], opener=fake, isatty=True) == 0
    assert "\x1b" not in target.read_text(encoding="utf-8"), "写进文件的产物不能被转义序列污染"
