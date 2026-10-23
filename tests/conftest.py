"""离线测试基座：fixtures 数据源 + 全局禁网。"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "study" / "mcp-tavily-endpoint" / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def server_tools() -> list[dict]:
    """线上 tools/list 抓到的 4 个工具定义（契约权威样本）。"""
    return load("tools_list.json")["result"]["tools"]


@pytest.fixture(scope="session")
def load_fixture():
    return load


@pytest.fixture(scope="session")
def search_result() -> dict:
    return load("out_tavily-search_sample.json")["result"]


@pytest.fixture(scope="session")
def extract_result() -> dict:
    return load("out_tavily-extract_sample.json")["result"]


@pytest.fixture(autouse=True)
def _block_network(monkeypatch, request):
    """NFR-9：离线单测零网络。@network 标记的契约测试除外。"""

    if request.node.get_closest_marker("network"):
        return

    def _denied(*_args, **_kwargs):
        raise AssertionError("离线测试禁止任何网络访问")

    monkeypatch.setattr(socket.socket, "connect", _denied)
    monkeypatch.setattr(socket, "create_connection", _denied)
    monkeypatch.setattr(socket, "getaddrinfo", _denied)
