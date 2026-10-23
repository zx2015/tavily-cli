# ADR-0003: 客户端全量前置校验——保护共享 Key 池是本 CLI 的第一职责

状态：已接受（2026-10-22）

## 背景

`mcp-tavily` 是一个**共享**服务：mcp-host 上聚合 4 个 Tavily Key，供该机器上所有
agent/客户端使用，且**网关自身无任何鉴权与入参防护**。

调研期间发生的真实事故（完整链路见 `study/mcp-tavily-endpoint/README.md` §5）：

```
CLI 探针发送 {"query":"test","include_domains":["!!bad"]}
  → Tavily 上游返回 400 "All domains in include_domains are invalid"
  → 服务端 execute_with_retry 把它误分类到 401（鉴权失败）分支
  → 对 4 个 Key 逐个 set_error()
  → Key 状态机中 ERROR 是终态（check_status() 只让 COOLDOWN 自愈）
  → 此后所有工具一律 "No active API keys available in the pool."
  → 唯一恢复手段：docker restart mcp-tavily（实测 touch .env 无效——
     ConfigManager.reload() 只在 Key 列表内容真的变化时才重建）
```

也就是说：**一个手滑的域名参数，代价是整台服务器上所有使用者立即失去联网搜索能力**，
且不会自动恢复。事发后已在使用者批准下执行 `docker restart mcp-tavily` 恢复，6s 内搜索可用。

服务端该误分类应在服务端修复；但在修复之前与之后，客户端侧都必须有自己的防线——
因为 CLI 是本工作空间里唯一能被立即约束的一环，而且它还要面对"服务端 README 与 git 提交记录
滞后于运行代码"带来的契约不确定性（实测：容器与工作区源码 MD5 一致，但 README 参数表缺少
`timeout` 入参）。

## 决策

把校验层设为 **transport 之前的单向闸门**，并且宁严勿宽：

1. **全量前置校验**（design.md §6 真值表）：域名格式、枚举取值、数值范围、URL scheme、
   正则可编译、必填非空。任何一项不通过 ⇒ 退出码 2 且 **零字节出网**。
2. **只发用户显式指定的键**：不发送值为 `null` 的可选键。服务端 schema
   `additionalProperties:false`，实测 FastMCP 对多余键直接 `isError`。
3. **`--dry-run` 一等公民**：只执行校验并打印将要发出的 JSON-RPC 请求体，不发网络包。
   让使用者和 agent 能在"是否伤害共享服务"之外先自我确认。
4. **`tests/guard/` 永久回归**：monkeypatch 掉 socket 层，断言 §6 的每个非法用例
   "零 socket 写入"。事故用例 `include_domains=["!!bad"]` 是其中固定一条。
5. **不做"让服务端更宽容"的假设**：即使服务端日后修复了误分类，本闸门也保留——
   它的成本是本地几十毫秒，收益是把上游 400 类错误消灭在发出之前。
6. **默认节制**：并发默认 4 / 上限 8；`POOL_DEAD`/`TOOL_ERROR`/`USAGE` 永不自动重试
   （见 ADR-0002），避免 CLI 变成共享配额的 DoS 源。

## 后果

**正面**：只要经由本 CLI，就不会再触发 §5 那类击穿全池事故；错误在毫秒级返回且带
"正确写法示例"，比等一个 1.5s 的上游 400 再撞上误分类好得多。

**代价**：
- 校验规则与服务端真实行为存在漂移风险。规则写太严会拦掉本可成功的请求。
  缓解：① 规则来源标注（每条规则对应一条实测证据）；② `tavily-cli tools` 输出 `schema_hash`；
  ③ 运行时比对 `tools/list`，漂移时提示而非静默；④ 留 `--raw-arguments '<json>'` 逃生通道
  （明确标注"绕过闸门，风险自担"），供高级用户在确认过参数合法时使用。
- 多写约 200 行校验与守卫测试代码。相对于它保护的东西（一台机器上所有 agent 的搜索能力），
  这个成本可以接受。

## 配套建议（超出本 CLI 范围，需服务端仓库处理）

`mcp-tavily` 应把 Tavily 上游的 **400 BadRequest 归为"入参错误"**，而不是落到 401 分支；
并给 `ERROR` 状态加一条恢复路径（周期性重探或管理端点），使单个坏参数不至于永久击穿 Key 池。
本工作空间不修改 `/srv/git/mcp-tavily`，只记录该缺陷与复现步骤。
