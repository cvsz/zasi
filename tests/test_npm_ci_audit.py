import json
import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "npm_ci_audit.sh"


class NpmCiAuditTests(unittest.TestCase):
    def _run_fake_npm(self, payload, *, exit_code=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_npm = fake_bin / "npm"
            payload_text = shlex.quote(json.dumps(payload))
            fake_npm.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -eu
                    printf '%s\\n' {payload_text}
                    exit {exit_code}
                    """
                ),
                encoding="utf-8",
            )
            fake_npm.chmod(0o700)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            return subprocess.run(
                [str(SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

    def test_zero_vulnerability_install_audit_passes(self):
        result = self._run_fake_npm(
            {
                "audited": 319,
                "audit": {
                    "vulnerabilities": {
                        "info": 0,
                        "low": 0,
                        "moderate": 0,
                        "high": 0,
                        "critical": 0,
                    }
                },
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0 vulnerabilities", result.stderr)

    def test_vulnerability_install_audit_fails_closed(self):
        result = self._run_fake_npm(
            {
                "audited": 319,
                "audit": {
                    "vulnerabilities": {
                        "info": 0,
                        "low": 0,
                        "moderate": 1,
                        "high": 0,
                        "critical": 0,
                    }
                },
            }
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("vulnerability finding", result.stderr)

    def test_missing_audit_metadata_fails_closed(self):
        result = self._run_fake_npm({"audited": 319})

        self.assertEqual(result.returncode, 1)
        self.assertIn("did not emit audit vulnerability metadata", result.stderr)

    def test_install_failure_does_not_infer_audit_result(self):
        result = self._run_fake_npm({}, exit_code=1)

        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to infer", result.stderr)


if __name__ == "__main__":
    unittest.main()
