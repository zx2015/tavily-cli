# tavily-search Agent Skill 需求规格（spec）

| 版本号 | 日期       | 变更说明 | 作者 |
|--------|------------|----------|------|
| v0.1.0 | 2026-10-23 | 首版：为本仓库新增一个可被其他 agent 加载的 Agent Skill（`search` 面）定规格。含载体格式实测结论、二进制发现问题、面向 agent 的输出契约、失败分支与配额节制、发布面脱敏义务、8 条验收用例、8 项待拍板决策 | Qoder |
| v0.2.0 | 2026-10-23 | 按使用者四条口径重写关键路径：**§5 改为"首次运行自举"**（探测常见 venv → 找不到就问用户并建议路径 → 建 venv 装 CLI → 把位置记进 `~/.config/tavily-cli/skill-state.toml`，端点同样首次采集并写进 CLI 自己的用户级配置）；**API Key 一项按实测驳回**（传输层零鉴权头、配置层未知键即退出码 2，故本期不采集，另开 D-S9 供拍板）；**§6.1 取消单轮搜索次数上限**并把它记成显式接受的风险 R-7；**新增 §6.2 能力路由**（宿主无原生 web search ⇒ 有搜索需求即直接用本技能；有原生工具 ⇒ 仅当用户点名 tavily 才激活），并规定该判定同时写进 `description` 与正文第一步。目标增至 9 条、验收 12 条、决策表扩到 14 项（其中 D-S3 随本次口径直接定稿），正文行数预算 120 → 170 | Qoder |
| v0.2.1 | 2026-10-23 | 按**实跑自举**（临时 HOME + 精简 PATH，全程零配额）修掉 §5 的五处：① §5.2 新增**先验证再记录**——`pip install -e` 拉不到构建后端 `hatchling` 时整条失败、`bin/tavily-cli` 不存在，原稿"装完立刻记录"会让下一轮探测读出假命中；② §5.4 状态文件改为**两形态**记录（`mode = binary` / `mode = source`），装不了的机器也能被 §5.2 第 1 步读回来，否则每个会话重问一遍；③ §5.2 第 5 步的零安装兜底修正为 `PYTHONPATH=<repo>/src python3 -m tavily_cli`（裸 `-m tavily_cli` 实测报 `No module named`）；④ §5.3 新增**先探测再问**——四层配置都空时内置 `DEFAULT_ENDPOINT` 是第五层且不落在任何文件里，实测零配额 `tools` 探测退出码 0，故探测成功就不打断用户；⑤ §5.3 补上 `tools` 信封的**实测形状**（清单在 `.results[]`、每条 `{name, description, inputSchema, title}`、`.tool = tools/list`）。同时把发现块产物统一成 `run` 调用形态，§5.2/§5.4 的判据从"`import tavily_cli` 成功"改成"`bin/tavily-cli` 存在"（等价且更省一次进程） | Qoder |
| v0.2.2 | 2026-10-23 | **真机验证挖出一条红线级风险并据此把规则改硬**：CLI 的 `tunnel` 缺省是 `auto`（`src/tavily_cli/config.py:161`），端点被判不可达时它会**自己 spawn 一条 SSH 端口转发到网关所在主机**——实测退出码 0、本机凭空多出一个转发进程并占住端口，而调用方只是想搜个网；且退出码 3 的 `.error.hint` 原文就建议改走隧道，`--quiet` 压不掉它（它在 JSON 信封里，不在 stderr）。因此 §6.4 从"不得教 agent 加 `--tunnel on`"**升级为"每一条调用行必须显式 `--tunnel off`"**，D-S5 随之改写、新增风险 R-11；技能面 14 条示例（`SKILL.md` 2 + `references/` 12）已全部钉上该旗标，并由 `test_every_invocation_pins_the_tunnel_off` 逐行守住。对照实测：同一坏端点加 `--tunnel off` ⇒ 退出码 3 / `TRANSPORT`、SSH 进程数前后不变 | Qoder |
| v0.2.3 | 2026-10-23 | **技能已实装进本机 Qoder agent**（SG-1 的 Qoder 这一支落地）：§3 新增"本地技能根"实测行——生效路径是 `<config root>/skills/<技能名>/SKILL.md`（本机即 `~/.qoder-cn/skills/`，与 `plugins/`、`settings.json` 同根），而**应用 UI 文案宣称的 `~/.qoder/skills` 实测不生效**（放进去、新会话也读不到）；技能清单在会话开始时冻结，目录放对后新会话才列出裸名 `tavily-search`。§9.1 的 SK-1 据此由"❌ 未执行"改为"⚠️ 部分"（登记 / 新会话列出 / `Skill` 原样加载正文三段有实机证据，"提问⇒选中并产出契约内命令"仍与 SK-7/SK-8 同批待批准）。本机另预置 `~/.config/tavily-cli/skill-state.toml`（`mode = binary`，路径先经 `--version` 退出码 0 验证），端点走内置默认且零配额 `tools` 探测退出码 0 ⇒ 按 §5.3 **不写** `config.toml`、不打断用户 | Qoder |

关联文档：CLI 契约 `docs/requirements.md`（§4.2 参数、§5.1–§5.2 输出、§6 退出码、§7 配置）·
技术方案 `docs/design.md` · 工作约定与红线 `AGENTS.md` · 发布脱敏 `scripts/publish_public.py`

