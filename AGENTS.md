# AGENTS.md — tavily-cli 工作约定（公开版）

本文件是本仓库的**执行手册**。开始任何编码前请先读完 §1–§4，尤其是 §3 红线。
公开版只保留与代码相关的约定与安全结论；网关主机标识、内网地址、部署路径等一律不在本仓库出现，
真实端点请用 `--endpoint`、`TAVILY_MCP_ENDPOINT` 或配置文件提供。

---

## 1. 这是什么项目

`tavily-cli`：在命令行里通过 MCP Streamable HTTP 调用一个自建的 `mcp-tavily` 聚合网关，
完成网页搜索/提取/爬取/站点地图四类任务。定位是"可脚本化、可被其他 agent 调用、
且不会伤害共享服务"的客户端。

**当前状态**：M1 + M2 已完成并通过真机验收（`search`/`extract`/`crawl`/`map`/`tools`/`doctor`
+ 隧道降级 + 四级配置 + TTY 着色）；M3（`batch` 流式 + 并发上限 + schema 漂移告警）代码与
离线断言已交付。离线单测 **366** 条全绿零网络。契约层按**配额消耗**分四档闸门
（默认 `-m network` 零配额 / `TAVILY_CONTRACT_QUOTA=1` / `TAVILY_ALLOW_DESTRUCTIVE=1` /
`TAVILY_CONTRACT_HEAVY=1`）。`M3` 的真机并发压测（约 20 个真实 `tools/call`）尚未执行，
那是一笔新的共享配额支出，需要网关运维方点头。

| 文档 | 用途 | 改动须知 |
|------|------|----------|
| `docs/requirements.md` | 需求基线（命令面、输出契约、退出码、验收标准） | 改命令语义前必须先与维护者确认 |
| `docs/design.md` | 如何实现（分层、模块签名、传输细节、性能预算） | 实现偏离时更新本文，不要悄悄改代码留文档过期 |
| `docs/adr/000{1,2,3}-*.md` | 三条关键决策及其实测依据 | 只增不删；推翻旧决策请新开 ADR 并把旧文件状态改为 `Superseded` |
| `study/mcp-tavily-endpoint/README.md` | **服务端接口事实来源**（实测，非 README 转述） | 服务端有任何变化先更新这里，再改代码 |
| `study/mcp-tavily-endpoint/fixtures/` | 线上原始响应样本（已脱敏），离线测试数据源 | 可用 `probe_*.py` 重新抓取刷新；⚠️ `out_tavily-map/crawl_sample.json` 的 `results` 是**空数组**，证不了条目形状（形状断言请用测试内联样本） |

## 2. 环境事实速查

```
端点        内置默认 http://127.0.0.1:18000/mcp
            真实网关用 --endpoint / TAVILY_MCP_ENDPOINT / 配置文件提供
服务        容器 mcp-tavily / FastMCP 4.1.3 / Python 3.12
            （serverInfo.version 报的是 **FastMCP 库版本**，不是应用版本；上游单请求超时由
             运维侧 TAVILY_REQUEST_TIMEOUT 决定，缺省 15s，客户端已无法覆盖）
服务端源码  由网关运维方持有（只读；本仓库不改服务端）
虚拟环境    .venv（本文写作时为 Python 3.14.4）
            安装：python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
            可执行：.venv/bin/tavily-cli     跑测试：.venv/bin/python -m pytest
            注意：不使用 `uv tool install`；`uv venv` 默认建的是 .venv/ 而不是 bin/，别按 bin/python 找。
```

探活（服务端没有 `/health`）：

```bash
curl -s -X POST "$TAVILY_MCP_ENDPOINT" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'
```

零配额隧道演练（只发 `initialize` + `tools/list`，**不消耗搜索配额**，但会 spawn
`ssh -f -N -L` 并在本机占住 `127.0.0.1:18000`，用完必须 `down`）：

