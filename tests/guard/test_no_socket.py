"""防污染守卫：非法入参必须止步于校验层，**零 socket 写入**。

对 study/mcp-tavily-endpoint/README.md §5 那起"一个 !!bad 打死共享 Key 池"事故的永久回归防线。
这些用例在 cli 装配完成后转绿；在此之前它们应当失败，且失败原因必须是功能缺失。
"""

from __future__ import annotations

import io
import json
import socket
import urllib.request

import pytest

from tavily_cli.cli import main

BAD_CALLS: list[str] = []


@pytest.fixture
def tripwire(monkeypatch):
    """任何 socket 写入 / urlopen 调用都记一笔并立刻炸。"""

    BAD_CALLS.clear()

    def spy(*args, **kwargs):
        BAD_CALLS.append(repr(args[:1]))
        raise AssertionError("校验失败的路径不得产生任何网络写入")

    for name in ("connect", "connect_ex", "send", "sendall"):
        monkeypatch.setattr(socket.socket, name, spy, raising=False)
    monkeypatch.setattr(socket, "create_connection", spy)
    monkeypatch.setattr(urllib.request, "urlopen", spy)
    return BAD_CALLS


def run(argv: list[str], stdin=None) -> int:
    try:
        return main(argv, stdin=stdin)
    except SystemExit as exc:  # argparse 的用法错误按约定退出码 2
        return exc.code if isinstance(exc.code, int) else 2


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "x", "--include-domain", "!!bad"],
        ["search", "x", "--include-domain", "tavily"],
        ["search", "x", "--include-domain", "http://tavily.com"],
        ["search", "x", "--exclude-domain", "bad-.com"],
        ["search", "x", "--depth", "bogus"],
        ["search", "x", "--topic", "crypto"],
        ["search", "x", "--time-range", "decade"],
        ["search", "x", "--max-results", "0"],
        ["search", "x", "--max-results", "21"],
        ["search", "x", "--request-timeout", "0.001"],
        ["search", "x", "--request-timeout", "120"],
        ["search", ""],
        ["search", "x" * 513],
        ["extract", "example.com"],
        ["extract", "ftp://example.com"],
        ["crawl", "example.com"],
        ["crawl", "https://example.com", "--select-path", "[(未闭合"],
        ["crawl", "https://example.com", "--exclude-path", "*"],
        ["crawl", "https://example.com", "--max-depth", "-1"],
        ["crawl", "https://example.com", "--limit", "0"],
        ["crawl", "https://example.com", "--max-breadth", "0"],
        ["map", "http://example.com", "--select-path", "(?"],
        ["map", "https://example.com", "--max-depth", "-2"],
        ["map", "ftp://example.com"],
        ["--dry-run", "crawl", "example.com"],
        ["--dry-run", "search", "x", "--include-domain", "!!bad"],
    ],
)
def test_invalid_args_never_touch_the_network(argv, tripwire, capsys):
    assert run(argv) == 2, argv
    assert tripwire == []
    err = capsys.readouterr().err
    assert err.strip(), "退出码 2 必须给出中文说明"
    assert "Traceback" not in err


def test_domain_error_message_names_the_suffix_requirement(tripwire, capsys):
    """§9 用例 3：stderr 用中文指出域名需带合法后缀。"""

    assert run(["search", "x", "--include-domain", "!!bad"]) == 2
    err = capsys.readouterr().err
    assert "后缀" in err
    assert "--include-domain" in err


def test_enum_error_lists_allowed_values(tripwire, capsys):
    """§9 用例 4：--depth bogus 必须列出允许取值。"""

    assert run(["search", "x", "--depth", "bogus"]) == 2
    err = capsys.readouterr().err
    assert "basic" in err and "advanced" in err


def test_unknown_option_is_rejected_without_network(tripwire, capsys):
    assert run(["search", "x", "--bogus-flag"]) == 2
    assert tripwire == []


def test_batch_bad_lines_never_touch_the_network(tripwire, capsys):
    """§9-22 / 红线 1：逐行隔离只意味着"坏行不进网络队列"，不意味着可以放宽校验。"""

    stream = io.StringIO(
        '{"id":"bad","tool":"search","arguments":{"query":"x","include_domains":["!!bad"]}}\n'
        "这不是 JSON\n"
        '{"id":"ghost","tool":"weather","arguments":{}}\n'
    )

    assert run(["batch"], stdin=stream) == 2
    assert tripwire == []
    captured = capsys.readouterr()
    docs = [json.loads(line) for line in captured.out.splitlines()]
    assert [doc["成功"] for doc in docs] == [False, False, False]
    assert "第 1 行" in captured.err and "第 2 行" in captured.err and "第 3 行" in captured.err
