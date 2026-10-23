"""`crawl` → `tavily-crawl`：§4.3 选项表。"""

from __future__ import annotations

from argparse import ArgumentParser

from . import drop_empty, loose_number

TOOL = "tavily-crawl"


def add_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("url", metavar="URL", help="起点地址（必须是 http(s) URL）")
    parser.add_argument("--max-depth", type=loose_number, help="链接递归层数，0 表示只抓起点页")
    parser.add_argument("--max-breadth", type=loose_number, help="每页最多跟进多少条链接（≥1）")
    parser.add_argument("--limit", type=loose_number, help="本次最多处理多少页（≥1）")
    parser.add_argument("--instructions", help="自然语言抓取指引（服务端用它挑选页面，不做正则解释）")
    parser.add_argument("--select-path", action="append", metavar="REGEX", help="只抓取匹配该正则的路径，可重复")
    parser.add_argument("--exclude-path", action="append", metavar="REGEX", help="排除匹配该正则的路径，可重复")
    parser.add_argument("--allow-external", action="store_true", help="允许跟随跳出起点域的链接")
    parser.add_argument("--include-images", action="store_true", help="附带页面里的图片地址")


def to_arguments(ns) -> dict:
    return drop_empty(
        {
            "url": ns.url,
            "max_depth": ns.max_depth,
            "max_breadth": ns.max_breadth,
            "limit": ns.limit,
            "instructions": ns.instructions,
            "select_paths": ns.select_path,
            "exclude_paths": ns.exclude_path,
            "allow_external": ns.allow_external or None,
            "include_images": ns.include_images or None,
        }
    )