> **本文只定"技能"这一层的规格，不重复 CLI 自身的契约。** CLI 的参数校验规则、键名映射、
> 退出码语义一律以 `docs/requirements.md` 为权威；技能文档只允许**指路**，不允许**复述**——
> 复述必然漂移（本仓库已实测过一次"文档写的 `标题` 字段服务端根本没有"，见 §7 R-2）。
> **例外**：§5 的自举流程与 §6.2 的能力路由是技能独有的面，CLI 里没有对应物，必须写实。

---

## 1. 背景

`tavily-cli` 已经把 mcp-tavily 网关还原成一条 Unix 命令，但"其他 agent 会用"这件事目前仍然
依赖**人类在提示词里教它**：agent 不知道该命令存在、不知道要先装、不知道该连哪个端点、
不知道非 TTY 默认输出什么，更不知道退出码 6 意味着"别再试了，共享 Key 池已经终态"。

Agent Skill 就是补这一层的载体：一个带 YAML frontmatter 的 `SKILL.md`，被 agent runtime 在
启动时索引进"可用技能"列表，`description` 决定它何时被选中，正文决定它被选中后怎么做。

目标是**让任意支持该规范的 agent，在只被人类点头一次的前提下完成自举**（找到自己的 CLI、
问到端点、把位置记下来），此后不需要任何额外解说就能正确、可诊断地用 `tavily-cli search`
完成联网搜索——并且**绝不对共享服务做出运维类动作**。

## 2. 目标与非目标

### 2.1 目标

| 编号 | 目标 |
|------|------|
| SG-1 | 随仓库分发一个技能目录，Qoder / Claude Code / Codex 三类 runtime 都能按同一份文件加载 |
| SG-2 | 被选中后，agent 发出的命令**一定**通过 CLI 前置校验（不产生出网的坏参数请求） |
| SG-3 | agent 能只靠退出码 + JSON 字段判定成功/失败/该不该停，不需要读自然语言错误提示 |
| SG-4 | **首次运行自举**：探测 → 问用户（附建议路径）→ 建 venv 安装 → 把位置与生效端点记录下来，全流程幂等，第二次不再问 |
| SG-5 | 端点由使用者在首次触发时提供并落盘到 CLI 自己的配置层，技能正文与示例**不含**任何真实端点、内网地址、ssh 主机或运维指令 |
| SG-6 | 能力路由明确：宿主没有原生 web search 时，本技能就是默认搜索通道；有原生工具时，只在用户点名 tavily 时介入 |
| SG-7 | 失败即停的规则写进技能（退出码 2/3/4/5/6/7/8 各自动作），使"没被人类叮嘱"的 agent 也不会对着一个已经终态的 Key 池继续灌请求 |
| SG-8 | 自举过程只写**用户目录**（`~/.config/tavily-cli/`），仓库工作树在自举后 `git status` 仍干净 |
| SG-9 | 技能自身可验收：12 条用例里 10 条零出网/零配额，真机那 2 条合并成**一次**真实搜索且需单独批准 |

### 2.2 非目标（本期明确不做）

- ❌ 不做 MCP server、不做 HTTP API 包装、不做多语言技能副本（先中文为主，见 D-S8）。
- ❌ 不把 `extract`/`crawl`/`map`/`batch` 展开成独立技能（本期只 `search`；其余放 `references/` 指路，见 D-S2）。
- ❌ **不采集、不存储、不透传任何 API Key**——理由不是"不做"而是"当前做了会把 CLI 打死"，见 §5.5 与 D-S9。
- ❌ 不静默修改用户 shell 环境（不改 `PATH`、不写 `~/.bashrc`）：靠状态文件 + 绝对路径解决，见 §5.4。
- ❌ 不教 agent 任何服务端运维动作（重启容器、改 `.env`、动 Key 池、起 SSH 隧道）——红线级，见 §6.4。
- ❌ 不引入新的 CLI 能力。若技能"需要"某个不存在的行为（如鉴权头），先回 `docs/requirements.md` 立项并开 ADR，不要在技能里绕。

## 3. 载体规格（实测得到的格式事实）

以下三条是**在探索了本机 1388 份 `SKILL.md` 之后**测得的，不是规范文本的转述：

| 事实 | 实测值 | 因此本项目的口径 |
|------|--------|------------------|
| frontmatter 必填键 | 样本 300 份里 `name` 299 次、`description` 299 次（1 份缺 `name` 属异常样本） | 两者都写，且 `name` **等于技能目录名** |
| 可选键 | `metadata` 68、`license` 18、`version` 11、`compatibility` 5、`disable-model-invocation` 6 | 用 `metadata.{author,version}`；**不依赖** `allowed-tools`（该样本 0 次出现，写了不保证被尊重） |
| 目录布局 | 插件根 = `<runtime>-plugin/plugin.json` + `skills/<name>/SKILL.md`，技能内可选 `references/`、`scripts/`、`assets/`、`agents/`；正文用**相对路径**引用同级资源 | 技能写相对路径（`references/exit-codes.md`），不写绝对路径 |
| 本地技能根（Qoder CN 构建，实装测得） | 生效路径是 `~/.qoder-cn/skills/<技能名>/SKILL.md`（与 `plugins/`、`settings.json` 同一个 config root）。**应用 UI 文案宣称的 `~/.qoder/skills` 实测不生效**：文件放那里、新会话也读不到；放对之后当前会话的技能清单会刷新，`Skill` 可原样加载正文 | 交付说明里给"复制到 `<config root>/skills/`"这条安装法，并提醒以 `name` == 目录名为准；不要把 UI 文案里的路径当事实写进技能 |

**规格约束**：

