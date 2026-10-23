#!/usr/bin/env python
"""刷新 fixtures/tools_list.json：只做 initialize + tools/list，**不产生上游 Tavily 调用**。

用途：服务端升级后（例如 4.1.0 → 4.1.3 移除了 `timeout` 入参）在**不消耗共享配额**的前提下
取回运行时权威 schema，并打印与内置副本的指纹差异。
跑法：.venv/bin/python study/mcp-tavily-endpoint/probe_tools_list.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tavily_cli import constants, schema  # noqa: E402
from tavily_cli.transport import McHttp  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tools_list.json"


def main() -> int:
    endpoint = constants.DEFAULT_ENDPOINT
    transport = McHttp(endpoint, timeout=20.0, client_version="probe-tools-list")
    transport.initialize()
    tools = transport.list_tools()

    document = {
        "_captured": {
            "endpoint": endpoint,
            "serverInfo": {"name": transport.session.server_name, "version": transport.session.server_version},
            "protocolVersion": transport.session.protocol_version,
            "method": "initialize + tools/list（零上游调用）",
        },
        "result": {"tools": tools},
    }
    FIXTURE.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    live_hash = schema.schema_hash(tools)
    builtin_hash = schema.schema_hash()
    print(f"serverInfo: {transport.session.server_name} {transport.session.server_version}")
    print(f"live   : {live_hash}")
    print(f"builtin: {builtin_hash}")
    print("已写入", FIXTURE.relative_to(ROOT))
    if live_hash != builtin_hash:
        print("\n⚠️ 契约漂移：内置副本需要刷新（AGENTS.md §6.3）")
        for tool in tools:
            props = tool["inputSchema"]["properties"]
            spec = schema.TOOL_SCHEMA.get(tool["name"])
            known = set(spec.params) if spec else set()
            print(f"  - {tool['name']}: 新增 {sorted(set(props) - known)} 移除 {sorted(known - set(props))}")
        return 1
    print("\n内置副本与服务端一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
