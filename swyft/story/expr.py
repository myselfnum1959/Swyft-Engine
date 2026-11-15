"""A small, *safe* expression language for scripts: ``courage >= 2 and not met_guard``.

We lean on Python's own parser (``ast``) for syntax, then walk the tree ourselves
and only accept a whitelist of node types. We never call ``eval``/``exec``, so
there is no route from a script (or a tampered save file) to running arbitrary
code: no attribute access, no function calls, no imports, no comprehensions.

Allowed: numbers, strings, booleans (true/false/none), variable names,
``+ - * / // %``, comparisons (chained too), ``and or not``, unary minus, and
list/tuple literals (for ``"x" in ["a", "b"]``).
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any, Callable, Mapping

from .errors import ExpressionError, ExpressionEvalError

_BINARY: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_COMPARE: dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}
_UNARY: dict[type, Callable[[Any], Any]] = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_CONSTANTS = {"true": True, "false": False, "none": None}


class Expression:
    """A pre-validated expression that can be evaluated against variables."""

    def __init__(self, source: str):
        self.source = source.strip()
        try:
            tree = ast.parse(self.source, mode="eval")
        except SyntaxError as exc:
            raise ExpressionError(f"invalid expression {self.source!r}: {exc.msg}") from exc
        self.names: set[str] = set()
        self._validate(tree.body)
        self._root = tree.body

    def __repr__(self) -> str:  # stable repr -> stable script fingerprints
        return f"Expression({self.source!r})"

    # ---- validation (compile time) ----------------------------------------
    def _validate(self, node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (bool, int, float, str, type(None))):
                raise ExpressionError(f"unsupported constant in {self.source!r}")
        elif isinstance(node, ast.Name):
            if node.id not in _CONSTANTS:
                self.names.add(node.id)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                self._validate(value)
        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in _UNARY:
                raise ExpressionError(f"operator not allowed in {self.source!r}")
            self._validate(node.operand)
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in _BINARY:
                raise ExpressionError(f"operator {type(node.op).__name__} not allowed in {self.source!r}")
            self._validate(node.left)
            self._validate(node.right)
        elif isinstance(node, ast.Compare):
            if any(type(op) not in _COMPARE for op in node.ops):
                raise ExpressionError(f"comparison not allowed in {self.source!r}")
            self._validate(node.left)
            for comparator in node.comparators:
                self._validate(comparator)
        elif isinstance(node, (ast.List, ast.Tuple)):
            for element in node.elts:
                self._validate(element)
        else:
            raise ExpressionError(
                f"{type(node).__name__} is not allowed in expressions (in {self.source!r}); "
                "only arithmetic, comparisons, and/or/not and variable names are supported"
            )

    # ---- evaluation (runtime) ---------------------------------------------
    def evaluate(self, variables: Mapping[str, Any]) -> Any:
        try:
            return self._eval(self._root, variables)
        except ExpressionEvalError:
            raise
        except ZeroDivisionError as exc:
            raise ExpressionEvalError(f"division by zero in {self.source!r}") from exc
        except TypeError as exc:
            raise ExpressionEvalError(f"type error in {self.source!r}: {exc}") from exc

    def _eval(self, node: ast.AST, env: Mapping[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in _CONSTANTS:
                return _CONSTANTS[node.id]
            if node.id in env:
                return env[node.id]
            raise ExpressionEvalError(f"unknown variable {node.id!r} in {self.source!r}")
        if isinstance(node, ast.BoolOp):
            # Short-circuit like Python: stop at the first decisive operand.
            if isinstance(node.op, ast.And):
                result: Any = True
                for value in node.values:
                    result = self._eval(value, env)
                    if not result:
                        return result
                return result
            result = False
            for value in node.values:
                result = self._eval(value, env)
                if result:
                    return result
            return result
        if isinstance(node, ast.UnaryOp):
            return _UNARY[type(node.op)](self._eval(node.operand, env))
        if isinstance(node, ast.BinOp):
            return _BINARY[type(node.op)](self._eval(node.left, env), self._eval(node.right, env))
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, env)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, env)
                if not _COMPARE[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self._eval(e, env) for e in node.elts]
        raise ExpressionEvalError(f"cannot evaluate {type(node).__name__}")  # pragma: no cover


# ---- text interpolation: "Hello, {name}!" ----------------------------------
_INTERPOLATION = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolation_names(text: str) -> set[str]:
    """Variable names referenced as ``{name}`` in ``text``."""
    return {m.group(1) for m in _INTERPOLATION.finditer(text) if m.group(1)}


def interpolate(text: str, variables: Mapping[str, Any]) -> str:
    """Replace ``{name}`` with the variable's value; ``{{`` and ``}}`` are literal braces."""

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        name = match.group(1)
        if name not in variables:
            raise ExpressionEvalError(f"unknown variable {name!r} in text {text!r}")
        return str(variables[name])

    return _INTERPOLATION.sub(replace, text)
