# tavily-cli 需求文档

| 版本号 | 日期       | 变更说明 | 作者 |
|--------|------------|----------|------|
| v0.10.0 | 2026-10-23 | §9 用例 **22/25 补上一条零出网的真机冒烟路径**：`scripts/smoke.sh` 末段新增 4 条 `batch`（混合批次 `--dry-run` ⇒ 恰好 3 行信封 + 坏行只坏自己 + `第 2 行`；`-f table` ⇒ 2；空输入 ⇒ 2；51 行 ⇒ 2），跑的是**已安装的二进制与真实退出码**，全程止步校验层故**零配额**。为此新增 `codin()` 助手——`code()` 不重定向 stdin，而 `batch` 按设计拒绝终端 tty。§9 前言与用例 22/25 的"只有离线断言"口径相应改为"离线断言 + 零网络冒烟"，20 条真实并发压测仍标为**未执行、需单独批准** | Qoder |
| v0.9.0 | 2026-10-23 | **M3 代码落地后的口径回填**：§4.6 补"顶层只认 `id`/`tool`/`arguments`，未声明键 ⇒ 该行错误"（单命令 `additionalProperties:false` 在输入面的同款）与"行号两个落点"（stdout 的 `"行"` 给 agent/`jq`、stderr 的 `第 N 行` 给人）；§5.4 把"紧凑 JSON"改成实现真实形状（单行、无缩进、保留分隔符空格，与 `-f ndjson` 同风格）并新增 `--dry-run` 的逐行 `{"行","关联编号","请求"}` 形状（`请求` 属协议面不过 `KEY_MAP`）与"每个失败行 stderr 说明一次"；§6 规则 6 钉死三点（整批只预检一次、复用同一 session 与同一次 `--tunnel` 决策、`--dry-run` 与全批坏行**完全跳过**预检）；§9 用例 21–25 逐条列出守它的**具名离线测试**；§10 的 M3 行改标"代码与离线断言已交付，真机 20 条压测仍待批准"，离线单测 329 → **366**；D-9 的代码指针从 `commands/batch.py` 修正为 `cli.py::_handle_batch`。**一处实现偏离已按文档纠正**：空输入原先返回退出码 0 + 提示，现改回 §9-25 的 **2**（与 TTY 拒绝、超上限同属输入面误用，不该回报成功） | Qoder |
| v0.8.0 | 2026-10-23 | **M3 口径定稿**（`batch`）：新增 §4.6（stdin NDJSON 行形状、逐行校验隔离、50 行上限、stdin 是 TTY 即拒绝）与 §5.4（逐行完整信封、顺序硬保证 + 及时性尽力而为、格式白名单、行数守恒）；§6 补规则 4–6（退出码聚合 `POOL_DEAD` 优先、池死亡即停止发起新调用、schema 漂移只警告不阻断）；`--concurrency` 重定义为"仅 batch 使用、越界即拒绝不截断"；新增 NFR-11 并发正确性；§9 扩到 **25 条**（21–25 为 M3，明确标注只有离线断言、真机 20 条压测属新的配额支出需单独批准）；§11 的"dev key 额度低"缓解改为实际落地的三道节制；§12 新增 **D-9/D-10**（实现侧定稿、附推翻成本）；顺带修掉 D-2 注释里那个会在 jq 上报语法错的裸中文标识符表达式 | Qoder |
| v0.7.0 | 2026-10-23 | **M2 真机验收完成，§9 用例 16/17 由 🔴 转 ✅** 并带出两条**实测修正**：① `crawl` 的页面条目**没有** `title`（原稿的 `标题` 是推断），表头实为 `序号 \| 网址 \| 原文`；② `map` 的 `results` 是**裸 URL 字符串数组**，不是对象——`table`/`md` 此前直接抛 `AttributeError`。据此新增决策 **D-8**（`节点` 归一化成单键记录，`-f raw` 保持原样）并在 §5.2 写下"1:1 透传的唯一例外"。HEAVY 两条契约改为"目标可爬 + 非空 + 逐条看字段 + 真渲染"（旧断言碰上 `example.com` 的 0 页会空转）。着色补一条零配额真实 TTY 证据（`tools -f table`）。§9 前言与 §10 的 M2 行收尾为 ✅；离线单测 325 → **329** | Qoder |
| v0.6.0 | 2026-10-23 | 隧道真机演练（零配额）完成：§9 用例 18 的 🔴 换成实测证据链（spawn/复用/auto 改道/收回四步），并补三条新口径——`--tunnel on` **对全部子命令生效**（原先 `tools`/`doctor` 静默忽略）、`doctor` 的 `auto` **不自行 spawn ssh**、ssh 只在校验与 `--dry-run` 闸门**之后**才可能起。演练顺带暴露并修掉 3 个缺陷：`--tunnel on` 原先**只对** `search`/`extract`/`crawl`/`map` 生效（`tools`/`doctor` 静默忽略）、`tools/list` 传输失败冒裸 traceback 且退出码 1（应为 `网络不可达` + 3）、`scripts/tunnel.sh` 的 `-N -L` 相邻模式永远匹配不到真进程（`status` 恒报无隧道、`down` 收不回 CLI 起的隧道）。§9 分组与 §10 的 M2 退出条件收敛为**只欠 `HEAVY` 一次**；离线单测 319 → 325 | Qoder |
| v0.5.0 | 2026-10-23 | M2 代码落地后的口径补齐：§5.3 增写**着色契约**（只在 TTY、只 `table`/`md`、机读格式与 `-o` 产物恒零转义、`--no-color`/`NO_COLOR` 关闭）与 `crawl`/`map` 各自的表头；§10 的 M2 行改标"代码已交付、真机验收仍欠 `HEAVY` 一次与隧道演练一次" | Qoder |
| v0.4.0 | 2026-10-23 | 契约测试层首跑发现服务端漂移：`serverInfo` 4.1.0 → **4.1.3**（该版本号是 **FastMCP 库版本**，非应用版本），4 个工具的 `timeout` 入参被删除、枚举改为 schema 声明。据此把 `--request-timeout` 重定义为**纯本地读超时**（不再出网），新增 §12 决策 **D-6**；§4.2/§4.4 同步 | Qoder |
| v0.3.0 | 2026-10-22 | M1 真机验收后修正 §9 四条口径：用例 1 的 jq 表达式改用 `.["结果"]`（裸中文标识符是语法错误）；用例 6 改为用不可达端点复现，不动共享容器；用例 12 记录"乱码查询不会返回空集"这一实测事实并给出稳定的空结果触发方式；用例 13 补充两次调用间必然不同的 4 个服务端字段 | Qoder |
| v0.2.0 | 2026-10-22 | 落地 5 项使用者决策（见 §12）：命令名 `tavily-cli`、输出全部中文含 JSON 键名（新增 §5.0 与 `--keys-en`）、`crawl`/`map` 确认 M2、安装运行改走本机 `.venv`、服务端缺陷改为"仅出根因分析、由使用者在 mcp-host 修复"；验收用例扩至 14 条；§4.4/§11 关于版本滞后的表述按 MD5 实测修正 | Qoder |
| v0.1.0 | 2026-10-22 | 首版：基于 mcp-host 上 mcp-tavily 4.1.0 实测契约确立需求基线 | Qoder |

关联文档：接口事实 `study/mcp-tavily-endpoint/README.md` · 服务端缺陷根因
`docs/adr/0003-validate-before-send.md` · 技术方案 `docs/design.md` ·
决策记录 `docs/adr/` · 工作约定 `AGENTS.md`

---

## 1. 背景

一台局域网主机（下文记作 `mcp-host`）上以 Docker 运行着 `mcp-tavily` 服务：它聚合多个 Tavily
API Key，对外以 **MCP Streamable HTTP**（默认端点 `http://127.0.0.1:18000/mcp`，
用 `--endpoint`／`TAVILY_MCP_ENDPOINT`／配置文件指向真实网关）暴露 4 个工具
（search / extract / crawl / map），做加权轮询、429 冷却与 401 熔断。

**现状问题**：这个能力目前只能被"支持 MCP 客户端的图形化/AI 工具"消费。命令行与脚本场景
（shell 管道、cron、CI、其他 agent 的 Bash 工具）没有可直接调用的入口，每次手工 `curl` 需要
自己处理 session 头、SSE 分帧、JSON 二次解码、参数校验和错误分类，成本高且极易出错——
实测已证明**一个格式不合法的域名参数就能把整台服务器共享的 Key 池永久打死**。

