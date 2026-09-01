"""
Symbolic AST Expression Parser for Arbitrary Invariants
"""
import ast
from typing import Dict, Any

class SymbolicExpressionEvaluator:
    @staticmethod
    def evaluate(expression_str: str, env: Dict[str, Any]) -> bool:
        """
        Safely evaluates an invariant boolean expression (e.g. 'x + y <= 100')
        using Python's AST without running unsafe arbitrary code.
        """
        tree = ast.parse(expression_str, mode='eval')

        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            elif isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.Name):
                if node.id in env:
                    return env[node.id]
                raise ValueError(f"Variable '{node.id}' unbound in environment.")
            elif isinstance(node, ast.BinOp):
                left = _eval(node.left)
                right = _eval(node.right)
                if isinstance(node.op, ast.Add): return left + right
                if isinstance(node.op, ast.Sub): return left - right
                if isinstance(node.op, ast.Mult): return left * right
                if isinstance(node.op, ast.Div): return left / right
                raise NotImplementedError(f"Op {type(node.op)} not supported")
            elif isinstance(node, ast.Compare):
                left = _eval(node.left)
                for op, comparator in zip(node.ops, node.comparators):
                    right = _eval(comparator)
                    if isinstance(op, ast.Lt) and not (left < right): return False
                    if isinstance(op, ast.LtE) and not (left <= right): return False
                    if isinstance(op, ast.Gt) and not (left > right): return False
                    if isinstance(op, ast.GtE) and not (left >= right): return False
                    if isinstance(op, ast.Eq) and not (left == right): return False
                    if isinstance(op, ast.NotEq) and not (left != right): return False
                    left = right
                return True
            raise TypeError(f"Unsupported AST node: {type(node)}")

        return bool(_eval(tree))
