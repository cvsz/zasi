r"""
Self-Compilation & AST-Isolated Code Generator Pipeline
Enforces strict AST safety audits (banning eval/exec/os/subprocess mutations)
and compiles in an isolated execution namespace.

Security: all exec() calls are logged to an append-only audit trail.
"""
import ast
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Any, Dict, Set

# --------------------------------------------------------------------------- #
# Exec Audit Trail                                                              #
# --------------------------------------------------------------------------- #
_exec_audit_log: list = []   # in-memory ring; max 1000 entries
_EXEC_AUDIT_LIMIT = 1000

_exec_logger = logging.getLogger("zasi.self_compilation.exec_audit")
if not _exec_logger.handlers:
    _exec_logger.setLevel(logging.INFO)
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [EXEC_AUDIT] %(message)s"))
    _exec_logger.addHandler(_h)


def _record_exec(version_id: str, source: str, success: bool, error: str = "") -> dict:
    """Append a structured entry to the in-memory exec audit log."""
    src_hash = hashlib.sha256(source.encode()).hexdigest()
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version_id": version_id,
        "source_sha256": src_hash,
        "source_lines": source.count("\n") + 1,
        "success": success,
        "error": error,
    }
    _exec_audit_log.append(entry)
    if len(_exec_audit_log) > _EXEC_AUDIT_LIMIT:
        _exec_audit_log.pop(0)
    _exec_logger.info(json.dumps(entry))
    return entry


class CapabilityDisabled(RuntimeError):
    """Raised when research-only dynamic execution is requested in the control plane."""


class SecurityError(ValueError):
    """Raised when a candidate fails static inspection."""


@dataclass
class CompilationResult:
    success: bool
    version: str
    bytecode_size_bytes: int
    exec_function: Callable
    ast_audit_passed: bool

class AutonomousSelfCompiler:
    def __init__(self, research_worker: Any = None):
        self.compiled_versions: Dict[str, Any] = {}
        self.forbidden_calls: Set[str] = {"exec", "eval", "compile", "__import__", "open", "system", "popen", "spawn"}
        self.research_worker = research_worker

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
        Dynamic execution is not a control-plane capability.

        Research compilation must be submitted to a separately deployed worker
        with an OS-level sandbox, signed artifact flow, and independent
        verification. This class deliberately does not provide a fallback.
        """
        _record_exec(
            version_id,
            py_source,
            success=False,
            error="dynamic execution disabled; submit to research worker",
        )
        raise CapabilityDisabled(
            "Dynamic self-compilation is disabled; use the isolated research worker."
        )

    @staticmethod
    def get_exec_audit_log() -> list:
        """Return a copy of the in-memory exec audit trail."""
        return list(_exec_audit_log)