**要做的东西**：`tavily-cli` —— 一个装在使用者工作站上的命令行客户端，把上述 MCP 服务还原成
符合 Unix 习惯的一等命令：可脚本化、结构化输出、明确退出码、并在客户端侧就挡住会伤害
共享服务的输入。

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 |
|------|------|
| G-1 | 用一条命令完成搜索，结果可被人读、也可被 `jq` 等工具机读 |
| G-2 | 覆盖服务端全部 4 个工具，参数与服务端 `tools/list` 契约一致 |
| G-3 | **零污染**：CLI 绝不向共享服务发出会让 Key 池进入 `ERROR` 终态的请求 |
| G-4 | 失败可判定：不同失败原因给出不同退出码与人话错误，脚本能据此分支处理 |
| G-5 | 面向 agent 友好：非 TTY 时默认输出稳定 JSON，启动开销小，无交互式提问 |
| G-6 | 网络受限时可一键降级到 SSH 隧道，不需要用户手写 `ssh -L` |

### 2.2 非目标（本期明确不做）

- ❌ 不做本地缓存 / 结果索引 / 历史检索。
- ❌ 不做 MCP **server** 端（不把 tavily 再暴露成 stdio MCP 给别的客户端）。
- ❌ 不做多网关配置切换（只有一个 mcp-tavily 端点；配置项存在但不做 profile 管理）。
- ❌ 不直接持有或代填 Tavily API Key——鉴权由网关承担，CLI 只依赖网络位置。
- ❌ 不做配额监控面板（服务端不暴露 `/usage`，见研究文档 §8）。
- ❌ 不做 TUI / 交互式浏览器界面。

## 3. 使用者与场景

| 角色 | 场景 | 关键诉求 |
|------|------|----------|
| 使用者本人（终端） | 临时查资料、验证某个信息 | 快、可读、少记参数 |
| 使用者的 shell 脚本 / cron | 定时抓取新闻、监控关键词 | 稳定退出码、JSON 输出、可静默 |
| 其他 AI agent 的 Bash 工具 | agent 需要联网搜索但没有 MCP 通道 | 单次调用启动快、无交互、错误信息可自修复 |
| 排障者（可能是未来的使用者本人） | 服务不可用时判断是网络、协议还是 Key 池 | `doctor` 一条命令定位层次 |

## 4. 命令面需求

### 4.1 命令结构

```
tavily-cli <command> [args] [options]
```

| 命令 | 映射工具 | 说明 |
|------|----------|------|
| `tavily-cli search <query>` | `tavily-search` | 网页搜索，主命令 |
| `tavily-cli extract <url> [<url>...]` | `tavily-extract` | 正文提取，支持多 URL |
| `tavily-cli crawl <url>` | `tavily-crawl` | 站点递归爬取 |
| `tavily-cli map <url>` | `tavily-map` | 站点链接结构地图 |
| `tavily-cli tools` | `tools/list` | 打印服务端权威 schema（含 hash） |
| `tavily-cli doctor` | `initialize`+`tools/list` | 分层探活：TCP → 握手 → schema → 最小搜索 |
| `tavily-cli batch` | 任一工具 | 从 stdin 读 NDJSON，逐行执行并流式输出逐行信封（M3）；契约见 §4.6 与 §5.4 |

### 4.2 `search` 选项（MVP 必须全部实现）

| 选项 | 类型 | 默认 | 对应 MCP 参数 | 校验规则（发出前完成） |
|------|------|------|---------------|------------------------|
| `<query>` | 位置参数 | 必填 | `query` | 非空、≤512 字符 |
| `--depth` | enum | `basic` | `search_depth` | ∈ {basic, advanced} |
| `--topic` | enum | `general` | `topic` | ∈ {general, news, finance} |
| `--days` | int | — | `days` | 仅 `--topic=news` 允许；1–365；其他 topic 给出则警告并忽略 |
| `--max-results` | int | `5` | `max_results` | 1–20 |
| `--time-range` | enum | — | `time_range` | ∈ {day, week, month, year} |
| `--include-answer` | flag | false | `include_answer` | — |
| `--include-images` | flag | false | `include_images` | — |
| `--include-image-descriptions` | flag | false | `include_image_descriptions` | — |
| `--include-raw-content` | flag | false | `include_raw_content` | — |
| `--include-domain <d>` | 可重复 | — | `include_domains` | **必须是合法域名**：`(?:[a-z0-9-]+\.)+[a-z]{2,}`，禁止协议/scheme/路径/空格 |
| `--exclude-domain <d>` | 可重复 | — | `exclude_domains` | 同上 |
| `--request-timeout <s>` | float | — | **无**（不出网） | **≥1 且 ≤60**；4.1.3 起服务端删掉了 `timeout` 入参（改由 `TAVILY_REQUEST_TIMEOUT` 注入），本选项只设本次调用的**本地 HTTP 读超时** |

### 4.3 其余命令选项

- `extract`：`urls`（1–20 个，必须是 `http(s)` URL）、`--depth`{basic,advanced}、`--include-images`。
- `crawl`：`--max-depth`、`--max-breadth`、`--limit`、`--instructions`、`--select-path`（可重复，须为可编译正则）、`--exclude-path`、`--allow-external`、`--include-images`。
- `map`：`--max-depth`、`--limit`、`--select-path`。
- 四者共用全局选项（§4.5）。

### 4.4 服务端契约对齐（强约束）

- CLI 的参数集合以**运行时 `tools/list`** 为权威；内置一份静态 schema 用于离线校验与快速失败，
  但每次联网调用需比对 `tools/list` 指纹（schema hash），发现服务端参数增删时给出显式提示
  （实测两个方向的漂移都存在：4.1.0 的 `tools/list` 有 `timeout` 而服务端 README 没有；
  4.1.3 又把 `timeout` 从 4 个工具里全部删掉。文档不可作为契约来源，静态副本必然漂移）。

### 4.5 全局选项

| 选项 | 说明 |
|------|------|
| `-f, --format <json\|ndjson\|table\|md\|raw>` | 输出格式；默认见 §5.1 |
| `-o, --output <path>` | 写入文件而非 stdout |
| `--endpoint <url>` | 覆盖 MCP 端点，默认 `http://127.0.0.1:18000/mcp` |
| `--timeout <s>` | 客户端总超时，默认 45s；`crawl`/`map` 默认 120s |
| `--retries <n>` | **仅对传输层失败**重试，默认 1；校验类与池死亡类永不重试 |
| `--concurrency <n>` | **仅 `batch` 使用**：同时在途的 `tools/call` 数，默认 4，上限 8。越界（<1 或 >8）**直接退出码 2**，不静默截断到 8（"我以为并发是 16"比报一次错更难查）；单命令路径不受它影响 |
| `--quiet / --verbose` | stderr 日志量控制 |
| `--no-color` | 禁用 ANSI（同时受 `NO_COLOR` 环境变量控制） |
| `--keys-en` | 机读输出的键名切回英文（默认中文，见 §5.0）；与 `--format raw` 互不影响 |
| `--dry-run` | 只做校验并打印将要发出的 JSON-RPC 请求体，**不发网络包** |
| `--tunnel [auto\|off\|on]` | 端点不可达时是否自动建立 SSH 隧道，默认 `auto` |
| `--version`, `-h/--help` | 标准 |

### 4.6 `batch` 输入契约（M3）

```
tavily-cli batch [全局选项] < requests.ndjson
```

**行形状**：stdin 每行一个 JSON 对象，三个键（**输入面一律英文**，理由见 §5.0——它是调用方
要键入/程序生成的协议面，不是输出文本）：

```json
{"id": "q-01", "tool": "search", "arguments": {"query": "示例股份 2026 半年报", "max_results": 3}}
```

| 键 | 必填 | 规则 | 违反时 |
|----|------|------|--------|
| `tool` | ✅ | 别名 `search`/`extract`/`crawl`/`map` 或服务端全名 `tavily-search` 等；其余为未知工具 | **该行**错误，零出网 |
| `arguments` | ✅ | 必须是 JSON 对象；随后走 §6 的**同一套**校验流水线（与单命令共用规则表，不另立标准） | **该行**错误，零出网 |
| `id` | ❌ | 调用方自定义的相关标识；未提供则输出 `null` | — |

- **逐行校验隔离**（与单命令最大的语义差别）：单命令里任何校验失败 ⇒ 整条命令退出码 2、零出网；
  `batch` 里坏行只让**那一行**失败，其余行照常执行。这是红线 1 的仍然成立的形式——坏行**永不进网络队列**，
  所以"非法入参零 socket 写入"的守卫断言对 `batch` 同样生效（`tests/guard/`）。
