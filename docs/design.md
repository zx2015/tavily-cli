# tavily-cli 技术设计

| 版本号 | 日期       | 变更说明 | 作者 |
|--------|------------|----------|------|
| v0.9.0 | 2026-10-23 | §11 的「冒烟」行改为**部分联网**：`scripts/smoke.sh` 末段新增 4 条零出网 `batch` 用例（§9 的 22/25），并记下为什么需要新的 `codin()` 助手——`code()` 不带 stdin 重定向，而 `batch` 拒绝终端 tty | Qoder |
| v0.8.0 | 2026-10-23 | **M3 实现回写**：§3 补"batch 每行各过一次校验闸门"；§4 新增两行（`commands/batch.py` 的输入面签名、`cli.py` 的批量编排 + **六个 handler 统一六位置参数、第 6 个是注入的 stdin**）；§5 新增第 7 条并发要点（session 合流用**锁内检查**而非双检锁——上一版文档写的"双检锁"与代码不符，已连带修正 requirements §9-23；`id` 自增无锁是实测过的非正式保证，free-threaded 构建下必须改）；§9 的 `KEY_MAP` 增 `batch` 段（`行`/`关联编号`/`请求`）并写明两个逐行文档助手，`--dry-run` 的内层 `request` 属协议面不过映射；§11 增第四类测试（并发时序用 Barrier/卡 `initialize` 的替身，不用 `sleep`）并记录 `mcp_stub` 的 `SERVER_TOOLS` 默认值/`fail_methods`/`calls()`；§12 增 `batch` 的 **N+3** 请求预算与墙钟公式；§13 把"并发 4/上限 8"扩成完整的批量滥用节制清单（含"零出网路径优先于预检"这条被守卫抓回来的实现教训） | Qoder |
| v0.7.0 | 2026-10-23 | M2 真机验收回写：§9 新增**条目形状归一化**（`_BARE_STRING_KEY`，`map` 的裸 URL 字符串 → `{"url": …}` 记录；`crawl` 页面无 `title` 时表头整列省略），对应需求新增 **D-8**；§11 "最重要的测试"由两类扩为三类，写明契约断言**不得被空载荷骗过**（`example.com` 返回 0 页让旧断言恒真），并声明 map/crawl 两个 fixture 的 `results` 是空数组、不能当形状证据 | Qoder |
| v0.6.0 | 2026-10-23 | 隧道真机演练（零配额）回写 §8：新增"`on` 的施加位置在校验与 `--dry-run` 之后（故对全部子命令生效）"、`_call_with_fallback`/`_list_tools` 两个助手（`tools/list` 的传输失败改走分类器）、`doctor` 的 `auto` 刻意不自行 spawn、`pgrep -f` 只能锚定 `-L <port>:…` 且会匹配到自身；同时标注本地无代理 opener 这一条**本次演练未能单独证明**（本机 `no_proxy` 已含 `127.0.0.1`），仍只有离线断言 | Qoder |
| v0.5.0 | 2026-10-23 | 与 M2 实现同步：§4 的 `render`/`tunnel` 签名改成落地后的真实签名；§8 补"隧道端点是 127.0.0.1，必须用无代理 opener，否则又被 `http_proxy` 送回那台连不上的机器"；§9 着色条目从"M1 不着色"改写为 M2 的实际规则（只在 TTY、只前景 SGR、`-o` 与机读格式恒无色）；§10 两级 toml 配置文件已由标准库 `tomllib` 落地 | Qoder |
| v0.4.0 | 2026-10-23 | 跟随服务端 4.1.3 漂移：§3 图示改为版本中性；§5 超时条目写清 `--request-timeout` 只覆盖本地读超时；§6 该行改到配置层并新增"枚举直接读 schema、不再手工维护 `_ENUMS`"；§tests 记录 `tests/contract/` 的三档配额闸门（D-6/D-7） | Qoder |
| v0.3.0 | 2026-10-22 | 与 M1 实现同步：§6 把 `instructions` 从"正则试编译"里拆出（运行时 schema 是 `anyOf[string,null]`）并写实 `urls` 规则；§9 明确 M1 不输出 ANSI；§10 收窄为 CLI > env > 默认值、toml 两级归 M2，并记录 `urllib` 会遵循 `http_proxy` 这一实测事实 | Qoder |
| v0.2.0 | 2026-10-22 | 落地使用者决策：入口改名 `tavily-cli`；§9 重写为"内部英文模型 + 渲染层单点中文键名映射 + `--keys-en`"；安装方式改为可编辑安装进本机 `.venv` | Qoder |
| v0.1.0 | 2026-10-22 | 首版设计：分层架构、传输层选型、校验前置流水线、错误分类模型 | Qoder |

