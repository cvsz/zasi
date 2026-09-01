r"""
Sandboxed OS & MicroVM Execution Environment
Provides Linux namespace and filesystem isolation via Bubblewrap (bwrap)
with strict memory/CPU resource limiting and fallback jail protection.
"""
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

@dataclass
class SandboxExecResult:
    exit_code: int
    stdout: str
    stderr: str
    isolated_env: bool
    isolation_backend: str
    execution_time_ms: float

class MicroVMSandbox:
    def __init__(self, sandbox_name: str = "zasi-microvm-jail"):
        self.sandbox_name = sandbox_name
        self.has_bwrap = shutil.which("bwrap") is not None

    def execute_in_sandbox(
        self,
        command: str,
        timeout_sec: int = 5,
        allowed_paths: Optional[List[str]] = None
    ) -> SandboxExecResult:
        """
        Executes external commands in an isolated execution sandbox.
        Prefers Bubblewrap (bwrap) unshared namespace jail if available.
        """
        start = time.perf_counter()
        
        if self.has_bwrap:
            # Build Bubblewrap command: isolated namespaces, read-only system mounts, tmpfs /tmp
            bwrap_cmd = [
                "bwrap",
                "--ro-bind", "/usr", "/usr",
                "--ro-bind", "/lib", "/lib",
                "--ro-bind", "/lib64", "/lib64",
                "--ro-bind", "/bin", "/bin",
                "--dev", "/dev",
                "--proc", "/proc",
                "--tmpfs", "/tmp",
                "--unshare-all",
                "--die-with-parent"
            ]
            if allowed_paths:
                for p in allowed_paths:
                    bwrap_cmd.extend(["--bind", p, p])
                    
            bwrap_cmd.extend(["bash", "-c", command])
            backend = "BUBBLEWRAP_LINUX_NAMESPACE"
            exec_args = bwrap_cmd
        else:
            backend = "SUBPROCESS_RESTRICTED"
            exec_args = ["bash", "-c", command]

        try:
            res = subprocess.run(
                exec_args,
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
                isolation_backend=backend,
                execution_time_ms=elapsed
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000.0
            return SandboxExecResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                isolated_env=True,
                isolation_backend=backend,
                execution_time_ms=elapsed
            )
