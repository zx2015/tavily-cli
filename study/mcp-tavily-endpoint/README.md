# mcp-tavily 服务端接口实测报告

| 版本号 | 日期       | 变更说明                                     | 作者 |
|--------|------------|----------------------------------------------|------|
| v1.0.0 | 2026-10-22 | 首次对 mcp-host 上的 mcp-tavily 做全量协议探测，确立 tavily-cli 的接口契约与红线 | Qoder |
| v1.1.0 | 2026-10-22 | 复核服务端修复：400→401 误判已在运行容器堵住（§5.0）；`ERROR` 终态、过小 `timeout` 放大耗时、同错熔断缺失三项未落地，客户端约束一律不放宽 | Qoder |
| v1.2.0 | 2026-10-23 | 新增 §1.4：运行时已是 FastMCP 4.1.3，且 `serverInfo.version` 其实是**库版本**（修正 §1.3 的归因错误）；4 个工具的 `timeout` 入参被删除、枚举改为 schema 声明；容器↔工作区 19/19 `.py` 一致；据此 CLI 侧把 `--request-timeout` 改为纯本地读超时 | Qoder |
| v1.3.0 | 2026-10-23 | 新增 §4.1：真机 crawl/map 首次跑通，**修正 §4 里两条凭推断填写的出参**——`map` 的 `results` 是裸 URL 字符串、`crawl` 的页面无 `title`；另记 `example.com` 不可爬（返回空集合而非失败）；声明 map/crawl 两个 fixture 的 `results` 是空数组、不能当形状证据 | Qoder |

本报告是 tavily-cli 的**唯一事实来源**。所有结论来自对线上服务的实测（脚本见本目录
`probe_*.py`，原始响应见 `fixtures/`），而不是来自服务端 README——服务端 README 已滞后于
部署镜像（见 §1.3）。

---

## 1. 部署事实

### 1.1 宿主与容器

| 项 | 值 |
|----|-----|
| 宿主 | 局域网内一台跑共享 Docker 服务的主机，本文记作 `mcp-host`（主机名、地址与登录方式不公开） |
| 宿主系统 | 通用 Linux 发行版 + Docker（具体版本与本报告结论无关） |
| 容器 | `mcp-tavily`，镜像 `mcp-tavily-mcp-tavily` |
| 端口映射 | 宿主 `0.0.0.0:18000` → 容器 `8000`（**监听 0.0.0.0，局域网可直接访问**） |
| Compose 源码 | 网关运维侧的 `docker-compose.yml`（内部路径不公开） |
| 进程 | `python -u app/main.py`，基础镜像 Python 3.12.13，框架 FastMCP |
| 关键环境变量 | `MCP_PATH=/mcp`、`PORT=8000`、`TAVILY_REQUEST_TIMEOUT=15`、`MONITOR_INTERVAL`（默认 10 分钟）、`HTTP(S)_PROXY`（指向内网代理，地址不公开） |

**从开发机直连 `http://mcp-host:18000/mcp` 已验证可达**，无需 SSH 隧道。隧道仅作为
网络受限时的降级路径（见 design.md §8）。CLI 的内置默认端点是 `http://127.0.0.1:18000/mcp`，真实网关地址由 `--endpoint`／配置文件给出。

### 1.2 服务端能力

- 传输：**仅 Streamable HTTP**。无 stdio、无 SSE-only、**无鉴权**（无 OAuth / 无 API Key /
  无 token），安全完全依赖"只在局域网暴露"这一网络层隔离。
- 4 个工具：`tavily-search`、`tavily-extract`、`tavily-crawl`、`tavily-map`。
- `initialize` 宣告的 capabilities：`logging`、`prompts{listChanged}`、
  `resources{subscribe:false,listChanged}`、`tools{listChanged}`。
  实测 `prompts/list` 与 `resources/list` 均返回**空数组** → CLI 不必实现这两条路径。
