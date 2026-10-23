"""`batch`：stdin NDJSON → 逐行信封（§4.6 / §5.4 / §6 规则 4–6 / §9 用例 21–25，全部离线）。"""

from __future__ import annotations

import io
import json
import threading
import time
import urllib.error

import pytest

from mcp_stub import FakeOpener, ok_call, run


def batch_input(*lines: str) -> io.StringIO:
    return io.StringIO("".join(f"{line}\n" for line in lines))


def search_line(query: str) -> str:
    return json.dumps({"tool": "search", "arguments": {"query": query}}, ensure_ascii=False)


def search_result(arguments: dict) -> dict:
    return ok_call(
        {
            "query": arguments["query"],
            "results": [{"url": f"https://{arguments['query']}.example", "title": "标题", "content": "摘要", "score": 0.5}],
            "request_id": "r-search",
            "response_time": 0.2,
        }
    )


def map_result(arguments: dict) -> dict:
    # 实测形状：map 的 results 是裸 URL 字符串（D-8 在批量面上同样要成立）
    return ok_call({"base_url": arguments["url"], "results": ["https://a", "https://b"], "request_id": "r-map", "response_time": 0.1})


def result_for(arguments: dict) -> dict:
    return search_result(arguments) if "query" in arguments else map_result(arguments)


# ------------------------------------------------------------------ §9-21 有序逐行输出


def test_batch_emits_one_envelope_per_line_in_input_order(capsys):
    fake = FakeOpener(call=result_for)
    stream = io.StringIO(
        '{"id":"q1","tool":"search","arguments":{"query":"示例","max_results":1}}\n'
        '{"id":"q2","tool":"map","arguments":{"url":"https://docs.tavily.com"}}\n'
        '{"tool":"search","arguments":{"query":"海康"}}\n'
    )

    assert run(["batch"], opener=fake, stdin=stream) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3, "一行输入必须一行输出"
    docs = [json.loads(line) for line in lines]
    assert [doc["行"] for doc in docs] == [1, 2, 3]
    assert [doc["关联编号"] for doc in docs] == ["q1", "q2", None]
    assert [doc["工具"] for doc in docs] == ["tavily-search", "tavily-map", "tavily-search"]
    assert [doc["成功"] for doc in docs] == [True, True, True]
    assert docs[0]["结果"][0]["网址"] == "https://示例.example"
    assert docs[1]["节点"] == [{"网址": "https://a"}, {"网址": "https://b"}]
    assert all("\n" not in line for line in lines)


def test_batch_handshakes_once_for_the_whole_batch(capsys):
    fake = FakeOpener(call=search_result)
    stream = io.StringIO('{"tool":"search","arguments":{"query":"a"}}\n{"tool":"search","arguments":{"query":"b"}}\n')

    assert run(["batch"], opener=fake, stdin=stream) == 0
    assert fake.count("initialize") == 1, "整批必须复用一个 session"
    assert fake.count("tools/call") == 2


def test_batch_keys_en_is_strictly_isomorphic(capsys):
    zh = FakeOpener(call=search_result)
    assert run(["batch"], opener=zh, stdin=io.StringIO('{"id":"q1","tool":"search","arguments":{"query":"示例"}}\n')) == 0
    zh_doc = json.loads(capsys.readouterr().out.splitlines()[0])

    en = FakeOpener(call=search_result)
    assert run(["batch", "--keys-en"], opener=en, stdin=io.StringIO('{"id":"q1","tool":"search","arguments":{"query":"示例"}}\n')) == 0
    en_doc = json.loads(capsys.readouterr().out.splitlines()[0])

    assert list(zh_doc) == ["行", "关联编号", "成功", "工具", "查询", "结果", "简答", "图片", "页面", "失败", "节点", "元信息", "错误"]
    assert list(en_doc) == ["line", "id", "ok", "tool", "query", "results", "answer", "images", "pages", "failed", "nodes", "meta", "error"]
    assert en_doc["line"] == zh_doc["行"] == 1
    assert en_doc["id"] == zh_doc["关联编号"] == "q1"
    assert [list(item) for item in en_doc["results"]] == [["url", "title", "content", "score"]]
    assert [list(item) for item in zh_doc["结果"]] == [["网址", "标题", "摘要", "评分"]]
    assert [list(item.values()) for item in en_doc["results"]] == [list(item.values()) for item in zh_doc["结果"]]


def test_batch_with_meta_prints_envelope_first_line(capsys):
    fake = FakeOpener(call=search_result)
    stream = io.StringIO('{"tool":"search","arguments":{"query":"示例"}}\n')

    assert run(["batch", "--with-meta"], opener=fake, stdin=stream) == 0
    lines = capsys.readouterr().out.splitlines()
    assert list(json.loads(lines[0])) == ["元信息"]
    assert len(lines) == 2