```bash
.venv/bin/tavily-cli tools --tunnel on -f json     # 直接建隧道；看 "元信息"."端点" 是否被改写
pgrep -a ssh | grep 18000                           # 数转发进程（不要用 pgrep -f，它会匹配到自身）
.venv/bin/tavily-cli tools --tunnel on -f json      # 再跑一次：应复用、不重复 spawn
scripts/tunnel.sh status                             # 脚本也看得见 CLI 起的隧道
scripts/tunnel.sh down && (ss -ltn | grep -w 18000 || echo 已释放)
```

## 3. 🔴 红线（违反即视为事故）

1. **禁止向服务发出未通过校验的入参**。这条红线**不因服务端已修复而放宽**。
   历史事故：一个语法非法的域名参数会让上游返回 400，被服务端误判成 401，
   把网关聚合的**全部** Key 标为 `ERROR` 终态，**整台机器的搜索能力立即瘫痪且不会自愈**
   （唯一恢复手段是重启网关容器）。完整链路与修复建议见
   [`docs/adr/0003-validate-before-send.md`](docs/adr/0003-validate-before-send.md)。
   仍然禁止真实发送坏参数，理由四条：
   ① 服务端补丁是否已进入部署由运维方掌握，重建镜像或回滚可能失去防护；
   ② 同错熔断未落地，未被 `tavily` SDK 类型覆盖的请求级错误**仍会轮换打满所有 Key**（浪费共享配额）；
   ③ `tests/guard/` 断言"非法入参零 socket 写入"——这是**客户端契约**，不是对服务端善意的依赖；
   ④ 端到端重放只证明"**这一类**被 `BadRequestError` 覆盖的错误不再污染池"，
   没有证明其余请求级错误安全，因此**不构成放宽理由**。
   任何探索性/破坏性参数测试，只能在 `--dry-run` 或本地 fixture 上做。
2. **禁止对 `isError=true` 盲目重试**。重试决策只走 `classify.py` 的重试矩阵（ADR-0002）。
3. **禁止把 Tavily API Key 写进本仓库任何文件**（包括文档、fixture、日志样本、`.env`）。
   网关不鉴权，CLI 永远不需要 Key。
   提交前跑一次（限定源码类型，`.pyc` 会假阳性）：
   `grep -rnoE --include="*.py" --include="*.md" --include="*.json" --include="*.toml" --include="*.sh" "tvly-[A-Za-z0-9_-]{8,}" .` 必须无输出。
4. **禁止擅自重启/修改共享网关所在的机器上任何其他服务**。那是共享基础设施。
   需要动它时先向运维方说明影响并取得确认。
5. **禁止修改服务端代码**。服务端缺陷只在本仓库记录根因与修复建议，由运维方落地。
6. **禁止把端点暴露到公网**或在 README 里给出反向代理/公网部署示例。
7. **禁止把真实主机名、内网地址、部署路径、文件哈希、个人线索写进本仓库**。公开产物只应
   包含"陌生访客能照做"的信息：端点由 `--endpoint`／环境变量／配置文件提供，安装走仓库内
   `.venv`。提交前跑 §6.2 的密钥扫描，并复核 `git status` 里没有临时 `*.json` 混进来。

## 4. 已知陷阱（都踩过或验证过，别再踩）

