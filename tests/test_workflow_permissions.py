"""Regression tests for least-privilege GitHub Actions defaults."""

from pathlib import Path
import unittest


WORKFLOW_DIR = Path(__file__).parents[1] / ".github" / "workflows"


def _top_level_permissions_block(workflow: str) -> str:
    lines = workflow.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line == "permissions:")
    except StopIteration:
        return ""

    block = [lines[start]]
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        block.append(line)
    return "\n".join(block)


class WorkflowPermissionTests(unittest.TestCase):
    def test_every_workflow_declares_top_level_contents_read_baseline(self):
        workflows = sorted(WORKFLOW_DIR.glob("*.y*ml"))
        self.assertTrue(workflows)

        for path in workflows:
            block = _top_level_permissions_block(path.read_text(encoding="utf-8"))
            with self.subTest(workflow=path.name):
                self.assertIn("permissions:", block)
                self.assertIn("  contents: read", block)

    def test_node_workflows_use_the_declared_electron_engine_and_bounded_audit(self):
        for name in ("ci.yml", "lint.yml", "pages.yml", "release.yml", "npm-publish.yml"):
            path = WORKFLOW_DIR / name
            workflow = path.read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertIn('node-version: "22.14.0"', workflow)

        ci = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("actions/dependency-review-action@v4", ci)
        self.assertIn("npm ci --ignore-scripts --no-audit", ci)
        install_audit_script = Path(__file__).parents[1] / "scripts" / "npm_ci_audit.sh"
        self.assertIn("npm_bulk_audit.mjs", install_audit_script.read_text(encoding="utf-8"))
        audit_script = Path(__file__).parents[1] / "scripts" / "npm_audit_retry.sh"
        self.assertIn("npm_bulk_audit.mjs", audit_script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
