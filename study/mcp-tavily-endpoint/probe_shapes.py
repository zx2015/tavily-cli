import json,urllib.request,time
URL="http://127.0.0.1:18000/mcp"; H={"Content-Type":"application/json","Accept":"application/json, text/event-stream"}
def rq(s,p,to=90):
    q=urllib.request.Request(URL,data=json.dumps(p).encode(),method="POST",headers={**H,**({"mcp-session-id":s} if s else {})})
    resp=urllib.request.urlopen(q,timeout=to); raw=resp.read().decode()
    return resp.headers.get("mcp-session-id"), raw, resp.status
sid,raw,_=rq(None,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"tavily-cli","version":"0.1"}}})
print("negotiated proto:", json.loads(raw.split("data:")[1].strip())["result"]["protocolVersion"])
print("SSE framing sample:", repr(raw[:120]))
rq(sid,{"jsonrpc":"2.0","method":"notifications/initialized"})
def call(name,args,to=90):
    t0=time.time(); s,raw,code=rq(sid,{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":name,"arguments":args}},to)
    el=time.time()-t0
    d=None
    for l in raw.splitlines():
        if l.startswith("data:"): d=json.loads(l[5:].strip())
    if d is None: print(f"[{name}] NO DATA code={code} raw={raw[:150]!r}"); return
    if "error" in d: print(f"[{name}] {el:.1f}s rpc-error {json.dumps(d['error'],ensure_ascii=False)[:180]}"); return
    r=d["result"]; sc=r.get("structuredContent")
    print(f"[{name}] {el:.1f}s isError={r.get('isError')} content_blocks={[c['type'] for c in r['content']]} structured={'Y' if sc else 'N'}")
    if sc: 
        print("   structured keys:", list(sc.keys()))
        for k,v in sc.items():
            if isinstance(v,list) and v and isinstance(v[0],dict): print(f"   {k}[0] keys:", list(v[0].keys()))
            elif isinstance(v,list): print(f"   {k}: list n={len(v)} sample={str(v[:2])[:110]}")
            else: print(f"   {k}: {str(v)[:90]}")
    json.dump(d,open(f"out_{name}.json","w"),ensure_ascii=False,indent=2)
call("tavily-search",{"query":"Tavily API pricing","max_results":2})
call("tavily-extract",{"urls":["https://example.com","https://this-domain-really-does-not-exist-zzz.com"]})
call("tavily-map",{"url":"https://example.com","limit":3})
call("tavily-crawl",{"url":"https://example.com","max_depth":1,"limit":2,"instructions":"只取首页"})
# concurrency: 5 parallel searches sharing one session
import concurrent.futures as cf
def one(i):
    t0=time.time()
    try:
        s,raw,code=rq(sid,{"jsonrpc":"2.0","id":100+i,"method":"tools/call","params":{"name":"tavily-search","arguments":{"query":f"quant computing news {i}","max_results":1}}},90)
        ok=any(l.startswith("data:") and '"isError": false' in l or '"isError":false' in l for l in raw.splitlines())
        return round(time.time()-t0,2), code, ok
    except Exception as e: return round(time.time()-t0,2), "EXC", str(e)[:60]
t0=time.time()
with cf.ThreadPoolExecutor(5) as ex: res=list(ex.map(one,range(5)))
print(f"\n[5 parallel searches] wall={time.time()-t0:.2f}s ->", res)
