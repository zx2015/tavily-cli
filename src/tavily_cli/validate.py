"""校验闸门：design §3 里 transport 之前的单向闸门。

永不抛异常，只返回 ValidationReport；`--dry-run` 时它是唯一被执行的层。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from . import schema
from .schema import ParamSpec, ToolSpec


@dataclass(frozen=True)
class FieldError:
    param: str
    value: object
    message: str
    hint: str = ""


@dataclass
class ValidationReport:
    errors: list[FieldError] = field(default_factory=list)
    warnings: list[FieldError] = field(default_factory=list)
    dropped: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def sanitize(self, args: dict) -> dict:
        return {key: value for key, value in args.items() if key not in self.dropped}


_TYPE_LABELS = {
    "string": "字符串",
    "integer": "整数",
    "number": "数字",
    "boolean": "布尔",
    "array": "数组",
}


def _is_control(text: str) -> bool:
    return any(ord(char) < 0x20 or ord(char) == 0x7F for char in text)


def _type_error(param: ParamSpec, value: object) -> FieldError | None:
    expected = param.kind
    wrong = False
    if expected == "string":
        wrong = not isinstance(value, str)
    elif expected == "boolean":
        wrong = not isinstance(value, bool)
    elif expected == "integer":
        wrong = isinstance(value, bool) or not isinstance(value, int)
    elif expected == "number":
        wrong = isinstance(value, bool) or not isinstance(value, (int, float))
    elif expected == "array":
        wrong = not isinstance(value, list)
    if wrong:
        return FieldError(
            param.name,
            value,
            f"{param.name} 需要{_TYPE_LABELS.get(expected, expected)}类型，实际是 {type(value).__name__}",
            hint=f"示例：--{param.name.replace('_', '-')} <{_TYPE_LABELS.get(expected, expected)}>",
        )
    return None


def _check_items(param: ParamSpec, values: list) -> list[FieldError]:
    errors: list[FieldError] = []
    if param.item_kind:
        for item in values:
            probe = ParamSpec(name=param.name, kind=param.item_kind)
            error = _type_error(probe, item)
            if error:
                errors.append(
                    FieldError(
                        param.name,
                        values,
                        f"{param.name} 的每一项必须是{_TYPE_LABELS.get(param.item_kind, param.item_kind)}",
                        hint=error.hint,
                    )
                )
                break
    if param.min_items is not None and len(values) < param.min_items:
        errors.append(
            FieldError(param.name, values, f"{param.name} 至少 {param.min_items} 项，当前 {len(values)} 项")
        )
    if param.max_items is not None and len(values) > param.max_items:
        errors.append(
            FieldError(
                param.name, values, f"{param.name} 最多 {param.max_items} 项，当前 {len(values)} 项"
            )
        )
    return errors


def _check_http_url(param: ParamSpec, value: object) -> FieldError | None:
    parts = urlsplit(value) if isinstance(value, str) else None
    if parts is None or parts.scheme not in ("http", "https") or not parts.hostname:
        return FieldError(
            param.name,
            value,
            f"{param.name} 必须是 http(s) URL，收到 {value!r}",
            hint="示例：https://example.com",
        )
    return None


def _semantic_errors(param: ParamSpec, args: dict) -> list[FieldError]:
    value = args.get(param.name)
    errors: list[FieldError] = []
    for check in param.checks:
        if check == "domain_list":
            for item in value:
                if not schema.validate_domain(item):
                    errors.append(
                        FieldError(
                            param.name,
                            value,
                            f"{param.name} 含非法域名 {item!r}：必须是带合法后缀的纯域名（如 example.com）",
                            hint="禁止协议前缀、路径、端口、空格与无后缀主机名",
                        )
                    )
        elif check == "http_url_list":
            for item in value:
                error = _check_http_url(param, item)
                if error:
                    errors.append(error)
        elif check == "http_url":
            error = _check_http_url(param, value)
            if error:
                errors.append(error)
        elif check == "regex_list":
            for item in value:
                try:
                    re.compile(item)
                except re.error as exc:
                    errors.append(
                        FieldError(
                            param.name,
                            value,
                            f"{param.name} 含无法编译的正则 {item!r}：{exc}",
                            hint="示例：^/docs 或 ^/(blog|news)",
                        )
                    )
    return errors


def _bounds_errors(param: ParamSpec, args: dict) -> list[FieldError]:
    value = args.get(param.name)
    errors: list[FieldError] = []
    if param.max_length is not None and isinstance(value, str) and len(value) > param.max_length:
        errors.append(
            FieldError(
                param.name, value, f"{param.name} 超过 {param.max_length} 字符，当前 {len(value)}"
            )
        )
    if "nonempty" in param.checks and isinstance(value, str) and not value.strip():
        errors.append(FieldError(param.name, value, f"{param.name} 不能为空或纯空白"))
    if "no_control" in param.checks and isinstance(value, str) and _is_control(value):
        errors.append(
            FieldError(param.name, value, f"{param.name} 含控制字符（换行/制表/转义等）", hint="请用单行文本")
        )
    if param.enum is not None and isinstance(value, str) and value not in param.enum:
        errors.append(
            FieldError(
                param.name,
                value,
                f"{param.name} 取值 {value!r} 非法，只允许：{' / '.join(param.enum)}",
            )
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if param.minimum is not None and value < param.minimum:
            errors.append(
                FieldError(param.name, value, f"{param.name} 不得小于 {param.minimum}")
            )
        if param.maximum is not None and value > param.maximum:
            errors.append(
                FieldError(param.name, value, f"{param.name} 不得大于 {param.maximum}")
            )
    return errors


def _check_one(param: ParamSpec, args: dict, report: ValidationReport) -> None:
    value = args[param.name]
    if value is None:
        report.errors.append(
            FieldError(
                param.name,
                value,
                f"{param.name} 的值是 null；本 CLI 只发用户显式指定的键，请省略该选项",
                hint="服务端 additionalProperties:false，传 null 与省略不等价",
            )
        )
        return

    type_error = _type_error(param, value)
    if type_error:
        report.errors.append(type_error)
        return

    if param.kind == "array":
        item_errors = _check_items(param, value)
        report.errors.extend(item_errors)
        if item_errors:
            return

    if "news_only" in param.checks and args.get("topic") != "news":
        report.warnings.append(
            FieldError(
                param.name,
                value,
                f"{param.name} 仅在 --topic news 时生效，本次已忽略",
                hint="加上 --topic news 才会发送该参数",
            )
        )
        report.dropped += (param.name,)
        return

    report.errors.extend(_semantic_errors(param, args))
    report.errors.extend(_bounds_errors(param, args))


def _unknown_tool(tool: str) -> ValidationReport:
    return ValidationReport(
        errors=[
            FieldError(
                "<tool>",
                tool,
                f"未知工具 '{tool}'，可用：{' / '.join(schema.TOOL_SCHEMA)}",
            )
        ]
    )


def validate(tool: str, args: dict) -> ValidationReport:
    spec: ToolSpec | None = schema.TOOL_SCHEMA.get(tool)
    if spec is None:
        return _unknown_tool(tool)

    report = ValidationReport()
    for param in spec.params.values():
        if param.name in args:
            _check_one(param, args, report)

    for name in spec.required:
        if name not in args:
            report.errors.append(
                FieldError(name, None, f"缺少必填参数 {name}", hint=f"{tool} 必须提供 {name}")
            )

    for key in args:
        if key not in spec.params:
            report.errors.append(
                FieldError(
                    key,
                    args[key],
                    f"{key} 是 {tool} 未声明的键，服务端 schema 为 additionalProperties:false 会直接拒绝",
                    hint="请先用 tavily-cli tools 核对服务端参数表",
                )
            )

    return report
