import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "npm_audit_retry.sh"


class NpmAuditRetryTests(unittest.TestCase):
    def _run_fake_npm(self, output: str, exit_code: int, *, attempts: int = 3):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            counter = root / "counter"
            fake_npm = fake_bin / "npm"
            fake_npm.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -eu
                    count=0
                    if [ -f "{counter}" ]; then count=$(cat "{counter}"); fi
                    count=$((count + 1))
                    printf '%s' "$count" > "{counter}"
                    {output}
                    exit {exit_code}
                    """
                ),
                encoding="utf-8",
            )
            fake_npm.chmod(0o700)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            environment["ZASI_NPM_AUDIT_ATTEMPTS"] = str(attempts)
            environment["ZASI_NPM_AUDIT_RETRY_DELAY_SECONDS"] = "0"
            result = subprocess.run(
                [str(SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            count = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
            return result, count

    def test_transient_registry_failure_is_retried_and_can_pass(self):
        result, count = self._run_fake_npm(
            "if [ \"$count\" -lt 3 ]; then echo 'npm warn audit 503 Service Unavailable' >&2; echo 'npm error audit endpoint returned an error' >&2; exit 1; fi; echo 'found 0 vulnerabilities'",
            0,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(count, 3)
        self.assertIn("found 0 vulnerabilities", result.stdout)

    def test_vulnerability_failure_is_not_retried(self):
        result, count = self._run_fake_npm(
            "echo '1 moderate vulnerability found' >&2",
            1,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(count, 1)
        self.assertIn("refusing to retry", result.stderr)

    def test_exhausted_transient_failure_is_not_a_pass(self):
        result, count = self._run_fake_npm(
            "echo 'npm warn audit 503 Service Unavailable' >&2",
            1,
            attempts=2,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(count, 2)
        self.assertIn("did not complete", result.stderr)


if __name__ == "__main__":
    unittest.main()
