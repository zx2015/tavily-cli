# ADR-0002: 错误分类与退出码——重试决策与 `isError` 解耦

状态：已接受（2026-10-22）

## 背景

直觉做法是"调用失败就重试一次"。本次调研证明在这个服务上**重试是有代价的动作**：

- 服务端 `execute_with_retry` 已经自己做了多 Key 轮询与重试，CLI 再重试等于叠两层放大。
- 实测 `Request timed out after 0.001 seconds` 被服务端归为"网络层错误"，于是在
  **每个 Key 上**各做 2 次原地退避重试，一次调用耗掉 7.6s。CLI 若再自动重试，会把这个
  数字继续乘下去。
- 更严重的是 ADR-0003 记录的事故：一次非法入参可让 4 个 Key 全部进入 `ERROR` 终态，
  此时任何"失败重试"都只会对着一个已死的池子空转，并掩盖真实原因。

MCP 的 `result.isError` 只表达"工具没成功"，**不表达可否重试**。把两者绑定是设计错误。

## 决策

引入显式错误分类器 `classify.py`，把原始信号（JSON-RPC error / `isError` + 文本 /
传输异常 / HTTP 码）归一为 8 个 `ErrorKind`，每个 Kind 固定绑定一个退出码与一个 `retryable` 布尔，
且 `retryable` 与 `isError` 无直接关系。

| ErrorKind | 退出码 | retryable | 判定信号（实测来源） |
|-----------|--------|-----------|----------------------|
| `USAGE` | 2 | ❌ | 客户端校验层，永不出网 |
| `TRANSPORT` | 3 | ✅ | `URLError`/`ConnectionRefused`/HTTP 5xx |
| `PROTOCOL` | 4 | ⚠️ 仅 session 失效重握手 1 次 | HTTP 400 `Missing session ID`、SSE 解析失败、`Unknown tool: 'x'`、schema 漂移 |
| `TOOL_ERROR` | 5 | ❌ | `isError=true` 且未命中其它专项模式；含 FastMCP `validation error for call[...]` |
| `POOL_DEAD` | 6 | ❌ | 文本 `No active API keys available` / `All available keys failed` |
| `TIMEOUT` | 7 | ❌ | 客户端总超时 / 文本 `Request timed out after` |
| `RATE_LIMITED` | 8 | ⚠️ 显式 `--retries` 时退避 ≥5s 一次 | 上游 429 语义透传 |
| `OK` | 0 | — | `isError=false`，**空结果也算 OK** |
| `INTERRUPTED` | 130 | — | SIGINT，且不输出半截 JSON |

## 后果

- 脚本可以可靠分支：`if tavily-cli search ... ; then ... elif [ $? -eq 6 ]; then 通知运维重启服务`。
  特别是 **6 让"服务端已瘫"与"我网断了"第一次可区分**——这是 CLI 相对手工 curl 的核心增值。
- 校验类错误必须永不出网，因此 `USAGE` 判定必须在 transport 之前完成（见 ADR-0003）。
- 空结果返回 0 而非非零：实测查无结果时服务端仍返回 `isError=false`，若 CLI 把"0 条"当失败，
  会诱导调用方对无果查询做无意义重试。
- 分类器靠文本模式匹配，服务端文案变更会削弱它。缓解：`tests/contract/` 断言模式仍命中，
  且未命中时降级为 `TOOL_ERROR`（保守、不重试），不会误判为可重试。