@pytest.mark.parametrize("fmt", ["json", "table", "md", "raw"])
def test_batch_rejects_formats_that_cannot_stream(fmt, capsys):
    """§5.4/§9-25：静默改用 ndjson 是本仓库踩过的"全局旗标静默失效"坑，必须报错。"""

    fake = FakeOpener(call=search_result)
    assert run(["batch", "-f", fmt], opener=fake, stdin=io.StringIO('{"tool":"search","arguments":{"query":"示例"}}\n')) == 2
    err = capsys.readouterr().err
    assert "逐行" in err and "jq -s" in err
    assert fake.requests == [], "格式闸门必须走在任何出网之前"


def test_batch_ndjson_is_accepted_explicitly(capsys):
    fake = FakeOpener(call=search_result)
    assert run(["batch", "-f", "ndjson"], opener=fake, stdin=io.StringIO('{"tool":"search","arguments":{"query":"示例"}}\n')) == 0
    assert len(capsys.readouterr().out.splitlines()) == 1


# ------------------------------------------------------------------ §9-22 逐行校验隔离


def test_bad_line_fails_only_that_line_and_never_enters_the_queue(capsys):
    fake = FakeOpener(call=search_result)
    stream = io.StringIO(
        '{"id":"bad","tool":"search","arguments":{"query":"示例","include_domains":["!!bad"]}}\n'
        '{"id":"ok","tool":"search","arguments":{"query":"海康"}}\n'
        '{"id":"ghost","tool":"weather","arguments":{}}\n'
    )

    assert run(["batch"], opener=fake, stdin=stream) == 2
    captured = capsys.readouterr()
    docs = [json.loads(line) for line in captured.out.splitlines()]
    assert [doc["成功"] for doc in docs] == [False, True, False]
    assert docs[0]["错误"]["类别"] == "参数校验失败"
    assert "!!bad" in docs[0]["错误"]["消息"]
    assert docs[2]["关联编号"] == "ghost"
    assert "第 1 行" in captured.err and "第 3 行" in captured.err

    assert fake.calls() == [("tavily-search", {"query": "海康"})], "坏行必须止步于校验，不得进网络队列"


def test_bad_json_line_reports_its_index_without_aborting_the_batch(capsys):
    fake = FakeOpener(call=result_for)
    stream = io.StringIO(
        "not json at all\n"
        '{"tool":"map","arguments":{"url":"https://docs.tavily.com"}}\n'
        "[1,2]\n"
    )

    assert run(["batch"], opener=fake, stdin=stream) == 2
    captured = capsys.readouterr()
    docs = [json.loads(line) for line in captured.out.splitlines()]
    assert [doc["行"] for doc in docs] == [1, 2, 3]
    assert [doc["成功"] for doc in docs] == [False, True, False]
    assert docs[0]["错误"]["类别"] == "参数校验失败"
    assert "第 1 行" in captured.err and "第 3 行" in captured.err
    assert fake.calls() == [("tavily-map", {"url": "https://docs.tavily.com"})]


def test_blank_lines_are_skipped_and_do_not_consume_an_index(capsys):
    fake = FakeOpener(call=search_result)
    stream = io.StringIO('\n   \n{"tool":"search","arguments":{"query":"a"}}\n\n{"tool":"search","arguments":{"query":"b"}}\n\n')

    assert run(["batch"], opener=fake, stdin=stream) == 0
    docs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [doc["行"] for doc in docs] == [1, 2]


def test_missing_tool_or_arguments_is_a_line_error(capsys):
    fake = FakeOpener(call=search_result)
    stream = io.StringIO('{"arguments":{"query":"a"}}\n{"tool":"search"}\n{"tool":"search","arguments":"示例"}\n')

    assert run(["batch"], opener=fake, stdin=stream) == 2
    docs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(docs) == 3
    assert all(doc["成功"] is False for doc in docs)
    assert fake.calls() == []


def test_undeclared_top_level_key_fails_only_its_own_line(capsys):
    """§4.6：拼错的 arguements 不能静默变成"该行 arguments 为空"然后出网。"""

    fake = FakeOpener(call=search_result)
    stream = io.StringIO(
        '{"tool":"search","arguements":{"query":"示例"}}\n'
        '{"tool":"search","arguments":{"query":"海康"}}\n'
    )

    assert run(["batch"], opener=fake, stdin=stream) == 2
    captured = capsys.readouterr()
    docs = [json.loads(line) for line in captured.out.splitlines()]
    assert docs[0]["错误"]["类别"] == "参数校验失败"
    assert "arguements" in docs[0]["错误"]["消息"]
    assert fake.calls() == [("tavily-search", {"query": "海康"})]


# ------------------------------------------------------------------ §6 规则 4/5 + §9-24


def pool_dead(arguments: dict) -> dict:
    return ok_call({"error": "No active API keys available"}, is_error=True)


