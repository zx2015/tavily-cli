"""argparse 装配 + 命令分发（design §3 最外层，不含业务逻辑）。

顺序固定：解析 → 配置合并 → 校验闸门 →（可选 dry-run）→ 传输 → 分类 → 渲染 → 退出码。
校验闸门在 transport 之前，所以非法入参**永不产生任何网络写入**（ADR-0003、§9 用例 3）。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__, render, schema, validate
from .classify import Classified, ErrorKind, classify, retry_budget
from .commands import batch as batch_command
from .commands import crawl as crawl_command
from .commands import doctor as doctor_command
from .commands import extract as extract_command
from .commands import loose_number, option_for
from .commands import map as map_command
from .commands import search as search_command
from .commands import tools as tools_command
from .config import Config, ConfigError
from .constants import EXIT_INTERRUPTED, EXIT_OK, EXIT_USAGE, LONG_TIMEOUT, MAX_BATCH_ITEMS
from .transport import McHttp, build_tool_request
from .tunnel import LOCAL_HOSTS, TunnelError, ensure_tunnel

USAGE_HINTS = {
    "unrecognized arguments": "存在未识别的选项",
    "the following arguments are required": "缺少必填参数",
    "expected one argument": "选项缺少取值",
}


class ZhHelpFormatter(argparse.HelpFormatter):
    """argparse 的 format_help 直接用 formatter 生成用法行，所以前缀必须在这一层换。"""

    def _format_usage(self, usage, actions, groups, prefix):
        # add_subparsers() 用空前缀预计算子命令 prog；连它一起换会产出"用法：用法：tavily-cli search"
        if prefix is None or prefix.lower().startswith("usage"):
            prefix = "用法："
        return super()._format_usage(usage, actions, groups, prefix)


class ZhArgumentParser(argparse.ArgumentParser):
    """把 argparse 的英文样板换成中文（§9 用例 10、AGENTS §5）。"""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("formatter_class", ZhHelpFormatter)
        wants_help = kwargs.get("add_help", True)
        kwargs["add_help"] = False
        super().__init__(**kwargs)
        self._optionals.title = "选项"
        self._positionals.title = "位置参数"
        if wants_help:
            self.add_argument("-h", "--help", action="help", help="显示帮助信息并退出")

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"tavily-cli：{_zh(message)}\n")


def _zh(message: str) -> str:
    for english, chinese in USAGE_HINTS.items():
        if english in message:
            return message.replace(english, chinese)
    return message


# ------------------------------------------------------------------ 参数面


def _add_global_options(parser: ZhArgumentParser) -> None:
    # 具名分组：argparse 按 title 复制父解析器的组，子命令里就会得到一个独立、名称正确的"全局选项"段。
    parser = parser.add_argument_group("全局选项", "所有子命令通用；可写在子命令前或后")
    # default=SUPPRESS：见 build_parser 注释——防止子命令把"子命令之前"的全局取值覆盖回默认。
    parser.add_argument("-f", "--format", dest="fmt", default=argparse.SUPPRESS, help="输出格式：auto / json / ndjson / table / md / raw（默认 TTY 用 table，管道用 json）")
    parser.add_argument("-o", "--output", default=argparse.SUPPRESS, help="把输出写入文件而不是 stdout")
    parser.add_argument("--endpoint", default=argparse.SUPPRESS, help="覆盖 MCP 端点，默认 http://127.0.0.1:18000/mcp")
    parser.add_argument("--timeout", type=loose_number, default=argparse.SUPPRESS, help="客户端总超时秒数，默认 45（crawl/map 默认 120）")
    parser.add_argument("--retries", type=loose_number, default=argparse.SUPPRESS, help="仅对传输层失败重试的次数，默认 1；校验/池死亡/超时永不重试")
    parser.add_argument("--concurrency", type=loose_number, default=argparse.SUPPRESS, help="批量与多 URL 并发上限，默认 4、最大 8（batch 属 M3）")
    parser.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS, help="压掉警告与提示；错误说明仍写 stderr（§6 要求）")
    parser.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS, help="在 stderr 打印 JSON-RPC 方法名、脱敏 session id、耗时与 HTTP 码")
    parser.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS, help="禁用 ANSI 着色（仅影响 TTY 下的 table/md；机读格式与 -o 产物本就不带转义）")
    parser.add_argument("--keys-en", action="store_true", default=argparse.SUPPRESS, help="机读输出的键名切回英文（默认中文）")
    parser.add_argument("--with-meta", action="store_true", default=argparse.SUPPRESS, help="ndjson 首行输出信封元数据")
    parser.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="只校验并打印将要发出的 JSON-RPC 请求体，不发网络包")
    parser.add_argument("--tunnel", choices=("auto", "off", "on"), default=argparse.SUPPRESS, help="SSH 隧道降级：auto=直连失败后自动改道，on=跳过直连，off=永不碰 ssh")


def build_parser() -> ZhArgumentParser:
    globals_ = ZhArgumentParser(add_help=False)
    _add_global_options(globals_)

    parser = ZhArgumentParser(
        prog="tavily-cli",
        parents=[globals_],
        description="通过 MCP Streamable HTTP 调用自建的 mcp-tavily 聚合网关（搜索/提取/爬取/站点地图）。",
        epilog="示例：tavily-cli search \"示例股份 2026 半年报\" --max-results 3 -f json",
    )
    parser.add_argument("--version", action="version", version=f"tavily-cli {__version__}", help="显示版本号并退出")
    sub = parser.add_subparsers(dest="command", metavar="<命令>", title="子命令", parser_class=ZhArgumentParser)

    search = sub.add_parser("search", parents=[globals_], help="网页搜索（tavily-search）", description="网页搜索：输出结果列表、可选简答与图片。")
    search_command.add_arguments(search)
    extract = sub.add_parser("extract", parents=[globals_], help="正文提取（tavily-extract）", description="正文提取：支持多个 URL，失败项落在\"失败\"字段而不是被吞掉。")
    extract_command.add_arguments(extract)
    crawl = sub.add_parser("crawl", parents=[globals_], help="站点递归爬取（tavily-crawl）", description="站点爬取：从起点 URL 逐层跟随链接，输出每页正文。耗时与配额开销最大，默认总超时放宽到 120s。")
    crawl_command.add_arguments(crawl)
    map_ = sub.add_parser("map", parents=[globals_], help="站点链接结构地图（tavily-map）", description="站点结构：只枚举 URL 与标题，不抓正文，比 crawl 便宜得多。")
    map_command.add_arguments(map_)
    batch = sub.add_parser(
        "batch",
        parents=[globals_],
        help="从 stdin 读 NDJSON 批量执行，逐行流式输出信封",
        description="批量：每行一个 {id?, tool, arguments} JSON。坏行只失败自己那一行，"
        "输出行数恒等于输入有效行数、顺序与输入一致；上限 50 行，只输出 -f ndjson 形状。",
    )
    tools = sub.add_parser("tools", parents=[globals_], help="打印服务端权威 schema 与指纹（tools/list）", description="读取运行时 tools/list，并与内置副本做指纹比对以发现契约漂移。")
    doctor = sub.add_parser("doctor", parents=[globals_], help="分层探活：TCP → 握手 → tools/list → 最小搜索", description="定位故障层次：网络不可达（3）、协议异常（4）、还是服务端 Key 池死亡（6）。")
    tools.set_defaults(handler=_handle_tools)
    doctor.set_defaults(handler=_handle_doctor)
    batch.set_defaults(handler=_handle_batch)
    search.set_defaults(handler=_handle_tool_command, module=search_command)
    extract.set_defaults(handler=_handle_tool_command, module=extract_command)
    # §4.5：crawl/map 实测显著更久，未显式给 --timeout 时用 120s。
    # 用另一个 dest 而不是 --timeout 的 default，才不会被"子命令之前的 --timeout"覆盖（§4 陷阱表）。
    crawl.set_defaults(handler=_handle_tool_command, module=crawl_command, default_timeout=LONG_TIMEOUT)
    map_.set_defaults(handler=_handle_tool_command, module=map_command, default_timeout=LONG_TIMEOUT)
    return parser


# ------------------------------------------------------------------ 分发


def main(
    argv: list[str] | None = None, *, opener=None, isatty=None, tcp_probe=None, stdin=None
) -> int:
    parser = build_parser()
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if ns.command is None:
        parser.error("缺少子命令，可用：search / extract / crawl / map / batch / tools / doctor")
    try:
        cfg = Config.from_args(ns)
    except ConfigError as exc:
        print(f"tavily-cli：{exc}", file=sys.stderr)
        return EXIT_USAGE

    tty = sys.stdout.isatty() if isatty is None else bool(isatty)
    # 只有 batch 会读它；其余命令拿到对象也不碰，保证 NFR-2"任何路径都不等待 stdin"。
    stream = sys.stdin if stdin is None else stdin
    try:
        return ns.handler(ns, cfg, tty, opener, tcp_probe, stream)
    except KeyboardInterrupt:
        print("tavily-cli：已中断（Ctrl-C），未写出完整输出。", file=sys.stderr)
        return EXIT_INTERRUPTED


def _handle_tool_command(ns, cfg: Config, tty: bool, opener, _probe, _stdin) -> int:
    module = ns.module
    tool = module.TOOL
    arguments = module.to_arguments(ns)
    report = validate.validate(tool, arguments)
    for warning in report.warnings:
        _notice(cfg, f"警告：{option_for(warning.param)}：{warning.message}")
    if not report.ok:
        return _fail(cfg, _usage_classified(report), tool=tool, query=arguments.get("query"), tty=tty)

    arguments = report.sanitize(arguments)
    if cfg.dry_run:
        _print(json.dumps(build_tool_request(tool, arguments, 1), ensure_ascii=False, indent=2))
        return EXIT_OK

    client, cfg, result, failure = _call_with_fallback(
        cfg, opener, lambda client: _invoke(client, tool, arguments, cfg)
    )
    if failure is not None:
        return _emit(_failure_envelope(cfg, client, tool, failure, arguments.get("query")), cfg, tty)
    env = render.build_envelope(
        tool,
        result.structured,
        meta=_meta(cfg, client, result.elapsed_ms),
        query=arguments.get("query"),
    )
    return _emit(env, cfg, tty)


def _handle_tools(ns, cfg: Config, tty: bool, opener, _probe, _stdin) -> int:
    if cfg.dry_run:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        _print(json.dumps(body, ensure_ascii=False, indent=2))
        return EXIT_OK
    client, cfg, tools, failure = _call_with_fallback(cfg, opener, lambda client: _list_tools(client, cfg))
    if failure is not None:
        return _emit(_failure_envelope(cfg, client, "tools/list", failure, None), cfg, tty)
    warning = tools_command.drift_warning(tools)
    if warning:
        _notice(cfg, warning)
    return _emit(tools_command.to_envelope(tools, _meta(cfg, client)), cfg, tty)


def _handle_doctor(ns, cfg: Config, tty: bool, opener, probe, _stdin) -> int:
    if cfg.dry_run:
        print("tavily-cli：doctor 的每一层都是真实探活，--dry-run 不适用。", file=sys.stderr)
        return EXIT_USAGE
    cfg = _apply_tunnel_on(cfg)
    client = _make_client(cfg, opener)
    env = doctor_command.run(client, endpoint=cfg.endpoint, tcp_probe=probe or _tcp_probe, timeout=cfg.timeout)
    return _emit(env, cfg, tty)


# ------------------------------------------------------------------ batch（§4.6 / §5.4）


def _handle_batch(ns, cfg: Config, _tty: bool, opener, _probe, stdin) -> int:
    if cfg.fmt not in ("auto", "ndjson"):
        print(
            "tavily-cli：batch 的唯一输出形状是逐行信封（等价 -f ndjson），"
            f"-f {cfg.fmt} 无法逐行消费。要 JSON 数组请 `tavily-cli batch < requests.ndjson | jq -s .`，"
            "要 table/md/raw 请改用对应的单命令。",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if stdin.isatty():
        print(
            "tavily-cli：batch 从 stdin 读 NDJSON，交互式终端上会一直等输入。"
            "请改用管道或文件重定向：`cat requests.ndjson | tavily-cli batch` "
            "或 `tavily-cli batch < requests.ndjson`。",
            file=sys.stderr,
        )
        return EXIT_USAGE

    items = batch_command.read_lines(stdin)
    if len(items) > MAX_BATCH_ITEMS:
        print(
            f"tavily-cli：批量上限 {MAX_BATCH_ITEMS} 行，收到 {len(items)} 行，请分批执行；本次未发起任何调用。",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if not items:
        print(
            "tavily-cli：stdin 里没有有效输入行（空行不算），未发起任何调用。"
            "输入面要求每行一个 JSON 对象：`{\"tool\":\"search\",\"arguments\":{\"query\":\"…\"}}`。",
            file=sys.stderr,
        )
        return EXIT_USAGE

    plans = [(item, _plan_batch_line(cfg, item)) for item in items]
    with _batch_output(cfg) as write:
        if cfg.with_meta:
            write(json.dumps(render.meta_doc(_meta(cfg), cfg.keys_lang), ensure_ascii=False))
        if cfg.dry_run or all(failure is not None for _, failure in plans):
            # 整批都停在校验时连零配额的 tools/list 预检也不发（红线 1 的"零 socket 写入"对 batch 同样成立）。
            return _write_batch_without_network(cfg, plans, write)

        client, cfg, tools, precheck = _call_with_fallback(cfg, opener, lambda client: _list_tools(client, cfg))
        _batch_precheck_notice(cfg, precheck, tools)
        return _run_batch(cfg, client, plans, write)


def _plan_batch_line(cfg: Config, item) -> Classified | None:
    """逐行校验隔离（§4.6）：坏行只标记自己，其余行照常走同一条流水线。"""

    if item.error:
        return classify(kind=ErrorKind.USAGE, message=item.error)
    report = validate.validate(item.tool, item.arguments)
    for warning in report.warnings:
        _notice(cfg, f"警告：第 {item.index} 行 {option_for(warning.param)}：{warning.message}")
    if not report.ok:
        detail = "；".join(f"{option_for(error.param)}：{error.message}" for error in report.errors)
        return classify(kind=ErrorKind.USAGE, message=detail)
    item.arguments = report.sanitize(item.arguments)
    return None


def _write_batch_without_network(cfg: Config, plans, write) -> int:
    """两条零出网路径共用：--dry-run 写出将要发出的请求体，整批停在校验时只剩逐行错误信封。"""

    failures = []
    for item, failure in plans:
        if failure is not None:
            failures.append(failure)
            _write_batch_line(cfg, write, item, _batch_failure_envelope(cfg, None, item, failure))
            continue
        body = build_tool_request(item.tool, item.arguments, item.index)
        write(json.dumps(render.batch_request_doc(item.index, item.id, body, cfg.keys_lang), ensure_ascii=False))
    return _finish_batch(plans, failures)


def _batch_precheck_notice(cfg: Config, failure: Classified | None, tools) -> None:
    """§6 规则 6：漂移与预检失败都只警告不阻断——逐行调用会如实报出自己的失败层次。"""

    if failure is not None:
        _notice(cfg, f"schema 漂移预检未完成（{failure.kind.label}：{failure.message}），批量继续执行。")
        return
    warning = tools_command.drift_warning(tools)
    if warning:
        _notice(cfg, warning)


def _run_batch(cfg: Config, client: McHttp, plans, write) -> int:
    """并发执行、按输入序写出：顺序是硬保证，及时性尽力而为（§5.4），整批复用一个 session（NFR-11）。"""

    stopped = threading.Event()

    def run_one(item):
        if stopped.is_set():
            return None, classify(kind=ErrorKind.POOL_DEAD, message="批量已在首个池死亡处停止，本行未发起调用")
        result, failure = _invoke(client, item.tool, item.arguments, cfg)
        if failure is not None and failure.kind is ErrorKind.POOL_DEAD:
            stopped.set()
        return result, failure

    failures: list[Classified] = []
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        futures = {item.index: pool.submit(run_one, item) for item, failure in plans if failure is None}
        for item, failure in plans:
            # 队首没就绪就先等，后面的结果攒着——消费方要能按行号对齐，不能靠完成顺序猜归属。
            result = None
            if failure is None:
                result, failure = futures[item.index].result()
            if failure is not None:
                failures.append(failure)
                env = _batch_failure_envelope(cfg, client, item, failure)
            else:
                env = render.build_envelope(
                    item.tool,
                    result.structured,
                    meta=_meta(cfg, client, result.elapsed_ms),
                    query=item.arguments.get("query"),
                )
            _write_batch_line(cfg, write, item, env)
    return _finish_batch(plans, failures)


def _batch_failure_envelope(cfg: Config, client: McHttp | None, item, failure: Classified) -> render.Envelope:
    return _failure_envelope(cfg, client, item.tool, failure, item.arguments.get("query"))


def _write_batch_line(cfg: Config, write, item, env: render.Envelope) -> None:
    doc = render.batch_line_doc(item.index, item.id, env, cfg.keys_lang)
    write(json.dumps(doc, ensure_ascii=False))
    if env.ok:
        return
    error = env.error or {}
    print(f"tavily-cli：第 {item.index} 行 {_kind_label(error)}：{error.get('message', '')}", file=sys.stderr)
    if error.get("hint"):
        print(f"建议：{error['hint']}", file=sys.stderr)


def _finish_batch(plans, failures: list[Classified]) -> int:
    """§6 规则 4：全绿 0；任一行池死亡 6；否则按输入序取第一个失败行的退出码。"""

    if not failures:
        return EXIT_OK
    code = (
        ErrorKind.POOL_DEAD.exit_code
        if any(f.kind is ErrorKind.POOL_DEAD for f in failures)
        else failures[0].exit_code
    )
    print(f"tavily-cli：批量 {len(plans)} 行，{len(failures)} 行失败（退出码 {code}）。", file=sys.stderr)
    return code


@contextlib.contextmanager
def _batch_output(cfg: Config):
    """流式写出：一行就绪就 flush，消费方不必等整批（§5.4）。"""

    if not cfg.output:
        yield lambda text: print(text, flush=True)
        return
    handle = Path(cfg.output).open("w", encoding="utf-8")
    try:

        def write(text: str) -> None:
            handle.write(f"{text}\n")
            handle.flush()

        yield write
    finally:
        handle.close()


# ------------------------------------------------------------------ 调用与重试


def _invoke(client: McHttp, tool: str, arguments: dict, cfg: Config):
    """ADR-0002 重试矩阵：只有分类器判定可重试的 Kind 才会再发一次。"""

    attempt = 0
    while True:
        attempt += 1
        failure: Classified | None = None
        try:
            result = client.call(tool, arguments)
        except Exception as exc:  # noqa: BLE001 - KeyboardInterrupt 等 BaseException 不在此列
            failure = classify(exc=exc)
        else:
            if result.is_error:
                failure = classify(result.text)
        if failure is None:
            return result, None
        if attempt < retry_budget(failure.kind, retries=cfg.retries, retries_given=cfg.retries_given):
            time.sleep(_backoff(attempt, failure.kind))
            continue
        return None, failure


def _backoff(attempt: int, kind: ErrorKind) -> float:
    if kind is ErrorKind.RATE_LIMITED:
        return 5.0
    return min(0.5 * 2 ** (attempt - 1), 4.0)


def _make_client(cfg: Config, opener) -> McHttp:
    return McHttp(
        cfg.endpoint,
        timeout=cfg.request_timeout if cfg.request_timeout is not None else cfg.timeout,
        opener=opener or _opener_for(cfg.endpoint),
        client_version=__version__,
        verbose=cfg.verbose,
    )


def _opener_for(endpoint: str):
    """隧道端点写的是 127.0.0.1，但 urllib 会照抄 http_proxy 把它交给代理机（§4 陷阱表）。
    本地转发口必须直连，否则"降级走隧道"会绕回那台已经连不上的主机。"""

    host = urlsplit(endpoint).hostname or ""
    if host not in LOCAL_HOSTS:
        return urllib.request.urlopen
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open


def _apply_tunnel_on(cfg: Config) -> Config:
    """`--tunnel on`：跳过直连。放在校验与 dry-run 闸门之后，保证非法入参仍零出网。"""

    if cfg.tunnel != "on":
        return cfg
    return _tunnel_config(cfg, forced=True) or cfg


def _call_with_fallback(cfg: Config, opener, call):
    """返回 (client, cfg, result, failure)：on 先改道，直连报 TRANSPORT 后 auto 再改道重试一次。"""

    cfg = _apply_tunnel_on(cfg)
    client = _make_client(cfg, opener)
    result, failure = call(client)
    if failure is not None and cfg.tunnel == "auto" and failure.kind is ErrorKind.TRANSPORT:
        switched = _tunnel_config(cfg)
        if switched is not None:
            cfg = switched
            client = _make_client(cfg, opener)
            result, failure = call(client)
    return client, cfg, result, failure


def _list_tools(client: McHttp, cfg: Config):
    """tools/list 的失败同样要先过分类器，否则一次 502 就变成裸 traceback + 退出码 1。"""

    attempt = 0
    while True:
        attempt += 1
        try:
            return client.list_tools(), None
        except Exception as exc:  # noqa: BLE001 - KeyboardInterrupt 等 BaseException 不在此列
            failure = classify(exc=exc)
        if attempt >= retry_budget(failure.kind, retries=cfg.retries, retries_given=cfg.retries_given):
            return None, failure
        time.sleep(_backoff(attempt, failure.kind))


def _tunnel_config(cfg: Config, *, forced: bool = False) -> Config | None:
    """建立/复用 SSH 隧道并改写端点；失败时返回 None，由调用方保留原路径并报中文原因。"""

    try:
        endpoint = ensure_tunnel(cfg.endpoint, cfg.ssh_host)
    except TunnelError as exc:
        _notice(cfg, f"隧道降级失败：{exc}")
        return None
    if endpoint == cfg.endpoint:
        return None
    _notice(
        cfg,
        f"{'已按 --tunnel on 走' if forced else '已降级走'} SSH 隧道 → {endpoint}（收回：scripts/tunnel.sh down）",
    )
    return replace(cfg, endpoint=endpoint)


def _tcp_probe(host: str, port: int, timeout: float) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        return None


# ------------------------------------------------------------------ 信封与输出


def _meta(cfg: Config, client: McHttp | None = None, elapsed_ms: int | None = None) -> dict:
    values = {
        "endpoint": cfg.endpoint,
        "cli_version": __version__,
        "server_version": client.server_version if client is not None else None,
        "elapsed_ms": elapsed_ms,
        "schema_hash": schema.schema_hash(),
    }
    return {key: value for key, value in values.items() if value is not None}


def _usage_classified(report: validate.ValidationReport) -> Classified:
    detail = "；".join(f"{option_for(error.param)}：{error.message}" for error in report.errors)
    return classify(kind=ErrorKind.USAGE, message=detail)


def _failure_envelope(cfg: Config, client: McHttp | None, tool: str, failure: Classified, query) -> render.Envelope:
    return render.build_envelope(
        tool,
        None,
        meta=_meta(cfg, client),
        ok=False,
        error={"kind": failure.kind.name, "message": failure.message, "hint": failure.hint},
        query=query,
    )


def _fail(cfg: Config, failure: Classified, *, tool: str, query=None, tty: bool = False) -> int:
    return _emit(_failure_envelope(cfg, None, tool, failure, query), cfg, tty)


def _emit(env: render.Envelope, cfg: Config, tty: bool) -> int:
    text = render.render(
        env, cfg.fmt, tty, lang=cfg.keys_lang, with_meta=cfg.with_meta, width=cfg.width,
        color=cfg.color and tty and not cfg.output,
    )
    if cfg.output:
        Path(cfg.output).write_text(f"{text}\n" if text else "", encoding="utf-8")
    elif text:
        _print(text)

    if not env.ok:
        error = env.error or {}
        code = _exit_code(error)
        print(f"tavily-cli：{_kind_label(error)}（退出码 {code}）：{error.get('message', '')}", file=sys.stderr)
        if error.get("hint"):
            print(f"建议：{error['hint']}", file=sys.stderr)
        return code
    if render.is_empty(env):
        _notice(cfg, "查询无结果（这不是错误，退出码 0）。")
    return EXIT_OK


def _exit_code(error: dict) -> int:
    kind = error.get("kind", "")
    return ErrorKind[kind].exit_code if kind in ErrorKind.__members__ else ErrorKind.TOOL_ERROR.exit_code


def _kind_label(error: dict) -> str:
    kind = error.get("kind", "")
    return ErrorKind[kind].label if kind in ErrorKind.__members__ else str(kind)


def _print(text: str) -> None:
    print(text)


def _notice(cfg: Config, message: str) -> None:
    if not cfg.quiet:
        print(f"tavily-cli：{message}", file=sys.stderr)
