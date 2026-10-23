"""`search` → `tavily-search`：§4.2 选项表与 MCP 参数一一对应。"""

from __future__ import annotations

from argparse import ArgumentParser

from . import drop_empty, loose_number

TOOL = "tavily-search"


def add_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("query", help="查询词（非空、单行、≤512 字符）")
    parser.add_argument("--depth", help="搜索深度：basic / advanced（服务端默认 basic）")
    parser.add_argument("--topic", help="主题：general / news / finance（服务端默认 general）")
    parser.add_argument("--days", type=loose_number, help="仅 --topic news 生效：回看 1–365 天")
    parser.add_argument("--max-results", type=loose_number, help="返回条数 1–20（服务端默认 5）")
    parser.add_argument("--time-range", help="时间范围：day / week / month / year")
    parser.add_argument("--include-answer", action="store_true", help="让服务端附带一段简答")
    parser.add_argument("--include-images", action="store_true", help="附带图片列表")
    parser.add_argument("--include-image-descriptions", action="store_true", help="附带图片描述")
    parser.add_argument("--include-raw-content", action="store_true", help="附带页面正文原文")
    parser.add_argument("--include-domain", action="append", metavar="DOMAIN", help="只在这些域名内搜索，可重复（如 example.com，须带合法后缀）")
    parser.add_argument("--exclude-domain", action="append", metavar="DOMAIN", help="排除这些域名，可重复（同上）")
    parser.add_argument("--request-timeout", type=loose_number, help="本次调用的本地读超时 1.0–60.0 秒（4.1.3 起服务端不再接受 timeout 入参，本选项不出网）")


def to_arguments(ns) -> dict:
    return drop_empty(
        {
            "query": ns.query,
            "search_depth": ns.depth,
            "topic": ns.topic,
            "days": ns.days,
            "max_results": ns.max_results,
            "time_range": ns.time_range,
            "include_answer": ns.include_answer or None,
            "include_images": ns.include_images or None,
            "include_image_descriptions": ns.include_image_descriptions or None,
            "include_raw_content": ns.include_raw_content or None,
            "include_domains": ns.include_domain,
            "exclude_domains": ns.exclude_domain,
        }
    )