- 协议版本协商：`2025-03-26` 与 `2025-06-18` 均被接受并原样回显。
- 聚合层行为：多 Key 平滑加权轮询（用量低者优先）；429 → 该 Key 冷却 60s；401 → 标记
  `ERROR`；其余 5xx/未分类异常 → 换 Key 重试但不改状态；DNS/连接类错误 → **同一 Key 上**
  指数退避重试（0.5s→1.0s，最多 2 次）。

### 1.3 ⚠️ 服务端 README 滞后于运行代码（初次推断已修正）

| 来源 | 版本 / 状态 |
|------|-------------|
| `initialize` 返回的 `serverInfo.version` | **4.1.0**（2026-10-23 复核：该字段其实是 **FastMCP 库版本**，见 §1.4） |
| 服务端仓库 `README.md` 变更表最新条目 | v3.4.7 |
| 服务端仓库 `git log` HEAD | 一个 v3.4.4 系列的提交（哈希略） |
| 服务端仓库**工作区**状态 | `app/main.py`、`app/tasks/monitor.py`、`docker-compose.yml`、`docs/**` 均有**未提交改动** |

**修正后的结论**（后续用 MD5 逐个核对得到）：容器 `/app` 与仓库**工作区**的 12 个 `.py` 文件
**全部一致（12/12 SAME）**。也就是说运行代码 = 工作区源码；真正滞后的只有 README 与 git HEAD。
**读工作区源码是可靠的**，读 README 不可靠。

（本节初稿曾判断"镜像领先源码树"，那是只比对了 README 版本表与 `serverInfo` 得出的错误推断，
未检查工作区 `git status`。修正过程记录在此以备追溯。**第二处错误**当时没看出来：初稿把
`serverInfo` 4.1.0 归因于"未提交的 `main.py`"，§1.4 已用源码证据推翻——它是 FastMCP 的库版本。）

`timeout` 入参的记载状态也随版本翻转（详见 §1.4）：4.1.0 时 README 未记而线上 4 个工具都有；
4.1.3 起线上 4 个工具又都**不再有** `timeout`。

**对 CLI 的直接影响**：不得把参数 schema 硬编码后就不再校验；必须在运行时以
`tools/list` 为权威 schema 做参数对齐（详见 design.md §6）。

### 1.4 2026-10-23 06:25 复核：运行中已是 FastMCP 4.1.3，`timeout` 入参被删除

| 证据 | 实测值 | 采集方式 |
|------|--------|----------|
| `serverInfo.version` | **4.1.3** | `tavily-cli doctor` / `initialize` |
| 容器内 `import fastmcp; fastmcp.__version__` | **4.1.3** | `docker exec mcp-tavily python -c ...` |
| 工作区 `requirements.txt` / `Dockerfile` | `fastmcp==4.1.3`（**未提交**；HEAD 仍是 `fastmcp==3.2.0`） | `git show HEAD:requirements.txt` |
| `app/main.py` 构造 | `super().__init__("mcp-tavily", lifespan=...)` — **不传 version** | 源码 |
| ⇒ 结论 | `serverInfo.version` 报的是 **FastMCP 库版本**，应用自身版本只在服务端仓库文档里（README v3.5.0 / PRD v1.4.4） | — |
| 容器 ↔ 工作区 `.py` | **19/19 一致**（含 `tests/`） | 逐文件 md5sum 排序后 diff |
| 镜像 / 容器 | 镜像 10-22 22:06 重建，容器 10-23 03:03 重新创建 | `docker inspect` |
| `tools/list` 的 4 个工具 | **均无 `timeout` 入参**；`search_depth`/`topic`/`time_range`/`extract_depth` 改为在 schema 里声明 `enum` | `probe_tools_list.py` 刷新 fixture |
| 服务端源码注释 | `app/main.py:171`「timeout 通过 Depends 注入，FastMCP 不会把服务端请求预算暴露到模型 Schema」 | 源码 |
| 上游超时来源 | `_configured_tool_timeout()` 读 `TAVILY_REQUEST_TIMEOUT`，缺省 **15s**（`app/main.py:28`，在 199/245/279/320 四处以 `Depends` 注入） | 源码 |
| 客户端再发 `timeout` 的后果 | `isError=true`：`1 validation error for call[tavily_search] timeout Unexpected keyword argument`（**不走上游、不污染 Key 池**） | 真机单次探测 |