- 位置：`skills/tavily-search/SKILL.md`（仓库根新建 `skills/`，理由见 D-S1）。
- 正文 ≤ **170 行**（v0.1.0 的 120 行容不下 §5 自举 + §5 端点采集 + §6.2 能力路由这三段关键路径，
  它们不能推给 `references/`，因为都在第一次调用就要被执行）。退出码全表、字段对照、
  排障配方仍**只放** `references/`，正文一行指路。超限即验收不通过（SK-2）。
- `description` ≤ 1024 字符，且必须同时包含四件事：
  ① **做什么**（用 `tavily-cli` 对自建 mcp-tavily 网关做网页搜索）；
  ② **能力路由条件**（宿主无原生 web search 时任何外部信息需求都用它；有原生工具时仅当用户点名 tavily / 自建网关 / 内网搜索通道）；
  ③ **首次运行会问什么**（需要 CLI 路径与端点，会写入用户配置）；
  ④ **触发词**（搜索、查一下、联网、最新、找资料、来源、引用链接、web search / tavily）。
  该字段是模型选中技能的**唯一**依据，禁止写成"tavily 相关"这种空话（路由判定还要在正文重复一次，见 D-S12）。

## 4. 面向 agent 的输出契约（技能必须教这一套）

| 项 | 技能里必须怎么写 | 依据 |
|----|------------------|------|
| 格式 | 固定显式写 `-f json`，不依赖"非 TTY 默认就是 json" | requirements §5.1；实测：管道下输出 JSON、`script` 造的 TTY 下输出人读渲染，二者不同 |
| 键名 | 固定显式加 `--keys-en` | 实测 `jq -r '.results[].url'` 可用；默认中文键必须写 `.["结果"][]."网址"`，agent 高频写错成 `.结果` 直接语法报错 |
| 成功判定 | `退出码 == 0 && .ok == true`；**0 条结果不是失败**（`.results == []` + 退出码 0） | §6 规则、AGENTS §4"空结果 ≠ 失败" |
| 取字段 | 只取 `.results[].{url,title,content,score}` 与 `.answer`；**不要**遍历 `pages/nodes/images` | 实测失败信封把 `页面/失败/节点` 一律输出为空数组，agent 遍历所有字段会误判"命令返回了空网页" |
| 失败解读 | `.error.kind`（`USAGE`/`TRANSPORT`/`PROTOCOL`/`TOOL_ERROR`/`POOL_DEAD`/`TIMEOUT`/`RATE_LIMITED`）+ `.error.message` | `--keys-en` 下 `类别` 输出英文枚举名，实测值 `USAGE` |
| 元信息 | 排障时读 `.meta.{endpoint,server_version,schema_hash,cli_version}`；正常路径不依赖 | 实测 `meta` 在失败时也齐全；`.meta.endpoint` 同时是 §5.3 端点验收的读数来源 |
| 静默 | 机器调用一律带 `--quiet`，把 stderr 留作日志通道 | requirements §5.1"stdout 只输出数据" |
| 原文透传 | 需要 Tavily 原始字段时用 `-f raw`（英文键、无信封），**默认不推荐**（绕过归一化 D-8） | requirements §5.2 |

## 5. 首次运行自举

本节是技能的关键路径：**任何一条命令发出之前**先走完 §5.2–§5.4。§5.2 与 §5.3 合并成
**一次**提问（不要先问路径、跑两步再回头问端点，那是对人类的第三次打断）。

### 5.1 为什么必须有这一节（实测事实）

在 agent 的 shell 里 `which tavily-cli` 退出码 **1**——venv 的 `bin` 不在 PATH 中。
所以任何直接写 `tavily-cli search "…"` 的示例，对没手工改过 PATH 的 agent 都是
`command not found`，而 agent 通常把它理解成"搜索能力不可用"然后静默放弃。

### 5.2 二进制发现与安装引导

**发现顺序（命中即停）**，解析产物是**一个调用形态**而非一个路径，正文把它封成 `run` 助手
（`env $ENV_PREFIX "$RUNNER" $RUN_ARGS "$@"`），此后每条示例都是 `run <命令> …`：

1. 状态文件 `~/.config/tavily-cli/skill-state.toml` 记录的形态 —— `mode = "binary"` 时看 `binary`
   是否可执行，`mode = "source"` 时看 `source_root/src/tavily_cli` 是否存在。**命中即跳过探测**。
   已记录的源码形态必须在这里直接生效，否则后面几步会把 `RUNNER` 覆盖掉（实现时真踩过这种串扰）。
2. `command -v tavily-cli`。
3. 环境变量 `$TAVILY_CLI_BIN`（给 cron/CI 与非标位置留口子）。
4. 探测常见 venv：`<repo>/.venv`、`~/.venv/tavily-cli`、`~/.venv`、`~/.local/pipx/venvs/tavily-cli`、
   `/home/<user>/venv`（本机即这一条）。**判据不是"目录存在"，而是该 venv 里有 `bin/tavily-cli`**：
   找到 venv ≠ 装了本 CLI，这条写反会产生一个假成功。
5. 仓库源码在但没装 ⇒ `PYTHONPATH=<repo>/src python3 -m tavily_cli`。
   实测：裸跑 `python3 -m tavily_cli` 在仓库根报 `No module named tavily_cli`——包住在 `src/` 下，
   不给 `PYTHONPATH` 就找不到它（本条是 v0.2.1 对 v0.2.0 原稿的修正）。
6. 全部失败 ⇒ 进入下面的提问。

**提问与安装（第 6 步才发生）**：

