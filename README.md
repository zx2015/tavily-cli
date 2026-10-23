# tavily-cli

在命令行里使用自建的 `mcp-tavily` 聚合网关做网页搜索、正文提取、站点爬取与结构映射。

| 版本号 | 日期       | 变更说明 | 作者 |
|--------|------------|----------|------|
| v0.1.0 | 2026-10-22 | 设计定稿：需求文档、技术设计、3 条 ADR、目录骨架与服务端实测报告；实现待启动（M1） | Qoder |
| v0.2.0 | 2026-10-22 | 落地 5 项使用者决策：命令名 `tavily-cli`、输出与 JSON 键名默认中文（`--keys-en` 切英文）、`crawl`/`map` 归 M2、安装运行统一走 `.venv`、服务端 400→401 误判只出根因分析由使用者修复 | Qoder |
| v0.3.0 | 2026-10-22 | M1 交付：`search`/`extract`/`tools`/`doctor` 可运行，中文键名 + `--keys-en` + `raw`、退出码与校验前置全部落地，离线单测 253 条，新增 `scripts/smoke.sh` 端到端冒烟；§9 验收口径按实测修正（jq 中文键需写作 `.["结果"]`） | Qoder |
| v0.4.0 | 2026-10-23 | M1 收尾：补齐 `tests/contract/` 契约层（按配额消耗分四档环境变量闸门）；同步服务端运行时漂移 4.1.0→4.1.3——`timeout` 入参已被删除，`--request-timeout` 改为**只作用于本地读超时、不出网**；离线单测 260 条；400 事故端到端重放已在使用者批准下执行并通过 | Qoder |
| v0.5.0 | 2026-10-23 | M2 代码落地：`crawl`/`map` 两条命令（默认 120s 超时）、`--tunnel auto|on|off` SSH 隧道降级、四级配置合并（toml 两级 + env + CLI）、TTY 下 `table`/`md` 着色（`--no-color`/`NO_COLOR` 可关）；离线单测 260 → 319 条 | Qoder |
| v0.6.0 | 2026-10-23 | 隧道降级**真机演练通过**（零配额：全程只发 `initialize` + `tools/list`）——`on` 自建、端口复用、`auto` 改道、`tunnel.sh down` 收回四步都有实测证据；演练中修掉 3 个缺陷（`--tunnel on` 原先对 `tools`/`doctor` 静默失效、`tools/list` 传输失败冒裸 traceback 且退出码 1、`tunnel.sh` 的进程模式匹配不到真进程）；离线单测 319 → 325 条 | Qoder |
| v0.7.0 | 2026-10-23 | **M2 真机验收完成**（使用者批准烧一次配额）：`crawl docs.tavily.com` → 2 页 / `map docs.tavily.com --limit 5` → 5 节点，退出码均 0。真机打出两处服务端形状意外——`map` 的 `results` 是**裸 URL 字符串**（`table`/`md` 曾抛 `AttributeError`，现已归一化为 `{"网址": …}` 记录，见需求 D-8；`-f raw` 仍是原样）、`crawl` 的页面**没有标题**（表头按规则省略该列）；另因 `example.com` 实测不可爬（返回 0 页）把两条 HEAVY 契约从"是列表就行"改成"非空 + 逐条看字段 + 真渲染"。着色加了一条零配额真实 TTY 证据（`tools -f table`）。离线单测 325 → **329** 条 | Qoder |
| v0.8.0 | 2026-10-23 | **M3 落地：`batch` 命令可用**（离线）。命令面新增 `batch` 与一段 NDJSON 示例，并列出首次使用必须知道的四件事（顶层只认 `id`/`tool`/`arguments`、逐行信封带 `行`/`关联编号`、只接受默认 `-f ndjson` 形状、`--concurrency` 默认 4 上限 8 且池死亡即停止发起）；退出码一节补上 `batch` 的**聚合规则**（全绿 0 / 任一池死亡 6 / 否则取按输入序第一个失败行）。离线单测 329 → **366** 条全绿零网络。真机那一步（`doctor` → 3 行小批 → 20 行压测）**未执行**，它约等于 20 个真实 `tools/call`，属新的共享配额支出，需使用者点头 | Qoder |
| v0.9.0 | 2026-10-23 | `scripts/smoke.sh` 末段新增 4 条**零出网** `batch` 冒烟（§9 用例 22/25：混合批次 `--dry-run`、`-f table`、空输入、51 行，均已在已安装二进制上跑通、不消耗配额），命令面章节与脚本头部注释同步；状态说明里"21–25 只有离线断言"改为更准确的"离线断言 + 4 条零网络冒烟，仍欠 20 行真实并发压测" | Qoder |

