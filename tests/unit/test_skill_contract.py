"""`skills/tavily-search/` 的技能契约（SK-2 / SK-6 / SK-12，全部离线）。

技能是给**别人的 agent** 读的文档，所以它的面必须可断言：frontmatter 能被子解析、行数不超预算、
引用的 `references/` 真的存在、示例走机读格式、且公开面不含内网拓扑与凭据字样。
这里重复了一份泄露模式，与 `scripts/publish_public.py` 的 `SKILL_FORBIDDEN` 刻意保持一致——
两处都要有：脚本是发布前的闸门，本文件是发布后仍然生效的回归防线（副本里没有那个脚本）。
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "tavily-search"
SKILL_MD = SKILL_DIR / "SKILL.md"

# 真实内网拓扑、主机别名、运维动作与凭据字样：技能里出现任何一条都算泄露。
# ⚠️ 带方括号的写法是**必需的**，不是排版冗余：这些字面串同时是发布脱敏脚本 GLOBAL 的替换目标，
# 原样写会让脚本把守护本身改写成没意义的模式（主机别名换成假别名、ssh 端口换成 22、
# 绝对家目录换成 `~` —— 最后这条会让副本里的断言被技能自己的 `~/.config` 路径打红），
# 副本里那条守护就**静默失效**。方括号让字面串不被 GLOBAL 命中，而正则语义不变。
# 本注释刻意不引用任何一条被替换的字面，否则这个文件自己就撞上发布闸门（真撞过）。
FORBIDDEN = [
    r"192\.168\.",
    r"10\.0\.96\.",
    r"/home/",
    r"mini[- ]server",
    r"\b12[5]80\b",
    r"server-defect-key[-]pool",
    r"\b54d4f5[1]\b",
    r"docker\s+restart",
    r"ssh\s+\w",
    r"api[_-]?key",
    r"Authorization",
    r"Bearer\s",
    r"tvly-[A-Za-z0-9_\-]{8,}",
    r"伊[利]",
    r"tunnel\.sh",
    r"--tunnel\s+on",
]


def _split(raw: str) -> tuple[dict[str, str], str]:
    """返回 (frontmatter 顶层键, 正文)。不引第三方 YAML。"""

    assert raw.startswith("---\n"), "SKILL.md 必须以 YAML frontmatter 开头"
    _, fm, body = raw.split("---\n", 2)
    top: dict[str, str] = {}
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+): (.*)$", line)
        if m:
            top[m.group(1)] = m.group(2).strip('"')
    return top, body


def _skill_files() -> list[Path]:
    return sorted(p for p in SKILL_DIR.rglob("*") if p.is_file())


def test_skill_dir_exists_with_expected_entrypoint():
    assert SKILL_MD.is_file(), f"缺少 {SKILL_MD}"
    assert (SKILL_DIR / "references").is_dir()


def test_name_equals_directory_name():
    """三个 runtime 都按 name 索引技能；与目录名不一致会让技能被列出却调不到。"""

    top, _ = _split(SKILL_MD.read_text(encoding="utf-8"))
    assert top["name"] == SKILL_DIR.name


def test_description_is_bounded_and_carries_four_elements():
    top, _ = _split(SKILL_MD.read_text(encoding="utf-8"))
    desc = top.get("description", "")
    assert desc and len(desc) <= 1024, f"description 长度 {len(desc)} 超预算或为空"
    for needle in ("tavily-cli", "原生", "点名", "首次", "端点", "不采集", "API Key"):
        assert needle in desc, f"description 缺要素：{needle}"
    for needle in ("搜索", "最新", "web search", "tavily"):
        assert needle in desc, f"description 缺触发词：{needle}"


def test_body_within_line_budget():
    """170 行是 spec §3 的硬约束：关键路径不能被推给 references/，但也不能无限膨胀。"""

    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    lines = body.count("\n")
    assert lines <= 170, f"正文 {lines} 行，超出 170 行预算"


def test_every_referenced_document_exists():
    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    mentioned = set(re.findall(r"references/[A-Za-z0-9_-]+\.md", body))
    assert mentioned, "正文必须至少指向一份 references/ 文档"
    for rel in mentioned:
        assert (SKILL_DIR / rel).is_file(), f"正文引用了不存在的 {rel}"
    # 反向也要成立：躺在目录里却没人指路的文档等于不存在
    on_disk = {f"references/{p.name}" for p in (SKILL_DIR / "references").glob("*.md")}
    assert on_disk == mentioned, f"未被正文引用的参考文档：{on_disk - mentioned}"


def test_examples_use_machine_readable_flags():
    """示例是 agent 会原样复制的东西：机读格式 + 英文键 + 静默必须写在示例里。"""

    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    assert 'search "<查询词>" -f json --keys-en --quiet --tunnel off --max-results 5' in body
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert not re.search(r"(^|[`\s])tavily-cli search", stripped), f"裸命令示例会让 agent 撞 command not found：{stripped}"


def test_zero_quota_probe_is_the_validation_step_not_doctor():
    """§3 端点验收必须用 tools（零配额）；doctor 自带一次最小搜索，配额支出要写清楚。"""

    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    assert "tools -f json --keys-en --quiet" in body
    assert "不要用 `doctor`" in body
    doctor_lines = [ln for ln in body.splitlines() if "doctor" in ln]
    assert doctor_lines and any("配额" in ln for ln in doctor_lines), "提到 doctor 的每一处都要说明它的配额代价"


def test_state_and_config_paths_are_outside_the_repo():
    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    assert "$HOME/.config/tavily-cli/skill-state.toml" in body or \
        "$HOME/.config/tavily-cli" in body
    assert "$HOME/.config/tavily-cli/config.toml" in body or \
        "$HOME/.config/tavily-cli" in body
    assert "绝不写进仓库工作树" in body


def test_state_is_written_only_after_a_verified_launch():
    """实测缺陷：`pip install -e` 拉不到构建依赖时整条失败，`bin/tavily-cli` 根本不存在，
    而原稿是"装完立刻记录"——于是下一轮探测读出一个假命中。必须验证过了才写。"""

    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    record = body.index('mode = "binary"')
    verify = body.index("--version")
    assert verify < record, "§2 必须先验证可执行、再写状态文件"
    assert "才允许执行下面的记录" in body
    assert "假命中" in body, "要留下这条踩过的原因，否则下次还会先写再验"


def test_both_launch_forms_are_resolvable_and_recordable():
    """没有 PyPI 可达的机器装不上 ⇒ 源码形态必须既能被记录、也能被 §1 读回来，
    否则每个会话都要重新问一遍，违背"只问一次"。"""

    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    for needle in ('mode = "binary"', 'mode = "source"', "source_root"):
        assert needle in body, f"缺少形态相关文本：{needle}"
    first, _ = body.split("## 2.", 1)
    for key in ("^mode", "^binary", "^source_root"):
        assert key in first, f"§1 的解析块没有读 {key}"


def _run_discovery_block(tmp_path: Path, state_text: str | None, cwd: Path) -> dict[str, str]:
    """执行 SKILL.md 里第一个 bash 块（逐字），返回解析出的三变量 + `run --version` 结果。

    技能的 shell 块是**会被原样复制执行**的东西，所以它必须真的能跑，不只是看着像。
    """

    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    block = re.search(r"```bash\n(.*?)```", body, re.S).group(1)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    if state_text is not None:
        (home / ".config" / "tavily-cli").mkdir(parents=True, exist_ok=True)
        (home / ".config" / "tavily-cli" / "skill-state.toml").write_text(
            state_text, encoding="utf-8"
        )
    probe = (
        block
        + '\nprintf "mode=[%s] runner=[%s] args=[%s] env=[%s]\\n" '
        '"${RUNNER:+set}" "$RUNNER" "$RUN_ARGS" "$ENV_PREFIX"\n'
        + '[ -n "$RUNNER" ] && { run --version 2>&1 | tail -1; }\n' '\ntrue\n'
    )
    proc = subprocess.run(
        ["bash", "-c", probe],
        cwd=cwd,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"发现块跑挂了：{proc.stderr}"
    return {"resolved": proc.stdout.splitlines()[0], "output": proc.stdout}


def test_discovery_block_falls_through_when_nothing_is_installed(tmp_path):
    proc_home = tmp_path / "empty"
    proc_home.mkdir()
    got = _run_discovery_block(tmp_path, None, proc_home)
    assert "runner=[]" in got["resolved"], "干净环境必须一无所获，否则 §2 永远不会被走到"


def test_discovery_block_resolves_recorded_source_form(tmp_path):
    state = f'mode = "source"\nsource_root = "{ROOT}"\nverified_at = "x"\n'
    got = _run_discovery_block(tmp_path, state, tmp_path)
    assert "args=[-m tavily_cli]" in got["resolved"]
    assert f"env=[PYTHONPATH={ROOT}/src]" in got["resolved"]
    assert "tavily-cli 0.1.0" in got["output"], "源码形态必须真的能起 CLI"


def test_discovery_block_resolves_recorded_binary_form(tmp_path):
    fake = tmp_path / "fake-cli"
    fake.write_text("#!/bin/sh\necho tavily-cli 0.1.0\n", encoding="utf-8")
    fake.chmod(0o755)
    state = f'mode = "binary"\nbinary = "{fake}"\nverified_at = "x"\n'
    got = _run_discovery_block(tmp_path, state, tmp_path)
    assert f"runner=[{fake}]" in got["resolved"]
    assert "args=[]" in got["resolved"] and "env=[]" in got["resolved"]
    assert "tavily-cli 0.1.0" in got["output"]


def test_discovery_block_ignores_a_stale_recorded_path(tmp_path):
    """状态文件里指向不存在文件的路径 ⇒ 必须继续往下探测，而不是照着它撞 No such file。"""

    missing = tmp_path / "gone" / "tavily-cli"
    state = f'mode = "binary"\nbinary = "{missing}"\nverified_at = "x"\n'
    got = _run_discovery_block(tmp_path, state, tmp_path)
    assert "runner=[]" in got["resolved"]


def test_examples_go_through_the_resolved_form():
    """所有示例统一用 §1 末尾的 `run`；残留的 `$TAVILY_BIN` 会让 agent 拿到空变量。"""

    for path in _skill_files():
        text = path.read_text(encoding="utf-8")
        assert "TAVILY_BIN" not in text, f"{path.name} 还在用旧变量名"
    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    assert 'run() { env $ENV_PREFIX "$RUNNER" $RUN_ARGS "$@"; }' in body
    assert 'run search "<查询词>" -f json --keys-en --quiet --tunnel off --max-results 5' in body


def test_every_invocation_pins_the_tunnel_off():
    """实测到的红线级风险：CLI 缺省 `tunnel=auto`，端点不可达时它会**自己 spawn 一条 SSH 端口
    转发到网关所在主机**（退出码 0、本机凭空多出一个转发进程并占住端口），而调用方只是想搜个网。
    技能不拥有那个动作的权限，所以每一条会被原样复制的调用行都必须显式 `--tunnel off`。
    散文里的指路（`run search --help`、`run search …`）不是调用行，按省略号与 `--help` 排除。"""

    invocations: list[tuple[str, int, str]] = []
    for path in _skill_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "…" in line or "--help" in line:
                continue
            if re.search(r"\brun (tools|search|extract|crawl|map|batch|doctor)\b", line):
                invocations.append((str(path.relative_to(ROOT)), lineno, line.strip()))
    assert len(invocations) >= 12, f"匹配到的调用行只有 {len(invocations)} 条，多半是正则失效"
    missing = [f"{rel}:{lineno}: {line}" for rel, lineno, line in invocations if "--tunnel off" not in line]
    assert not missing, "这些示例没显式关隧道：\n" + "\n".join(missing)

    _, body = _split(SKILL_MD.read_text(encoding="utf-8"))
    assert "自己 spawn 一条 SSH 端口转发" in body, "§7 要写明为什么必须 off，否则旗标会被当成冗余删掉"


def test_forbidden_patterns_survive_the_sanitizer():
    """守护自己也是被改写的对象。脱敏脚本若把某条 FORBIDDEN 的字面替换掉，
    公开副本里那条断言就**悄悄失效**——比缺失更糟，因为它照样"通过"。"""

    script = ROOT / "scripts" / "publish_public.py"
    if not script.is_file():
        pytest.skip("发布脱敏脚本是本机专用文件，公开副本里没有")
    spec = importlib.util.spec_from_file_location("_publish", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for pattern in FORBIDDEN:
        out = pattern
        for kind, old, new in mod.GLOBAL:
            out = re.sub(old, new, out) if kind == "re" else out.replace(old, new)
        assert out == pattern, f"模式 {pattern!r} 会被发布脚本改写成 {out!r}，副本里这条守护会失效"


def test_skill_never_mentions_server_ops_or_credentials():
    """FORBIDDEN 扫整个技能目录：正文与 references 都算公开面。"""

    hits: list[str] = []
    for path in _skill_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in FORBIDDEN:
                if re.search(pattern, line, re.IGNORECASE if pattern.startswith("api") else 0):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}:{pattern}")
    assert not hits, "技能面出现禁止内容：\n" + "\n".join(hits)


def test_skill_is_not_imported_or_packaged():
    """技能是文档不是代码：src/ 不该 import 它，打包也不该把它算进 wheel。"""

    for py in (ROOT / "src").rglob("*.py"):
        assert "skills/tavily-search" not in py.read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "skills" not in pyproject.lower().replace("skillspec", ""), \
        "打包配置里不应出现 skills/（技能不随包分发）"


def test_skill_files_are_text_only():
    for path in _skill_files():
        assert path.suffix == ".md", f"技能目录只该放 markdown：{path}"
        assert not path.name.endswith((".env", ".toml", ".json")), path