**对 CLI 的直接影响**：

1. `--request-timeout` **不可能再透传**给服务端 ⇒ 重定义为本调用的**本地 HTTP 读超时**（决策 D-6）。
2. "过小 `timeout` 在每个 Key 上各退避重试 2 次"这条客户端风险**消失**；风险面移到运维侧的
   `TAVILY_REQUEST_TIMEOUT` 配置。
3. 枚举允许取值改由 schema 提供 ⇒ `schema.py` 删掉手工 `_ENUMS`，`_RULES` 只留 schema
   表达不了的约束。
4. `serverInfo.version` 不得当作服务端应用版本展示或据此判断契约（它跟着 FastMCP 走）。

---

## 2. 协议层实测细节

### 2.1 必须走 session

```
POST /mcp  (不带 mcp-session-id) → HTTP 400
{"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"Bad Request: Missing session ID"}}
```

标准调用序列（实测可用）：

```
1) POST initialize                  → 响应头 mcp-session-id: <hex32>
2) POST notifications/initialized   → HTTP 202，无响应体
3) POST tools/list | tools/call     → 请求头带上第 1 步的 session id
```

### 2.2 响应是 SSE 分帧，不是裸 JSON

即使 `Accept: application/json, text/event-stream`，服务端仍返回
`content-type: text/event-stream`，body 形如：

```
event: message\r
data: {"jsonrpc":"2.0","id":1,"result":{...}}\r
\r
```

CLI 解析器必须：按行取 `data:` 前缀、剥离前缀后 `json.loads`、忽略 `event:`/空行/心跳注释行。
**不能**假设单次响应只有一帧。

### 2.3 只有 /mcp 一个路由

```
GET / → 404      GET /health → 404     GET /usage → 404
GET /docs → 404  GET /metrics → 404    GET /mcp/health → 404
```

服务**没有 HTTP 健康检查端点**。探活只能用 MCP 的 `initialize`（服务端 README 也是这么建议的）。
CLI 的 `doctor` / `ping` 子命令必须走 `initialize` + `tools/list`，不能走 `/health`。

---

## 3. 工具入参契约（来自线上 `tools/list`，见 fixtures/tools_list.json）

`additionalProperties: false` —— **传任何未声明的键都会被 FastMCP 拒绝**。

| 工具 | 必填 | 可选参数（含默认值） |
|------|------|----------------------|
| `tavily-search` | `query` (string) | `search_depth`(basic\|advanced, 默认 basic)、`topic`(general\|news\|finance, 默认 general)、`days` (int\|null)、`max_results`(int, 默认 5, README 称上限 20)、`include_images`(bool,false)、`include_answer`(bool,false)、`include_raw_content`(bool,false)、`include_domains`(string[]\|null)、`exclude_domains`(string[]\|null)、`time_range`(day\|week\|month\|year\|null)、`include_image_descriptions`(bool,false) |
| `tavily-extract` | `urls` (string[]) | `extract_depth`(basic\|advanced,默认 basic)、`include_images`(bool,false) |
| `tavily-crawl` | `url` (string) | `max_depth`(int)、`max_breadth`(int)、`limit`(int)、`instructions`(string)、`select_paths`(string[])、`exclude_paths`(string[])、`include_images`(bool,false)、`allow_external`(bool,false) |
| `tavily-map` | `url` (string) | `max_depth`(int)、`limit`(int)、`select_paths`(string[]) |