> **当前状态（2026-10-23）**：**M1 + M2 全部完成并通过真机验收；M3 代码与离线断言已交付**。七个命令
> `search`/`extract`/`crawl`/`map`/`batch`/`tools`/`doctor` 可用，中文键名 + `--keys-en` + `-f raw`、
> 校验前置（非法入参零出网）、9 个退出码、`--tunnel auto|on|off` 降级、四级配置合并、
> TTY 下 `table`/`md` 着色；离线单测 **366** 条全绿零网络。
> `docs/requirements.md` §9 用例 1–6、8–18 已真机通过（用例 7 要人为打死共享 Key 池，
> 按红线不执行），四档配额闸门（零配额 / QUOTA / DESTRUCTIVE / HEAVY）均已实跑；
> §9 用例 21–25（M3）由具名离线断言守着，其中 22/25 的 4 条零出网路径已进 `scripts/smoke.sh` 末段
> 并在已安装二进制上跑通（不消耗配额）。**仍未执行**的是真机那一步：3 行小批 + 20 行压测，
> 约 20 个真实 `tools/call`，属新的共享配额支出，需使用者点头。
> 想做贡献或继续推进，请先读 [`AGENTS.md`](AGENTS.md)。

## 为什么需要它

`mcp-tavily` 已经把多个 Tavily API Key 聚合成一个 MCP 服务（加权轮询、429 冷却、故障切换），
但它只讲 MCP Streamable HTTP。要在 shell / cron / CI / 其他 agent 的 Bash 工具里用搜索能力，
每次都得自己处理 session 头、SSE 分帧、JSON 二次解码、参数校验和错误分类。

`tavily-cli` 把这些还原成一条 Unix 命令，并且——更重要的是——**在客户端侧就挡住会击穿共享
Key 池的入参**。实测证明一个格式不合法的域名参数（如 `!!bad`）会被服务端误判为鉴权失败，
把全部 Key 标成终态、导致整台机器的搜索能力瘫痪且不会自愈。详见
[`study/mcp-tavily-endpoint/README.md` §5](study/mcp-tavily-endpoint/README.md) 与根因分析
[`docs/adr/0003-validate-before-send.md`](docs/adr/0003-validate-before-send.md)。

> 该误判已在网关侧修复（上游 400 不再落入 401 分支），并在一次经批准的端到端重放中
> 实测确认不再污染 Key 池。
> **客户端前置校验仍然保留**：服务端补丁尚未提交、"同错熔断"这类加固未落地，
> 而且本地校验能省下一次真实往返与共享配额——本 CLI 的约束不依赖服务端的善意。

## 命令面（M1 + M2 + M3 全部可用）

```bash
tavily-cli search "示例股份 2026 半年报 营收" --max-results 5
tavily-cli search "Tavily pricing" -f json | jq -r '.["结果"][]."网址"'
tavily-cli search "Tavily pricing" -f json --keys-en | jq -r '.results[].url'
tavily-cli extract https://example.com --depth advanced
tavily-cli crawl https://docs.tavily.com --max-depth 2 --max-breadth 5 --select-path '^/api'
tavily-cli map https://docs.tavily.com --limit 50
tavily-cli tools          # 运行时 tools/list + schema 指纹（契约漂移告警）
tavily-cli doctor         # 分层探活：TCP → 握手 → tools/list → 最小搜索

# batch：stdin 每行一个 JSON 对象，输出一行一个信封，顺序恒等于输入顺序
printf '%s\n' \
  '{"id":"q-01","tool":"search","arguments":{"query":"示例股份 2026 半年报","max_results":3}}' \
  '{"id":"q-02","tool":"extract","arguments":{"urls":["https://docs.tavily.com"]}}' \
  | tavily-cli batch --concurrency 4 --with-meta | jq -c '.["行"], .["关联编号"], .["成功"]'
```