def test_pool_death_stops_submitting_but_keeps_the_line_count(capsys):
    fake = FakeOpener(call=pool_dead)
    stream = io.StringIO('{"tool":"search","arguments":{"query":"a"}}\n{"tool":"search","arguments":{"query":"b"}}\n{"tool":"search","arguments":{"query":"c"}}\n')

    assert run(["batch", "--concurrency", "1"], opener=fake, stdin=stream) == 6
    docs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(docs) == 3, "行数守恒：停止发起新调用也不能少输出行"
    assert all(doc["错误"]["类别"] == "密钥池已死亡" for doc in docs)
    assert "未发起调用" in docs[1]["错误"]["消息"] and "未发起调用" in docs[2]["错误"]["消息"]
    assert fake.count("tools/call") == 1, "ERROR 是服务端终态，继续发只是白烧共享配额"


def test_rate_limited_line_does_not_stop_the_batch(capsys):
    fake = FakeOpener(call=lambda arguments: ok_call({"error": "Rate limit exceeded"}, is_error=True))
    stream = io.StringIO('{"tool":"search","arguments":{"query":"a"}}\n{"tool":"search","arguments":{"query":"b"}}\n')

    assert run(["batch", "--concurrency", "1"], opener=fake, stdin=stream) == 8
    assert fake.count("tools/call") == 2, "限流不是终态，不能据此放弃整批"


def test_exit_code_follows_the_first_failing_line(capsys):
    fake = FakeOpener(call=lambda arguments: ok_call({"error": "上游 Tavily 500"}, is_error=True))
    stream = io.StringIO(
        '{"tool":"search","arguments":{"query":"a"}}\n'
        '{"tool":"search","arguments":{"query":"b","include_domains":["!!bad"]}}\n'
    )

    assert run(["batch"], opener=fake, stdin=stream) == 5


def test_pool_death_outweighs_an_earlier_usage_line(capsys):
    fake = FakeOpener(call=pool_dead)
    stream = io.StringIO(
        '{"tool":"search","arguments":{"query":"a","max_results":99}}\n'
        '{"tool":"search","arguments":{"query":"b"}}\n'
    )

    assert run(["batch", "--concurrency", "1"], opener=fake, stdin=stream) == 6
    assert fake.count("tools/call") == 1


# ------------------------------------------------------------------ §9-25 节制与闸门


