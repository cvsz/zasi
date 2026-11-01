r"""
Symbolic AST Expression Parser for Arbitrary Invariants
"""
from __future__ import annotations

import ast
import operator as _op
from typing import Any, Dict

__all__ = ["SymbolicExpressionEvaluator"]

# ---------------------------------------------------------------------------
# Operator dispatch tables — kept outside the hot path for clarity
# ---------------------------------------------------------------------------

_BINOP_TABLE: Dict[type, Any] = {
    ast.Add:      _op.add,
    ast.Sub:      _op.sub,
    ast.Mult:     _op.mul,
    ast.Div:      _op.truediv,
    ast.FloorDiv: _op.floordiv,
    ast.Mod:      _op.mod,
    ast.Pow:      _op.pow,
    ast.LShift:   _op.lshift,
    ast.RShift:   _op.rshift,
    ast.BitOr:    _op.or_,
    ast.BitXor:   _op.xor,
    ast.BitAnd:   _op.and_,
    ast.MatMult:  _op.matmul,
}

_UNARYOP_TABLE: Dict[type, Any] = {
    ast.UAdd:   _op.pos,
    ast.USub:   _op.neg,
    ast.Invert: _op.invert,
    ast.Not:    _op.not_,
}

_CMPOP_TABLE: Dict[type, Any] = {
    ast.Lt:     _op.lt,
    ast.LtE:    _op.le,
    ast.Gt:     _op.gt,
    ast.GtE:    _op.ge,
    ast.Eq:     _op.eq,
    ast.NotEq:  _op.ne,
    ast.Is:     _op.is_,
    ast.IsNot:  _op.is_not,
    ast.In:     lambda a, b: a in b,
    ast.NotIn:  lambda a, b: a not in b,
}


class SymbolicExpressionEvaluator:
    @staticmethod
    def evaluate(expression_str: str, env: Dict[str, Any]) -> bool:
        """Safely evaluate an invariant boolean expression.

        Parses *expression_str* via Python's :mod:`ast` module and walks the
        resulting tree without calling :func:`eval`, so no arbitrary code can
        execute.  Only a safe, deterministic subset of Python expressions is
        supported:

        * Literals (``int``, ``float``, ``bool``, ``str``, ``None``).
        * Variable names resolved against *env*.
        * All binary arithmetic / bitwise operators
          (``+``, ``-``, ``*``, ``/``, ``//``, ``%``, ``**``,
           ``<<``, ``>>``, ``|``, ``^``, ``&``, ``@``).
        * All unary operators (``+``, ``-``, ``~``, ``not``).
        * Boolean operators (``and``, ``or``).
        * All comparison operators
          (``<``, ``<=``, ``>``, ``>=``, ``==``, ``!=``,
           ``is``, ``is not``, ``in``, ``not in``).
        * Conditional expressions / ternary (``x if cond else y``).

        Args:
            expression_str: Source text of the expression to evaluate.
            env: Mapping of variable names to their current values.

        Returns:
            The boolean truth value of the evaluated expression.

        Raises:
            ValueError: If a variable name in the expression is not in *env*.
            TypeError: If the expression contains an unsupported AST node type.
        """
        tree = ast.parse(expression_str, mode="eval")

        def _eval(node: ast.AST) -> Any:  # noqa: ANN001
            # Wrapper node produced by mode='eval'
            if isinstance(node, ast.Expression):
                return _eval(node.body)

            # ---------- Literals ----------
            if isinstance(node, ast.Constant):
                return node.value

            # ---------- Variable lookup ----------
            if isinstance(node, ast.Name):
                if node.id not in env:
                    raise ValueError(f"Variable '{node.id}' unbound in environment.")
                return env[node.id]

            # ---------- Unary ops: +x  -x  ~x  not x ----------
            if isinstance(node, ast.UnaryOp):
                fn = _UNARYOP_TABLE.get(type(node.op))
                if fn is None:
                    raise TypeError(f"Unsupported unary operator: {type(node.op)}")
                return fn(_eval(node.operand))

            # ---------- Binary ops: x + y, x ** y, x & y, … ----------
            if isinstance(node, ast.BinOp):
                fn = _BINOP_TABLE.get(type(node.op))
                if fn is None:
                    raise TypeError(f"Unsupported binary operator: {type(node.op)}")
                return fn(_eval(node.left), _eval(node.right))

            # ---------- Boolean ops: x and y, x or y ----------
            if isinstance(node, ast.BoolOp):
                if isinstance(node.op, ast.And):
                    result: Any = True
                    for value in node.values:
                        result = _eval(value)
                        if not result:
                            return result
                    return result
                if isinstance(node.op, ast.Or):
                    result = False
                    for value in node.values:
                        result = _eval(value)
                        if result:
                            return result
                    return result
                raise TypeError(f"Unsupported boolean operator: {type(node.op)}")

            # ---------- Comparisons: a < b <= c, a in b, a is not b, … ----------
            if isinstance(node, ast.Compare):
                left = _eval(node.left)
                for op, comparator in zip(node.ops, node.comparators):
                    right = _eval(comparator)
                    fn = _CMPOP_TABLE.get(type(op))
                    if fn is None:
                        raise TypeError(f"Unsupported comparison operator: {type(op)}")
                    if not fn(left, right):
                        return False
                    left = right
                return True

            # ---------- Ternary / conditional expression: x if cond else y ----------
            if isinstance(node, ast.IfExp):
                return _eval(node.body) if _eval(node.test) else _eval(node.orelse)

            raise TypeError(f"Unsupported AST node: {type(node)}")

        return bool(_eval(tree))