`batch` 的四件事要先知道：
① 输入面**只认** `id`/`tool`/`arguments` 三个顶层键（拼错的键 ⇒ 该行失败，别的行照跑），
交互式终端上直接执行会被拒绝（退出码 2）并提示改用管道或重定向；
② 输出是逐行完整信封，额外带 `行` / `关联编号`（`--keys-en` 下 `line` / `id`），
一行输入恒一行输出，池死亡没跑到的行也会占一行；
③ 只接受默认（等价 `-f ndjson`）格式，`-f json/table/md/raw` ⇒ 退出码 2；
要 JSON 数组就 `tavily-cli batch … | jq -s .`；
④ `--concurrency` 默认 4、上限 8（越界直接报错不截断），任一行被判 `密钥池已死亡` 后
**不再发起新调用**——共享 Key 池是终态，继续灌请求只是白烧配额。

> ⚠️ `crawl`/`map` 的目标站点必须**可爬**：实测 `crawl https://example.com` 返回
> `成功: true` + 0 页（退出码 0，不是错误）。要判断"真没内容"还是"命令失败"，看退出码与 `"成功"`。

输出与 `--help`、错误信息默认**全中文，含 JSON 键名**；需要英文键名时用 `--keys-en`，
需要服务端原样字段时用 `--format raw`（见 requirements §5.0）。
`table`/`md` 在 TTY 下会着色（表头加粗、网址与汇总暗淡、失败与错误类别红色），
`--no-color` 或 `NO_COLOR` 关闭；`json`/`ndjson`/`raw` 与 `-o` 写出的文件**永不含转义序列**。

## 配置与隧道

取值优先级 **命令行 > 环境变量 > 配置文件 > 内置默认**：

```bash
# ~/.config/tavily-cli/config.toml（用户级）或项目内 .tavily-cli.toml（向上查找，覆盖前者）
endpoint = "http://127.0.0.1:18000/mcp"
timeout  = 90
format   = "table"
tunnel   = "auto"
```

对应环境变量为 `TAVILY_MCP_ENDPOINT` / `TAVILY_CLI_TIMEOUT` / `TAVILY_CLI_FORMAT` /
`TAVILY_CLI_TUNNEL` / `TAVILY_SSH_HOST` / `TAVILY_CLI_KEYS_LANG`。坏配置一律退出码 2，
并在消息里写明**是哪一层**（哪个文件、哪个变量、哪个选项）写错的；未知键直接拒绝。

`--tunnel`：`auto`（默认，直连失败且分类为网络不可达时自动改道 SSH 隧道并只重试一次）、
`on`（跳过直连）、`off`（永不碰 ssh）。三档对**全部六个子命令**一致生效；`--dry-run` 与参数校验
失败（退出码 2）都走在 spawn 之前，所以非法入参绝不会起 ssh。池死亡、超时、限流都不会触发降级——
隧道救不了它们，再发一次只会多烧一次共享配额。本机 `127.0.0.1:<port>` 已有转发口时**直接复用**，
不重复起进程；ssh 起不来则保留原端点、在 stderr 报中文原因、退出码不变。
手工建/看/收回用 `scripts/tunnel.sh`（`status|up|down`）。
这套流程已于 2026-10-23 以**零配额**方式真机演练通过（全程只发 `initialize` + `tools/list`）。

## 退出码

退出码：`0` 成功 · `2` 参数校验失败（不出网） · `3` 网络不可达 · `4` 协议异常 ·
`5` 工具执行失败 · `6` **服务端 Key 池已死亡** · `7` 超时 · `8` 限流。完整语义见
[`docs/requirements.md` §6](docs/requirements.md)。

