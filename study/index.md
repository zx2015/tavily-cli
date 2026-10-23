# Study Index

| 版本号 | 日期       | 变更说明 | 作者 |
|--------|------------|----------|------|
| v1.1.0 | 2026-10-22 | 新增服务端 Key 池误判缺陷根因分析与修复建议 | Qoder |
| v1.0.0 | 2026-10-22 | 首版：mcp-tavily 服务端全量协议探测与 Key 池故障模式研究 | Qoder |

`study/` 存放**调研证据**：探针脚本、线上原始响应样本、结论报告。
此目录内容不得被 `src/` import；它是设计与测试的输入，不是实现的一部分。

## mcp-tavily-endpoint/

- [README.md](mcp-tavily-endpoint/README.md) — **接口契约事实来源**。部署事实、协议层细节
  （session 强制、SSE 分帧、无 /health）、4 个工具入参出参、性能与并发实测、客户端库选型实测、
  以及 §5 记录的"一次非法入参击穿共享 Key 池"事故全链路与恢复手段。
- 上述事故的**根因分析与修复方案**已并入 [ADR-0003](../docs/adr/0003-validate-before-send.md)：
  400 被误判成鉴权失败的分支位置、同错熔断判据、`ERROR` 终态的恢复方案。
  服务端代码的修复动作由网关运维侧执行，不在本仓库。
- `probe_basic.py` — 握手 + `tools/list` + 一次真实搜索；最简探活。
- `probe_error_paths.py` — 错误路径测绘：缺参/多余键/类型错/非法域名/过小 timeout/未知工具/
  无 session/并发。⚠️ 含会污染 Key 池的用例，注释里标明前置条件（仅在可牺牲实例上跑）。
- `probe_shapes.py` — 4 个工具的 `structuredContent` 结构抓取 + 5 路并发墙钟测量。
- `fixtures/tools_list.json` — 线上 `tools/list` 完整原始响应（4 工具权威 schema）。
- `fixtures/out_tavily-*_sample.json` — 各工具一次真实调用的完整原始结果，离线渲染测试的数据源。

### 重新抓取

```bash
cd study/mcp-tavily-endpoint && python3 probe_shapes.py   # 需要能连通 203.0.113.10:18000
```

抓取后请检查无密钥泄漏：`grep -rnoE "tvly-[A-Za-z0-9_-]{8,}" fixtures/` 必须无输出。