| 陷阱 | 事实 | 应对 |
|------|------|------|
| 服务端 README/git log ≠ 运行时契约 | 容器内代码与工作区逐字节一致，滞后的其实是文档；`serverInfo.version` 是 FastMCP 的**库**版本，4.1.0→4.1.3 那次升级顺手删了 4 个工具的 `timeout` 入参 | 以运行时 `tools/list` 为权威；用 `study/mcp-tavily-endpoint/probe_tools_list.py` 刷新副本与 fixture，靠 `schema_hash` 比对告警 |
| 响应是 SSE 不是 JSON | 即便 POST 也返回 `text/event-stream`，帧分隔符是 `\r\n` | 逐行取 `data:` 前缀、strip 后 `json.loads`；缓冲跨 read 分块 |
| session 是强制的 | 不带 `mcp-session-id` ⇒ HTTP 400 `Missing session ID` | `initialize` → 取响应头 → 发 `notifications/initialized`（202）→ 后续带该头 |
| 没有健康检查端点 | `/health` `/usage` `/docs` `/metrics` 全 404 | 探活走 `initialize` + `tools/list` |
| `ERROR` 是终态 | `key.py::check_status()` 只让 `COOLDOWN` 自愈；`EXHAUSTED` 靠用量回落 | 池死亡只能重启容器；CLI 必须映射成退出码 6 |
| 热加载救不了池 | `ConfigManager.reload()` 仅在 `old_raw_keys != new_raw_keys` 时重建 | `touch .env` 是无效操作，别当排障手段 |
| `additionalProperties:false` | 传未声明键 ⇒ FastMCP `unexpected_keyword_argument` | 只发用户显式指定的键，**省略 ≠ 传 null**，永不发 null |
| 过小 `timeout` 放大耗时（**4.1.3 起客户端已不可达**） | 4.1.0 上实测 `timeout:0.001` 被当网络错误，在每个 Key 上各退避重试 2 次 → 7.6s；4.1.3 删掉了这个入参 ⇒ 客户端发它只得到 FastMCP "未声明键" 拒绝 | `--request-timeout` 只做**本地**读超时，下限 1.0s（防调用方刚发出就自己 TIMEOUT/退出码 7） |
| mcp SDK 符号改名 | 2.3.0 是 `streamable_http_client`，旧文档 `streamablehttp_client` 会 ImportError；且无 `headers` 参数 | 依 ADR-0001 用标准库自研，绕开该问题 |
| 空结果 ≠ 失败 | 查无结果仍返回 `isError=false` | 退出码 0、`"成功": true`、`"结果": []`（`--keys-en` 时 `ok`/`results`），只在 stderr 打一行中文提示 |
| 中文 JSON 键不能用裸 jq 标识符 | `jq -r '.结果[].网址'` 直接语法报错（jq 标识符只接受 `[a-zA-Z_]`） | 写成 `.["结果"][]."网址"`；`--keys-en` 才有裸标识符写法 |
| Tavily 不会为乱码返回空集 | 乱码查询实测返回 5 条低分无关结果 | 要稳定触发空结果，用语法合法但索引里没有的 `--include-domain`（见 requirements §9-12） |
| `__pycache__` 让 Key grep 假阳性 | `tvly-` 前缀与测试里的拼接常量在字节码里相邻，`grep -rnoE` 会命中 `.pyc` | 扫描限定源码类型；`.pyc` 已在 `.gitignore` 内 |
| `add_subparsers` 用**空前缀**预计算子命令 prog | 自定义 `HelpFormatter._format_usage` 无条件替换前缀 ⇒ 子命令帮助出现 `用法：用法：tavily-cli search` | 只在 `prefix is None` 或以 `usage` 开头时才换成 `用法：`，空串必须原样放过 |
| 子解析器会覆盖父命名空间 | `parse_args` 把子命令 namespace 整份盖到父 namespace 上，`--keys-en search x` 这类**子命令之前**的全局选项被重置为默认 | 所有共享全局选项 `default=argparse.SUPPRESS`，`Config.from_args` 用 `getattr` 取值 |
| `argparse` 的 `-h`/`--version` 文案是英文 | `show this help message and exit` 直接印进 `--help` | `add_help=False` + 自加中文 `-h`；`--version` 显式传 `help=` |
| `classify(kind=…, message=…)` | 给了 `kind` 时**位置参数 text 会被忽略** | 第二个参数必须写成 `message=`；裸 `OSError` 也要先包成明确的 `ErrorKind`，否则保守降级成 TOOL_ERROR |
| 端点流量会走系统代理 | 若机器挂了 `http_proxy`，`urllib` 遵循它：LAN 请求由代理转发，代理还会替你生成 502 文本 | 想让诊断反映真实直连，把端点主机写进 `NO_PROXY`；`doctor` 的 TCP 层是裸 socket，本就不过代理 |
| 隧道口写着 `127.0.0.1` 却仍走代理 | `urllib` 不看主机名是不是本地，只看 `http_proxy`：于是"降级到本机转发口"等于绕回刚连不上的那台机器，隧道形同白建 | 端点主机属于 `tunnel.LOCAL_HOSTS` 时用 `build_opener(ProxyHandler({})).open` |
| 配置文件"不存在"被当成错误 | 只判 `path is None`、没判存在性 ⇒ `FileNotFoundError` 被包成 `ConfigError` ⇒ **没写配置的机器上每条命令直接退出码 2** | 缺文件是正常状态，返回空字典；只有"存在却读不动/TOML 语法坏"才算错，且消息必须带完整路径 |
| `Path.home` 是 classmethod | `monkeypatch.setattr(Path, "home", lambda self: tmp)` 在调用 `Path.home()` 时报缺参 | 打桩用**零参** lambda（`lambda: tmp`） |
| TTY 默认着色会打断列宽断言 | `isatty=True` 下按单元格文本比较的用例集体变红 | 着色只加转义不动排版（`strip_ansi(有色) == 无色` 是不变式），测试侧比较文本前先剥 SGR |
| batch 的漂移预检**会出网** | 那次"零配额"的 `tools/list` 仍是真实请求；预检放在逐行执行之前会导致**全批都是坏行**的输入也发一次请求，直接违反红线 1 | 零出网路径（`--dry-run`、整批停在校验）**必须在预检之前 return**。永久回归防线：`tests/guard/test_no_socket.py::test_batch_bad_lines_never_touch_the_network` |
| 离线 batch 测试忘加 `--tunnel off` | 注入 `tools/list` 失败路径的用例走默认 `auto`，会去试 `socket.create_connection` ⇒ 被禁网 fixture 拦下，报错看起来像"传输层泄漏" | 凡是要注入 `tools/list` 失败的离线用例，一律显式 `--tunnel off` |
| 并发的真缺陷是**重复握手**，不是 id 重号 | GIL 构建上多线程自增实测打不出重号，为它写断言等于写一条永远不会红的测试；而 N 个线程各自 `initialize` 会互相覆盖 `mcp-session-id` | 断言只写**能强制复现**的性质（`_ensure_session` 锁内检查、`Barrier` 逼并发、峰值 ≤ 上限、整批一次握手）。⚠️ 改用 free-threaded 构建后，id 自增必须换成 `itertools.count()` 或加锁 |
| `map` 的 `results` 是**裸 URL 字符串** | 真机首跑 `map … -f table`/`md` 抛 `AttributeError`；`-f json` 却"看着正常"，机读格式掩盖了它 | `build_envelope` 按 `_BARE_STRING_KEY` 包成 `{"url": …}`（D-8）；`-f raw` 保持服务端原样 |
| `crawl` 的页面**没有 `title`** | 实测条目键只有 `url` + `raw_content` | 表头按"整列皆空则省略"自动去掉标题列（既有规则正确工作） |
| "是列表"式契约断言在空载荷上恒真 | 不可爬的目标返回 `成功: true` + **0 页**，`isinstance(页面, list)` 照样绿；fixture 的 `results` 也是空数组 | HEAVY 断言改为"目标可爬 + 结果非空 + 逐条看字段 + 真渲染 table/md" |