- 一次性告知用户：没找到 `tavily-cli`，需要一个虚拟环境来装；**建议路径 `~/.venv/tavily-cli`**，
  可以改；不覆盖任何已存在的非 venv 目录（先探测再建议，见 R-10）。
- 用户确认路径后执行：`python3 -m venv <路径>` → `<路径>/bin/pip install -e <仓库路径>`；
  若本地没有仓库源码，先问用户要 clone 到哪儿，再走公开仓库地址安装。**技能自带 CLI 源码**属明确不做（会让技能成为第二份实现）。
- **先验证再记录**：`env <路径>/bin/tavily-cli --version` 退出码 0 才允许写状态文件。
  实测理由：`pip install -e` 要先拉构建后端 `hatchling`，PyPI 不可达时整条失败、`bin/tavily-cli`
  根本不存在，而原稿写的是"装完立刻记录"——那会让下一轮 §5.2 第 1 步读出一个假命中，
  第一条搜索撞 `No such file or directory`。
- 装不上但本地有仓库源码 ⇒ 改记 `mode = "source"`（同样先验证）。**这一步是必需的**：
  只记 `binary` 的话，装不了的机器每个会话都要重新问一遍，违背"只问一次"。
- 两种形态都不可用 ⇒ **停止并如实回报**"未安装，搜索能力不可用"，并说清缺什么（能不能上 PyPI、
  有没有本地源码）。绝不静默 `pip install` 到用户当前环境里（那是不可逆的环境污染，且用户没同意）。

### 5.3 端点采集

- **先读现有配置**，四层任一有值就不问：`--endpoint` > `TAVILY_MCP_ENDPOINT` >
  项目 `.tavily-cli.toml` > 用户 `~/.config/tavily-cli/config.toml`（实测 `config.py:23-31` 就是这 6 个键）。
  已有值 ⇒ 打印当前生效端点（取自 `.meta.endpoint`）后直接进入搜索，不再提问。
- 四层都空 **不等于"必须问用户"**：还有 `constants.DEFAULT_ENDPOINT` 这一层内置默认值，它不落在
  任何文件里。所以先做一次**零配额探测** `run tools -f json --keys-en --quiet`（实测退出码 0，
  `.meta.endpoint` 即内置默认值）：探测成功 ⇒ 不打断用户直接进搜索；**探测失败** ⇒ 才与 §5.2 合并成
  一次提问（v0.2.1 补的规则，原稿是"四层空就问"，会在默认端点本来就通的机器上白白打断一次）。
- 没有 ⇒ 与 §5.2 合并成一次提问，请用户提供网关 URL。校验：必须是绝对 `http(s)://` URL、
  host 非空、路径通常是 `/mcp`；不接受裸 IP 无端口、不接受 `localhost` 之类的占位回答。
  用户答"不知道" ⇒ **停止并回报**，绝不猜一个地址发出去。
- **写入 CLI 自己的用户级配置**：`~/.config/tavily-cli/config.toml` 里 `endpoint = "…"`。
  选它而不是技能私有文件，是因为四级合并已实现、此后**每条命令与 `tools`/`doctor` 自动继承**，
  不需要技能在每次调用上贴 `--endpoint`（漏贴一次就连不上）。见 D-S13。
- 落盘后**必须**用零配额方式验证再回报：`run tools -f json --keys-en --quiet`，
  期望退出码 0、`.meta.endpoint` 等于用户给的值、`.meta.server_version` 非空。
  实测形状：`tools` 的信封与 `search` 同源，工具清单在 `.results[]` 里、每条是
  `{name, description, inputSchema, title}`，`.tool` 为 `tools/list`——**技能正文要写清这一点**，
  否则 agent 会拿读 `url/title` 的那套代码去读它。
  ⚠️ **不要用 `doctor` 做这一步验收**：`doctor` 自带一次最小搜索，会消耗 1 点共享配额。
  验证失败 ⇒ 明确说明是哪一层坏（TOML 语法、未知键、URL 非法、端点不可达），
  并**把写进去的那行删掉或改回**，不留一个坏配置给下一次运行。

### 5.4 状态文件规格

- 路径 `~/.config/tavily-cli/skill-state.toml`；键为**一个形态标记 + 一条路径 + 时间**：
  `mode = "binary"` 配 `binary = "<绝对路径>"`，或 `mode = "source"` 配 `source_root = "<仓库绝对路径>"`；
  两者都带 `verified_at`（ISO 8601）。形态只有这两种，写第三种等于给 §5.2 加一条没人实现的分支。
- 只存**形态、路径与时间**：端点归 `config.toml`（单一来源，别两处不一致），凭据一律不存。
- 目录不存在则创建。失效处理：记录的路径不存在 ⇒ 回到 §5.2 重新发现 ⇒ 必要时重新问 ⇒
  **整份覆写**状态文件，绝不追加第二个 `mode` 键（TOML 重复键会让 CLI 直接退出码 2）。
- **绝不写进仓库工作树**：不能落在 `<repo>/.tavily-cli.toml`（那是项目级配置，会把用户端点
  随仓库带出去，也会污染 `git status`）。仓库内**最多**只允许出现用户明确选定的 `<repo>/.venv`
  （已被 `.gitignore` 覆盖）；配置与状态文件一律写在用户目录。
  正文必须显式禁止"顺手在项目目录里生成配置"。（验收 SK-10。）

### 5.5 API Key：本期不采集（三条实测硬事实）

按你的第 2 条我把端点做了，但 Key 这一项当前**做不到不伤害 CLI**：

