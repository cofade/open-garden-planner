"""Safe arithmetic expression evaluator for smart-symbol geometry (US-C4).

Smart-symbol definitions (data files, possibly user-authored) express geometry
coordinates as small arithmetic formulas over their parameters, e.g.
``"W * i / rows"`` or ``"max(L - 2*margin, 0)"``. Those strings must be
evaluated **without** Python's ``eval()`` — a dropped JSON file is untrusted
input. This module parses the expression with ``ast`` and walks a strict
whitelist of node types, so anything outside basic arithmetic (attribute
access, arbitrary calls, comprehensions, imports, lambdas, names not in the
supplied variable map) raises ``ValueError`` instead of executing.

Intentionally Qt-free so it can be unit-tested in isolation.
"""

from __future__ import annotations

import ast
import math
from typing import Any

# Whitelisted callables. All pure, numeric, side-effect-free.
_FUNCS: dict[str, Any] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "floor": lambda x: math.floor(x),
    "ceil": lambda x: math.ceil(x),
    "sqrt": lambda x: math.sqrt(x),
}

_BIN_OPS: dict[type, Any] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
    ast.FloorDiv: lambda a, b: a // b,
}

_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}


def safe_eval(expr: str, variables: dict[str, float] | None = None) -> float:
    """Evaluate an arithmetic ``expr`` over ``variables`` and return a float.

    Supports ``+ - * / % ** //``, unary ``+ -``, parentheses, numeric literals,
    variable names present in ``variables``, and calls to the whitelisted
    functions (min/max/abs/round/floor/ceil/sqrt). Anything else raises
    ``ValueError``. Never executes arbitrary code.
    """
    variables = variables or {}
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression {expr!r}: {exc}") from exc
    return float(_eval_node(tree.body, variables))


def _eval_node(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"Non-numeric constant: {node.value!r}")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f"Unknown variable: {node.id!r}")
        return float(variables[node.id])
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Operator not allowed: {type(node.op).__name__}")
        return op(_eval_node(node.left, variables), _eval_node(node.right, variables))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unary operator not allowed: {type(node.op).__name__}")
        return op(_eval_node(node.operand, variables))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ValueError("Only whitelisted function calls are allowed")
        if node.keywords:
            raise ValueError("Keyword arguments are not allowed")
        args = [_eval_node(a, variables) for a in node.args]
        return float(_FUNCS[node.func.id](*args))
    raise ValueError(f"Expression element not allowed: {type(node).__name__}")