上游依据：`docs/requirements.md`（需求）+ `study/mcp-tavily-endpoint/README.md`（服务端实测事实）。
本文只讲"怎么实现"，不重复"要什么"。

---

## 1. 设计原则（由实测事实倒推）

1. **校验先于网络**：客户端是共享 Key 池的最后一道防线。任何参数在进入 transport 前必须
   已通过静态 schema + 语义规则双重校验（研究文档 §5 的 400→401 误判事故是硬约束，不是建议）。
2. **不信任 `isError`**：MCP 层的 `isError=true` 只说明"工具没成功"，不说明可否重试。重试
   决策由错误分类器决定，而不是由 HTTP 码或 isError 决定。
3. **stdout 只有数据**：日志、进度、错误一律 stderr。
4. **进程即调用**：为 agent 高频调用设计，冷启动预算 ≤150ms，避免导入重型 SDK（ADR-0001）。
5. **契约漂移可观测**：内置 schema 是缓存，`tools/list` 是权威，二者不一致必须告知而非静默。

## 2. 目录结构

```
tavily-cli/
├── AGENTS.md                  # 给后续 agent 的工作约定（红线/流程/验收）
├── README.md                  # 项目入口：是什么、怎么装、最小可用示例
├── pyproject.toml             # 打包元数据；`.venv/bin/pip install -e ".[dev]"` 装入口 tavily-cli
├── .gitignore
├── docs/
│   ├── requirements.md        # 需求文档（需求基线，改动需谨慎）
│   ├── design.md              # 本文
│   └── adr/                   # 决策记录：一条决策一个文件，只增不删
│       ├── 0001-transport-layer.md
│       ├── 0002-error-taxonomy-and-exit-codes.md
│       └── 0003-validate-before-send.md
├── study/                     # 调研与证据（不可被代码 import）
│   ├── index.md
│   └── mcp-tavily-endpoint/
│       ├── README.md          # 服务端实测报告 = 接口契约事实来源
│       ├── probe_*.py         # 可复跑的探针脚本
│       └── fixtures/          # 线上抓到的原始响应样本，离线测试的数据源
├── src/tavily_cli/            # 实现
│   ├── __init__.py            # __version__ 单点定义
│   ├── __main__.py            # python -m tavily_cli
│   ├── cli.py                 # argparse 装配 + 命令分发（不含业务逻辑）
│   ├── config.py              # CLI>env>file 三级配置合并
│   ├── schema.py              # 内置静态 schema + 域名/枚举/范围校验规则 + schema_hash
│   ├── validate.py            # 语义校验流水线，产出 ValidationReport
│   ├── transport.py           # Streamable HTTP：initialize/session/SSE 读写/超时/重试
│   ├── session.py             # session 生命周期与失效重握手（至多 1 次）
│   ├── classify.py            # 错误分类器 → ErrorKind → 退出码
│   ├── render.py              # json/ndjson/table/md/raw 渲染；东亚宽字符列宽
│   ├── tunnel.py              # SSH 隧道建立/复用（--tunnel auto）
│   ├── commands/              # 每个子命令一个文件，只做参数→arguments 映射
│   │   ├── search.py extract.py crawl.py map.py tools.py doctor.py batch.py
│   └── constants.py           # 端点默认值、超时默认、退出码常量
├── tests/
│   ├── unit/                  # 纯逻辑，禁网；用 fixtures 驱动
│   ├── contract/              # 对真实端点的契约测试，标记 @network，默认不跑
│   └── guard/                 # 防污染回归：非法入参不得产生任何 socket 写入
└── scripts/
    ├── tunnel.sh              # 手工建隧道的便捷脚本（等价 --tunnel on）
    └── smoke.sh               # 装了 CLI 之后的端到端冒烟
```