1. **网关不鉴权**（AGENTS 红线 6、研究文档），CLI 从不发鉴权头：实测
   `grep -riE 'authorization|api.?key|bearer|token' src/tavily_cli/{transport,session,constants}.py`
   对请求头**零命中**（唯一一处 `headers` 是解析响应头）。Key 发出去没有任何接收方。
2. **配置层会拒绝它**：`config.py` 只认 `endpoint/timeout/format/tunnel/ssh_host/keys_lang` 六个键，
   写入 `api_key = "…"` 直接撞上"未知键 ⇒ 退出码 2"（`config.py:62-66`）
   ⇒ **一旦技能替用户写了这一行，每一条命令都失败**，而且失败点在配置层，用户看不出跟技能的关系。
3. **技能是公开分发物**：收集并落盘 Key 会把密钥管理责任揽进一个"任何 agent 都能加载"的文件里；
   红线 3 的口径是本仓库任何位置都不出现 `tvly-*`。

⇒ 结论：**首次运行只问端点，不问 Key**。若你确实要连"带鉴权的网关"，那是 CLI 的新能力，
需要 ADR + 请求头 + 只从环境变量读 Key（永不落盘、永不打印、永不进仓库）+ 契约测试，
记在 D-S9 等你拍板要不要立项。

## 6. 行为契约（技能正文必须写进去的规则）

### 6.1 搜索次数：**不设上限**（使用者口径）

单轮对话里不做调用次数限制。仍然成立的只有这三条，且它们的理由不是"省配额"而是"别做错事"：

- **多查询走 `batch`**：N 个查询用一次 `batch` 而不是 N 次 `search`——省的是握手与 session 建立，
  并换来"输出顺序恒等于输入顺序"这条硬保证。
- **失败不许重播**：退出码 2/3/4/5/6/7 各自的处置见 §6.3，绝不因"还能再试"而重试。
- **不做无意义轮询**：同一查询反复刷同一结果、或为凑答案无限换近义词轰炸，属同类伤害。
- 并发上限仍由 CLI 的 `--concurrency ≤ 8` 守住；上游 429 冷却在网关侧兜底。

> ⚠️ 这一条把共享配额的敞口交给了调用方自觉（R-7）。维护者若日后要收紧，改动面只在技能正文
> 这一节，不动 CLI；本 spec 记录该风险**已由使用者知情并接受**。

### 6.2 能力路由（第 4 条口径）

技能正文的**第一件事**（在 §5 自举之前，因为它决定要不要自举）：

| 宿主能力 | 本技能何时用 |
|----------|--------------|
| **没有**原生 web search 工具 | 任何需要外部 / 最新 / 带来源链接的信息时，直接用 `tavily-cli search`，无需用户点名 |
| **有**原生 web search 工具 | 仅当用户点名 tavily、本仓库 CLI、自建 mcp-tavily 网关、或明确要求走内网搜索通道时使用；否则让路给原生工具 |

约束：
- 判定依据是宿主自己可见的工具列表，**不许猜**；猜不出来时按"有原生工具"处理（保守分支，避免抢活）。
- 两条分支共用 §5 自举与 §6.3/§6.4 全部规则；技能不得为被选中而贬低原生工具（不写"原生搜索不准"这类诱导语）。
- 该条件同时写进 `description`（§3）与正文（D-S12），因为 description 只影响"能不能被选中"，
  正文才影响"选中后怎么做"，缺一半都会跑偏。

### 6.3 失败分支（正文放这张表，细节进 `references/exit-codes.md`）

| 退出码 | `.error.kind` | agent 该做什么 |
|--------|---------------|----------------|
| 0 | — | 用结果；空数组时如实说"没查到"，不要当成命令失败 |
| 2 | `USAGE` | 改正参数后最多再发一次；这类错误零出网，重试不消耗配额 |
| 3 | `TRANSPORT` | 停止并回报"网关不可达"。**不照 hint 去开隧道**（每条调用行已显式 `--tunnel off`，见 §6.4），不自愈 |
| 4 | `PROTOCOL` | 停止并回报；建议人类自己跑 `tavily-cli doctor`（把配额消耗留在人的决定里） |
| 5 | `TOOL_ERROR` | 停止并回报服务端原文；**绝不自动重试**（AGENTS 红线 2） |
| 6 | `POOL_DEAD` | **立即停止本会话内全部搜索**并回报"服务端 Key 池已终态、需运维介入"；绝不重试 |
| 7 | `TIMEOUT` | 可**一次**加 `--timeout 90`；仍失败则回报，不重试 |
| 8 | `RATE_LIMITED` | 退避 ≥5s 后**至多一次** `--retries 1`；再失败即回报 |
| 130 | `INTERRUPTED` | 回报被中断，不重发 |

### 6.4 技能里禁止出现的内容（红线在技能面的投影）

- ❌ **不得包含**真实端点、内网 IP、ssh 主机别名、端口、服务端源码路径、文件哈希——技能是公开产物的一部分（§8）。
- ❌ **不得教 agent 执行** `docker restart`、`ssh <host>`、`scripts/tunnel.sh up`，也不得教它加 `--tunnel on`：
  这些是**维护者的共享基础设施动作**（AGENTS 红线 4），被第三方 agent 自动执行等于把共享服务的写权限交给不可信调用方。
  ⚠️ CLI 自身的退出码 6 提示文本里**含一条服务端运维命令**（`src/tavily_cli/classify.py:49`），
  所以技能正文**不得整段转述 CLI 的 hint**，
  只能写"退出码 6 = 池死亡 = 停止并回报人类"。
