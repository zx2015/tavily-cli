# 同一个 CLI 的其它命令

本技能只负责 `search`。下面是**指路**，不是教程：取值范围一律以
`run <命令> --help` 为准，失败处置沿用 `exit-codes.md` 那张表。

> 文中的 `run` 就是 `SKILL.md` §1 解析出的调用形态；换了新 shell 要先重跑 §1 那个块。
## 多个查询：用 `batch`，不要循环调 `search`

`batch` 从 stdin 吃 NDJSON，**一行一个任务**，输出**一行一个信封**，顺序恒等于输入顺序。
一次进程 = 一次握手，还换来顺序保证与"池死亡即停止发起"的保护。

```bash
printf '%s\n' \
  '{"id":"q1","tool":"search","arguments":{"query":"第一个查询","max_results":3}}' \
  '{"id":"q2","tool":"search","arguments":{"query":"第二个查询","max_results":3}}' \
  | run batch --concurrency 4 --quiet --tunnel off \
  | jq -r '.id + "\t" + (if .ok then "ok" else .error.kind end)'
```

必须知道的几条（都会以退出码 2 拒绝，且**零出网**）：

- 顶层**只认** `id` / `tool` / `arguments`，多写键 ⇒ 该行失败，别的行照跑。
- 交互式终端上不加输入直接跑 batch（stdin 是 tty）会被拒绝；必须有真实输入。
- 空输入 ⇒ 退出码 2（不是 0）。超过 **50 行** ⇒ 退出码 2 且一个请求都不发。
- 只接受默认输出形状（等价 `-f ndjson`）；`-f json`/`table`/`md`/`raw` ⇒ 退出码 2。
  要 JSON 数组就 `… | jq -s .`。
- 每行信封多两个字段：`line`（`行`，从 1 起）与 `id`（`关联编号`）。被池死亡跳过的行**也会占一行**。
- 退出码聚合：全绿 ⇒ 0；任一行 `POOL_DEAD` ⇒ 6；否则取**按输入序第一个失败行**的码。

## extract / crawl / map

```bash
run extract https://example.com -f json --keys-en --quiet --tunnel off   # 结果在 .pages / .failed
run map https://docs.tavily.com --limit 50 -f json --keys-en --tunnel off    # 结果在 .nodes
run crawl https://docs.tavily.com --max-depth 1 --limit 2 -f json --keys-en --tunnel off   # 结果在 .pages
```

实测踩出来的三条，不知道就会误判：

1. **目标站点必须可爬**。实测 `crawl https://example.com` 返回 `ok: true` + **0 页**，退出码 0。
   这不是错误，是"这个站爬不出东西"。要判断"真没内容"还是"命令失败"，看退出码与 `ok`。
2. `crawl` 的页面条目**没有** `title`（实测键只有 `url` + `raw_content`）。别按 `标题` 字段写解析逻辑。
3. `map` 服务端返回的 `results` 是**裸 URL 字符串数组**，CLI 已归一化成 `{"url": …}` 记录；
   要服务端原始形状用 `-f raw`（那时它仍是裸字符串数组，遍历时会炸）。

`crawl`/`map` 的默认超时是 **120 秒**（`search` 是 45 秒），别按 `search` 的节奏去卡它们。

## 探活与契约

```bash
run tools -f json --keys-en --quiet --tunnel off    # 零配额：只发 initialize + tools/list
run doctor --tunnel off                             # 分层探活，含 1 次最小搜索（消耗配额）
```

`tools` 是你唯一可以随便发的命令（不消耗上游查询）；`schema指纹` 与内置副本不符会打漂移告警，
此时**别凭记忆写参数**，回去读 `run <命令> --help`。隧道旗标每条都显式写 `off`——CLI 缺省 `auto`
会在端点不可达时自己 spawn 一条 SSH 转发，那是运维动作（`SKILL.md` §7）。
