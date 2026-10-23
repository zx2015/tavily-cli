"""子命令层：只做"CLI 选项 → MCP arguments"映射与该命令的编排，不含渲染与传输细节。"""

from __future__ import annotations

# MCP 参数名 → 用户在命令行上写的选项，用于把校验错误说成使用者听得懂的话（§6 退出码 2）。
OPTION_OF_PARAM = {
    "query": "<查询词>",
    "search_depth": "--depth",
    "topic": "--topic",
    "days": "--days",
    "max_results": "--max-results",
    "time_range": "--time-range",
    "include_answer": "--include-answer",
    "include_images": "--include-images",
    "include_image_descriptions": "--include-image-descriptions",
    "include_raw_content": "--include-raw-content",
    "include_domains": "--include-domain",
    "exclude_domains": "--exclude-domain",
    "timeout": "--request-timeout",
    "urls": "<URL>…",
    "extract_depth": "--depth",
    "url": "<URL>",
    "max_depth": "--max-depth",
    "max_breadth": "--max-breadth",
    "limit": "--limit",
    "instructions": "--instructions",
    "select_paths": "--select-path",
    "exclude_paths": "--exclude-path",
    "allow_external": "--allow-external",
}


def option_for(param: str) -> str:
    return OPTION_OF_PARAM.get(param, f"--{param.replace('_', '-')}")


def drop_empty(values: dict) -> dict:
    """只保留用户显式给出的键：省略 ≠ 传 null，服务端 additionalProperties:false 会拒 null。"""

    return {key: value for key, value in values.items() if value is not None}


def loose_number(raw: str):
    """argparse 转换器：能变成数字就变，不能就原样交给校验层报中文类型错误。"""

    try:
        number = float(raw)
    except ValueError:
        return raw
    return int(number) if number.is_integer() else number
