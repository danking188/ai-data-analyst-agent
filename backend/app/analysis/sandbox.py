from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from app.domain.errors import state_conflict, validation_error

FORBIDDEN_PARAMETER_TOKENS = {
    "__import__",
    "eval",
    "exec",
    "open(",
    "socket",
    "subprocess",
    "http://",
    "https://",
}

ALLOWED_EXPRESSION_NODES = {
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
}


def validate_tool_context(context: dict[str, Any]) -> None:
    data_path = context.get("data_path")
    data_root = context.get("data_root")
    if data_path is not None and data_root is not None:
        resolved_path = Path(str(data_path)).resolve()
        resolved_root = Path(str(data_root)).resolve()
        if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
            raise state_conflict("工具输入路径越过 DATA_ROOT 边界")
    _reject_forbidden_parameters(context.get("parameters", {}))


def validate_safe_expression(expression: str) -> None:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise validation_error("表达式语法无效") from exc
    for node in ast.walk(tree):
        if type(node) not in ALLOWED_EXPRESSION_NODES:
            raise validation_error(
                "表达式包含不允许的语法节点",
                node_type=type(node).__name__,
            )


def _reject_forbidden_parameters(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if "code" in lowered_key or "expression" in lowered_key:
                raise validation_error("工具参数不得包含代码或表达式字段", field=str(key))
            _reject_forbidden_parameters(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_forbidden_parameters(item)
        return
    if isinstance(value, str):
        lowered = value.lower()
        forbidden = [token for token in FORBIDDEN_PARAMETER_TOKENS if token in lowered]
        if forbidden:
            raise validation_error("工具参数包含不允许的执行或网络能力", tokens=forbidden)