注（2026-10-23 更新）：**4.1.3 起枚举已是真正的 JSON Schema `enum` 约束**。
**推断**（未真机验证——验证要故意向共享服务发一个非法枚举，属红线 1 禁止范围）：
非法 `search_depth`/`topic`/`time_range`/`extract_depth` 取值应被 FastMCP 在层内拒绝、不再打到上游。
本表 2026-10-22 首次采集时（4.1.0）枚举是宽松的 `{"type":"string"}`、且 4 个工具都带
`timeout`(number) 入参——§5 事故的入口与"过小 `timeout` 放大耗时"都是在 4.1.0 上实测得到的，
那两条路径在 4.1.3 上都已对客户端关闭（见 §1.4）。

---

## 4. 工具出参契约（实测样本见 fixtures/）

`tools/call` 结果同时给出两种表示，**内容重复**：

- `result.content[0].text`：一个 JSON **字符串**（需二次 `json.loads`）；
- `result.structuredContent`：已解析的对象。

CLI 应优先取 `structuredContent`，仅在缺失时回退解析 text。

| 工具 | `structuredContent` 顶层键 | 列表元素键 |
|------|---------------------------|-----------|
| `tavily-search` | `query`, `follow_up_questions`, `answer`, `images`, `results`, `response_time`, `request_id` | `results[]`: `url`, `title`, `content`, `score`, `raw_content`, `id` |
| `tavily-extract` | `results`, `failed_results`, `response_time`, `request_id` | `results[]`: `url`,`title`,`raw_content`,`images`；`failed_results[]`: `url`,`error` |
| `tavily-map` | `base_url`, `results`, `response_time`, `request_id` | ⚠️ `results[]` 是**裸 URL 字符串**，不是对象（见 §4.1） |
| `tavily-crawl` | `base_url`, `results`, `response_time`, `request_id` | `results[]`: `url`, `raw_content`（实测**没有** `title`，见 §4.1） |

其它可观测事实：
- `include_answer` 未在 CLI 侧显式开启时，`answer` 为 `null`；开启后返回 AI 简答文本。
- 服务端在 `result._meta` / `usage` 上**不返回**配额信息（实测无 `usage` 字段），
  所以 CLI 无法从响应里读到剩余额度，配额状态属于服务端黑箱。
- 空结果不等于错误：查无结果时仍返回 `isError=false` 与 `results` 数组（实测 nresults 与
  `max_results` 相关）。CLI 不能用"结果数量"判断成功与否。

### 4.1 `tavily-crawl` / `tavily-map` 出参实测（2026-10-23 07:55–08:20）

这两行是本文原先**唯一凭推断填写**的出参，真机跑下来两条都不对：

| 事实 | 实测数据 | 对 CLI 的影响 |
|------|----------|----------------|
| `map` 的 `results` 是**字符串数组** | `map https://docs.tavily.com --limit 5` → `["https://docs.tavily.com/", …]`（5 个裸 URL，`服务端耗时 0.07s`） | 渲染层按 dict 取键会 `AttributeError: 'str' object has no attribute 'get'`。`build_envelope` 现已把字符串归一化成 `{"url": …}`，`-f raw` 仍原样透传 |
| `crawl` 的页面**没有 `title`** | `crawl https://docs.tavily.com --max_depth 1 --max_breadth 2 --limit 2` → 2 页，条目键只有 `url` + `raw_content`（6090 / 20277 字符） | `table` 的标题列按"整列皆空则省略"自动消失，实际表头 `序号 \| 网址 \| 原文` |
| 不可爬的站点返回**空集合而非失败** | `crawl https://example.com --max_depth 1 --max_breadth 2` → `成功: true`、`results: []`、`failed_results` 缺失、`服务端耗时 0.37s` | 契约闸门不能拿 `example.com` 当 crawl/map 目标：`isinstance(页面, list)` 这类断言在空载荷上恒真 |
| 耗时量级 | `map` 0.07–0.3s、`crawl`（2 页）0.4–0.6s，均远低于 120s 默认读超时 | §4.5 的 120s 默认对这两个站点是过度保守，但 crawl 页数上去以后仍不可预测，保持不变 |

