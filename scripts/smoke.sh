#!/usr/bin/env bash
# requirements §9 验收用例的端到端冒烟（设计 §11：用例 1–6、8–10 + 21–25 的零配额子集）。
# 会发出真实查询：1 次 search + 1 次 extract + doctor 自带的 1 次最小 search，跑之前请确认配额。
# 用例 3 排在 doctor 之前——doctor 顺带复跑，就是"污染尝试后 Key 池仍健康"的证据。
# 末段「M3 batch」4 条全部止步校验层或 --dry-run，**零出网、零配额**，配额不允许时也能单独验收。
# 用法: scripts/smoke.sh        覆盖: TAVILY_BIN / TAVILY_ENDPOINT / TAVILY_DEAD_ENDPOINT
set -uo pipefail

BIN="${TAVILY_BIN:-tavily-cli}"
ENDPOINT="${TAVILY_ENDPOINT:-http://127.0.0.1:18000/mcp}"
DEAD="${TAVILY_DEAD_ENDPOINT:-http://127.0.0.1:18999/mcp}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fails=0

code() { local want="$1" name="$2"; shift 2; "$@" >"$WORK/out" 2>"$WORK/err"; local got=$?
  if [[ "$got" == "$want" ]]; then echo "ok   [$name] exit=$got"; else
    echo "FAIL [$name] 期望 exit=$want 实得 $got"; sed 's/^/       /' "$WORK/err" | head -3; fails=$((fails + 1)); fi
  return 0; }

# 读 stdin 的命令必须显式喂文件：否则会继承终端 tty，batch 按设计直接拒绝（§9-25 / NFR-2）
codin() { local want="$1" name="$2" file="$3"; shift 3; "$@" <"$file" >"$WORK/out" 2>"$WORK/err"; local got=$?
  if [[ "$got" == "$want" ]]; then echo "ok   [$name] exit=$got"; else
    echo "FAIL [$name] 期望 exit=$want 实得 $got"; sed 's/^/       /' "$WORK/err" | head -3; fails=$((fails + 1)); fi
  return 0; }

say() { grep -q "$2" "$WORK/$1" && echo "     [$3] 命中 $2" || { echo "FAIL [$3] $1 里找不到 $2"; fails=$((fails + 1)); }; }

# 1 真实搜索：3 条结果、退出码 0
code 0 "1 search 三条结果" "$BIN" search "Tavily API pricing" --max-results 3 -f json --endpoint "$ENDPOINT"
jq -e '.["结果"] | length == 3' "$WORK/out" >/dev/null && echo "     [1] jq 取到 3 条网址" || { echo "FAIL [1] 结果不是 3 条"; fails=$((fails + 1)); }

# 2 --dry-run 不出网，且 arguments 里不得有值为 null 的可选键
code 0 "2 dry-run" "$BIN" search x -f json --dry-run
jq -e '.params.arguments | to_entries | map(select(.value == null)) | length == 0' "$WORK/out" >/dev/null \
  && echo "     [2] arguments 无 null 键" || { echo "FAIL [2] arguments 含 null 键"; fails=$((fails + 1)); }

# 3 非法域名止步校验层（永不发出该请求）→ 2
code 2 "3 非法域名" "$BIN" search x --include-domain "!!bad" -f json
say err 域名 "3"

# 4 枚举非法 → 2，并列出允许取值
code 2 "4 非法枚举" "$BIN" search x --depth bogus -f json
say err basic "4"

# 5 混合 URL：失败项不得被吞掉
code 0 "5 extract 部分失败" "$BIN" extract https://example.com https://不存在.invalid -f json
jq -e '(.["页面"] | length == 1) and (.["失败"] | length == 1)' "$WORK/out" >/dev/null \
  && echo "     [5] 页面 1 / 失败 1" || { echo "FAIL [5] 页面或失败计数不对"; fails=$((fails + 1)); }

# 6 端点不可达 → 3，并提示隧道
code 3 "6 端点不可达" "$BIN" search x --endpoint "$DEAD" -f json
say err "tunnel on" "6"