- **顶层只认 `id`/`tool`/`arguments` 三个键**：出现未声明的顶层键 ⇒ **该行**错误、零出网。
  这是单命令面 `additionalProperties:false` 那条硬约束在输入面上的同款形态——
  拼错的 `arguements` 静默失效（该行会带着空 arguments 出网）比报一次错危险得多。
- 坏 JSON 行（语法错、值为数组/字符串/数字等非对象）⇒ 该行 `参数校验失败`。
  行号有两个落点，各司其职：**结构化定位用 stdout 的 `"行"` 字段**（agent 与 `jq` 消费它），
  stderr 另给一行中文说明并写成 `第 N 行`（人读）。整批不会因为一行坏而中止。
- 空行与纯空白行忽略（不计入输出行）。
- **行数上限 50**：超出 ⇒ 退出码 **2**、**零出网**，stderr 说明"请分批执行"。
  上限写在常量里（`constants.MAX_BATCH_ITEMS`），依据是 §11 的"dev key 额度低"，
  且 50 × `max_results=20` 早已越过任何现实的配额。
- **stdin 是 TTY ⇒ 退出码 2** 并提示改用管道或文件重定向：NFR-2 要求任何路径都不等待 stdin，
  这条是 `batch` 特有的实现义务（它恰恰是唯一读 stdin 的命令）。
- `--dry-run` 在 `batch` 上有明确含义：逐行校验 + 打印将要发出的 JSON-RPC 请求体（逐行形状见 §5.4），**零出网**。
- **整批都停在校验时 ⇒ 一条 socket 都不许有**，连 §6 规则 6 那次零配额的 `tools/list` 漂移预检也跳过。
  这是实现层面真踩到的坑：坏行本身不出网，但"先预检再逐行执行"的编排会让**全批都是坏行**的输入仍然出网一次，
  直接违反红线 1 的守卫断言（`tests/guard/test_no_socket.py::test_batch_bad_lines_never_touch_the_network`）。

## 5. 输出契约

### 5.0 语言约定（使用者决策：全部中文）

**所有面向使用者的文本与机读键名一律中文**——包括 `--help`、错误信息、stderr 日志、
`table` 表头、`md` 标题、以及 JSON 的**键名**。

三处**必须**保持英文，因为它们是协议或键入成本决定的，不属于"输出文本"：

| 保持英文的部分 | 原因 |
|----------------|------|
| 发往服务端的 MCP 参数名与枚举值（`query`、`search_depth`、`basic`/`advanced`、`news`…） | 线上协议，改成中文服务端直接拒绝 |
| CLI 选项名（`--max-results`、`--include-domain`…） | 命令行键入中文长选项不现实，且 shell 补全与脚本已习惯 ASCII |
| `--format raw` 输出的字段名 | 该格式的语义就是"服务端原样直通"，映射即失真 |

需要英文键名的场景（复用既有脚本、跨语言环境）用 `--keys-en` 或配置 `keys_lang = "en"` 切换；
两种键名**一一对应且长期稳定**，映射表是实现里的单点（见 design.md §9）。

### 5.1 格式选择

- stdout **只输出数据**，任何日志/进度只写 stderr。
- TTY 且未指定 `--format` → `table`（人读）；非 TTY（管道/agent）→ `json`（机读）。
  该判断必须由 `isatty` 决定且可用 `--format` 强制覆盖，禁止"检测到管道就打印彩色表格"。

### 5.2 机读 JSON 结构（`--format json`）

统一信封，便于脚本对任何命令用同一段代码处理：

```json
{
  "成功": true,
  "工具": "tavily-search",
  "查询": "示例股份 2026 半年报 营收",
  "结果": [
    {"网址": "https://…", "标题": "…", "摘要": "…", "评分": 0.82, "编号": "…"}
  ],
  "简答": null,
  "图片": [],
  "元信息": {
    "请求编号": "d0df3237-…",
    "服务端耗时": 1.02,
    "本地耗时毫秒": 1513,
    "端点": "http://127.0.0.1:18000/mcp",
    "CLI版本": "0.1.0",
    "服务端版本": "4.1.0",
    "schema指纹": "sha256:…"
  },
  "错误": null
}
```

失败时 `"成功": false`，`"错误"` 为对象
`{"类别": "参数校验失败|网络不可达|协议异常|工具执行失败|密钥池已死亡|超时|被限流", "消息": "…", "建议": "…"}`，
`"结果"` 为空数组而非 `null`（消费方不必判空类型）。
`"类别"` 与退出码严格一一对应（§6），脚本亦可只用数字退出码分支，不依赖语言。

- `extract` 用 `"页面"` + `"失败"`；`map`/`crawl` 用 `"节点"` / `"页面"`。
  除键名翻译外，值与服务端 `structuredContent` **保持 1:1**，不加工、不截断、不重排
  （见研究文档 §4）。**唯一例外**（实测逼出来的）：`tavily-map` 的 `results` 是**裸 URL 字符串数组**，
  信封里归一化成 `{"网址": "…"}` / `--keys-en` 下 `{"url": "…"}` 的单键记录 —— 否则 `table`/`md`/`ndjson`
  要各自判类型，且 `ndjson` 会吐出行级裸字符串。需要服务端原始形状时用 `-f raw`，它**不经归一化**。
- `--format ndjson`：每个结果对象一行，供 `jq -c` / `while read` 直接消费；信封元数据走
  `--format ndjson --with-meta` 时作为首行 `{"元信息":{…}}`。
- `--format raw`：**原样吐出服务端 `structuredContent`**，英文键名、不加信封、不做任何映射。
  给"我就要 Tavily 原始字段"的场景留后门。
- `--format md`：`## 标题 — 网址` + 摘要，适合把搜索结果直接粘进笔记/报告。

### 5.3 人类可读 table

表头按工具而定，**整列皆空的列会被省略**：

| 命令 | 表头 | 汇总行 |
|------|------|--------|
| `search` | `序号 \| 评分 \| 标题 \| 网址` | `共 N 条` |
| `extract` / `crawl` | `序号 \| 标题 \| 网址 \| 原文`（原文列只给"N 字符"，不内联正文） | `共 N 页`（另有失败时追加 `M 失败`） |
| `map` | `序号 \| 标题 \| 网址` | `共 N 节点` |
| `tools` | `序号 \| 名称 \| 标题` | `共 N 工具` |
| `doctor` | 无表头，一检查项一行（检查项 / 状态 / 耗时 / 细节） | — |

汇总行以计数开头，后面按可得性追加 `M 失败` · `耗时 Nms` · `请求编号 …`
（后两项取决于服务端与本地是否测到）。除 `doctor` 外每条命令都输出这一行。

宽度自适应终端，中文按显示宽度 2 计算列宽（NFR-10），超宽截断加 `…`。

**着色契约**：

- 只在 **stdout 是 TTY** 时着色；`json`/`ndjson`/`raw` 这三种机读格式**任何情况下零转义序列**
  （它们是 agent 的消费面），用 `-o` 写进文件的产物同样不带转义。
- 关闭开关：`--no-color` 或环境变量 `NO_COLOR`。
- 只用前景与加粗/暗淡（`bold`/`dim`/`red`/`green`/`yellow`），不用背景色。
  语气：表头与标题 `bold`、网址与汇总行 `dim`、失败原因与错误`类别`行 `red`、
  `doctor` 状态列 `green`/`red`/`yellow`。
- 🔴 **着色不得改变排版**：剥掉 ANSI 之后的输出必须与 `--no-color` 的输出逐字符相同，
  列位置、截断、`…` 都不受着色影响（离线单测守着这条不变式）。

### 5.4 `batch` 输出契约（M3）

**一行输入 = 一行输出**，且**顺序与输入完全一致**（即便并发执行）。每行是一个**单行 JSON**
（无缩进；分隔符保留 `": "`/`", "` 空格，与已交付的 `-f ndjson` 单命令格式同风格——两处都是
`json.dumps(..., ensure_ascii=False)` 且不传 `separators`，因此改格式也要一起改）的完整 §5.2 信封，
外加两个批处理专属字段：

```json
{"行": 1, "关联编号": "q-01", "成功": true, "工具": "tavily-search", "查询": "示例股份 2026 半年报", "结果": […], "简答": null, "图片": [], "页面": [], "失败": [], "节点": [], "元信息": {…}, "错误": null}
```

（样例按实现原样留空格；上面这段与 `… | jq -c .` 的产物只差分隔符，字段集完全一致。）