> ⚠️ **`fixtures/out_tavily-map_sample.json` 与 `out_tavily-crawl_sample.json` 的 `results` 都是空数组**，
> 是早期探测留下的，**不能**用作形状证据（上面这些崩溃正是被它们掩盖的）。刷新需要 1 次 crawl + 1 次 map：
> `TAVILY_CONTRACT_HEAVY=1 TAVILY_CONTRACT_QUOTA=1 .venv/bin/python -m pytest tests/contract/test_minimal_calls.py -q -m network`；
> 本次交付没有重写这两个文件，因为**重建的样本不是真机抓的**，宁可留空数组并在此声明。

---

## 5. 🔴 核心风险：一次非法入参可击穿共享 Key 池

这是本次调研最重要的发现，直接决定了 CLI 的设计取向。

### 5.0 状态更新（2026-10-22 22:35 复核）：主修已生效，风险降级但未消除

网关运维侧已落地补丁，**运行中的容器已加载**：

| 证据 | 实测判据（主机内部路径与文件哈希不公开） |
|------|--------|
| 进程启动时刻 | **晚于**补丁文件 mtime ⇒ 排除"改了没生效" |
| 宿主↔容器 | 同路径文件逐字节一致（md5sum 相同） |
| 关键代码 | `if isinstance(e, BadRequestError): raise`（227 行，位于网络退避与 401 判定之前）；401 分支改用 `InvalidAPIKeyError` / `http status 401` 正则 / `unauthorized` / `invalid api key`，裸 `"invalid"` 子串已删除 |

**修复后的语义**：`include_domains:["!!bad"]` 这类 Tavily 400 立即上抛，
返回 `isError=true` 但**不改任何 Key 状态、不轮换 Key**（一次坏请求的上游调用从 4 次压回 1 次），
Key 池不再因此永久死亡。

**仍未落地**（详见 docs/adr/0003-validate-before-send.md）：

1. `ERROR` **依旧是终态**：`key.py::check_status()` 仍只让 `COOLDOWN` 自愈 ⇒ 恢复手段仍只有
   `docker restart mcp-tavily`，退出码 6 的设计前提不变。
2. **同错熔断缺失**：若某类请求级错误不被 `tavily` SDK 类型覆盖，仍会轮换打满 4 个 Key（浪费配额，但不误标 `ERROR`）。
3. **过小 `timeout` 的放大效应仍在服务端代码里**：`_is_network_error()` 关键词表仍含 `timeout` /
   `timed out`，`tavily.TimeoutError` 仍在每个 Key 上各退避重试 2 次（4.1.0 实测 ~7.6s）。
   但 **4.1.3 起客户端无法再注入这个值**（§1.4），该路径只剩运维侧 `TAVILY_REQUEST_TIMEOUT` 配错时才会触发。
4. 补丁**在采集时点尚未提交**到服务端仓库（工作区有大量 ` M` 文件，含把 `fastmcp` 从 `3.2.0`
   提到 `4.1.3` 的 `requirements.txt`/`Dockerfile`）⇒ 重建镜像或回滚可能丢失。
   镜像重建、容器重新创建之后，`manager.py` 与上表仍逐字节一致 ⇒ "修复已生效"继续成立。

⚠️ 本节以下 §5.1–§5.5 均为**修复前**的实测记录，保留作为事故回溯与判据来源；
其中导致全池 `ERROR` 的那条链路（§5.1–§5.3）已不再成立，其余行为（SSE 分帧、session 强制、
`additionalProperties:false` 等）**未变**。

### 5.1 复现

```json
{"name":"tavily-search",
 "arguments":{"query":"test","include_domains":["!!bad"]}}
```

### 5.2 实际发生链路（服务端日志原文摘录）

```
WARNING Key tvly...H7vv failed: All domains in include_domains are invalid: ['!!bad'].
ERROR   [Key失效] 第 1 个 Key（尾号 ttH7vv）鉴权失败，已标记为 ERROR。原始错误: All domains ...
... 对第 2/3/4 个 Key 重复同样判定 ...
ERROR   No active Tavily API keys available.
```

