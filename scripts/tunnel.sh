#!/usr/bin/env bash
# 建立/复用到 mcp-host 的 SSH 隧道，用于本机无法直连 18000 端口时的降级访问。
# 用法: scripts/tunnel.sh [status|up|down]
set -euo pipefail

SSH_HOST="${TAVILY_SSH_HOST:-mcp-host}"
PORT="${TAVILY_LOCAL_PORT:-18000}"
ENDPOINT="http://127.0.0.1:${PORT}/mcp"

# -N 与 -L 之间会被插入若干 -o 选项（CLI 还多带 BatchMode=yes），因此只锚定转发口与主机名。
PATTERN="ssh.*-L ${PORT}:127\.0\.0\.1:${PORT}.*${SSH_HOST}"

running() { pgrep -f "$PATTERN" >/dev/null 2>&1; }

case "${1:-up}" in
  status)
    if running; then echo "隧道在运行 · ${ENDPOINT}（pid $(pgrep -f "$PATTERN" | tr '\n' ' ')）"; else echo "无隧道（可直连时无需建立）"; fi
    ;;
  up)
    if running; then echo "复用已有隧道 · ${ENDPOINT}"; exit 0; fi
    ssh -f -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=20 \
        -L "${PORT}:127.0.0.1:${PORT}" "${SSH_HOST}"
    echo "已建立隧道 · ${ENDPOINT}"
    ;;
  down)
    pkill -f "$PATTERN" && echo "隧道已关闭" || echo "本来就没有隧道"
    ;;
  *)
    echo "用法: $0 [status|up|down]" >&2; exit 2 ;;
esac