- `行` 是**有效输入行**的序号：忽略空行后从 **1** 递增，坏 JSON 行同样占一个序号。
  它**不是**文件物理行号（那样消费方还得自己数空行）。
  `关联编号` 回显输入里的 `id`，未提供则为 `null`。
  这两个键同样进 `KEY_MAP`（`batch` 段：`行`/`关联编号` ↔ `line`/`id`），
  `--keys-en` 下变成 `line`/`id`——**不得**在 `commands/batch.py` 里手写中文键名（AGENTS §5）。
- **流式**：某行一旦可写出就立即写出并 flush，不等整批完成。并发下"按序"意味着
  队首未就绪时后面的结果先攒着（线程池 + 按 index 消费 future），
  因此**顺序是硬保证、及时性是尽力而为**。这是有意的取舍：`jq`/`while read` 的消费方
  需要能按行号对齐，不能靠完成顺序猜归属。
- **格式白名单**：`batch` 只接受默认（等价 `-f ndjson`）与显式 `-f ndjson`。
  `-f json` / `table` / `md` / `raw` ⇒ **退出码 2** 并说明"逐行信封是 batch 的唯一形状，
  要 JSON 数组请 `… | jq -s .`，要单条的其它格式请用单命令"。
  故意拒绝而不是"默默按 ndjson 输出"：本仓库踩过一次同类坑（AGENTS §4"全局旗标只在部分 handler 生效 = 静默失效"），
  用户显式要 `table` 却拿到 NDJSON 比报错更难发现。
- `--with-meta`：首行输出 `{"元信息":{…}}`（`端点`/`CLI版本`/`schema指纹`，`--keys-en` 同构），
  与 §5.2 的既有语义一致；其余行是逐行信封。不加该选项时不产出这一行。
- `-o <path>`：同样逐行写入文件，且**零 ANSI**（机读格式本就如此）。
- **`--dry-run` 的逐行形状**：好行输出将要发出的 JSON-RPC 请求体，坏行输出正常的失败信封——两种行
  都占一行、序号连续，所以 `--dry-run` 同样满足"输出行数 == 输入有效行数"：

  ```json
  {"行": 1, "关联编号": "q-01", "请求": {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "tavily-search", "arguments": {"query": "示例股份", "max_results": 1}}}}
  ```

  `请求` 是**协议面**，内部键名（`jsonrpc`/`method`/`params`/`arguments`）**不经过 `KEY_MAP`**、
  `--keys-en` 下也不变，与 §5.0 的 `--format raw` 同理；只有外层 `行`/`关联编号`/`请求` 三个键跟语言开关。
  · **`请求.id` 是占位**：`--dry-run` 下它等于行号（坏行不占号，所以 1、3 这种跳号是正常现象），
    真跑时 `id` 由 `transport` 逐次自增分配，两者**不会相等**。要对齐请用外层 `行`/`关联编号`，
    不要拿 `请求.id` 做关联键；`method` 与 `params` 才是与真跑逐字节一致的部分。
- **每个失败行都在 stderr 说明一次**：`tavily-cli：第 N 行 <类别>：<消息>` 加上它的 `建议` 行；
  stdout 只留数据（§5.1），所以 agent 端按行解析不会被人读噪声打断。
- 未执行的行（见 §6 规则 4 的池死亡停止）也**必须有输出行**：
  `成功: false` + `类别: 密钥池已死亡` + 消息写明"批量已在首个池死亡处停止，本行未发起调用"，
  这样输出行数恒等于输入有效行数，消费方可逐行对齐、不会静默少一条。

## 6. 错误处理与退出码

| 退出码 | 名称 | JSON `"类别"` 取值 | 触发条件 | 是否重试 | stderr 必须说明 |
|--------|------|--------------------|----------|----------|-----------------|
| 0 | OK | `成功` | 成功（含 0 条结果——空结果不是错误） | — | — |
| 2 | USAGE | `参数校验失败` | 参数缺失/枚举非法/域名格式不对/范围越界 | ❌ 永不 | 哪个选项、错在哪、正确写法示例；**不发网络包** |
| 3 | TRANSPORT | `网络不可达` | TCP 不可达、DNS 失败、连接被拒、HTTP 5xx | ✅ 至多 `--retries` | 端点 URL、是否尝试过隧道 |
| 4 | PROTOCOL | `协议异常` | `initialize` 失败、缺 session id、SSE 无法解析、JSON-RPC `error` 对象、schema 漂移 | ⚠️ 仅 session 失效可重握手一次 | 期望/实际协议版本、原始帧片段 |
| 5 | TOOL_ERROR | `工具执行失败` | `isError=true` 且非池死亡（上游 Tavily 报错、工具内部异常） | ❌ 默认不 | 服务端原文错误文本（已脱敏） |
| 6 | POOL_DEAD | `密钥池已死亡` | 错误文本含 `No active API keys available` / `All available keys failed` | ❌ 绝不重试 | **专门指引**：服务端 Key 池已 ERROR 终态，需 `ssh mcp-host docker restart mcp-tavily`；并说明"客户端无法自愈"。根因见 `docs/adr/0003-validate-before-send.md` |
| 7 | TIMEOUT | `超时` | 客户端总超时或 `Request timed out after N seconds` | ❌ | 实际耗时、建议的 `--timeout` 值 |
| 8 | RATE_LIMITED | `被限流` | 上游 429 语义（服务端会转成冷却后换 Key，若仍透传出限流） | ⚠️ 退避后 1 次 | 建议退避秒数 |
| 130 | INTERRUPTED | `已中断` | Ctrl-C | — | 干净退出，不留半截 JSON |

`--keys-en` 时 `"类别"` 输出英文标识名（`OK`/`USAGE`/`POOL_DEAD`…），与中文取值**一一对应**，
数字退出码不受键名开关影响。

规则：
1. **`isError=true` 绝不等于可重试**（实测证据：429 之外的错误会污染 Key 池）。
2. 退出码 6 是 CLI 存在的核心价值之一：让脚本能区分"我这边网络问题"与"服务端已瘫痪"。
3. 错误文本里的 `tvly-*` 一律脱敏为 `tvly...xxxx`（服务端日志已做，CLI 不得反向泄漏）。
4. **`batch` 的退出码聚合**（M3）：全部行 `成功: true` ⇒ **0**（某行 0 条结果仍是成功，§9 用例 12 同规则）；
   否则**只要有任一行**分类为 `密钥池已死亡` 就是 **6**（共享服务已不可用、需要人工介入，其它噪声不该盖住它）；
   再否则取**按输入顺序第一个失败行**的退出码。逐行分类仍走同一张表——`batch` 不引入新退出码。
5. **`batch` 遇池死亡即停**：某一行被分类为 `POOL_DEAD` 后**不再发起新调用**（取消尚未开始的排队行），
   未执行的行按 §5.4 输出跳过信封。理由直接来自 §11：`ERROR` 是服务端 Key 池的**终态**、客户端不会自愈，
   继续把剩下的请求灌上去只是白烧共享配额并把失败面摊得更宽。限流（8）不触发这个停止——
   它有退避语义，且换 Key 后可能自行恢复。
6. **schema 漂移只警告不阻断**：`batch` 开始前发一次零配额的 `tools/list`，与内置静态副本比指纹
   （§4.4 的强约束在批量面上落地）。漂移 ⇒ stderr 一行中文警告并**继续执行**（服务端可能只是加了个可选参数）；
   预检本身失败（网络/协议）⇒ 同样只警告不阻断，因为逐行调用会如实报出自己的失败层次。
   实现侧把这条钉死为三点：**整批只预检一次**（在第一个 `tools/call` 之前，逐行重复预检会把零配额探测
   变成 N 次）；预检与后续调用**复用同一个 session**、走同一次 `--tunnel` 决策（`auto` 因此只判定一次，
   不会"预检走直连、调用走隧道"）；`--dry-run` 与"整批都停在校验"这两种零出网路径**完全跳过预检**（见 §4.6）。

## 7. 配置需求

优先级：命令行 > 环境变量 > 配置文件 > 内置默认。

| 环境变量 | 配置文件键 | 默认 |
|----------|-----------|------|
| `TAVILY_MCP_ENDPOINT` | `endpoint` | `http://127.0.0.1:18000/mcp` |
| `TAVILY_CLI_TIMEOUT` | `timeout` | `45` |
| `TAVILY_CLI_FORMAT` | `format` | `auto` |
| `TAVILY_CLI_TUNNEL` | `tunnel` | `auto` |
| `TAVILY_SSH_HOST` | `ssh_host` | `mcp-host` |
| `TAVILY_CLI_KEYS_LANG` | `keys_lang` | `zh`（`en` 等价于 `--keys-en`） |
| `NO_COLOR` | — | — |