随后**所有**工具调用一律失败：

```
Error calling tool 'tavily-map': No active API keys available in the pool.
```

### 5.3 根因

Tavily 上游对这个入参返回的是 **400 BadRequest**，但服务端 `execute_with_retry` 的错误分类
把它落到了 **401（鉴权失败）** 分支，于是 `set_error()`。而 Key 状态机里：

```python
# app/core/key.py
def check_status(self):
    if self.status == KeyStatus.COOLDOWN:      # 只有 COOLDOWN 会自愈
        if datetime.now() >= self.cooldown_until: self.set_active()
    return self.status
```

`ERROR` 是**终态**，没有任何定时器或监控任务会把 Key 从 `ERROR` 恢复成 `ACTIVE`
（`EXHAUSTED` 只在使用量回落时恢复）。4 个 Key 全部 `ERROR` ⇒ 池永久死亡。

### 5.4 恢复手段（实测验证）

| 手段 | 是否有效 | 依据 |
|------|----------|------|
| 等待冷却 | ❌ 无效 | `ERROR` 非 `COOLDOWN`，`check_status()` 不处理 |
| `touch .env` 触发热加载 | ❌ 无效 | `ConfigManager.reload()` 仅在 `old_raw_keys != new_raw_keys` 时才重建 Key 列表 |
| `docker restart mcp-tavily` | ✅ 有效 | **已实测**：重启后 6s 内搜索恢复，池回到 ACTIVE |

2026-10-22 18:44 因本次探测导致服务瘫痪，经使用者批准后于稍后执行 `docker restart mcp-tavily` 恢复。

### 5.5 其它入参的行为差异（同样重要）

| 输入 | 结果 | 是否污染 Key 池 |
|------|------|------------------|
| 缺必填 `query` | `isError=true`，text 为 `1 validation error for call[tavily_search] ... Missing required argument` | ❌ 不污染（FastMCP 层拦下，未走 Key 循环） |
| 传未声明键 `bogus` | `isError=true`，`unexpected_keyword_argument` | ❌ 不污染 |
| `query` 传数字 | `isError=true`，`string_type` 校验错 | ❌ 不污染 |
| `include_domains:["!!bad"]` | `isError=true`，Tavily 400 | 修复前 ✅ **污染：全池 ERROR**；修复后（§5.0）❌ 不污染，400 立即上抛、不轮换 Key |
| `timeout: 0.001` | 7.6s 后 `isError=true`，`Request timed out after 0.001 seconds` | ⚠️ 被判定为网络错误，在**每个 Key 上**各做 2 次退避重试，白耗 ~7.6s 并拖慢调用方。**4.1.3 起客户端再也发不进这个键**（§1.4，改由运维侧 `TAVILY_REQUEST_TIMEOUT` 决定），本行只作历史实测保留 |
| 工具名拼错 | `isError=true`，text `Unknown tool: 'nope'` | ❌ 不污染 |

### 5.6 对 CLI 的强制约束

服务端主修落地后，这四条**一条都不放宽**——补丁**尚未提交**、`ERROR` 仍是终态、同错熔断缺失、
且"零出网"本身就是 CLI 对调用方承诺的契约（"过小 `timeout` 放大耗时"从 4.1.3 起已非客户端可达路径，
不再作为理由，见 §1.4）：

1. **本地先行校验**：域名格式（必须带合法后缀，如 `tavily.com` 而非 `tavily`）、枚举取值
   （4.1.3 起 `search_depth`/`topic`/`time_range`/`extract_depth` 已在 schema 里声明 `enum`，
   直接读它，不再手工维护）、数值范围（`max_results` ≤ 20）必须在**发出请求前**于客户端校验完毕，
   不合法就退出，绝不发包。`timeout` **已不是 MCP 参数**，客户端发它就是"未声明键"违例。
