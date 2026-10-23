"""toml 配置文件层（requirements §7）：CLI > env > 配置文件 > 内置默认。

配置文件用标准库 `tomllib` 解析（design §10），读取者只有 `Config.from_args`。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tavily_cli.cli import main
from tavily_cli.config import Config, ConfigError

ENDPOINT = "http://127.0.0.1:1/mcp"


def write(path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def layout(tmp_path, monkeypatch):
    """把家目录与当前目录都挪进 tmp_path，避免读到真机上可能存在的配置。"""

    home = tmp_path / "home"
    cwd = tmp_path / "proj"
    cwd.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("TAVILY_MCP_ENDPOINT", raising=False)
    monkeypatch.delenv("TAVILY_CLI_TIMEOUT", raising=False)
    monkeypatch.delenv("TAVILY_CLI_FORMAT", raising=False)
    monkeypatch.delenv("TAVILY_CLI_TUNNEL", raising=False)
    monkeypatch.delenv("TAVILY_SSH_HOST", raising=False)
    monkeypatch.delenv("TAVILY_CLI_KEYS_LANG", raising=False)
    return home, cwd


def args(**overrides):
    return Config.from_args(type("NS", (), overrides)())


def test_user_config_file_supplies_defaults(layout):
    home, _ = layout
    write(home / ".config/tavily-cli/config.toml", 'endpoint = "http://10.0.0.1:18000/mcp"\nformat = "table"\n')
    cfg = args()
    assert cfg.endpoint == "http://10.0.0.1:18000/mcp"
    assert cfg.fmt == "table"


def test_project_file_overrides_user_file(layout):
    home, cwd = layout
    write(home / ".config/tavily-cli/config.toml", 'ssh_host = "home-box"\n')
    write(cwd / ".tavily-cli.toml", 'ssh_host = "mini-alt"\n')
    assert args().ssh_host == "mini-alt"


def test_environment_beats_config_file(layout, monkeypatch):
    home, _ = layout
    write(home / ".config/tavily-cli/config.toml", 'endpoint = "http://10.0.0.1:18000/mcp"\n')
    monkeypatch.setenv("TAVILY_MCP_ENDPOINT", "http://203.0.113.9:18000/mcp")
    assert args().endpoint == "http://203.0.113.9:18000/mcp"


def test_command_line_beats_everything(layout, monkeypatch):
    home, _ = layout
    write(home / ".config/tavily-cli/config.toml", 'endpoint = "http://10.0.0.1:18000/mcp"\ntimeout = 20\n')
    monkeypatch.setenv("TAVILY_MCP_ENDPOINT", "http://203.0.113.9:18000/mcp")
    cfg = args(endpoint="http://127.0.0.2:1/mcp", timeout=33)
    assert (cfg.endpoint, cfg.timeout) == ("http://127.0.0.2:1/mcp", 33.0)


def test_keys_lang_from_file_behaves_like_keys_en(layout):
    home, _ = layout
    write(home / ".config/tavily-cli/config.toml", 'keys_lang = "en"\n')
    assert args().keys_lang == "en"


def test_command_timeout_default_still_loses_to_the_file(layout):
    """§4.5 的 crawl/map 120s 是"内置默认"，配置文件写 timeout 应当压过它。"""

    home, _ = layout
    write(home / ".config/tavily-cli/config.toml", "timeout = 300\n")
    cfg = args(command="crawl", url="https://a.com", default_timeout=120.0)
    assert cfg.timeout == 300.0


def test_invalid_value_in_file_names_the_file_that_broke(layout):
    home, _ = layout
    write(home / ".config/tavily-cli/config.toml", 'format = "yaml"\n')
    with pytest.raises(ConfigError) as excinfo:
        args()
    message = str(excinfo.value)
    assert "yaml" in message and "format" in message
    assert "config.toml" in message, "配置错误必须说清是哪一层写错的"


def test_flag_errors_name_the_flag(layout):
    with pytest.raises(ConfigError) as excinfo:
        args(fmt="yaml")
    assert "--format" in str(excinfo.value)


def test_env_errors_name_the_variable(layout, monkeypatch):
    monkeypatch.setenv("TAVILY_CLI_FORMAT", "yaml")
    with pytest.raises(ConfigError) as excinfo:
        args()
    assert "TAVILY_CLI_FORMAT" in str(excinfo.value)


def test_unknown_key_in_file_is_rejected(layout):
    """配置文件里的笔误不能被静默忽略——它会让用户以为改动生效了。"""

    home, _ = layout
    write(home / ".config/tavily-cli/config.toml", "endpoints = \"http://10.0.0.1/mcp\"\n")
    with pytest.raises(ConfigError) as excinfo:
        args()
    message = str(excinfo.value)
    assert "endpoints" in message and "endpoint" in message


def test_broken_toml_reports_the_path(layout):
    home, _ = layout
    bad = write(home / ".config/tavily-cli/config.toml", "endpoint = \n")
    with pytest.raises(ConfigError) as excinfo:
        args()
    assert str(bad) in str(excinfo.value)


def test_missing_config_files_are_fine(layout):
    assert args().endpoint == "http://127.0.0.1:18000/mcp"


def test_cli_reports_bad_config_with_exit_code_2(layout, capsys):
    home, _ = layout
    write(home / ".config/tavily-cli/config.toml", 'tunnel = "sometimes"\n')
    assert main(["search", "x", "--endpoint", ENDPOINT]) == 2
    assert "tunnel" in capsys.readouterr().err
