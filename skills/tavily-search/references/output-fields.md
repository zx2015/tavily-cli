# `--keys-en` 字段对照与取值配方

内部数据模型是英文的，中文键只发生在渲染边界（决策 D-2）。**给 agent 用就固定 `--keys-en`**：
默认中文键在 `jq` 里必须写成 `.["结果"][]."网址"`，裸 `.结果` 是语法错误，这是高频踩坑点。

> 文中的 `run` 就是 `SKILL.md` §1 解析出的调用形态；换了新 shell 要先重跑 §1 那个块。
## 信封（所有命令共用）

| `--keys-en` | 默认中文 | 类型 | 说明 |
|-------------|----------|------|------|
| `ok` | `成功` | bool | 与退出码 `0` 一起构成成功判据 |
| `tool` | `工具` | str | 服务端工具名，如 `tavily-search` |
| `query` | `查询` | str | 回显你发出去的查询词 |
| `results` | `结果` | array | `search` 的结果列表；失败时是**空数组**不是 `null` |
| `answer` | `简答` | str\|null | 仅 `--include-answer` 时有值 |
| `pages` | `页面` | array | `extract` / `crawl` 用 |
| `failed` | `失败` | array | `extract` 里失败的 URL 及原因 |
| `nodes` | `节点` | array | `map` 用（服务端原始是裸 URL 字符串，CLI 已归一化成 `{"url": …}`） |
| `images` | `图片` | array | 仅 `--include-images` |
| `meta` | `元信息` | object | 见下表 |
| `error` | `错误` | object\|null | 见 `exit-codes.md` |

## `results[]` 条目

| 英 | 中 | 用法建议 |
|----|----|----------|
| `url` | `网址` | 引用来源就用它 |
| `title` | `标题` | 可能为空字符串 |
| `content` | `摘要` | 主要可读文本 |
| `score` | `评分` | 0–1 相关性，**低分不等于无关**，要自己判断 |
| `id` | `编号` | 服务端给条目分配的 id |
| `raw_content` | `原文` | 仅 `--include-raw-content`，可能很大 |

## `meta`

| 英 | 中 | 出现时机 |
|----|----|----------|
| `request_id` | `请求编号` | 走到上游才有 |
| `response_time` | `服务端耗时` | 同上 |
| `elapsed_ms` | `本地耗时毫秒` | 有网络往返时 |
| `endpoint` | `端点` | **恒有**，含失败与退出码 2 的场合——所以它也是"当前生效端点"的读数来源 |
| `cli_version` | `CLI版本` | 恒有 |
| `server_version` | `服务端版本` | 握手成功过就有。注意它是 **FastMCP 库版本**，不是服务端应用版本 |
| `schema_hash` | `schema指纹` | 恒有；与线上一致说明参数面没漂移 |

⚠️ 实测：**本地校验拦下（退出码 2）时 `meta` 只有 `endpoint` / `cli_version` / `schema_hash` 三项**，
没有 `request_id`——因为请求根本没发出去。别把"缺 `request_id`"当成新的一种错误类别。

## 取值配方

```bash
run search "查询词" -f json --keys-en --quiet --tunnel off | jq -r '.results[] | "\(.score)\t\(.url)\t\(.title)"'
run search "查询词" -f json --keys-en --quiet --tunnel off | jq -r '.answer // empty'
run search "查询词" -f json --keys-en --quiet --tunnel off | jq '.meta | {endpoint, server_version, schema_hash}'
```

其它格式：

- `-f ndjson`：每个结果对象一行，适合 `while read` / `jq -c`；`--with-meta` 时首行是多一个
  `{"meta":{…}}` 对象（**只有 ndjson 认 `--with-meta`**）。
- `-f raw`：服务端 `structuredContent` 原样透传，英文键、无信封、**不经归一化**（`map` 的
  `results` 在 raw 下仍是裸字符串数组）。需要原始形状时才用，别拿它当默认。
- `-f table` / `-f md`：给人读的，agent 不要解析它们（TTY 下还会着色）。
- `-o <path>` 写出的文件与机读格式一样，**永不含 ANSI 转义序列**。