2. **区分错误类别**：`isError=true` 不是"可重试"信号。校验类/池死亡类错误重试只会加剧污染。
3. **专项识别池死亡**：`No active API keys available in the pool` 必须映射到专用退出码，
   并在 stderr 明确告知"服务端 Key 池已进入 ERROR 终态，需要 `ssh mcp-host docker restart mcp-tavily`"，
   而不是让调用方以为是网络问题。
4. **不暴露危险默认值**：`--request-timeout` 只作用于**本地** HTTP 读超时，下限 1.0s——
   比上游真实耗时更小的值会让调用方刚发出就自己超时（退出码 7），而不是伤害 Key 池。

---

## 6. 性能与并发实测

| 场景 | 端到端耗时（含本机往返与握手后复用 session） |
|------|-----------------------------------------------|
| `tavily-search` basic，`max_results=2~3` | 1.5s |
| `tavily-search` advanced + `topic=news` + `days=3` | 4.1s |
| `tavily-extract`（2 个 URL，含 1 个无效域） | 0.5s |
| `tavily-map` example.com `limit=3` | 6.8s |
| `tavily-crawl` example.com `max_depth=1,limit=2` | 0.4s |
| 单 session 并发 5 路 search | 全部 200 成功；整体墙钟 3.79s，单次 2.4~3.8s |

要点：
- 服务端 `TAVILY_REQUEST_TIMEOUT=15`，即上游单请求 15s 封顶；服务端 README 另提到"客户端
  60s 硬超时"。CLI 默认超时建议 **45s**，`crawl`/`map` 类深任务放宽到 **120s**。
- **session 可复用且支持并发**，无需每次调用重新 `initialize`（握手本身约 0.1s 量级）。
- 并发在服务端是被支持的（多 Key 轮询），但 CLI 仍应把默认并发限制在 4，避免无节制消耗共享配额。

---

## 7. 客户端库选型实测

| 方案 | 冷启动 | 结论 |
|------|--------|------|
| 官方 `mcp` SDK **2.3.0**（`uv pip install mcp`） | `import mcp` + client 子模块 **≈0.87s**（纯 Python 解释器启动 ≈60ms） | 入口名已从 1.x 的 `streamablehttp_client` **改名为 `streamable_http_client`**；且签名 `(url, *, http_client=None, terminate_on_close, max_sse_event_size)` **没有 headers 参数**，想自定义 header 必须自己注入 `httpx2.AsyncClient`。`CallToolResult` 字段为 snake_case（`structured_content`），靠 alias 映射线上 JSON 的 `structuredContent` |
| 标准库 `urllib` 自研极薄传输层 | 约 **80ms**（含 `import urllib.request, json, time`） | 协议面极小（4 个 JSON-RPC 方法 + SSE 取 `data:` 行 + 1 个 session header），本报告 §2 已给出全部所需细节 |

选型结论与权衡记录见 `docs/adr/0001-transport-layer.md`。

---

## 8. 尚未解决 / 待后续确认

- **配额可见性**：服务端不暴露 `/usage`，MCP 响应里也没有 usage 元数据。CLI 无法预警
  "还剩多少额度"，只能靠失败信息事后判断。是否为 tavily-cli 增加"配额探测"能力，需要
  服务端先提供端点（可列入对服务端仓库的改进建议）。
- **服务端 bug 归属**：§5 的 400→401 误分类属于 `mcp-tavily` 仓库缺陷，应在服务端修复；
  tavily-cli 的本地校验只是**客户端侧的防护措施**，不能替代服务端修复，也无法防护其他调用方。
- **`max_results` 上限 20** 来自 README 描述，未实测验证（受配额限制未做压测）。
- **`time_range` 与 `days` 的相互作用**、`finance` topic 的实际支持度未验证。
- 服务重启后 Key 池 ACTIVE，但**长期跑是否会把 dev key 配额耗尽**未观察（dev key 额度较低）。