## 5. 代码约定

- **语言/版本**：Python ≥3.11，入口命令 `tavily-cli`（`pyproject.toml [project.scripts]`）。
- **依赖**：运行时第三方依赖目标为 **0**（ADR-0001）。开发依赖只允许 `pytest`。
  新增任何依赖必须先开 ADR。
- **结构**：严格按 design.md §2 的目录；`src/tavily_cli/` 下模块职责不交叉。
  `commands/` 只做"选项 → MCP arguments"映射，不含业务逻辑；渲染只依赖 `Envelope`。
- **命名**：模块与函数 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE`。
- **键名（D-2）**：**内部数据模型一律英文标识符**（`url/title/content/score/request_id/kind/…`）；
  中文只发生在**渲染边界**。`render.py` 里那张 `KEY_MAP`（`zh`/`en` 两列）是**唯一的**对外键名来源。
  · 默认输出中文键名；`--keys-en` 走同一张表的 `en` 列，两套键名必须**严格同构**。
  · `--format raw` 是服务端 `structuredContent` 原样透传，**不经过 `KEY_MAP`**，永远是英文键。
- **注释**：默认不写。只在"为什么"非显然处写一行。
- **语言边界**：错误信息、`--help`、日志、表头、JSON 键名用中文；
  **CLI 选项名、协议参数名、枚举值标识**保持英文。
- **异常**：不允许裸 `except:`；不允许把 `POOL_DEAD` 吞进通用异常路径。

## 6. 工作流

### 6.1 实现一个命令的顺序

1. 读 `docs/requirements.md` 对应小节 → 确认参数与校验规则表。
2. 写 `schema.py` / `validate.py` 规则（**此时一行网络代码都不该有**）。
3. 写 `tests/guard/` 用例：非法入参必须止步校验、零 socket 写入。
4. 写 `transport.py` 调用 + `commands/<cmd>.py` 映射 + `render.py`。
5. 用 `fixtures/` 做离线渲染测试；再用 `--dry-run` 看请求体；最后才真机验证。
6. 真机验证顺序固定：`doctor` → `search`（1 次，basic，max_results=1）→ 需要时才 `extract`。
   **不要**用批量真实查询做调试，那是共享配额。

### 6.2 每次交付前自检

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/python -m pytest tests/ -q              # 必须全绿，且无网络访问
.venv/bin/python -m pytest tests/ -q -m network   # 契约层：零配额档，可直接跑
TAVILY_CONTRACT_QUOTA=1 .venv/bin/python -m pytest tests/ -q -m network   # 1 search + 1 extract，先征得同意
TAVILY_CONTRACT_HEAVY=1 TAVILY_CONTRACT_QUOTA=1 .venv/bin/python -m pytest tests/contract/test_minimal_calls.py -q  # crawl/map
# 必须无输出：源码类型限定，否则 __pycache__ 里的 .pyc 会假阳性
grep -rnoE --include="*.py" --include="*.md" --include="*.json" --include="*.toml" --include="*.sh"   "tvly-[A-Za-z0-9_-]{8,}" . || true
.venv/bin/tavily-cli search x --include-domain "!!bad" -f json ; echo "exit=$?"   # 期望 exit=2 且未出网
.venv/bin/tavily-cli search "x" --dry-run          # 检查 arguments 无 null 值键
.venv/bin/tavily-cli search "x" -f json --keys-en  # 与默认中文输出严格同构（§9 用例 13）
```

