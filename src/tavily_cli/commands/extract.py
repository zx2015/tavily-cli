"""`extract` → `tavily-extract`：§4.3 选项表。"""

from __future__ import annotations

from argparse import ArgumentParser

from . import drop_empty

TOOL = "tavily-extract"


def add_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("urls", nargs="+", metavar="URL", help="要提取正文的 http(s) 地址，1–20 个")
    parser.add_argument("--depth", dest="depth", help="提取深度：basic / advanced（服务端默认 basic）")
    parser.add_argument("--include-images", action="store_true", help="附带图片列表")


def to_arguments(ns) -> dict:
    return drop_empty(
        {
            "urls": ns.urls,
            "extract_depth": ns.depth,
            "include_images": ns.include_images or None,
        }
    )