- 配置文件：`~/.config/tavily-cli/config.toml`，项目内 `.tavily-cli.toml` 可覆盖。
- **配置文件与仓库中禁止出现 Tavily API Key**：网关不鉴权，CLI 不需要 Key；`.env.example`
  若要提供，只允许放端点与超时类配置。

## 8. 非功能需求

| 编号 | 需求 | 验收指标 |
|------|------|----------|
| NFR-1 | 启动快：agent 每次调用都会新起进程 | 冷启动到发出第一个字节 **≤150ms**（除网络 RTT） |
| NFR-2 | 无交互 | 任何路径都不等待 stdin / 不弹问题；需要输入时报退出码 2 |
| NFR-3 | 幂等与最小伤害 | 默认单次调用只发 1 次 `tools/call`；`--dry-run` 可 100% 离线验证 |
| NFR-4 | 依赖克制 | 运行时第三方依赖目标为 **0**（ADR-0001，仅标准库）；开发依赖只允许 `pytest` |
| NFR-5 | 可安装 | **不使用 `uv tool install`**；安装与运行统一走本机 `.venv`（Python 3.14.4）：`.venv/bin/pip install -e .`（开发时 `-e ".[dev]"` 带上 `pytest`），入口名 `tavily-cli`，可执行路径 `.venv/bin/tavily-cli` |
| NFR-6 | 可观测 | `--verbose` 打印 JSON-RPC 方法名、session id（脱敏）、耗时、HTTP 码 |
| NFR-7 | 稳健输入 | 对 stdin/参数的畸形 UTF-8、超长串、控制字符不崩溃 |
| NFR-8 | 安全边界 | 只在受信局域网使用；文档明确"端点无鉴权，任何人可消耗共享配额"；不向公网暴露 |
| NFR-9 | 测试 | 纯逻辑（校验、SSE 解析、格式渲染、错误分类）用 `fixtures/` 离线可测；对真实端点的契约测试标记 `@network`，默认不跑 |
| NFR-10 | 中文优先 | 搜索结果里的中文、全角字符必须正确显示，`table` 列宽按显示宽度（东亚宽字符占 2）计算 |
| NFR-11 | 并发正确性（`batch`） | 整批复用**一次**握手得到的 session：多线程同时首次调用时**只允许握一次手**（否则会各自 adopt 新 session id、把在途请求的 id 覆盖掉——这才是本文件真正担心的并发缺陷）。JSON-RPC `id` 仍需**唯一且响应按 id 归属**；离线测试只断言"握手次数、id 唯一、逐行形状、有序、停止行为"这些**可确定复现**的性质（实测：GIL 构建上 8 线程 × 20 万次 `+= 1` 打不出重号，故不为它写测不出来的断言） |

## 9. 验收标准（每条都可执行验证）

本节分三组：**用例 1–15** 是 MVP（`search` + `extract` + `doctor` + JSON/table + 退出码），
已全部真机通过（用例 7 例外，见该条）；**用例 16–20** 是 M2（`crawl`/`map`、隧道、配置文件、着色），
截至 2026-10-23 **16/17/18 已全部真机通过**（16/17 由使用者批准烧一次配额；18 是零配额演练），
**19/20 做过零配额抽查**（配置文件里的 `endpoint` 真实路由、pty 下的错误表着色），
着色另有一条零配额的真实 TTY 证据：`script -qec "tavily-cli tools -f table" /dev/null` 下
表头与名称为 SGR 1、标题与汇总行为 SGR 2，且列宽对齐不受转义序列影响。
**用例 21–25** 是 M3（`batch` + 并发上限 + schema 漂移预检），五条都有具名**离线断言**
（`tests/unit/` + `tests/guard/`，零网络）；其中 **22/25 的零出网路径已进 `scripts/smoke.sh` 末段**
（4 条：混合批次 `--dry-run`、`-f table`、空输入、51 行），跑的是已安装二进制与真实退出码，
同样**不消耗配额**。**仍未执行**的是真机并发压测那一条：它要一次发 20 个真实查询，属
**新的共享配额支出**，必须先取得使用者批准才跑，不要为了"补齐绿灯"就悄悄执行。
唯一仍未执行且**不计划执行**的是 **用例 7**（退出码 6 / 池死亡）：它要求人为打死**共享** Key 池，按红线 4 不执行。

1. `.venv/bin/tavily-cli search "Tavily API pricing" --max-results 3` → 退出码 0，stdout 是 3 条结果；TTY 下表可读，`-f json | jq -r '.["结果"][]."网址"'` 得 3 行 URL。（实测修正：jq 的标识符不接受裸中文，`.结果` 会报语法错，中文键必须写成 `.["结果"]`。）
2. `tavily-cli search x -f json --dry-run` → 退出码 0 且**未发出网络包**（可用 `timeout 1` 或断网验证），打印的 arguments 中**不含任何值为 `null` 的可选键**。
3. `tavily-cli search x --include-domain "!!bad"` → **退出码 2**，stderr 用中文指出域名需带合法后缀，且用 `doctor` 复跑确认服务端 Key 池仍健康（这是防污染回归用例，对应研究文档 §5）。
4. `tavily-cli search x --depth bogus` → 退出码 2，并列出允许取值。
5. `tavily-cli extract https://example.com https://不存在.invalid -f json` → 退出码 0，`"页面"` 长度 1、`"失败"` 长度 1（`failed_results` 不得被吞掉）。
6. 拔掉网线/关停容器后 `tavily-cli search x` → 退出码 3，且提示可用 `--tunnel on`。（实测修正：不必动共享容器，`--endpoint http://127.0.0.1:18999/mcp` 即复现同一退出码 3——该端口无人监听时直连得到 `Connection refused`，挂着代理时由代理侧返回 HTTP 502，两者都归 TRANSPORT。）
7. 人为使服务端池失效（**仅在测试实例上**，或由使用者明确批准）→ 退出码 6，`"错误"."类别"` 为 `密钥池已死亡`，stderr 含 `docker restart mcp-tavily` 指引。
8. `tavily-cli doctor` → 分 4 行输出 TCP/握手/tools-list/最小搜索 的状态与耗时，全部通过时退出码 0。
9. `tavily-cli tools -f json` → 含 4 个工具名与服务端 schema 指纹。
10. `tavily-cli --help` / `tavily-cli search --help` → 全部为中文，列出所有选项且与本文 §4.2 表一致。
11. `.venv/bin/python -m pytest tests/ -q` 全绿且**无网络访问**；`@network` 用例被 deselect。
12. 空结果：`tavily-cli search "zzzqqqxxnonexistent12345"` → 退出码 **0**、`"成功": true`、`"结果": []`，并打一行中文 stderr 提示"无结果"。（实测修正：Tavily 对乱码查询**不会返回空集**，而是给出 5 条低分无关结果，因此这条触不到空分支。真机改用语法合法但索引里没有的域名过滤即可稳定得到空结果：`search "Tavily API pricing" --include-domain qzx-verify-empty-2026a.com -f json` → 退出码 0、`"结果": []`、stderr `查询无结果（这不是错误，退出码 0）。`）
13. 键名等价性：同一查询下 `--keys-en` 输出的 JSON 与默认中文输出**结构同构**（键一一对应、值完全相同），`--format raw` 则始终等于服务端 `structuredContent`。（实测口径：两次独立调用之间只有 4 个每次必变的服务端字段不同——`编号`/`请求编号`/`服务端耗时`/`本地耗时毫秒`——比对时应排除它们；`raw` 的键集合已与 fixture 里抓到的 `structuredContent` 逐键相等：`query/follow_up_questions/answer/images/results/response_time/request_id`。）
14. 中文渲染：含中文标题与正文的结果在 `table` 下**列对齐不乱**（宽字符按 2 计宽）。
15. 本地读超时（D-6）：`tavily-cli search x --request-timeout 0.5` → 退出码 **2**、零出网；`--request-timeout 7 --dry-run` 与真机调用的 arguments 中**都不得出现 `timeout` 键**，而本次调用的 HTTP 读超时取 7s。（离线断言：`tests/unit/test_cli.py::test_request_timeout_is_the_local_read_timeout` 等 4 条。）

M2（`crawl` + `map` + 隧道 + 配置文件 + 着色；2026-10-23 全部真机通过，16/17 各消耗一次使用者批准的配额）：