# 8 分层探活 4 项全绿（同时也是用例 3 之后的 Key 池健康复查）
code 0 "8 doctor" "$BIN" doctor -f json --endpoint "$ENDPOINT"
jq -e '.["结果"] | length == 4 and all(.[]; .["状态"] | test("成功|可达"))' "$WORK/out" >/dev/null \
  && echo "     [8] 4 层全通过" || { echo "FAIL [8] doctor 有层未通过"; jq -c '.["结果"]' "$WORK/out"; fails=$((fails + 1)); }

# 9 运行时 tools/list：4 个工具 + 服务端 schema 指纹
code 0 "9 tools" "$BIN" tools -f json --endpoint "$ENDPOINT"
jq -e '(.["结果"] | length == 4) and (."元信息"["schema指纹"] | startswith("sha256:"))' "$WORK/out" >/dev/null \
  && echo "     [9] 4 个工具 + 指纹" || { echo "FAIL [9] 工具数或指纹不对"; fails=$((fails + 1)); }

# 10 帮助文本全中文
code 0 "10 help" "$BIN" search --help
say out 用法 "10"; say out 全局选项 "10"
grep -q "usage:" "$WORK/out" && { echo "FAIL [10] 帮助里残留英文样板"; fails=$((fails + 1)); }

# ---- M3 batch：以下 4 条零出网（止步校验层 / --dry-run），不消耗共享配额 ----

# 22/25 逐行校验隔离：中间一行是红线 1 的历史肇事值，只准坏它自己
cat >"$WORK/mixed.ndjson" <<'EOF'
{"id":"a","tool":"search","arguments":{"query":"Tavily API pricing","max_results":1}}
{"id":"b","tool":"search","arguments":{"query":"x","include_domains":["!!bad"]}}
{"tool":"extract","arguments":{"urls":["https://example.com"]}}
EOF
codin 2 "22 batch 坏行只坏那一行" "$WORK/mixed.ndjson" "$BIN" batch --dry-run
[[ "$(wc -l <"$WORK/out")" -eq 3 ]] && echo "     [22] stdout 恰好 3 行信封" \
  || { echo "FAIL [22] 信封行数不等于 3：$(wc -l <"$WORK/out")"; fails=$((fails + 1)); }
jq -s -e 'length == 3 and (.[0]["请求"].params.name == "tavily-search")
          and (.[1]["错误"]["类别"] == "参数校验失败")
          and (.[2]["请求"].params.name == "tavily-extract")' "$WORK/out" >/dev/null \
  && echo "     [22] 前后两行照常产出请求体" \
  || { echo "FAIL [22] 坏行吞掉了邻居或请求体形状不对"; head -3 "$WORK/out"; fails=$((fails + 1)); }
say err "第 2 行" "22"
say err "不会发出任何网络请求" "22"

# 25 格式白名单：只认逐行信封，不得默默改按 ndjson 吐 table
codin 2 "25 batch -f table" "$WORK/mixed.ndjson" "$BIN" batch -f table
say err 逐行信封 "25"

# 25 空输入（零有效行）⇒ 2，且未发起任何调用
printf '\n\n' >"$WORK/empty.ndjson"
codin 2 "25 batch 空输入" "$WORK/empty.ndjson" "$BIN" batch --dry-run
say err "没有有效输入行" "25"

# 25 超上限 51 行 ⇒ 2，且一批都没发起
seq 51 | sed 's|^.*$|{"tool":"search","arguments":{"query":"x"}}|' >"$WORK/cap51.ndjson"
codin 2 "25 batch 51 行超上限" "$WORK/cap51.ndjson" "$BIN" batch --dry-run
say err "未发起任何调用" "25"

echo
if [[ "$fails" == 0 ]]; then echo "冒烟通过：§9 用例 1–6、8–10 + batch 零配额子集（21–25 中的 22/25）"; exit 0; fi
echo "冒烟失败：$fails 项"; exit 1
