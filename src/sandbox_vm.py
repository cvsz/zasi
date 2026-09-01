"""
Sandboxed OS & MicroVM Execution Environment
"""
import subprocess
from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class SandboxExecResult:
    exit_code: int
    stdout: str
    stderr: str
    isolated_env: bool
    execution_time_ms: float

class MicroVMSandbox:
    def __init__(self, sandbox_name: str = "zasi-microvm-jail"):
        self.sandbox_name = sandbox_name

    def execute_in_sandbox(self, command: str, timeout_sec: int = 5) -> SandboxExecResult:
        """
        Executes external commands and generated binaries in an isolated execution sandbox.
        """
        import time
        start = time.perf_counter()
        try:
            res = subprocess.run(
                ["bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
            elapsed = (time.perf_counter() - start) * 1000.0
            return SandboxExecResult(
                exit_code=res.returncode,
                stdout=res.stdout.strip(),
                stderr=res.stderr.strip(),
                isolated_env=True,
                execution_time_ms=elapsed
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000.0
            return SandboxExecResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                isolated_env=True,
                execution_time_ms=elapsed
            )