`batch` 不引入新码，只做**聚合**：全部行成功 ⇒ `0`；任一行是 `密钥池已死亡` ⇒ `6`（共享服务已不可用，
不该被其它噪声盖住）；否则取**按输入序第一个失败行**的码。每行自己的类别仍写在该行信封的 `"错误"` 里。

## 文档地图

| 文件 | 内容 |
|------|------|
| [`AGENTS.md`](AGENTS.md) | 执行手册：红线、已知陷阱、工作流、自检清单 |
| [`docs/requirements.md`](docs/requirements.md) | 需求文档：目标、命令面、输出契约、验收标准、里程碑 |
| [`docs/design.md`](docs/design.md) | 技术设计：分层架构、模块职责、传输细节、性能预算 |
| [`docs/adr/`](docs/adr/) | 决策记录：传输层选型 / 错误分类与退出码 / 校验前置 |
| [`docs/requirements.md` §12](docs/requirements.md) | 7 项使用者决策记录 D-1…D-7（命令名、语言、里程碑、分发方式、服务端缺陷处置、`--request-timeout` 语义、契约测试配额闸门） |
| [`study/mcp-tavily-endpoint/`](study/mcp-tavily-endpoint/) | 服务端实测报告 + 可复跑探针 + 原始响应 fixture（已脱敏） |

## 安装与运行

以下命令统一走本仓库的虚拟环境 `.venv`（本文写作时为 Python 3.14.4），**不使用 `uv tool install`**：

```bash
python3 -m venv .venv                            # 首次使用先建虚拟环境
.venv/bin/pip install -e ".[dev]"                 # 可编辑安装，产出 .venv/bin/tavily-cli
.venv/bin/python -m pytest tests/ -q  # 离线单测（默认 deselect @network）
.venv/bin/python -m pytest tests/ -q -m network   # 契约层零配额档（只握手 + tools/list）
scripts/smoke.sh                                # §9 用例 1–6、8–10 端到端冒烟 + 末段 batch 零配额子集
```

会消耗上游配额的契约用例按**消耗量**分三档环境变量闸门（默认档零配额，只需 `-m network`），
默认一律 skip：
`TAVILY_CONTRACT_QUOTA=1`（1 次 search + 1 次 extract）、
`TAVILY_CONTRACT_HEAVY=1`（`crawl`/`map`，开销最大；2026-10-23 已在使用者批准下真机跑过，
断言已改为"目标可爬 + 结果非空 + 逐条看字段 + 真渲染 table/md"，空载荷不再能让它变绿）、
`TAVILY_ALLOW_DESTRUCTIVE=1`（400 事故端到端重放，非常规排障手段，见 AGENTS 红线 1）。

`scripts/smoke.sh` 会发出**真实查询**（1 次 search + 1 次 extract + doctor 自带的 1 次最小
search），跑之前请确认共享配额；它把非法入参用例排在 doctor 之前，因此 doctor 通过同时也是
"污染尝试后 Key 池仍健康"的证据。末段 4 条 `batch` 用例（§9 的 22 与 25）全部止步校验层或
`--dry-run`，**零出网、零配额**，配额没批也能单独验收——但请照旧读一眼它们的期望退出码。

未执行安装时，可直接用 `.venv/bin/python -m tavily_cli …` 运行同一份代码。
运行时零第三方依赖（ADR-0001），`pytest` 只是开发依赖。

## 端点与安全说明

```
http://mcp-host:18000/mcp          # 你自己的 mcp-tavily 容器：宿主 18000 → 容器 8000
                                   # 内置默认值是 http://127.0.0.1:18000/mcp，用 --endpoint 指向真实网关
```

该网关**没有鉴权**，同一内网里任何能连上它的主体都能消耗共享配额。因此：
只可在受信内网使用；禁止公网暴露；本 CLI 不持有也不需要 Tavily API Key。
网络受限时 CLI 默认按 `--tunnel auto` 自动改道 SSH 隧道；手工建/看/收回用
[`scripts/tunnel.sh`](scripts/tunnel.sh)（`status|up|down`，等价于 `--tunnel on` 与事后清理）。