16. `tavily-cli crawl https://docs.tavily.com --max-depth 1 --max-breadth 2 --limit 2 -f json` → 退出码 0，
    `"页面"` 每项含 `网址`/`原文`。**实测修正**：原稿写的 `标题` 是凭推断填写的——服务端 crawl 的页面条目
    只有 `url` + `raw_content`，没有 `title`（`study/mcp-tavily-endpoint/README.md` §4.1）。
    `"查询"` 等于服务端 `base_url`（crawl 无 `query` 字段，信封回落 base_url）。
    非法入参（`--select-path '[(未闭合'`、`--max-depth -1`、`--limit 0`、裸域名 `crawl example.com`）→ 退出码 2 且零出网。
    （离线已断言：`tests/unit/test_cli.py` 的 crawl/map 13 条 + `tests/guard/test_no_socket.py`（共 29 条）里的
    crawl/map 非法参数。）
    ✅ **真机已通过（2026-10-23 08:20，使用者批准烧一次配额）**：
    `crawl https://docs.tavily.com --max-depth 1 --max-breadth 2 --limit 2 -f table` → 退出码 0、
    表头 `序号 | 网址 | 原文`（标题列因整列皆空而按 §5.3 自动省略）、
    `共 2 页 · 耗时 578ms · 请求编号 1a61bd9e-4146-4b2f-981b-a52775028cb5`；
    契约闸门 `TAVILY_CONTRACT_HEAVY=1 … -k test_crawl_maps_pages_and_base_url` 同刻度通过（0.40s）。
    ⚠️ 目标站点必须**可爬**：`crawl https://example.com` 实测返回 `成功: true` + **0 页**（0.37s、无 `失败` 条目），
    而旧断言只判 `isinstance(页面, list)`，在空载荷上恒真 ⇒ 两条 HEAVY 契约已改成"非空 + 逐条看字段 + 真渲染一遍 table/md"。
17. `tavily-cli map https://docs.tavily.com --limit 5 -f json` → 退出码 0，`"节点"` 是**对象数组**
    （每项 `{"网址": …}`，`--keys-en` 下严格同构为 `{"url": …}`）。**实测修正**：服务端给的是**裸 URL 字符串数组**，
    不是 `{url,title}`；`build_envelope` 把字符串归一化进 `url` 标识符，`table`/`md`/`ndjson` 才不必各自判类型，
    `-f raw` 仍原样透传服务端形状。服务端没给标题时不得凭空补出 `标题` 键。
    `table` 下汇总行是 `共 N 节点`。
    （离线已断言：`test_map_success_renders_nodes`、`test_map_table_counts_nodes`、
    `test_map_nodes_keep_titles_when_the_server_provides_them`、`test_map_md_and_ndjson_survive_bare_string_nodes`、
    `tests/unit/test_render.py::test_build_envelope_normalizes_bare_string_nodes`。）
    ✅ **真机已通过（2026-10-23 08:19）**：`map https://docs.tavily.com --limit 5 -f table` → 退出码 0、
    表头 `序号 | 网址`、5 行 URL、`共 5 节点 · 耗时 317ms · 请求编号 e45945e3-769c-4bb5-a2b2-c4ca9871efe3`；
    契约 `… -k test_map_returns_nodes` 通过（0.87s）。
    🔴→✅ 修复记录：修复前 `table`/`md` 在真机数据上抛 `AttributeError: 'str' object has no attribute 'get'`，
    而 `fixtures/out_tavily-map_sample.json` 的 `results` 恰好是**空数组**，离线渲染测试因此没能提前抓到。
18. `--tunnel`：`off` 时全程不 spawn ssh；`on` 直接建隧道并把端点改写为 `http://127.0.0.1:<port>/mcp`
    （保留 path），`"元信息"."端点"` 反映改写结果，且**对全部子命令生效**（含 `tools`/`doctor`）；
    `auto` 只在首次失败被分类为**网络不可达**后降级且只重试一次，池死亡/超时/限流一律不触发；
    `doctor` 的 `auto` **不自行 spawn ssh**（它的 TCP 层就是要如实报"直连不通"，只提示 `--tunnel on`）；
    ssh 起不来时保留原端点、报中文原因、退出码不变。`--dry-run` 与校验失败（退出码 2）**一律走在 spawn 之前**。
    （离线已断言：`tests/unit/test_tunnel.py` 8 条 + `test_cli.py` 隧道相关 11 条（按 `-k "tunnel or ssh"` 计数，
    含 M1 的 `--tunnel off` 对照、`池死亡不触发隧道`、`tools`/`doctor` 遵守 `on`、`dry-run`/非法入参不起 ssh），
    注入 `run`/`listening` 故不起真 ssh。）
    ✅ **真机演练已完成（2026-10-23，使用者批准，零配额：全程只发 `initialize` + `tools/list`，不消耗搜索配额）**：
    CLI 自行 spawn 出 `ssh -f -N … -L 18000:127.0.0.1:18000 mcp-host`（`BatchMode=yes` 可证是 `tunnel.py` 起的那条），
    `tools --tunnel on` → `"元信息"."端点" = http://127.0.0.1:18000/mcp`、`服务端版本 4.1.3`、退出码 0；
    复用检查：第二次 `--tunnel on` 与 `scripts/tunnel.sh up` 起的隧道都不重复 spawn（`pgrep -a ssh` 恒为 1 条转发进程）；
    `auto` 检查：`tools --endpoint http://203.0.113.11:18000/mcp`（直连由代理返回 502 ⇒ `网络不可达`）→
    先复用既有隧道成功、再在 `tunnel.sh down` 之后**从零 spawn** 新隧道成功（7.1s，含直连重试退避）；
    收回检查：`scripts/tunnel.sh down` 后 `ss -ltn` 上 18000 已释放、无残留进程，直连随即恢复 `v4.1.3`。
    演练中发现并修掉两个真实缺陷：① `--tunnel on` 此前**只对** `search`/`extract`/`crawl`/`map` 生效，
    `tools`/`doctor` 静默忽略该旗标；② `tools/list` 的传输层失败没走分类器，一次 HTTP 502 直接冒成
    裸 Python traceback 且退出码 1（应为 `网络不可达` + 退出码 3）。
    另修 `scripts/tunnel.sh` 的进程匹配：原模式要求 `-N -L` 相邻，而脚本自身与 `tunnel.py` 都在两者之间插 `-o`，
    导致 `status` 永远报"无隧道"、`up` 会重复起进程、`down` 收不回 CLI 起的隧道。
    注意 `pgrep -f 'ssh.*-L 18000'` 会匹配到**携带该模式的 shell 自身**，数进程请用 `pgrep -a ssh`。
19. 配置四级合并：`.tavily-cli.toml` 的 `endpoint` 决定真机请求发往何处；用户级与项目级同键时**项目级胜出**；
    `TAVILY_*` 环境变量压过文件、命令行选项压过一切；`format = "yaml"` 之类的坏值 → 退出码 2 且消息里
    **写明是哪个文件/哪个变量/哪个选项**；未知键（`endpoints`）直接拒绝；坏 TOML 报出完整路径；
    **缺文件不算错误**。`crawl`/`map` 的 120s 属"内置默认"层，被文件与命令行逐级压过。
    （离线已断言：`tests/unit/test_config.py` 13 条；真机已抽查：写文件里的 `endpoint` 指向死口 → 退出码 3 且
    `"元信息"."端点"` 即文件值，坏 `format` 值 → 退出码 2 带文件路径。均未消耗配额。）
20. 着色：TTY 下 `table`/`md` 含前景 SGR，`--no-color` 与 `NO_COLOR` 立即关闭；
    **剥掉 ANSI 的有色输出必须与无色输出逐字符相同**（列位置、`…` 截断都不变）；
    `json`/`ndjson`/`raw` 与 `-o` 写出的文件**任何情况下零转义序列**；`doctor` 状态列按通过/失败/跳过取绿/红/黄。
    （离线已断言：`tests/unit/test_render.py` 着色块 5 个函数 / 8 条参数化实例 + `test_cli.py` 5 条；
    真机抽查已在 pty 下做过一次：错误表 `类别` 行带 `^[[31m`、加 `--no-color` 后字节级消失，零配额。）

M3（`batch` + 并发上限 + schema 漂移预检；下列五条**全部是离线断言**，真机那一步见组末。
§6 规则 6 的预检另由 `test_batch_prechecks_schema_drift_once_before_the_first_line`、
`test_batch_does_not_warn_when_the_server_schema_matches_the_builtin`、
`test_batch_continues_when_the_precheck_itself_fails`、`test_batch_dry_run_skips_the_schema_precheck` 守着；
零配额真机侧 `tools -f json` 实测 `schema指纹` 仍等于内置副本 `sha256:6244c028…ecbf82`，
即今天线上不漂移、批量预检不会乱叫）：