对照 `docs/requirements.md` §9 的 **25** 条验收用例逐条打勾，并在交付说明里写明哪几条已验证、
哪几条未验证（**不要把没跑的写成通过**）。

### 6.3 文档同步义务

| 变化 | 必须更新 |
|------|----------|
| 服务端行为/参数变化 | `study/mcp-tavily-endpoint/README.md` + 刷新 `fixtures/` |
| 命令面/输出契约/退出码 | `docs/requirements.md`（并先与维护者确认） |
| 模块划分/技术选型 | `docs/design.md`，必要时新 ADR |
| 新踩到的坑 | 本文件 §4 表格 |
| 阶段推进 | 本文件 §1"当前状态"一行 |

## 7. 交付与提交

- 提交粒度建议：文档骨架 / 校验层 / 传输层 / 渲染层 / 各命令 / 测试与脚本 分别成提交，
  每个提交带一句"为什么"，不要一次性大提交。
- 绝不 `git push`、绝不建 PR，除非维护者明确要求。
- 提交前必查：源码类型限定的 `tvly-` 扫描无输出，`git status` 里没有 `__pycache__/`、
  `.venv/`、临时 `*.json` 混进来。

## 8. 与维护者协作的默认姿态

- 维护者同时是这套网关的运维方，习惯中文交流、喜欢可直接执行的命令与明确的影响说明。
- 涉及共享网关所在机器的状态变更（重启容器、改 compose、占端口）：**先说影响，等确认再动**。
- 探索性研究允许自由做（只读探测、读代码、跑 fixture）；但**避免高频真实查询**，
  dev Key 配额有限。
- 报告结论要区分"实测得到"与"推断"。引用服务端 README 的说法时，标注它是否与运行时一致。
