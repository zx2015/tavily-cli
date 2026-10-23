import json, urllib.request, time, urllib.error, os
URL="http://127.0.0.1:18000/mcp"
H={"Content-Type":"application/json","Accept":"application/json, text/event-stream"}
def req(sid,payload,timeout=70):
    r=urllib.request.Request(URL,data=json.dumps(payload).encode(),method="POST",
        headers={**H,**({"mcp-session-id":str(sid)} if sid else {})})
    t0=time.time()
    try: resp=urllib.request.urlopen(r,timeout=timeout); raw=resp.read().decode(); code=resp.status
    except urllib.error.HTTPError as e: return {"_code":e.code,"_body":e.read().decode()[:300]},"x"
    sid2=resp.headers.get("mcp-session-id")
    for line in raw.splitlines():
        if line.startswith("data:"): return json.loads(line[5:].strip()), sid2
    return {"_raw":raw[:300]}, sid2
out=req(None,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"p","version":"1"}}})
sid=out[1]
req(sid,{"jsonrpc":"2.0","method":"notifications/initialized"})
def timed(label,args):
    t0=time.time(); res,_=req(sid,{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"tavily-search","arguments":args}})
    el=time.time()-t0
    if "error" in res: print(f"[{label}] {el:.2f}s JSON-RPC error: {json.dumps(res['error'],ensure_ascii=False)[:200]}"); return
    r=res["result"]; sc=r.get("structuredContent") or {}
    print(f"[{label}] {el:.2f}s isError={r.get('isError')} nresults={len(sc.get('results',[]))} answer={'Y' if sc.get('answer') else 'N'}")
    if r.get("isError"): print("   errtext:", r["content"][0]["text"][:200])
timed("basic-3res",{"query":"openclaw 2.0 release","max_results":3})
timed("advanced-news",{"query":"杭州 新闻","search_depth":"advanced","topic":"news","days":3,"max_results":3})
timed("empty-result",{"query":"zzzqqqxxnonexistent12345","max_results":2})
# ⚠️ 下面两个用例会让服务端把 4 个 Key 全部标记为 ERROR 终态、整台机器的搜索能力瘫痪且
#    不会自愈（唯一恢复手段 docker restart mcp-tavily）。默认跳过。
#    只有在【可牺牲的测试实例】上、且已获使用者明确批准时，才用
#    TAVILY_ALLOW_DESTRUCTIVE=1 python3 probe_error_paths.py 执行。
if os.environ.get("TAVILY_ALLOW_DESTRUCTIVE") == "1":
    timed("timeout-arg-0.001",{"query":"test","timeout":0.001})
    timed("bad-domain-filter",{"query":"test","include_domains":["!!bad"]})
else:
    print("[SKIPPED] 破坏性用例（非法域名 / 过小 timeout）需 TAVILY_ALLOW_DESTRUCTIVE=1")
for label,args in [("missing-query",{}),("extra-key",{"query":"x","bogus":1}),("wrong-type",{"query":123})]:
    res,_=req(sid,{"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"tavily-search","arguments":args}})
    if "error" in res: print(f"[{label}] JSON-RPC error: {json.dumps(res['error'],ensure_ascii=False)[:220]}")
    else: print(f"[{label}] isError={res['result'].get('isError')} text={res['result']['content'][0]['text'][:180]}")
res,_=req(sid,{"jsonrpc":"2.0","id":12,"method":"tools/call","params":{"name":"nope","arguments":{}}})
print("[unknown-tool]", json.dumps(res.get("error") or res.get("result",{}).get("content"),ensure_ascii=False)[:200])
res,_=req(None,{"jsonrpc":"2.0","id":13,"method":"tools/list","params":{}})
print("[tools/list without session]", json.dumps(res)[:200])
for m in ["prompts/list","resources/list"]:
    res,_=req(sid,{"jsonrpc":"2.0","id":14,"method":m,"params":{}})
    print(f"[{m}]", json.dumps(res.get("error",res.get("result")),ensure_ascii=False)[:160])
# extract + map cheap calls
res,_=req(sid,{"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"tavily-extract","arguments":{"urls":["https://example.com"],"include_images":False}}})
r=res.get("result",{}); sc=r.get("structuredContent") or {}
print("[extract] isError=",r.get("isError"),"keys=",list(sc.keys()),"results=",len(sc.get("results",[])), "failed=",len(sc.get("failed_results",[])))
res,_=req(sid,{"jsonrpc":"2.0","id":16,"method":"tools/call","params":{"name":"tavily-map","arguments":{"url":"https://example.com","limit":5}}})
r=res.get("result",{}); print("[map] isError=",r.get("isError"),"text=",json.dumps(r.get("structuredContent") or r.get("content"),ensure_ascii=False)[:200])
