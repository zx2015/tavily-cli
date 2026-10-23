"""`map` → `tavily-map`：§4.3 选项表；只枚举链接结构，不抓正文。"""

from __future__ import annotations

from argparse import ArgumentParser

from . import drop_empty, loose_number

TOOL = "tavily-map"


def add_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("url", metavar="URL", help="起点地址（必须是 http(s) URL）")
    parser.add_argument("--max-depth", type=loose_number, help="链接发现层数，0 表示只看起点页")
    parser.add_argument("--limit", type=loose_number, help="最多枚举多少个 URL（≥1）")
    parser.add_argument("--select-path", action="append", metavar="REGEX", help="只保留匹配该正则的路径，可重复")


def to_arguments(ns) -> dict:
    return drop_empty(
        {
            "url": ns.url,
            "max_depth": ns.max_depth,
            "limit": ns.limit,
            "select_paths": ns.select_path,
        }
    )