class TerminalStdin(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_batch_refuses_a_terminal_stdin(capsys):
    fake = FakeOpener(call=search_result)
    stream = TerminalStdin('{"tool":"search","arguments":{"query":"a"}}\n')

    assert run(["batch"], opener=fake, stdin=stream) == 2
    captured = capsys.readouterr()
    assert "管道" in captured.err and "重定向" in captured.err
    assert captured.out == ""
    assert fake.requests == []


def test_batch_refuses_more_than_the_line_cap_without_touching_the_network(capsys):
    fake = FakeOpener(call=search_result)
    stream = io.StringIO('{"tool":"search","arguments":{"query":"q"}}\n' * 51)

    assert run(["batch"], opener=fake, stdin=stream) == 2
    captured = capsys.readouterr()
    assert "50" in captured.err and "分批" in captured.err
    assert fake.requests == []


def test_batch_dry_run_prints_request_bodies_and_sends_nothing(capsys):
    fake = FakeOpener(call=search_result)
    stream = io.StringIO(
        '{"id":"q1","tool":"search","arguments":{"query":"示例"}}\n'
        '{"id":"q2","tool":"map","arguments":{"url":"https://docs.tavily.com"}}\n'
        '{"id":"bad","tool":"search","arguments":{"query":"b","include_domains":["!!bad"]}}\n'
    )

    assert run(["batch", "--dry-run"], opener=fake, stdin=stream) == 2
    docs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [doc["行"] for doc in docs] == [1, 2, 3]
    assert docs[0]["请求"]["method"] == "tools/call"
    assert docs[0]["请求"]["params"] == {"name": "tavily-search", "arguments": {"query": "示例"}}
    assert docs[1]["请求"]["params"]["name"] == "tavily-map"
    assert docs[2]["成功"] is False
    assert fake.requests == []


def test_batch_writes_the_output_file_line_by_line(tmp_path, capsys):
    target = tmp_path / "out.ndjson"
    fake = FakeOpener(call=search_result)
    stream = io.StringIO('{"tool":"search","arguments":{"query":"a"}}\n{"tool":"search","arguments":{"query":"b"}}\n')

    assert run(["batch", "-o", str(target)], opener=fake, stdin=stream) == 0
    text = target.read_text(encoding="utf-8")
    assert len(text.splitlines()) == 2
    assert "\x1b" not in text, "机读产物不得带 ANSI"
    assert capsys.readouterr().out == ""


def test_batch_with_no_valid_line_is_a_usage_failure(capsys):
    """§9-25：空输入与 TTY/超上限同属"输入面用错"，不得回报成功。"""

    fake = FakeOpener(call=search_result)

    assert run(["batch"], opener=fake, stdin=io.StringIO("\n\n")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "没有有效输入行" in captured.err
    assert fake.requests == []


# ------------------------------------------------------------------ §9-23 并发（NFR-11）


def test_batch_runs_lines_at_the_same_time_but_writes_in_input_order(capsys):
    barrier = threading.Barrier(3, timeout=3)

    def synced(arguments: dict) -> dict:
        # 三条必须同时在途；顺序执行的实现会在这里超时并让整批失败。
        barrier.wait()
        return search_result(arguments)

    fake = FakeOpener(call=synced)
    assert run(["batch", "--concurrency", "3"], opener=fake, stdin=batch_input(*(search_line(f"q{i}") for i in (1, 2, 3)))) == 0
    docs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [doc["行"] for doc in docs] == [1, 2, 3], "并发执行不得打乱写出顺序"
    assert [doc["查询"] for doc in docs] == ["q1", "q2", "q3"]


def test_batch_never_exceeds_the_concurrency_cap(capsys):
    state = {"in_flight": 0, "peak": 0}
    lock = threading.Lock()

    def tracked(arguments: dict) -> dict:
        with lock:
            state["in_flight"] += 1
            state["peak"] = max(state["peak"], state["in_flight"])
        time.sleep(0.02)
        with lock:
            state["in_flight"] -= 1
        return search_result(arguments)

    fake = FakeOpener(call=tracked)
    eight = [search_line(f"q{i}") for i in range(8)]
    assert run(["batch", "--concurrency", "2"], opener=fake, stdin=batch_input(*eight)) == 0
    assert state["peak"] <= 2, f"同时在途的调用数突破了 --concurrency：峰值 {state['peak']}"
    assert len(capsys.readouterr().out.splitlines()) == 8


@pytest.mark.parametrize("value", ["0", "9", "-1", "abc"])
def test_concurrency_out_of_range_is_rejected_before_anything_is_read(value, capsys):
    """§4.5：越界直接退出码 2，不静默截断到 1–8。"""

    fake = FakeOpener(call=search_result)
    assert run(["batch", "--concurrency", value], opener=fake, stdin=batch_input(search_line("a"))) == 2
    captured = capsys.readouterr()
    assert "--concurrency" in captured.err
    assert captured.out == "" and fake.requests == []


def test_parallel_lines_still_share_one_session(capsys):
    fake = FakeOpener(call=search_result)
    assert run(["batch", "--concurrency", "4"], opener=fake, stdin=batch_input(*(search_line(f"q{i}") for i in range(4)))) == 0
    assert fake.count("initialize") == 1, "并发 worker 不得各自重握手"
    assert fake.count("tools/call") == 4


# ------------------------------------------------------------------ §6 规则 6：漂移预检


def test_batch_prechecks_schema_drift_once_before_the_first_line(capsys):
    drifted = [{"name": "tavily-search", "inputSchema": {"type": "object", "properties": {"newest": {"type": "string"}}}}]
    fake = FakeOpener(call=search_result, tools=drifted)
    assert run(["batch"], opener=fake, stdin=batch_input(search_line("a"), search_line("b"))) == 0
    captured = capsys.readouterr()
    assert "漂移" in captured.err, "漂移只警告，不阻断"
    assert len(captured.out.splitlines()) == 2
    assert fake.count("tools/list") == 1, "预检每批一次，不能逐行重复"
    assert fake.methods.index("tools/list") < fake.methods.index("tools/call")


def test_batch_does_not_warn_when_the_server_schema_matches_the_builtin(capsys):
    fake = FakeOpener(call=search_result)
    assert run(["batch"], opener=fake, stdin=batch_input(search_line("a"))) == 0
    assert "漂移" not in capsys.readouterr().err


def test_batch_continues_when_the_precheck_itself_fails(capsys):
    # --tunnel off：预检以传输层失败告终时，auto 会去探测本地转发口，离线守卫不允许（与 test_cli.py 同惯例）。
    fake = FakeOpener(call=search_result, fail_methods={"tools/list": urllib.error.URLError("预检坏了")})
    assert run(["batch", "--tunnel", "off"], opener=fake, stdin=batch_input(search_line("a"))) == 0
    assert "预检" in capsys.readouterr().err
    assert fake.count("tools/call") == 1


def test_batch_dry_run_skips_the_schema_precheck(capsys):
    fake = FakeOpener(call=search_result)
    assert run(["batch", "--dry-run"], opener=fake, stdin=batch_input(search_line("a"))) == 0
    assert fake.requests == [], "预检也是网络请求，--dry-run 下必须一次都不发"
    assert capsys.readouterr().err == ""
