import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NpmAuditEntrypointTests(unittest.TestCase):
    def test_compatibility_entrypoint_uses_bulk_advisory_audit(self):
        script = (ROOT / "scripts" / "npm_audit_retry.sh").read_text(encoding="utf-8")

        self.assertIn("node scripts/npm_bulk_audit.mjs", script)
        self.assertNotIn("npm audit", script)

    def test_install_entrypoint_disables_retired_npm_audit_fallback(self):
        script = (ROOT / "scripts" / "npm_ci_audit.sh").read_text(encoding="utf-8")

        self.assertIn("npm ci --ignore-scripts --no-audit", script)
        self.assertIn("node scripts/npm_bulk_audit.mjs", script)


if __name__ == "__main__":
    unittest.main()
