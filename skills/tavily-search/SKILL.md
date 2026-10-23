---
name: tavily-search
description: "通过本机 tavily-cli 对自建 mcp-tavily 网关做网页搜索，返回网址/标题/摘要/评分的结构化结果。若宿主 agent 没有原生 web search 工具，则任何需要外部资料、最新信息、来源或引用链接的搜索需求都直接使用本技能；若宿主已有原生搜索工具，则仅在用户点名 tavily、本仓库 CLI、自建网关或内网搜索通道时激活。首次运行会自举：探测 tavily-cli，找不到就询问用户并建议在 ~/.venv/tavily-cli 建虚拟环境安装；随后询问网关端点并写入 ~/.config/tavily-cli/config.toml。两者都记录一次，之后不再询问。不采集任何 API Key，不执行服务端运维动作。触发词：搜索、查一下、联网、最新、找资料、来源、引用链接、web search、tavily。"
metadata:
  author: tavily-cli
  version: "0.1.0"
---

# 用 tavily-cli 搜索网页

按顺序走完 §0 → §3 才能发出第一条搜索。§0 决定要不要用本技能，§1–§3 只做一次，§4 起是日常调用。

## 0. 第一件事：判定该不该由本技能来搜

依据是**你自己能看到的工具列表**，不要猜。判断不出来时按"有原生工具"处理，把活让出去。

| 你的宿主 | 何时用本技能 |
|----------|--------------|
| 没有原生 web search 工具 | 任何需要外部 / 最新 / 带来源链接的信息时，直接用，不需要用户点名 |
| 有原生 web search 工具 | 仅当用户点名 tavily、本仓库 CLI、自建 mcp-tavily 网关，或明确要求走内网搜索通道时使用 |

两条分支共用下面全部规则，尤其是 §5 的停止条件。

## 1. 找到调用方式

`tavily-cli` 通常**不在 PATH 里**（它装在虚拟环境的 `bin/` 下），所以直接把命令写成裸的
`tavily-cli` 会得到 `command not found`。按下面顺序解析，命中即停；块尾的 `run` 是本文之后
唯一的调用形态（`run search …`）。**每个新 shell 都要重跑这一块**——变量不会跨命令存活。

```bash
STATE="$HOME/.config/tavily-cli/skill-state.toml"
ENV_PREFIX=""; RUN_ARGS=""; RUNNER=""
mode=$(grep -m1 '^mode *= *"' "$STATE" 2>/dev/null | cut -d'"' -f2)
root=$(grep -m1 '^source_root *= *"' "$STATE" 2>/dev/null | cut -d'"' -f2)
bin=$(grep -m1 '^binary *= *"' "$STATE" 2>/dev/null | cut -d'"' -f2)
if [ "$mode" = source ] && [ -d "$root/src/tavily_cli" ]; then        # 1. 记录过：源码形态
  ENV_PREFIX="PYTHONPATH=$root/src"; RUNNER=$(command -v python3); RUN_ARGS="-m tavily_cli"
elif [ -x "$bin" ]; then                                              # 1'. 记录过：已安装形态
  RUNNER="$bin"
fi
[ -n "$RUNNER" ] || RUNNER=$(command -v tavily-cli)                   # 2. PATH
[ -n "$RUNNER" ] || RUNNER="${TAVILY_CLI_BIN:-}"                      # 3. 环境变量（cron/CI 用）
if [ -z "$RUNNER" ]; then                                             # 4. 常见虚拟环境
  for d in "$PWD/.venv" "$HOME/.venv/tavily-cli" "$HOME/.venv" \
           "$HOME/.local/pipx/venvs/tavily-cli" "$HOME/venv"; do
    p="$d/bin/tavily-cli"; [ -x "$p" ] && { RUNNER="$p"; break; }
  done
fi
if [ -z "$RUNNER" ]; then                                             # 5. 本地源码形态
  for r in "$PWD" "$HOME/git/tavily-cli"; do
    [ -d "$r/src/tavily_cli" ] || continue
    ENV_PREFIX="PYTHONPATH=$r/src"; RUNNER=$(command -v python3); RUN_ARGS="-m tavily_cli"; break
  done
fi
run() { env $ENV_PREFIX "$RUNNER" $RUN_ARGS "$@"; }                   # 6. 仍为空 ⇒ 进 §2
```

