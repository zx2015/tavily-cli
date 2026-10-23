"""四级配置合并：命令行 > 环境变量 > 配置文件 > 内置默认（requirements §7）。

配置文件用标准库 `tomllib`（Python ≥3.11）读两级：`~/.config/tavily-cli/config.toml`
与项目内 `.tavily-cli.toml`（后者覆盖前者）。未知键、坏 TOML、坏取值都按 USAGE（退出码 2）
报出**是哪一层写错的**——配置静默失效比配置报错更难查。
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import constants

FORMATS = ("auto", "json", "ndjson", "table", "md", "raw")
TUNNELS = ("auto", "off", "on")
LANGS = ("zh", "en")

_ENV = {
    "endpoint": "TAVILY_MCP_ENDPOINT",
    "timeout": "TAVILY_CLI_TIMEOUT",
    "format": "TAVILY_CLI_FORMAT",
    "tunnel": "TAVILY_CLI_TUNNEL",
    "ssh_host": "TAVILY_SSH_HOST",
    "keys_lang": "TAVILY_CLI_KEYS_LANG",
}

_CONFIG_KEYS = tuple(_ENV)
_CLI_FLAG = {"endpoint": "--endpoint", "timeout": "--timeout", "format": "--format", "tunnel": "--tunnel"}
_DEFAULT_SOURCE = "内置默认"


class ConfigError(Exception):
    """配置来源（命令行 / 环境变量 / 配置文件）里的值不合法，按 USAGE（退出码 2）处理。"""


def _user_config_path() -> Path:
    return Path.home() / ".config" / "tavily-cli" / "config.toml"


def _project_config_path(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        candidate = folder / ".tavily-cli.toml"
        if candidate.is_file():
            return candidate
    return None


def _read_config(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"配置文件 {path} 不是合法 TOML：{exc}") from exc
    except OSError as exc:
        raise ConfigError(f"配置文件 {path} 读取失败：{exc}") from exc
    unknown = sorted(set(data) - set(_CONFIG_KEYS))
    if unknown:
        raise ConfigError(
            f"配置文件 {path} 含未知键 {' / '.join(unknown)}；"
            f"本 CLI 只认：{' / '.join(_CONFIG_KEYS)}"
        )
    return {key: (value, str(path)) for key, value in data.items()}


def load_config_files(start: Path | None = None) -> dict:
    merged = _read_config(_user_config_path())
    merged.update(_read_config(_project_config_path(Path.cwd() if start is None else start)))
    return merged


def _resolve(files: dict, flag_value: object, key: str, default: str) -> tuple[str, str]:
    """返回 (取值, 来源标签)。CLI > env > 配置文件 > 内置默认。"""

    if flag_value is not None and key in _CLI_FLAG:
        return str(flag_value), _CLI_FLAG[key]
    env_value = os.environ.get(_ENV[key])
    if env_value not in (None, ""):
        return str(env_value), _ENV[key]
    if key in files:
        value, path = files[key]
        return str(value), path
    return default, _DEFAULT_SOURCE


def _where(key: str, source: str) -> str:
    return key if source == _DEFAULT_SOURCE else f"{key}（来源：{source}）"


def _one_of(value: str, allowed: tuple[str, ...], label: str) -> str:
    if value not in allowed:
        raise ConfigError(f"{label} 取值 {value!r} 非法，只允许：{' / '.join(allowed)}")
    return value


def _number(value: str, label: str, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{label} 需要数字，收到 {value!r}") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{label} 必须在 {minimum}–{maximum} 之间，收到 {value}")
    return parsed


def _optional_number(value: object, key: str, minimum: float, maximum: float) -> float | None:
    return None if value is None else _number(value, key, minimum, maximum)  # type: ignore[arg-type]


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} 需要整数，收到 {value!r}")
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} 必须在 {minimum}–{maximum} 之间，收到 {value}")
    return value


@dataclass(frozen=True)
class Config:
    endpoint: str
    timeout: float
    request_timeout: float | None
    fmt: str
    tunnel: str
    ssh_host: str
    keys_lang: str
    retries: int
    retries_given: bool
    concurrency: int
    quiet: bool
    verbose: bool
    color: bool
    dry_run: bool
    output: str | None
    with_meta: bool
    width: int

    @classmethod
    def from_args(cls, ns) -> "Config":
        # 全局选项默认是 argparse.SUPPRESS：未出现在命令行上时属性根本不存在。
        def _get(name: str):
            return getattr(ns, name, None)

        files = load_config_files()
        keys_lang, lang_from = (
            ("en", "--keys-en") if _get("keys_en") else _resolve(files, None, "keys_lang", "zh")
        )
        retries = _get("retries")
        concurrency = _get("concurrency")
        retries_given = retries is not None
        # crawl/map 由 set_defaults(default_timeout=120) 抬高内置默认；env 与配置文件仍压过它。
        base_timeout = str(_get("default_timeout") or constants.DEFAULT_TIMEOUT)
        endpoint, _ = _resolve(files, _get("endpoint"), "endpoint", constants.DEFAULT_ENDPOINT)
        raw_timeout, timeout_from = _resolve(files, _get("timeout"), "timeout", base_timeout)
        fmt, fmt_from = _resolve(files, _get("fmt"), "format", "auto")
        tunnel, tunnel_from = _resolve(files, _get("tunnel"), "tunnel", "auto")
        ssh_host, _ = _resolve(files, None, "ssh_host", constants.DEFAULT_SSH_HOST)
        return cls(
            endpoint=endpoint,
            timeout=_number(raw_timeout, _where("timeout", timeout_from), 1.0, 600.0),
            request_timeout=_optional_number(_get("request_timeout"), "--request-timeout", 1.0, 60.0),
            fmt=_one_of(fmt, FORMATS, _where("format", fmt_from)),
            tunnel=_one_of(tunnel, TUNNELS, _where("tunnel", tunnel_from)),
            ssh_host=ssh_host,
            keys_lang=_one_of(keys_lang, LANGS, _where("keys_lang", lang_from)),
            retries=_integer(retries if retries_given else constants.DEFAULT_RETRIES, "--retries", 0, constants.MAX_RETRIES),
            retries_given=retries_given,
            concurrency=_integer(
                concurrency if concurrency is not None else constants.DEFAULT_CONCURRENCY,
                "--concurrency",
                1,
                constants.MAX_CONCURRENCY,
            ),
            quiet=bool(_get("quiet")),
            verbose=bool(_get("verbose")),
            color=not _get("no_color") and not os.environ.get("NO_COLOR"),
            dry_run=bool(_get("dry_run")),
            output=_get("output"),
            with_meta=bool(_get("with_meta")),
            width=shutil.get_terminal_size().columns,
        )
