"""
Self-Compilation & AST-Isolated Code Generator Pipeline
Enforces strict AST safety audits (banning eval/exec/os/subprocess mutations)
and compiles in an isolated execution namespace.
"""
import ast
from dataclasses import dataclass
from typing import Callable, Any, Dict, Set

@dataclass
class CompilationResult:
    success: bool
    version: str
    bytecode_size_bytes: int
    exec_function: Callable
    ast_audit_passed: bool

class AutonomousSelfCompiler:
    def __init__(self):
        self.compiled_versions: Dict[str, Any] = {}
        self.forbidden_calls: Set[str] = {"exec", "eval", "compile", "__import__", "open", "system", "popen", "spawn"}

    def _audit_ast_safety(self, tree: ast.AST) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in self.forbidden_calls:
                    raise SecurityError(f"AST Audit Violation: Forbidden call '{node.func.id}' detected in JIT source.")
                elif isinstance(node.func, ast.Attribute) and node.func.attr in self.forbidden_calls:
                    raise SecurityError(f"AST Audit Violation: Forbidden method '{node.func.attr}' detected.")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name in {"os", "sys", "subprocess", "shutil", "socket"}:
                        raise SecurityError(f"AST Audit Violation: Forbidden import '{alias.name}' detected.")
        return True

    def compile_dynamic_subroutine(self, version_id: str, py_source: str) -> CompilationResult:
        """
        Parses, validates with AST safety audit, and compiles Python AST into executable bytecode.
        """
        tree = ast.parse(py_source)
        ast_safe = self._audit_ast_safety(tree)

        code_obj = compile(tree, filename=f"<zasi_jit_{version_id}>", mode="exec")
        
        # Build sandboxed execution globals
        isolated_globals: Dict[str, Any] = {
            "__builtins__": {
                "range": range, "len": len, "min": min, "max": max, "sum": sum,
                "abs": abs, "round": round, "int": int, "float": float, "str": str,
                "bool": bool, "dict": dict, "list": list, "set": set, "tuple": tuple
            }
        }
        namespace: Dict[str, Any] = {}
        exec(code_obj, isolated_globals, namespace)

        func = namespace.get("optimized_policy")
        if not func:
            raise ValueError("Dynamic source must define 'optimized_policy'.")

        self.compiled_versions[version_id] = func
        return CompilationResult(
            success=True,
            version=version_id,
            bytecode_size_bytes=len(code_obj.co_code),
            exec_function=func,
            ast_audit_passed=ast_safe
        )
