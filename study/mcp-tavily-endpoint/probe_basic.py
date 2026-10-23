import json, urllib.request, sys
from pathlib import Path
FIX = Path(__file__).resolve().parent / "fixtures"; FIX.mkdir(exist_ok=True)
URL="http://127.0.0.1:18000/mcp"
def rpc(sid, payload, want_response=True):
    body=json.dumps(payload).encode()
    req=urllib.request.Request(URL, data=body, method="POST",
        headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream",
                 **({"mcp-session-id":sid} if sid else {})})
    r=urllib.request.urlopen(req, timeout=60)
    sid_out=r.headers.get("mcp-session-id"); raw=r.read().decode()
    if not want_response: return sid_out, None
    for line in raw.splitlines():
        if line.startswith("data:"):
            return sid_out, json.loads(line[5:].strip())
    return sid_out, {"_raw": raw}
sid, res = rpc(None, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"tavily-cli-probe","version":"0.0.1"}}})
rpc(sid, {"jsonrpc":"2.0","method":"notifications/initialized"}, want_response=False)
_, tl = rpc(sid, {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
tools=tl["result"]["tools"]
json.dump(tl, open(FIX/"tools_list.json","w"), ensure_ascii=False, indent=2)
print("server:", res["result"]["serverInfo"], "| proto:", res["result"]["protocolVersion"])
print("tools:")
for t in tools:
    props=list(t["inputSchema"]["properties"].keys()); req=t["inputSchema"].get("required",[])
    print(f"  - {t['name']} (title={t.get('title')}): required={req} n_params={len(props)}")
    print(f"      params: {', '.join(props)}")
_, call = rpc(sid, {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"tavily-search","arguments":{"query":"示例股份 2026 半年报 营收","max_results":2,"include_answer":True}}})
json.dump(call, open(FIX/"search_latest.json","w"), ensure_ascii=False, indent=2)
r=call.get("result", call)
print("\n=== tools/call tavily-search ===")
print("isError:", r.get("isError"), "| content blocks:", [c["type"] for c in r.get("content",[])], "| has structuredContent:", "structuredContent" in r)
txt=r["content"][0]["text"]
print("text length:", len(txt))
print("text head:", txt[:600].replace("\n"," ")[:600])