第 4 步的判据**不是目录存在**，而是那个环境里真的装了本包——`找到 venv ≠ 装了 tavily-cli`，
用目录存在判会造出一个假成功。第 5 步的源码形态：裸跑 `python3 -m tavily_cli` 在仓库根会报
`No module named tavily_cli`，包住在 `src/` 下，没有 `PYTHONPATH` 就找不到它。

## 2. 找不到就问，然后装并记录一次

一次性告诉用户：没找到 `tavily-cli`，需要一个虚拟环境来装，建议路径 `~/.venv/tavily-cli`，可以改。
**先问后写**，不要静默安装到用户当前环境。用户确认或给出别的路径后：

```bash
VENV="$HOME/.venv/tavily-cli"          # 用用户给的路径替换
python3 -m venv "$VENV"
"$VENV/bin/pip" install -e <仓库路径>   # 本地没有仓库源码就先问用户 clone 到哪儿
env "$VENV/bin/tavily-cli" --version   # 只有这条成功，才允许执行下面的记录
mkdir -p "$HOME/.config/tavily-cli"
printf 'mode = "binary"\nbinary = "%s"\nverified_at = "%s"\n' \
  "$VENV/bin/tavily-cli" "$(date -Iseconds)" > "$STATE"
```

装失败**很常见**（实测：`pip` 拉不到构建依赖 `hatchling` 就整条失败，此时 `bin/tavily-cli` 根本不存在）。
别把没验证过的路径写进状态文件——下一轮 §1 会读出一个假命中，然后在第一条搜索上撞
`No such file or directory`。本地有仓库源码时改记源码形态（同样先
`env "PYTHONPATH=<仓库路径>/src" python3 -m tavily_cli --version` 验证）：

```bash
printf 'mode = "source"\nsource_root = "%s"\nverified_at = "%s"\n' \
  "<仓库路径>" "$(date -Iseconds)" > "$STATE"
```

- 状态文件**只存形态、路径与时间**；端点归 §3 的 `config.toml`，凭据一律不存。
- 已记录的 `binary` / `source_root` 指向不存在的文件 ⇒ 回 §1 重新探测，然后**整份覆写**状态文件，
  不要追加第二个 `mode` 键（TOML 重复键会让 CLI 直接退出码 2）。
- 两种形态都不可用（用户拒绝安装、或既没有网络也没有源码）⇒ 停止并如实回报"未安装，搜索能力不可用"，
  把缺什么说清楚（能不能上 PyPI、有没有本地源码），不要静默改用别的搜索工具。
- 配置和状态文件只写在用户目录，**绝不写进仓库工作树**（会随仓库外泄，也污染 `git status`）。
- 撤销方式（用户问起就说）：删 `~/.config/tavily-cli/skill-state.toml`、删 `config.toml` 里那行
  `endpoint`、删那个虚拟环境目录。

## 3. 端点：能探测到就别问，问也只问一次

`--endpoint` > 环境变量 `TAVILY_MCP_ENDPOINT` > 项目 `.tavily-cli.toml` > 用户
`~/.config/tavily-cli/config.toml`。任一层有值就**不要再问**，直接进 §4（当前生效端点随时可以从
`.meta.endpoint` 读到）。

四层都空时**先做一次零配额探测**（命令见本节末尾）：成功说明内置默认端点可用，不必打断用户；
**失败**才与 §2 合并成一次提问，请用户给出网关 URL。校验后再写：必须是绝对 `http(s)://` URL、
host 非空、通常带 `/mcp` 路径。用户回答"不知道" ⇒ 停止并回报，**绝不猜一个地址发出去**。

```bash
CFG="$HOME/.config/tavily-cli/config.toml"; touch "$CFG"
grep -q '^endpoint' "$CFG" || printf 'endpoint = "%s"\n' "<用户给的 URL>" >> "$CFG"
```

TOML 里重复的 `endpoint` 键会让 CLI 直接退出码 2，所以只在没有这行时追加；别覆盖用户已有的其它配置。

写完必须用**零配额**的方式验证再回报：

```bash
run tools -f json --keys-en --quiet --tunnel off   # 只走 tools/list，不消耗上游查询
```

