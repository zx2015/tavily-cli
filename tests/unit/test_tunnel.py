"""tunnel.py：SSH 隧道降级（design §8）离线单测。

这里的 `ssh` 一律用假 runner 替掉——测试**绝不真的去连 mcp-host**。
"""

from __future__ import annotations

import subprocess

import pytest

from tavily_cli import tunnel


class Runner:
    def __init__(self, returncode=0, stderr="", raises=None):
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stderr = stderr
        self.raises = raises

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self.raises is not None:
            raise self.raises
        return type("Done", (), {"returncode": self.returncode, "stdout": "", "stderr": self.stderr})()


class Ports:
    """按调用次序返回"127.0.0.1:port 是否有人监听"，用于区分 spawn 前探测与 spawn 后确认。"""

    def __init__(self, *values: bool):
        self.values = list(values)
        self.seen: list[tuple[str, int]] = []

    def __call__(self, host: str, port: int, timeout: float = 0.2) -> bool:
        self.seen.append((host, port))
        return self.values.pop(0) if self.values else False


def test_tunnel_endpoint_rewrites_only_the_host():
    assert tunnel.tunnel_endpoint("http://203.0.113.10:18000/mcp") == "http://127.0.0.1:18000/mcp"


def test_tunnel_endpoint_keeps_path_and_defaults_the_port():
    assert tunnel.tunnel_endpoint("https://mini.example/mcp") == "https://127.0.0.1:443/mcp"


def test_spawn_when_nothing_is_listening():
    runner, ports = Runner(), Ports(False, True)
    endpoint = tunnel.ensure_tunnel("http://203.0.113.10:18000/mcp", "mcp-host", run=runner, listening=ports)
    assert endpoint == "http://127.0.0.1:18000/mcp"
    argv = runner.calls[0]
    assert argv[:3] == ["ssh", "-f", "-N"]
    assert argv[-1] == "mcp-host"
    assert argv[argv.index("-L") + 1] == "18000:127.0.0.1:18000"
    assert "ExitOnForwardFailure=yes" in " ".join(argv), "转发失败要当场报错，而不是留下一个假隧道"
    assert ports.seen == [("127.0.0.1", 18000), ("127.0.0.1", 18000)]


def test_existing_tunnel_is_reused_without_spawning():
    """§8：本地转发口已有人监听 ⇒ 视为隧道已存在，直接复用，不再 spawn。"""

    runner, ports = Runner(), Ports(True)
    assert tunnel.ensure_tunnel("http://127.0.0.1:18000/mcp", "mcp-host", run=runner, listening=ports) == "http://127.0.0.1:18000/mcp"
    assert runner.calls == []


def test_ssh_failure_becomes_tunnel_error():
    runner = Runner(returncode=255, stderr="Permission denied (publickey)")
    with pytest.raises(tunnel.TunnelError) as excinfo:
        tunnel.ensure_tunnel("http://203.0.113.10:18000/mcp", "mcp-host", run=runner, listening=Ports(False))
    message = str(excinfo.value)
    assert "255" in message and "publickey" in message


def test_missing_ssh_binary_is_explained_in_chinese():
    runner = Runner(raises=FileNotFoundError("ssh"))
    with pytest.raises(tunnel.TunnelError) as excinfo:
        tunnel.ensure_tunnel("http://203.0.113.10:18000/mcp", "mcp-host", run=runner, listening=Ports(False))
    assert "ssh" in str(excinfo.value)


def test_ssh_timeout_becomes_tunnel_error():
    runner = Runner(raises=subprocess.TimeoutExpired(cmd="ssh", timeout=15))
    with pytest.raises(tunnel.TunnelError):
        tunnel.ensure_tunnel("http://203.0.113.10:18000/mcp", "mcp-host", run=runner, listening=Ports(False))


def test_ssh_ok_but_port_dead_is_not_a_tunnel():
    runner = Runner()
    with pytest.raises(tunnel.TunnelError) as excinfo:
        tunnel.ensure_tunnel("http://203.0.113.10:18000/mcp", "mcp-host", run=runner, listening=Ports(False, False))
    assert "18000" in str(excinfo.value)
    assert runner.calls, "没有转发口可复用时才 spawn"