- ✅ **反过来也不够**：CLI 的 `tunnel` 缺省是 `auto`（`config.py:161`），**不写任何隧道旗标就会踩到同一个动作**——
  实测端点不可达时它自己 spawn 一条 SSH 端口转发到网关所在主机，退出码还是 0，调用方完全看不出发生过什么。
  所以本技能的硬规则是：**每一条会被原样复制的调用行都必须显式 `--tunnel off`**（`SKILL.md` §7 第一条给出理由，
  `tests/unit/test_skill_contract.py::test_every_invocation_pins_the_tunnel_off` 逐行守）。
  配套事实：退出码 3 的 `.error.hint` 原文建议"必要时改走 SSH 隧道"，且它在 JSON 信封里、`--quiet` 压不掉——
  技能必须写明"不照 hint 做"，否则一条失败提示就会把 agent 推去 spawn 隧道（R-11）。
- ❌ 不得出现 `tvly-*`、`api_key`、`Authorization`、`.env` 样例（§5.5）。
- ❌ 不得把配置、状态文件、venv 写进仓库工作树（§5.4）。
- ❌ 不得承诺结果质量或时效（不写"这个网关能给你最新财报"）；只说"返回 Tavily 搜索结果，可信度需自行判断"。

## 7. 风险与缓解

| 编号 | 风险 | 缓解 |
|------|------|------|
| R-1 | 技能示例被原样复制成 `tavily-cli search …` → command not found → 静默放弃 | §5 自举在第一条命令之前；正文示例一律用"解析出的绝对路径"占位而非裸命令（SK-3 实跑） |
| R-2 | 技能复述 CLI 参数/字段，CLI 演进后技能说谎 | 正文只写"选项与语义以 `tavily-cli search --help` 为准"，字段表限定在 §4 的稳定信封键集合 |
| R-3 | agent 把退出码 6 当可重试 → 继续灌请求 → 白烧共享配额 | §6.3 对 3/4/5/6/7 一律"停止并回报"，6 附加"本会话内全部搜索停手" |
| R-4 | 技能随公开仓库分发，泄漏内网拓扑 | 技能文本零真实端点（§5.5/§6.4）+ §8 泄露闸门；端点只在**用户目录**里，天然进不了 git |
| R-5 | 触发词太宽 → 本地代码问题也去搜索 | §3 description 第 ② 项 + §6.2 保守分支；SK-11 含 4 条负样本 |
| R-6 | 多 runtime 的 frontmatter 差异导致加载失败 | 只用实测确认的 `name`/`description`/`metadata` 三键；不出 plugin manifest（D-S1） |
| R-7 | **单轮不限搜索次数** ⇒ 共享配额敞口交给调用方自觉 | 已知并被使用者接受；仍保留三道兜底：失败不重播（§6.3）、多查询走 `batch`、CLI 侧 `--concurrency ≤8` 与池死亡即停。要收紧时只改 §6.1 一节 |
| R-8 | 技能写用户环境（建 venv、写 `~/.config`）属副作用 | 必须**先问后写**、写后回报路径、幂等（第二轮不再问，SK-9），并在正文告诉用户撤销方式（删状态文件 + `config.toml` 里那行 + venv 目录） |
| R-9 | 端点/路径被写进仓库工作树，随公开副本外泄 | §5.4 显式禁止 + SK-10 用 `git status --short` 断言自举全流程后仍干净 |
| R-10 | 建议的 venv 路径撞上用户已有目录 | 只建议在"不存在或已是 venv"的路径上创建；`python3 -m venv` 失败原样回报，不强推 `--force` |
| R-11 | **CLI 缺省 `tunnel=auto`** ⇒ 一次"只是搜个网"的调用在端点不可达时自己 spawn SSH 转发到网关所在主机（退出码 0、无痕），把共享基础设施的写权限间接交给任意 agent | 技能侧**每一条调用行显式 `--tunnel off`**（14/14，`test_every_invocation_pins_the_tunnel_off` 逐行守）+ `SKILL.md` §7 写明理由与实测对照 + 明令"不照 `hint` 做"（退出码 3 的 hint 就建议开隧道，且 `--quiet` 压不掉信封里的 `.error.hint`） |

## 8. 发布面义务（不可省略）

技能一旦进仓库，就同时是**公开 GitHub 副本**的一部分，必须登记进既有脱敏流水线：

1. `scripts/publish_public.py` 的 `GLOBAL`/`FILE_RULES` 覆盖 `skills/` 下所有文件；
   需要改写的片段用**带命中次数断言**的文件级规则，不在副本里手工编辑。
2. 泄露闸门 `FORBIDDEN` 新增技能专属检查：`skills/**` 内不得出现真实端点、内网地址、
   `ssh` 命令样例、`docker restart`、`api_key`/`Authorization`/`tvly-`。
   （这三项在 `classify.py` 里是合法的，在技能文档里不是——同一段文本不能一处能进一处不能进。）
3. 生成后重跑：公开副本离线单测（当前 366 条）+ 三条零命中扫描 + SK-6/SK-10/SK-12。

## 9. 验收标准（每条可执行）

