import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "npm_ci_audit.sh"


class NpmCiAuditTests(unittest.TestCase):
    def _run_with_stubs(self, *, npm_status=0, node_status=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            npm_args = root / "npm.args"
            node_args = root / "node.args"
            (fake_bin / "npm").write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -eu
                    printf '%s\\n' "$@" > {npm_args}
                    exit {npm_status}
                    """
                ),
                encoding="utf-8",
            )
            (fake_bin / "node").write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -eu
                    printf '%s\\n' "$@" > {node_args}
                    exit {node_status}
                    """
                ),
                encoding="utf-8",
            )
            (fake_bin / "npm").chmod(0o700)
            (fake_bin / "node").chmod(0o700)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            result = subprocess.run(
                [str(SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            npm_invocation = npm_args.read_text(encoding="utf-8").splitlines() if npm_args.exists() else None
            node_invocation = node_args.read_text(encoding="utf-8").splitlines() if node_args.exists() else None
            return result, npm_invocation, node_invocation

    def test_install_disables_npm_audit_and_runs_bulk_audit(self):
        result, npm_args, node_args = self._run_with_stubs()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(npm_args, ["ci", "--ignore-scripts", "--no-audit"])
        self.assertEqual(node_args, ["scripts/npm_bulk_audit.mjs"])

    def test_install_failure_stops_before_bulk_audit(self):
        result, npm_args, node_args = self._run_with_stubs(npm_status=1)

        self.assertEqual(result.returncode, 1)
        self.assertIsNotNone(npm_args)
        self.assertIsNone(node_args)

    def test_bulk_audit_failure_is_returned(self):
        result, npm_args, node_args = self._run_with_stubs(node_status=1)

        self.assertEqual(result.returncode, 1)
        self.assertIsNotNone(npm_args)
        self.assertIsNotNone(node_args)


if __name__ == "__main__":
    unittest.main()