21. 有序逐行输出：三行 NDJSON 输入 ⇒ stdout **恰好三行**、每行是单行 JSON（无缩进、逐行可被 `jq` 吃），
    `"行"` 依次为 1/2/3、`"关联编号"` 回显输入 `id`（未给则为 `null`），其余字段与 §5.2 信封**同构**。
    `--keys-en` 下同一批产出 `line`/`id` 且与中文输出严格同构（键一一对应、值相同）。
    `--with-meta` 时首行是 `{"元信息":{…}}`。空行被忽略但**不占序号**。
    （离线：`test_batch_emits_one_envelope_per_line_in_input_order`、`test_batch_keys_en_is_strictly_isomorphic`、
    `test_batch_with_meta_prints_envelope_first_line`、`test_blank_lines_are_skipped_and_do_not_consume_an_index`。）
22. 逐行校验隔离 + 坏行零出网（红线 1 的批量形态）：中间一行
    `{"tool":"search","arguments":{"query":"x","include_domains":["!!bad"]}}` ⇒ 只有该行
    `"成功": false` + `"错误"."类别" == "参数校验失败"`，前后两行照常执行；
    未知 `tool`、`arguments` 不是对象、JSON 语法错、非对象顶层值、**未声明的顶层键**
    ⇒ 同样只坏那一行且消息里带该行序号（`"行"` 字段 + stderr `第 N 行`）；
    整批退出码取"第一个失败行"的码。**守卫**：`tests/guard/` 必须断言这类输入**零 socket 写入**。
    （离线：`test_bad_line_fails_only_that_line_and_never_enters_the_queue`、
    `test_bad_json_line_reports_its_index_without_aborting_the_batch`、
    `test_missing_tool_or_arguments_is_a_line_error`、`test_undeclared_top_level_key_fails_only_its_own_line`、
    守卫 `tests/guard/test_no_socket.py::test_batch_bad_lines_never_touch_the_network`。）
    ✅ **零出网冒烟已通过（2026-10-23，`scripts/smoke.sh` 末段 `22 batch 坏行只坏那一行`）**：三行输入
    （中间一行的 `include_domains` 就是红线 1 的历史肇事值 `!!bad`）在已安装二进制上 → 退出码 2、
    stdout 恰好 3 行信封、`.[0]["请求"].params.name == tavily-search` 与 `.[2]["请求"]…tavily-extract` 都在、
    `.[1]["错误"]["类别"] == 参数校验失败`、stderr 含 `第 2 行`。全程 `--dry-run`，一次调用都没发。
23. 并发上限与 session 复用：`--concurrency 0`、`--concurrency 9`、`--concurrency abc` ⇒ 退出码 2、零出网、
    不静默截断；合法值下离线断言"同时在途调用数 ≤ n"且**整批只握手一次**
    （`transport` 层的 `_ensure_session` 走**锁内检查**：多线程同时首次调用时后到的线程复用已 adopt 的 session，
    不再各自 initialize 覆盖 session id）；`tools/call` 的 JSON-RPC `id` 在并发下不重号、响应按 `id` 归属。
    （离线：`test_batch_runs_lines_at_the_same_time_but_writes_in_input_order` 用 `threading.Barrier(3)`
    **强制**三行同时在途，顺序执行必然超时失败；`test_batch_never_exceeds_the_concurrency_cap` 观测峰值；
    `test_parallel_lines_still_share_one_session`、`test_batch_handshakes_once_for_the_whole_batch`、
    `test_concurrency_out_of_range_is_rejected_before_anything_is_read`；
    传输层 `tests/unit/test_transport.py::test_concurrent_first_calls_handshake_only_once`
    ——用能卡在 `initialize` 里等放行的替身 opener **强制**两次握手重叠，不靠线程时序碰运气。）
24. 池死亡即停 + 行数守恒：注入首行返回 `No active API keys available` ⇒ 后续行**不再发起调用**
    （假 client 记录调用次数可证），但输出行数仍等于输入有效行数，未执行行为
    `成功:false` + `类别:密钥池已死亡` + 消息说明"本行未发起调用"，整批退出码 **6**。
    限流（`RATE_LIMITED`）**不**触发这个停止，仍按 `--retries` 的退避矩阵处理。
    （离线：`test_pool_death_stops_submitting_but_keeps_the_line_count`、
    `test_rate_limited_line_does_not_stop_the_batch`、`test_exit_code_follows_the_first_failing_line`、
    `test_pool_death_outweighs_an_earlier_usage_line`。）
25. 格式白名单与输入面保护：`batch -f table` / `-f json` / `-f md` / `-f raw` ⇒ 退出码 **2**、零出网，
    stderr 中文说明逐行信封是唯一形状并给出 `| jq -s .` 的替代写法（**不得**默默改按 ndjson 输出）；
    stdin 是 TTY ⇒ 退出码 2 并提示用管道/重定向（NFR-2）；空输入（零有效行）⇒ 退出码 2、零出网；
    51 行 ⇒ 退出码 2 且**未发起任何调用**；`--dry-run` ⇒ 逐行打印将要发出的 JSON-RPC 请求体、零出网；
    `-o <path>` ⇒ 逐行写入该文件且零 ANSI 转义；
    **整批都是坏行时连 §6 规则 6 的零配额预检也不发**（实现第一版在这里违反了红线 1，由守卫测试抓出后修正）。
    （离线：`test_batch_rejects_formats_that_cannot_stream`、`test_batch_ndjson_is_accepted_explicitly`、
    `test_batch_refuses_a_terminal_stdin`、`test_batch_refuses_more_than_the_line_cap_without_touching_the_network`、
    `test_batch_with_no_valid_line_is_a_usage_failure`、`test_batch_dry_run_prints_request_bodies_and_sends_nothing`、
    `test_batch_dry_run_skips_the_schema_precheck`、`test_batch_writes_the_output_file_line_by_line`。）
    ✅ **零出网冒烟已通过（2026-10-23，`scripts/smoke.sh` 末段三条）**：已安装二进制上
    `batch -f table` → 2 + stderr 含"逐行信封"、空输入 → 2 + "没有有效输入行"、
    51 行 → 2 + "未发起任何调用"。这三条与用例 22 那条都走校验层/`--dry-run`，**一次 socket 都不该有**；
    stdin 是 TTY 与 `-o <path>` 两条只在离线断言里（冒烟脚本的 stdin 恒为文件，无法复现终端）。

⚠️ **M3 的真机退出条件"20 条查询压测无池污染"尚未执行**：它等于一次烧掉 20 个真实 `tools/call` 的
共享配额（本仓库前三档闸门从未涉及这个量级），且并发本身还可能把 dev key 打进冷却。
执行前需要使用者单独批准；批准后按 `doctor`（零配额）→ 小批 3 条 → 20 条的顺序放大，
并在压测后**必须**用 `tools`/`doctor` 复跑确认 4 个 Key 仍 `ACTIVE`。

## 10. 里程碑