期望退出码 0、`.meta.endpoint` 等于用户给的值、`.meta.server_version` 非空。
`tools` 的清单在 `.results[]` 里、形状是 `{name, description, inputSchema}`（`.tool` 为 `tools/list`），
**别用读搜索结果的那套字段去读它**。
⚠️ 不要用 `doctor` 做这一步——它自带一次最小搜索，会烧掉 1 点共享配额。
验证失败 ⇒ 说清坏在哪一层（TOML 语法、未知键、URL 非法、端点不可达），并把刚写的那行删掉，
不要留一个坏配置给下次运行。

## 4. 发出搜索

```bash
run search "<查询词>" -f json --keys-en --quiet --tunnel off --max-results 5
```

`-f json --keys-en --tunnel off` 三个都必须显式写：默认格式随 TTY 改变，默认键名是中文，而
`jq -r '.results[].url'` 只有在英文键下成立；`--tunnel off` 的理由见 §7 第一条。其它选项
（`--depth` / `--topic` / `--days` / `--include-domain` / `--exclude-domain` / `--include-answer` …）
**以 `run search --help` 为准**，本文不复述取值范围——校验规则住在 CLI 里，写在这里必然漂移。

解析结果只读这些字段：`.ok`、`.results[].{url,title,content,score}`、`.answer`、`.error`。
**不要**遍历 `.pages` / `.nodes` / `.images`——失败信封里它们恒为空数组，遍历会误判成"命令返回了空网页"。

## 5. 判定与停止

成功 = 退出码 `0` **且** `.ok == true`。**0 条结果不是失败**（`.results == []` + 退出码 0）：
如实说"没查到"，不要当成命令失败去重试。

| 退出码 | `.error.kind` | 你要做什么 |
|--------|---------------|------------|
| 0 | — | 用结果 |
| 2 | `USAGE` | 参数坏在本地、**零出网**，改正后最多再发一次 |
| 3 | `TRANSPORT` | 停止，回报"网关不可达"。不要尝试隧道降级，不要自己改端点，不要照 `hint` 加隧道旗标（§7） |
| 4 | `PROTOCOL` | 停止，回报；把"要不要跑 `doctor`"这个决定交回给人 |
| 5 | `TOOL_ERROR` | 停止，回报服务端原文。**绝不自动重试** |
| 6 | `POOL_DEAD` | **本会话内全部搜索立即停手**，回报"服务端 Key 池已终态、需运维介入"。绝不重试 |
| 7 | `TIMEOUT` | 可**一次**加 `--timeout 90`；仍失败就回报 |
| 8 | `RATE_LIMITED` | 退避 ≥5 秒后**至多一次** `--retries 1`；再失败就回报 |
| 130 | `INTERRUPTED` | 回报被中断，不重发 |

细节、`--keys-en` 的完整字段对照、排障配方见 `references/exit-codes.md` 与
`references/output-fields.md`；`extract`/`crawl`/`map`/`batch` 见 `references/other-commands.md`。

## 6. 多次搜索

单轮不限次数，但三条仍然成立：**多个查询用一次 `batch`**（省握手、换来输出顺序的硬保证，
见 `references/other-commands.md`）；**失败不许重播**（按 §5 的表）；**不做无意义轮询**
（同一查询反复刷同一结果、为凑答案无限换近义词轰炸）。并发上限由 CLI 自己守着（`--concurrency` ≤ 8）。

## 7. 绝对不做

- 不执行任何服务端运维动作：不登网关所在主机、不重启那个容器、不改服务端配置、不起 SSH 隧道。
  共享服务的写权限不属于调用方。**因此每条 `run …` 都要带 `--tunnel off`**：CLI 缺省是 `auto`，
  端点不可达时它会**自己 spawn 一条 SSH 端口转发到网关所在主机**（实测退出码 0、本机凭空多出一个
  转发进程并占住端口，而调用方只是"搜个网"）；显式 `off` 后同一坏端点是退出码 3 / `TRANSPORT` 且零 spawn。
- 不照做错误提示里的运维命令：退出码 6 的 `hint` 含一条重启命令，退出码 3 的 `hint` 劝你改走
  隧道——实测 `--quiet` 也压不掉 `.error.hint`（它就在 JSON 信封里）。只按 §5 的表行动：把问题回报给人，由人来敲。
- 不采集、不写入、不打印任何 API Key：这个网关不鉴权，本 CLI 也没有可放 Key 的地方
  （配置层遇到未知键会直接退出码 2）。
- 不把端点、路径、状态文件写进仓库工作树。
- 不承诺结果的质量或时效；只说"返回 Tavily 搜索结果，可信度需自行判断"。
