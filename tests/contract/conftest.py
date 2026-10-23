"""契约测试基座：真实端点、默认不跑。

两道闸门（顺序不能反）：
1. `pyproject.toml addopts = "-m 'not network'"` 默认把本目录全部用例 deselect 掉；
   下面的 hook 负责给本目录每个用例自动补上 `network` 标记，所以 `pytest -m network` 才会跑。
2. 真正会消耗上游 Tavily 配额的用例额外要求 `TAVILY_CONTRACT_QUOTA=1`
   （共享 Key 池是有配额的，见 AGENTS.md §3/§8）；只碰协议层、不产生上游调用的用例不受此限制。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tavily_cli import constants
from tavily_cli.transport import McHttp

HERE = Path(__file__).resolve().parent

NO_QUOTA = "需要真实上游调用，消耗共享 Key 池配额：显式设 TAVILY_CONTRACT_QUOTA=1 才执行"


def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.is_relative_to(HERE):
            item.add_marker(pytest.mark.network)


def endpoint_url() -> str:
    return os.environ.get("TAVILY_MCP_ENDPOINT", constants.DEFAULT_ENDPOINT)


@pytest.fixture(scope="session")
def endpoint() -> str:
    return endpoint_url()


@pytest.fixture(scope="session")
def client(endpoint):
    """一个 session 共用一条握手成功的连接：session 强制是实测契约，别每个用例重连一次。"""

    transport = McHttp(endpoint, timeout=30.0, client_version="contract")
    transport.initialize()
    return transport


@pytest.fixture(scope="session")
def quota():
    """放行真实上游调用的闸门；同时返回一个调用计数以便报告配额开销。"""

    if os.environ.get("TAVILY_CONTRACT_QUOTA") != "1":
        pytest.skip(NO_QUOTA)
    spent: list[tuple[str, dict]] = []
    return spent


def call_tool(endpoint: str, tool: str, arguments: dict, timeout: float = 60.0):
    transport = McHttp(endpoint, timeout=timeout, client_version="contract")
    return transport.call(tool, arguments), transport