| 阶段 | 范围 | 退出条件 |
|------|------|----------|
| M0 设计定稿 | 本文 + `design.md` + ADR + `AGENTS.md` | ✅ 已完成（2026-10-22，5 项决策见 §12） |
| M1 MVP | `search`/`extract`/`doctor`、JSON+table（中文键名）、校验层、退出码、离线单测、契约测试层 | ✅ 已完成（2026-10-22 主体 + 2026-10-23 收尾）：§9 用例 1–6、8–15 真机通过，用例 7 未跑（需人为打死共享 Key 池，违反红线 4）；离线单测 260 条全绿零网络；`tests/contract/` 四档配额闸门落地，零配额档与 QUOTA 档、DESTRUCTIVE 档均已真机通过 |
| M2 全覆盖 | `crawl`/`map`、隧道 `auto` 降级、toml 配置文件、table/md 着色 | ✅ **已完成（2026-10-23）**：离线单测 **329** 条全绿零网络；真机 §9 用例 16/17/18 全部通过（16/17 由使用者批准烧配额：`crawl docs.tavily.com` → 2 页 / `map docs.tavily.com --limit 5` → 5 节点，均退出码 0；18 为零配额隧道演练），19/20 做过零配额抽查，着色另有 `tools -f table` 的真实 TTY 证据。真机把 5 个离线测不到的缺陷打了出来：① `--tunnel on` 原先只对 `search`/`extract`/`crawl`/`map` 生效；② `tools/list` 传输失败冒裸 traceback 且退出码 1；③ `scripts/tunnel.sh` 的 `-N -L` 相邻模式永远匹配不到真进程（`status`/`down` 全部失效）；④ `map -f table`/`md` 在服务端的**裸 URL 字符串**上抛 `AttributeError`；⑤ HEAVY 契约只断言"是列表"，碰上 `example.com` 返回 0 页时空转 —— 现已改为"非空 + 逐条看字段 + 真渲染 table/md"。§9 用例 7 依旧不跑（需人为打死共享 Key 池，违反红线 4）。注：`tools`、ndjson/md/raw、`--keys-en` 已在 M1 交付 |
| M3 批处理 | `batch` NDJSON 流式、并发上限、schema 漂移告警 | 契约见 §4.6（输入）/§5.4（输出）/§6 规则 4–6（聚合、池死亡即停、漂移只警告）/§9 用例 21–25。**当前状态（2026-10-23）**：**代码与离线断言已交付**——`commands/batch.py` 输入面 + `cli.py` 编排（线程池并发、按输入序流式 flush、`POOL_DEAD` 停止发起、退出码聚合、整批一次 `tools/list` 预检）+ `render.py` 的 `batch` 键名段，§9 用例 21–25 逐条有命名断言（见各条末），离线单测 **329 → 366** 条全绿零网络。**实现期间**由守卫层抓出并修掉 1 个红线级缺陷：**全批都是坏行时预检仍出网一次**（违反红线 1，由 `tests/guard/` 的 tripwire 抓到）；另把"空输入 ⇒ 退出码 0 + 提示"改回文档口径的 **2**。真机退出条件"20 条查询压测无池污染"**尚未执行**，它是一次新的共享配额支出，需使用者单独批准 |
| 后续候选 | 配额探测（需服务端加端点）、`mcp-config` 生成器、结果 diff | 依服务端演进 |

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 服务端把 400 误判为 401（**主修已在运行容器生效，但补丁尚未提交**；根因与残留项见 docs/adr/0003-validate-before-send.md） | 复发时单次误用即永久打死共享池，影响该服务器上所有使用者 | 客户端全量前置校验 + `--dry-run` + 永不自动重试 `isError`（闸门一律不放宽） |
| 服务端 README / git 提交记录滞后于运行代码（容器 = 工作区源码，19/19 `.py` MD5 一致；`serverInfo.version` 其实是 **FastMCP 库版本**） | 静态契约漂移，参数增删无预警 | 运行时以 `tools/list` 为准 + `schema_hash` 比对告警 |
| 网关无鉴权 | 任何局域网主机可耗尽配额；CLI 不能"更安全"只能"更节制" | 默认并发 4、文档禁止公网暴露、建议隧道访问 |
| dev key 额度低 | 批量场景易 429/EXHAUSTED | M3 的三道节制：并发默认 4 / 上限 8 且**越界即拒绝**（不静默截断）、单次 `batch` 最多 50 行（超出退出码 2、零出网）、任一行判定 `POOL_DEAD` 后**不再发起新调用**（§6 规则 5）；另有明确退出码 8 与文档标注 |
| 端点变更（compose 改端口） | CLI 硬编码失效 | 端点走配置，`doctor` 首先检查连通性并给出真实 URL |
| Python 冷启动 | agent 高频调用感知变慢 | 见 ADR-0001：默认标准库传输层，避免导入重型 SDK |

## 12. 决策记录（2026-10-22 使用者拍板）

| 编号 | 议题 | 决策 | 影响章节 |
|------|------|------|----------|
| D-1 | 命令名 | **`tavily-cli`**（不用 `tavily` / `tvy`） | §4.1、§9、`pyproject.toml [project.scripts]`、README |
| D-2 | 输出语言 | **全部中文**——`--help`、错误、日志、表头、以及 JSON **键名**均中文；仅"线上协议参数名/枚举值、CLI 选项名、`--format raw` 字段"三处保持英文，并提供 `--keys-en` 切回英文键名 | §5.0、§4.5、§6、§7、design.md §9、AGENTS.md §5 |
| D-3 | `crawl`/`map` 归属 | **确认放 M2**，不进 MVP（耗时最长且最容易消耗共享配额） | §10、§9 前言 |
| D-4 | 实现与分发 | **Python**；**不使用 `uv tool install`**，统一安装与运行在本机 `.venv`（Python 3.14.4） | §8 NFR-4/NFR-5、§9 用例 1/11、AGENTS.md §2/§6.2 |
| D-5 | 服务端 400→401 缺陷 | 本工作空间**只做根因分析，不改服务端代码**；分析见 `docs/adr/0003-validate-before-send.md`，**修复由使用者在 mcp-host 上执行** | §11 风险表、AGENTS.md §3 红线 5 |
| D-6 | `--request-timeout` 归属 | 服务端 4.1.3 删掉 `timeout` 入参后，**保留选项但重定义为本次调用的本地 HTTP 读超时**（仍校验 1.0–60.0，**永不出网**）；不删除选项、不改名 | §4.2、§4.5、design.md §6 |
| D-7 | 契约测试的配额闸门 | 契约层按代价分档：`-m network` 默认**零配额**（只走 FastMCP 层拒绝）；`TAVILY_CONTRACT_QUOTA=1` 才允许 1 次 search + 1 次 extract；`TAVILY_CONTRACT_HEAVY=1` 才跑 `crawl`/`map`；`TAVILY_ALLOW_DESTRUCTIVE=1` 才复测 `!!bad` 事故 | §9、§10、tests/contract/ |
| D-8 | `节点` 的形状 | 实测服务端 `map` 返回**裸 URL 字符串**；`build_envelope` 归一化成 `{"url": …}` 记录（对外 `{"网址": …}`），使 `table`/`md`/`ndjson` 共用一条记录路径，`-f raw` 保持服务端原样。**此条由实现侧定稿**（不归一化就等于 `map -f table` 崩溃），使用者若偏好"字符串数组原样透出、只在渲染层判类型"，推翻本条即可，改动面只在 `render.build_envelope` + §5.2 那段"唯一例外" | §5.2、§9 用例 17、design.md §9 |
| D-9 | `batch` 的输出面 | **逐行完整信封**是唯一形状；`-f json/table/md/raw` 一律**拒绝**（退出码 2）而不是默默改成 ndjson；**顺序优先于及时性**（并发执行、按输入序写出）。**由实现侧定稿**：拒绝的理由是本仓库真踩过"全局旗标只在部分 handler 生效 = 静默失效"（AGENTS §4）；若要"其它格式也接受、内部强制降级"，改动面只在 `cli.py` 的 `_handle_batch` 格式闸门（`commands/batch.py` 只管输入面解析，不含格式判断），但请同时保留一条断言证明降级会在 stderr 说明 | §4.6、§5.4、§9 用例 21/25 |
| D-10 | `batch` 的配额节制 | 单次最多 **50 行**（`constants.MAX_BATCH_ITEMS`，超出零出网拒绝）；任一行分类为 `POOL_DEAD` 后**停止发起新调用**，未执行行仍输出跳过信封以保证**行数守恒**；退出码聚合优先级 = `POOL_DEAD(6)` > 第一个失败行。**由实现侧定稿**：守恒的取舍是"宁可多写几行无用信封，也不让消费方按行号对齐时静默少一条"；若改成"直接截断输出"，需同时放弃 §9 用例 24 的行数断言 | §4.6、§5.4、§6 规则 4/5、§11、§9 用例 24 |

D-2 的取舍已在 §5.0 明确写出：中文键名让 `jq` 表达式需写成 `.["结果"][]."网址"`（裸中文标识符是语法错误，见 §9 用例 1），
而脚本的**稳定契约是数字退出码**，不是键名拼写；需要英文键名时用 `--keys-en`。

**D-5 落地情况**：网关侧主修**已生效并实测**——判据是`isinstance(e, BadRequestError)` 的分支位于 Key 轮换与网络退避**之前**，且 401 判定里的裸 `"invalid"` 子串已删除 ⇒ Tavily 400 不再污染 Key 池。
但三项加固未落地（`ERROR` 仍是终态、同错熔断缺失、过小 `timeout` 仍会逐 Key 退避重试），且补丁是否已进服务端仓库由运维侧掌握 ⇒ **本文件的派生约束、§11 风险表与全部前置校验要求一律不变**。
根因与修复建议见 `docs/adr/0003-validate-before-send.md`。

**D-6 补充**：网关镜像因 `fastmcp==4.1.3` 重建后，上一条结论已在**重建后的容器**上重新实测成立。
本次升级同时**删掉了 4 个工具的 `timeout` 入参**（改由 `Depends(_configured_tool_timeout)` 从
环境变量 `TAVILY_REQUEST_TIMEOUT` 注入，默认 15s），因此"过小 `timeout` 逐 Key 退避重试"这一
风险**从客户端已不可达**，只剩运维侧配置错误的可能；其余闸门不变。