| 编号 | 用例 | 期望 | 配额 |
|------|------|------|------|
| SK-1 | 把 `skills/` 挂进 agent 会话，问"帮我查一下 X 的最新进展" | 技能被列出并选中；产出的命令与 §4 契约一致（`-f json --keys-en --quiet`） | 只看命令文本时零出网 |
| SK-2 | 解析 `SKILL.md` frontmatter 与结构 | `name` == 目录名；`description` 非空 ≤1024 且含 §3 四要素；正文 ≤170 行；引用的 `references/*` 全部存在 | 离线 |
| SK-3 | **干净环境实跑自举**：PATH 无 `tavily-cli`、无状态文件、无 `config.toml` | 按 §5 顺序探测到第 6 步 → 一次提问（路径 + 端点合并）→ 建 venv 装 CLI → 写状态文件与 `config.toml` → 第二次调用不再问 | 零出网（安装走本地 `-e`；验证走 `tools` 属 SK-9） |
| SK-4 | 触发评测：6 条应触发（"查一下…"、"最新进展"、"有没有公开资料"…）+ 4 条不应触发（改本地代码、纯计算、读仓库内文件、闲聊） | ≥6/10 命中，4 条负样本不误触发 | 离线 |
| SK-5 | 按技能示例发一条坏参数查询（`--include-domain "!!bad"`） | 退出码 **2**、`.error.kind == "USAGE"`、**零 socket** | 零出网 |
| SK-6 | 公开副本 `skills/**` 过泄露闸门 | 对端点/IP/内网地址/ssh/docker/`api_key`/`tvly-` 全部**零命中** | 离线 |
| SK-7 | 一次真实搜索（`--max-results 3`） | 退出码 0、`.ok == true`、`.results` 非空、`jq -r '.results[].url'` 直接可取 | **1 次 search，需批准** |
| SK-8 | 全新会话端到端：只给一个需要联网的问题，不提 `tavily` 字样（在"无原生搜索"分支下） | agent 自行解析二进制、按契约发命令、成功后**不复述**服务端运维文本 | 与 SK-7 合并成同一次搜索，需批准 |
| SK-9 | 端点采集幂等：`config.toml` 无 `endpoint` 时提问；已有时 | 无 → 问 → 写入 → `tools -f json --keys-en` 退出码 0 且 `.meta.endpoint` 等于用户给的值；再次运行**不再提问**且直接显示当前端点 | 零配额（`tools/list`） |
| SK-10 | 自举全流程后 `git status --short` | **输出为空**：无 `.tavily-cli.toml`、无状态文件、无 `.venv` 被跟踪、无 `__pycache__` 泄漏 | 离线 |
| SK-11 | 能力路由对照：同一问题分别给"有原生 web search"与"没有"两种宿主 | 前者不激活本技能（除非点名 tavily）；后者直接激活 | 离线（看命令文本） |
| SK-12 | 全文（含 `references/`）扫描凭据面 | `api_key` / `Authorization` / `Bearer` / `tvly-` **零命中**；若 D-S9 改为"要支持鉴权"，本条改为断言 Key 只从环境变量读、永不落盘 | 离线 |

### 9.1 执行状态（2026-10-23 交付时）

| 用例 | 状态 | 证据 / 未执行的原因 |
|------|------|---------------------|
| SK-1 | ⚠️ 部分 | **登记与加载已实机验证**（2026-10-23 本机 Qoder 会话）：复制到 `~/.qoder-cn/skills/tavily-search/` 后，当前会话技能清单出现该条目、**新开会话**列出裸名 `tavily-search`（无插件前缀）且 `description` 完整、`Skill` 工具原样加载 170 行正文。**仍缺**"问一句『帮我查一下 X 的最新进展』⇒ 被选中并产出契约内命令"这一支（要真人提问，且真跑会含一次搜索 ⇒ 与 SK-7/SK-8 同批待批准） |
| SK-2 | ✅ 已验证 | `tests/unit/test_skill_contract.py`（20 条，全程离线） |
| SK-3 | ⚠️ 部分 | 发现块第 6 步（一无所获）与两种记录形态由 4 条子进程断言真跑；**"一次合并提问 → 建 venv → 写两份文件"这条人机交互分支未在真实 agent 会话里复现**（本机受控实跑走的是"装失败 ⇒ 改记 source 形态"分支） |
| SK-5 | ✅ 已验证 | 零配额实跑：退出码 2、`kind=USAGE`、`results` 空、无 socket（守卫层同一性质由 `tests/guard/` 长期守着） |
| SK-6 / SK-12 | ✅ 已验证 | 发布闸门 `SKILL_FORBIDDEN` 零命中 + 副本内 `test_skill_never_mentions_server_ops_or_credentials`；另有一条元测试守着"模式本身不被脱敏脚本改写失效" |
| SK-9 | ⚠️ 部分 | 探测幂等、`tools` 零配额验证、`.meta.endpoint` 读回均已实跑；**"用户给出 URL"这一支**只在临时 HOME 里以受控写入复现，未经真人回答 |
| SK-10 | ✅ 已验证 | 全流程（含状态文件与配置写入）之后 `git status --short` 仍只有既有未跟踪文件；两份文件都落在临时 HOME |
| SK-4 / SK-11 | ❌ 未执行 | 触发评测（10 条正负样本）与"有/无原生 web search 两种宿主"的对照都需要可复跑的评测装置，本机没有。**这是交付剩余的未知面**——`description` 触发词命中与 §6.2 路由判定离线证不了 |
| SK-7 / SK-8 | ⏸ 需批准 | 各含**一次真实 `search`**（共享配额支出）。按 D-S7 两条合并成同一次搜索执行，等你点头 |

## 10. 待使用者拍板的口径

