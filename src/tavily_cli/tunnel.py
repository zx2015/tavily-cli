"""SSH 隧道降级（design §8）：直连不可达时把端点改写成本地转发口。

`--tunnel off` 严格不碰 ssh；端口已被占用视为隧道已存在，直接复用（与 scripts/tunnel.sh 同语义）。
"""

from __future__ import annotations

import socket
import subprocess
from urllib.parse import urlsplit, urlunsplit

SPAWN_TIMEOUT = 15.0
PROBE_TIMEOUT = 0.3
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


class TunnelError(RuntimeError):
    """隧道没能建立：ssh 缺失、被拒、或转发口没有真的在听。"""


def tunnel_endpoint(endpoint: str) -> str:
    """只换主机名为 127.0.0.1，端口/路径原样保留。"""

    parts = urlsplit(endpoint)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return urlunsplit((parts.scheme, f"127.0.0.1:{port}", parts.path, parts.query, parts.fragment))


def is_listening(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ssh_command(port: int, ssh_host: str) -> list[str]:
    return [
        "ssh",
        "-f",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=20",
        "-o",
        "BatchMode=yes",
        "-L",
        f"{port}:127.0.0.1:{port}",
        ssh_host,
    ]


def ensure_tunnel(
    endpoint: str,
    ssh_host: str,
    *,
    run=subprocess.run,
    listening=is_listening,
) -> str:
    """确保 127.0.0.1:<port> 上有可用的转发口，返回可直接使用的端点。"""

    target = tunnel_endpoint(endpoint)
    port = urlsplit(target).port
    if listening("127.0.0.1", port):
        return target
    try:
        completed = run(ssh_command(port, ssh_host), capture_output=True, text=True, timeout=SPAWN_TIMEOUT)
    except FileNotFoundError as exc:
        raise TunnelError(f"本机没有 ssh 命令，无法降级到隧道（端点 {endpoint}）") from exc
    except subprocess.TimeoutExpired as exc:
        raise TunnelError(
            f"ssh 建立隧道超过 {SPAWN_TIMEOUT:.0f}s 未返回（{ssh_host} 端口 {port}）"
        ) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:200]
        raise TunnelError(f"ssh 隧道建立失败（退出码 {completed.returncode}）：{detail or '无输出'}")
    if not listening("127.0.0.1", port):
        raise TunnelError(f"ssh 已返回但 127.0.0.1:{port} 无人监听，隧道未生效")
    return target