约定：`study/` 只放证据与探针，**代码不得 import study/**；`fixtures/` 是测试数据源，
不是断言对象（服务端会变）。

## 3. 分层架构

```
用户 / agent / shell
        │
        ▼
┌───────────────────────────────────────────────┐
│ cli.py        解析 argv → CommandSpec          │  不做业务
├───────────────────────────────────────────────┤
│ commands/*    CommandSpec → mcp arguments      │  字段映射（kebab→camel/snake）
├───────────────────────────────────────────────┤
│ validate.py   ★校验闸门★                       │  失败 ⇒ 退出码 2，零网络
│   ① 静态 schema：键名存在、类型正确、无多余键  │
│   ② 枚举：depth/topic/time_range               │
│   ③ 语义：域名正则、范围、URL scheme、正则可编译│
│   ④ 组合规则：days 仅在 topic=news 生效         │
├───────────────────────────────────────────────┤
│ session.py    initialize → session-id → notify │  至多一次重握手
├───────────────────────────────────────────────┤
│ transport.py  POST /mcp · SSE 取 data: 行      │  超时/连接错误/退避
├───────────────────────────────────────────────┤
│ classify.py   文本/码 → ErrorKind → exit code  │
├───────────────────────────────────────────────┤
│ render.py     structuredContent → 输出格式      │
└───────────────────────────────────────────────┘
        │
        ▼  HTTP (直连优先，失败按 --tunnel 降级)
  mcp-tavily @ 203.0.113.10:18000/mcp（FastMCP 4.1.3；版本以运行时 serverInfo 为准）
```

关键设计：**校验层是单向闸门**，它在 transport 之前，且 `--dry-run` 时它是唯一执行的层。
`batch` 不新开一条流水线：每一行**各自**过一次这个闸门（`_plan_batch_line` → `validate.validate`），
所以坏行只失败自己那一行，而整批的"非法入参零 socket 写入"保证与单命令**同等强度**。

## 4. 模块职责与关键接口

| 模块 | 对外接口（签名级） | 备注 |
|------|--------------------|------|
| `schema.py` | `TOOL_SCHEMA: dict[str, ToolSpec]`、`schema_hash() -> str`、`validate_domain(s) -> bool` | 域名规则直接采用 Tavily 报错原文语义：必须有合法后缀（`tavily.com` ✅ / `tavily` ❌） |
| `validate.py` | `validate(tool, args) -> ValidationReport` | `ValidationReport(errors: list[FieldError])`；永不抛异常，返回结构化结论 |
| `transport.py` | `McpHttp(endpoint, timeout)`：`.initialize() -> session_id`、`.call(tool, args) -> CallResult`、`.list_tools() -> list[dict]` | 只认 4 个 JSON-RPC 方法；SSE 解析见 §5 |
| `session.py` | `ensure_session() -> str` | 首次 `initialize` + `notifications/initialized`；收到 400 `Missing session ID` 时重握手 1 次 |
| `classify.py` | `classify(rpc_resp_or_exc) -> ErrorKind` | 返回 `(kind, exit_code, retryable: bool)` |
| `render.py` | `render(env, fmt, isatty, *, lang, with_meta, width, color) -> str` | 表宽按 `wcwidth` 语义自算，避免手工引入第三方依赖；`color` 只在 TTY 且未写文件时为真 |
| `tunnel.py` | `ensure_tunnel(endpoint, ssh_host, *, run=subprocess.run, listening=is_listening) -> endpoint` | `ssh -f -N -L <port>:127.0.0.1:<port> <ssh_host>`；端口已监听 ⇒ 复用不重复 spawn。`run`/`listening` 是注入点，让离线测试永不真起 ssh |
| `commands/batch.py` | `read_lines(stream) -> list[BatchLine]`、`parse_line(index, text) -> BatchLine \| None`、`resolve_tool(name) -> (规范工具名, 错误说明)` | **只做输入面**：一行 NDJSON → `BatchLine(index, id, tool, arguments, error)`。不校验、不出网、不渲染，所以坏行只失败自己那一行；上限判断留给调用方（`len(items) > MAX_BATCH_ITEMS`） |
| `cli.py`（batch 编排） | `_handle_batch(ns, cfg, tty, opener, tcp_probe, stdin)`、`_run_batch(cfg, client, plans, write)` | 六个 handler 现统一为**六个位置参数**，第 6 个是注入进来的 `stdin`（只有 `batch` 消费，其余签名里叫 `_stdin`）；执行走 `ThreadPoolExecutor(max_workers=cfg.concurrency)` + **按输入序消费 future**，`threading.Event` 实现 `POOL_DEAD` 停止发起，写出一行即 `flush` |

## 5. 传输层实现要点（全部来自实测）

1. 请求头固定：`Content-Type: application/json`、
   `Accept: application/json, text/event-stream`，握手后带 `mcp-session-id`。
2. 响应**总是** `text/event-stream`。解析算法：
   ```
   按行迭代 → 忽略 event: 与空行与 ":" 心跳 → 以 "data:" 开头的行
   → strip 前缀 → json.loads → 匹配 id 的那个对象即结果
   ```
   注意实测分隔符是 `\r\n`，且一帧可能很大（search 结果 ~4KB），必须支持跨多次
   `read()` 的行缓冲，不能一次 readline 就假设帧完整。
3. `initialize` 参数：`protocolVersion` 发 `2025-06-18`（实测被接受并回显），
   `clientInfo.name = "tavily-cli"`、`version = __version__`。
4. 不发送值为 `null` 的可选键：服务端 schema `additionalProperties:false`，且实测
   FastMCP 对 `unexpected_keyword_argument` 会直接 isError。只发用户显式指定的键 +
   必填键，其余省略（省略 ≠ 传 null）。
5. 超时：`--timeout` 同时用作连接超时与整帧读取超时；`--request-timeout`（配置层校验 1.0–60.0）
   只覆盖**本次调用**的这个值、从不出网（4.1.3 已把服务端自身的请求预算藏进
   `Depends` + `TAVILY_REQUEST_TIMEOUT`）；`crawl`/`map` 默认放宽至 120s
   （实测 map 单站 6.8s，深爬会显著更久，服务端 `TAVILY_REQUEST_TIMEOUT=15` 只约束上游单请求）。
6. 探活不使用 `/health`：实测除 `/mcp` 外全部 404。
7. **并发下的 session 合流（M3）**：`_ensure_session()` 是**先取锁、锁内再判**
   （`with self._session_lock: if not self.session.ready: self._handshake_locked()`），
   不是"锁外快路径 + 锁内复检"的双检锁。选更简单的那个形式是因为每次调用多一次无竞争的
   `Lock` acquire 相对一个 HTTP 往返可以忽略，而双检锁多写的那一遍检查在这里换不来什么。
   要防的缺陷是 NFR-11 真正指出的那个：`batch` 的 N 个线程同时首次调用会各自 `initialize`、
   各自 adopt 一个新 session id，后写的覆盖先写的，在途请求的 `mcp-session-id` 就错了。
   离线用能卡在 `initialize` 里等放行的替身 opener **强制**两次握手重叠来证明只握一次
   （`tests/unit/test_transport.py::test_concurrent_first_calls_handshake_only_once`），不靠线程时序碰运气。
   对比之下 JSON-RPC `id` 的递增是**无锁**的 `self._next_id += 1`：实测 CPython 3.14 GIL 构建上
   8 线程 × 20 万次自增打不出重号，所以不为它写一条复现不出来的断言；
   这是**非正式保证**，一旦改用 free-threaded（`--disable-gil`）构建必须换成 `itertools.count()` 或加锁。

## 6. 校验层规则表（实现即真值表）

| 参数 | 规则 | 违反时 |
|------|------|--------|
| `query` | strip 后非空，≤512 字符，不含控制字符 | 退出码 2 |
| `include_domains`/`exclude_domains` | 每项匹配 `^(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})*\.[a-z]{2,}$`（小写化后），**禁止** `http://`、`/`、空格、端口、纯 `tavily` 这类无后缀 | 退出码 2，**绝不出网** |
| `search_depth`/`extract_depth` | ∈ {basic, advanced} | 退出码 2 |
| `topic` | ∈ {general, news, finance} | 退出码 2 |
| `time_range` | ∈ {day, week, month, year} | 退出码 2 |
| `max_results` | 1–20（README 声明上限 20） | 退出码 2 |
| `days` | 1–365；`topic != news` 时降级为警告并忽略 | 警告/退出码 2 |
| `urls` | 1–20 项，须带 `http(s)://` scheme 且 hostname 非空；不做 IDN/TLD 白名单（实测 `https://不存在.invalid` 由服务端落在 `failed_results`） | 退出码 2 |
| `select_paths`/`exclude_paths` | 正则以 `re.compile` 试编译 | 退出码 2 |
| `instructions` | 自然语言串（运行时 schema 为 `anyOf[string,null]`），仅校验类型与非空；**不是正则**，不得试编译 | 退出码 2 |
| `--request-timeout`（**已非 MCP 参数**） | 1.0–60.0，在**配置层**校验后只设本次调用的本地 HTTP 读超时；4.1.3 删掉了 `timeout` 入参，校验层收到它反而按"未声明键"拒绝 | 退出码 2，**绝不出网** |
| 未知选项 | argparse 层拦截 | 退出码 2 |

枚举不再单独维护：`search_depth`/`topic`/`time_range`/`extract_depth` 的允许取值直接读
`schema._BUILTIN_TOOLS_JSON` 里的 `enum`（含 `anyOf` 分支内的枚举，如可空的 `time_range`），
`_RULES` 只保留 JSON schema 表达不了的约束（长度、更严的区间、语义检查）。

## 7. 错误分类模型

```
输入源：JSON-RPC error 对象 / result.isError / 传输层异常 / HTTP 码
              │
              ▼
   ┌──────────────────────────┐  文本命中 "No active API keys available"
   │ classify(raw) -> Kind    │  或 "All available keys failed"        → POOL_DEAD (6)
   └──────────────────────────┘
            │ 命中 "validation error for call[" → TOOL_ERROR(5) + 提示"这是服务端 FastMCP 校验，说明客户端校验有遗漏，应补规则"
            │ 命中 "Unknown tool"               → PROTOCOL(4)
            │ 命中 "Request timed out after"    → TIMEOUT(7)
            │ 命中 rate limit / 429 语义        → RATE_LIMITED(8)
            │ URLError / ConnectionRefused      → TRANSPORT(3)
            │ HTTP 400 Missing session ID       → 重握手 1 次，仍失败 → PROTOCOL(4)
            └─ 其余                              → TOOL_ERROR(5)
```

**重试矩阵（唯一真相）**

| Kind | 重试 | 说明 |
|------|------|------|
| TRANSPORT | ✅ ≤`--retries` | 指数退避 0.5s→1s |
| PROTOCOL（仅 session 失效） | ✅ 1 次 | 重握手后重发 |
| RATE_LIMITED | ✅ 1 次 | 退避 ≥5s，且仅在用户显式 `--retries` 时 |
| TOOL_ERROR / POOL_DEAD / USAGE / TIMEOUT | ❌ | **重试会加剧共享池损伤** |

## 8. 隧道降级

`--tunnel auto`：先按配置端点直连（实测本机可直连）。若 TRANSPORT 且属"连接不可达/拒绝"，
则用 `ssh -f -N -L 18000:127.0.0.1:18000 mcp-host` 建立隧道，把端点临时改写为
`http://127.0.0.1:18000/mcp` 重试 1 次，并在 stderr 说明"已降级走隧道"。
端口已被占用 ⇒ 视为隧道已存在，直接复用，不再 spawn。`--tunnel off` 严格不碰 ssh。

落地补充（M2 实测/实现）：

- 三档语义：`on` 跳过直连先建隧道；`auto` 只在**第一次失败被分类为 TRANSPORT** 后降级，且**只重试一次**；
  `off` 永不 spawn。池死亡、超时、用量限制都不触发降级——那是服务端活着而请求被拒，隧道救不了，
  再发一次只会多消耗一次共享配额。
- 主机名改写只换 host、保留 path（`/mcp` 不能丢）；端口缺省按 scheme 取 443/80。
- 🔴 **本地转发口必须绕开系统代理**：隧道端点写的是 `127.0.0.1`，但 `urllib` 遵循 `http_proxy`，
  会把这个"本机口"交给 `203.0.113.10:6060` 去连——等于绕回那台刚刚连不上的主机。
  因此端点主机属于 `LOCAL_HOSTS` 时改用 `urllib.request.build_opener(ProxyHandler({})).open`。
  （证据强度：2026-10-23 的隧道演练**没能单独证明**这一条是必需的——本机 `no_proxy` 已含 `127.0.0.1`，
  两条路径观察不到差异；该分支目前只有离线断言支撑。）
- ssh 起不来（缺 binary、非零退出、超时、端口仍未监听）时**不改写端点**，在 stderr 报中文原因，
  由调用方沿原路径给出原本的退出码；降级本身不会把 3 变成别的数字。
- **施加位置**（2026-10-23 真机演练后修正）：`on` 由 `cli._apply_tunnel_on(cfg)` 在**校验与 `--dry-run`
  闸门之后、构造 client 之前**改写 `cfg.endpoint`，因此对**全部子命令**生效（含 `tools`/`doctor`），
  而非法入参仍然零出网。`_call_with_fallback(cfg, opener, call)` 把"on 先改道 → TRANSPORT 后 auto 再改道
  重试一次"收敛成一处，`_list_tools` 让 `tools/list` 的异常同样先过 `classify()` 再进重试矩阵
  （此前一次 HTTP 502 会冒成裸 traceback、退出码 1）。
- `doctor` 的 `auto` **不自行 spawn ssh**：它的 TCP 层就是用来如实报"直连不通"的，只提示 `--tunnel on`。
- 进程匹配：`tunnel.sh` 与 `tunnel.py` 都在 `-N` 与 `-L` 之间插 `-o`（CLI 还多 `BatchMode=yes`），
  所以 `pgrep/pkill -f` 只能锚定 `-L <port>:127.0.0.1:<port>.*<host>`；且该模式会匹配到**携带它的 shell 自身**，
  数进程要用 `pgrep -a ssh`。

## 9. 输出层

**语言策略（D-2：输出全部中文）**：内部数据模型**保持英文标识符**，中文只发生在渲染边界。
这样做的原因：① 代码里到处写 `"结果"` 这类中文字面量极易打错且无法静态检查；
② `--keys-en` 要求两套键名严格同构，单点映射表能保证；③ `--format raw` 的语义是"服务端原样"，
必须能完全绕过映射。

- 统一 `Envelope` dataclass（字段：`ok/tool/query/results/answer/images/pages/failed/nodes/meta/error`），
  渲染器只依赖它，因此加格式与加命令互不牵连。
- `render.py` 内一张 `KEY_MAP: dict[str, dict[str, str]]`（`zh` / `en` 两列）是**唯一的**键名来源；
  新加字段必须同时补两列，并有单测断言"中文与英文键集合同构"（§9 验收用例 13）。
- 默认键名对照（节选，完整以 `KEY_MAP` 为准）：

  | 内部字段 | 默认中文键 | `--keys-en` |
  |----------|-----------|-------------|
  | `ok` / `tool` / `query` | `成功` / `工具` / `查询` | `ok` / `tool` / `query` |
  | `results[]` 的 `url`/`title`/`content`/`score`/`id` | `网址`/`标题`/`摘要`/`评分`/`编号` | 同名英文 |
  | `meta.request_id`/`response_time`/`elapsed_ms` | `请求编号`/`服务端耗时`/`本地耗时毫秒` | `request_id`/`response_time`/`elapsed_ms` |
  | `error.kind`/`message`/`hint` | `类别`/`消息`/`建议` | `kind`/`message`/`hint` |
  | `batch` 段的 `line`/`id`/`request` | `行`/`关联编号`/`请求` | `line`/`id`/`request` |

  `"类别"` 的**取值**默认也是中文（`密钥池已死亡` 等），与退出码的对应关系见 requirements §6。
- `json`：缩进 2，`ensure_ascii=False`（中文必须原样输出，实测结果含大量中文正文）。
- `ndjson`：每条结果一行，行内不含换行；元数据用 `--with-meta` 首行输出。
- **`batch` 的两个文档助手**：`batch_line_doc(line, item_id, env, lang)` = `行`/`关联编号` 头部
  **拼上同一份** `_doc(env, lang)` 信封体，所以逐行输出走的还是单命令那条渲染路径，
  加字段只加一次；`batch_request_doc(line, item_id, request, lang)` 是 `--dry-run` 的形状，
  外层三个键跟语言开关、内层 `request`（`jsonrpc`/`method`/`params`）是**协议面**不过 `KEY_MAP`，
  与 `raw` 同理。`meta_doc(meta, lang)` 供 `--with-meta` 的首行复用。
- **条目形状归一化（D-8，实测逼出来的）**：`build_envelope` 把列表条目统一变成 **dict 记录**，
  字符串条目按 `_BARE_STRING_KEY`（当前只有 `nodes → url`）包成单键记录。
  动机是 2026-10-23 的真机首跑：`tavily-map` 的 `results` 实测是**裸 URL 字符串数组**，
  `_cell(item, "title")` 直接在 `table`/`md` 上抛 `AttributeError`；而 `crawl` 的页面实测**没有 `title`**，
  表头因此只剩 `序号 | 网址 | 原文`（"整列皆空则省略"是既有规则，见 requirements §5.3）。
  归一化放在这里而不是各渲染器里，是为了让 `Envelope` 的下游只有一种形状；
  `-f raw` 走 `env.raw`，**不经归一化**，仍是服务端原样。
- **着色范围（M2 已落地）**：只用 `bold/dim/red/green/yellow` 五种**前景** SGR，不用背景色
  （浅色终端上背景色常不可读）。上色发生在**剪贴与填充之后**，所以"剥掉 ANSI 的输出"与
  "无色输出"逐字符相同——列位置不可能被着色改动，这条不变式由单测守着。
  · 只有 `table`/`md` 会着色；`json`/`ndjson`/`raw` **任何情况下零转义**（它们是 agent 的消费面）。
  · 触发条件是 `Config.color 且 stdout 是 TTY 且没有 -o`：写进文件的产物不被转义序列污染。
  · 关闭开关：`--no-color` 或环境变量 `NO_COLOR`（两者都解析进 `Config.color`）。
  · 语气分配：表头与标题 `bold`、网址与汇总 `dim`、失败原因与错误`类别`行 `red`、
    `doctor` 状态列按字面量取 `green`/`red`/`yellow`（`失败`/`跳过` 之外都算通过）。
- `table`：中文表头 `序号 | 评分 | 标题 | 网址`；列宽按**显示宽度**计算（CJK 计 2），
  超宽截断加 `…`。不用第三方 `wcwidth`，在 `render.py` 里用
  `unicodedata.east_asian_width` 自行实现（保持零依赖）。
- `md`：`## {标题}` + `{网址}` + 摘要 + `评分`，便于粘贴进笔记。
- `raw`：服务端 `structuredContent` 原样 JSON，**英文键名、不加任何字段**，且不经过 `KEY_MAP`
  （逃生通道 + 契约测试的断言对象）。
- `--include-raw-content` 打开时 `content`/`raw_content` 可能极长（实测 raw_content 数十 KB），
  默认在 `table`/`md` 中省略正文只给长度，`json`/`raw` 保留全文。

## 10. 配置与状态

无守护进程、无本地状态文件（不做缓存）。M2 起实现**四级合并：CLI > 环境变量 > 配置文件 > 内置默认**，
配置文件为标准库 `tomllib`（Python ≥3.11，本机 3.14）读两级，后者覆盖前者：

1. `~/.config/tavily-cli/config.toml`（用户级）
2. 从当前目录**逐级向上**找到的第一个 `.tavily-cli.toml`（项目级）

坏配置一律按 USAGE（退出码 2）报出**是哪一层写错的**：错误消息带来源标签
（`format（来源：/path/.tavily-cli.toml）` / `TAVILY_CLI_FORMAT` / `--format` / `内置默认`），
因为"配置静默失效"比"配置报错"难查得多。具体规则：

- **文件不存在不是错误**；存在却读不动（权限等）或 TOML 语法坏了才报错，且消息里带完整路径。
- **未知键直接拒绝**（`endpoints` 这类笔误不能被忽略），消息里列出本 CLI 只认的键名。
- 可由配置文件写的键：`endpoint`、`timeout`、`format`、`tunnel`、`ssh_host`、`keys_lang`。
  只走命令行/环境变量的键：`--request-timeout`、`--retries`、`--concurrency`、`--quiet`、
  `--verbose`、`--dry-run`、`-o`、`--with-meta`、`--keys-en`（`keys_lang` 是它的文件侧等价物）。
- `crawl`/`map` 的 120s 默认（§4.5）属于**内置默认**这一层：写在配置文件里的 `timeout` 压过它，
  命令行 `--timeout` 更压过它。

环境变量：`TAVILY_MCP_ENDPOINT`、`TAVILY_CLI_TIMEOUT`、`TAVILY_CLI_FORMAT`、
`TAVILY_CLI_TUNNEL`、`TAVILY_SSH_HOST`、`TAVILY_CLI_KEYS_LANG`、`NO_COLOR`。

**代理事实（2026-10-22 实测）**：标准库 `urllib` 遵循 `http_proxy`/`HTTPS_PROXY`。本机挂着
`http://203.0.113.10:6060` 时，对 LAN 端点的请求会经代理转发（两种路径都通）；代理会替它
生成中文 502 文本，看起来像端点错误。要让诊断反映真实直连，把端点主机写进 `NO_PROXY`。

## 11. 测试策略

| 层 | 位置 | 是否联网 | 数据来源 |
|----|------|----------|----------|
| 单元 | `tests/unit/` | ❌ | `study/mcp-tavily-endpoint/fixtures/` 原始响应 + 手工构造帧。`batch` 面在 `test_batch.py`，假 opener 集中在 `tests/unit/mcp_stub.py`：它的 `tools/list` **默认返回内置 schema 副本**（`schema.BUILTIN_TOOLS`），这样漂移预检默认就是"不告警"的那条路径；`fail_methods=` 可按 JSON-RPC 方法注入失败（预检自身的失败靠它）；`calls()` 记录实际发出的 `(name, arguments)`，是"坏行零出网"与"只握手一次"两类断言的观测点 |
| 防污染守卫 | `tests/guard/` | ❌（ monkeypatch socket） | §6 全部非法用例，断言"零 socket 写入"。`batch` 的形态是 `test_batch_bad_lines_never_touch_the_network`：**全批都是坏行时连零配额的 `tools/list` 预检都不许发**——这条曾真被实现违反过 |
| 契约 | `tests/contract/` | ✅ `@network` opt-in | 真实端点：`tools/list` schema hash 比对、错误分类命中、无 session 头被拒——**默认零配额**。花配额需再叠闸门：`TAVILY_CONTRACT_QUOTA=1`（1 次 search + 1 次 extract）、`TAVILY_CONTRACT_HEAVY=1`（`crawl`/`map`）、`TAVILY_ALLOW_DESTRUCTIVE=1`（`!!bad` 事故复测） |
| 冒烟 | `scripts/smoke.sh` | ✅（末段除外） | §9 验收用例 1–6、8–10 走真实查询；末段 4 条 `batch`（用例 22/25）全部止步校验层或 `--dry-run`，**零出网**，读 stdin 因此需要 `codin()` 显式喂文件（否则继承终端 tty，batch 按设计直接拒绝） |

最重要的四类测试：
1. **SSE 解析**：分块到达、`\r\n`、多帧、超大帧、心跳行。
2. **守卫测试**：`include_domains=["!!bad"]` 必须止步于校验层——这是对研究文档 §5 事故的
   永久回归防线。
3. **并发时序类（M3）**：绝不用 `sleep` 猜时序。要么 `threading.Barrier(3)` **强制**三行同时在途
   （顺序执行的实现必然超时失败，而不是"碰巧通过"），要么让替身 opener 卡在 `initialize` 里等放行
   （证明只握一次手），要么在锁里统计在途峰值（证明不超上限）。断言的是**必然性**，不是概率。
4. **契约断言不得被空载荷骗过**（2026-10-23 真机学到的）：`isinstance(页面, list)` 在
   `example.com`（实测返回 0 页）上恒真，所以 HEAVY 两条改成了"目标可爬 + 结果非空 + 逐条看字段 +
   真渲染一遍 `table`/`md`"。同理，上表那行"数据来源 = fixtures"有例外：
   `out_tavily-map_sample.json` 与 `out_tavily-crawl_sample.json` 的 `results` 是**空数组**，
   证明不了条目形状，所以 crawl/map 的形状断言用**测试内联**的实测样本（裸 URL 字符串、无 `title` 的页面）。

## 12. 性能预算

| 阶段 | 预算 | 依据/手段 |
|------|------|-----------|
| 解释器 + 模块导入 | ≤80ms | ADR-0001：不导入 mcp SDK（实测其 import ≈0.87s） |
| 配置加载 + 校验 | ≤20ms | 静态表驱动，无正则回溯风险（模式已锚定） |
| 握手（首次） | ≈0.1s | 单次 initialize + notify |
| `tools/call` | 1.5s(basic) / 4.1s(advanced+news) | 实测中位数 |
| 端到端（search，热 session 复用不可行时） | ≈1.7s | 主要为网络与上游耗时 |
| `batch` 的 HTTP 请求数 | **N + 3**（`initialize` + `notifications/initialized` + 一次 `tools/list` 预检 + N 次 `tools/call`） | 与 `--concurrency` 无关：session 整批复用，预检整批只做一次 |
| `batch` 的墙钟 | ≈ `ceil(N / cap) × 最慢一行` | 顺序是硬约束：按输入序消费 future，队首未就绪时后面的结果先攒着 |

`batch` 的实现取向是**顺序优先于及时性**（D-9）：线程池负责把 N 行并发推出去，
主循环按 `item.index` 逐个 `.result()` 取出再写出，所以消费方永远能按行号对齐；
代价是慢行会挡住它后面已经完成的行——这是有意的，不是待修的缺陷。
单命令路径不受影响，仍是最多 2 次 HTTP（握手 + 调用）。

## 13. 安全与滥用控制

- 端点**无鉴权**：CLI 不得提供任何"把它暴露到公网"的选项或文档示例；README 明确风险。
- 不读取、不存储、不打印任何 Tavily API Key；`.gitignore` 兜底。
- `--verbose` 打印 session id 时做部分脱敏（保留前 8 位）。
- 错误文本原样透传服务端信息前，先跑一遍 `tvly-[A-Za-z0-9_-]{6,}` → `tvly…<redacted>` 替换。
- **`batch` 的滥用节制（M3 落地，全部在发出第一个请求之前生效）**：
  · 并发默认 **4**、上限 **8**，`--concurrency` 越界（`0`/`9`/`abc`）⇒ 退出码 2 **不静默截断**；
  · 单次最多 **50 行**（`constants.MAX_BATCH_ITEMS`），超限在读取阶段就退出、**一个 socket 都没有**；
  · stdin 是 TTY ⇒ 退出码 2（NFR-2：任何路径都不等待人输入）；空输入同样退出码 2；
  · 整批**只做一次**零配额的 `tools/list` 漂移预检，漂移与预检失败都**只警告不阻断**；
  · 任一行分类为 `POOL_DEAD` ⇒ 停止发起新调用（`threading.Event` 闸门），未执行行仍写出跳过信封保证行数守恒；
  · **零出网路径优先于预检**：`--dry-run` 与"整批都停在校验"这两种情况连那次零配额预检也不发
    （实现第一版正是在这里漏了一个请求，被 `tests/guard/` 的 tripwire 抓回来）。
- 单命令路径不受并发影响，仍是最多 2 次 HTTP。

## 14. 未来演进（不在本期）

- `tavily-cli mcp-config`：输出 Cursor/Claude 的 MCP JSON 片段。
- 向服务端提议 `GET /health` 与 `GET /usage` 只读端点，届时 CLI 的 `doctor` 可直接读配额。
- 若服务端修复 400→401 误判，可放宽 §6 中部分规则的严格度（保留域名/枚举校验作为快速失败）。