| 编号 | 议题 | 我的推荐 | 备选与代价 |
|------|------|----------|------------|
| D-S1 | 技能放哪、要不要打包成 plugin | 仓库根 `skills/tavily-search/`，**不写** plugin manifest | 写 `.qoder-plugin/plugin.json` + `.codex-plugin/plugin.json` 可让安装变成一条命令，但两套清单字段会漂移、要额外维护版本号 |
| D-S2 | 覆盖面 | 只 `search`；其余命令在 `references/other-commands.md` 一行指路 | 五命令合一会让正文远超 §3 的行数预算且触发词互相污染；拆 5 个技能则维护面 ×5 |
| ~~D-S3~~ | ~~二进制发现归技能还是环境~~ | **已定**（v0.2.0）：技能负责发现 + 引导安装 + 记录 | — |
| D-S4 | 是否固定 `--keys-en` | **固定**，正文不出现中文键示例 | 尊重 D-2"默认中文" → 每个示例都要写 `.["结果"][]."网址"`，agent 出错率高 |
| D-S5 | 是否教 `--tunnel` | ~~一律不教~~ → **不教开启，且每条调用行显式 `--tunnel off`**（v0.2.2 定稿） | 教了等于把共享基础设施的 ssh spawn 权限交给任意 agent（红线 4）；而**不写旗标同样会 spawn**——CLI 缺省 `auto`。故"沉默"不是中立选择，必须显式关 |
| D-S6 | 是否附 `scripts/search.sh` 薄封装 | **不附**：CLI 已是封装，再套一层正是"全局旗标只在部分 handler 生效＝静默失效"的温床 | 附了可统一发现逻辑，但多一处要测试与脱敏的面 |
| D-S7 | 验收是否含真机（SK-7/8） | 需要，**合计 1 次真实 search**（批准后才跑） | 全离线也能交，但"agent 是否真按契约行动"离线证不了 |
| D-S8 | 技能语言 | 正文中文、命令与字段英文（仓库既有口径） | 英文正文对海外 agent 触发更稳（`description` 已中英并列触发词） |
| **D-S9** | **是否首次运行时向用户收集 API Key** | **不收集**（§5.5 三条实测：网关不鉴权、CLI 无鉴权头、配置层未知键即退出码 2） | 要支持得先在 CLI 立项：ADR + `Authorization` 头 + Key 只从环境变量读（不落盘/不打印/不进仓库）+ 契约测试；技能侧同步放开 §6.4 与 SK-12 |
| **D-S10** | 状态文件位置与格式 | `~/.config/tavily-cli/skill-state.toml`（TOML 与 CLI 一致、与配置同目录） | 技能目录内 `.state`（随仓库走、易被误提交 ⇒ 违背 R-9）；`~/.tavily-cli-skill.json`（多一处根目录散落文件） |
| **D-S11** | venv 建议路径 | `~/.venv/tavily-cli`（用户目录、不撞仓库、删了不影响别处） | `<repo>/.venv`（与公开 README 口径一致，但仓库一删即失效、且易被 `git add -A` 牵连）；`~/.venv`（可能与用户已有的单一 venv 冲突） |
| **D-S12** | 能力路由写在哪 | **`description` 与正文第一步都写**（前者决定能否被选中，后者决定选中后怎么做） | 只写正文 ⇒ 无原生搜索的宿主可能压根不选中；只写 description ⇒ 选中后判定不了工具列表 |
| **D-S13** | 端点落盘位置 | `~/.config/tavily-cli/config.toml`（复用 CLI 四级合并，全部命令自动继承） | 状态文件里另存一份 ⇒ 技能每条命令都要贴 `--endpoint`，漏贴即失败；两处都存 ⇒ 必然不一致 |
| **D-S14** | 单轮搜索次数 | **不限**（你的口径），风险 R-7 由维护者知情接受 | 保守档"单轮 ≤2 次"能压住失控，但会把合法的深挖场景一起掐掉 |

## 11. 交付后要同步的文档

- ✅ `AGENTS.md`：§1 文档表加一行（本 spec 的用途与改动须知）、§6.3 文档同步义务加一行
  "`skills/**` 变更 ⇒ 同步本 spec §3–§6 并重跑泄露闸门"、版本表追加一行。
- ✅ `docs/design.md`：§2 目录树补 `skills/tavily-search/{SKILL.md,references/}`，
  并新增一节说明"技能不进入 `src/`、不被代码 import、不参与打包"。
- ✅ `README.md`：命令面之后新增"给其他 agent 用"一节（技能目录、首次自举会问什么、写在哪、怎么撤销）。
- ✅ `docs/requirements.md`：§2.1 的 G-5（面向 agent 友好）补一条指向本 spec。
- ✅ `scripts/publish_public.py`：按 §8 补改写规则与专属闸门。
- ✅ （v0.2.2 追加）`AGENTS.md` §4 两条隧道坑 + 公开面覆盖文本同步；`README.md` "配置与隧道"
  补一条"缺省 `auto` ⇒ 不写旗标也会 spawn"的实测提醒；`docs/requirements.md` G-6 同步该口径。
- ✅ （v0.2.3 追加）本机实装：技能复制到 `~/.qoder-cn/skills/tavily-search/`、状态文件
  `~/.config/tavily-cli/skill-state.toml` 预置为 `mode = binary`（两者都在用户目录，**仓库工作树不动**）；
  `AGENTS.md` §2 补"本地技能根"这一环境事实、§4 补一条"UI 文案的路径不等于生效路径"的坑、
  `README.md`"给其他 agent 用"一节补安装动作本身（复制目录 + 新会话才列出）。
