# ADR-0001: 传输层用标准库自研，不引入官方 `mcp` SDK

状态：已接受（2026-10-22）

## 背景

tavily-cli 需要一个 MCP Streamable HTTP 客户端。两条路：

- A：官方 Python SDK `mcp`（本机 `uv pip install mcp` 可得 **2.3.0**，PyPI 可达）
- B：`urllib` + `json` 自研约 200 行的极薄传输层

约束来自需求 NFR-1：**冷启动 ≤150ms**。这个 CLI 的主要消费者之一是其他 agent 的 Bash 工具，
它们每次都新起进程；启动开销会被高频调用放大成可感知延迟。

## 实测证据（不是估计）

| 测量项 | 结果 |
|--------|------|
| `import mcp` + `from mcp.client.streamable_http import ...` | **≈0.87s** |
| 同一 venv 里裸 `python -c "import argparse"` | ≈61ms |
| `import urllib.request, json, time` | ≈80ms 量级 |
| SDK 2.3.0 入口符号 | `streamable_http_client`（**注意**：1.x 时代文档里的 `streamablehttp_client` 已改名，直接照旧文档写会 ImportError） |
| SDK 2.3.0 签名 | `(url, *, http_client=None, terminate_on_close=True, max_sse_event_size=None)` —— **没有 headers 参数**，要注入 `mcp-session-id` 必须自己构造并传入 `http_client`（依赖 `httpx2.AsyncClient`） |
| SDK 结果模型字段 | snake_case（`structured_content`），依赖 alias 映射线上 `structuredContent` |

服务端需要的协议面（研究文档 §2）只有 4 个 JSON-RPC 方法 + 1 个 session 响应头 + SSE 取
`data:` 行，且已全部实测确认，不含任何未验证的分支。

## 决策

选 **B：标准库自研极薄传输层**（`transport.py`），运行时依赖降为 0 个第三方包
（`tomllib` 属标准库，Python ≥3.11）。

配套义务（否则自研会退化成隐性债务）：

1. 自研层必须由 `tests/contract/` 的 `@network` 契约测试守护：至少断言
   `initialize` 协商成功、`tools/list` schema hash 未意外漂移、4 工具最小成功调用、
   session 失效能重握手。
2. `fixtures/` 里的线上原始响应作为离线单测数据源，SSE 解析需覆盖分块到达、`\r\n`、
   多帧、超大帧、心跳行。
3. `--verbose` 暴露方法名/HTTP 码/耗时，出问题时能直接对比 curl 行为。

## 后果

**正面**：冷启动从 ~870ms 降到 ~80ms 量级；无 pydantic/httpx2 版本漂移风险；单文件可读，
便于排障；可编辑安装（`.venv/bin/pip install -e .`）后几乎无依赖树。

**负面与代价**：
- 协议语义需自行维护。若服务端未来要求 `origin` 校验、`MCP-Protocol-Version` 请求头、
  resume 语义或鉴权，自研层要自己跟进 —— 缓解：契约测试会在漂移时先失败，而不是静默出错。
- 放弃了 SDK 附带的类型与高级能力（progress notification、cancellation、采样等）。
  本 CLI 用不到：实测 `prompts/list`、`resources/list` 均为空数组，服务端只宣告 tools 相关能力。

## 重新评估触发条件

- 需要支持第二个 MCP 网关且协议面扩大；或
- 上游引入鉴权/resume/流式 progress；或
- 自研层 bug 修复成本连续两个里程碑高于 SDK 依赖成本。

## 修订

- 2026-10-22：依 D-4（不使用 `uv tool install`，统一安装运行在本机 `.venv`）修正
  "后果"一节的安装方式表述。**决策本身不变**，仍是标准库自研。
