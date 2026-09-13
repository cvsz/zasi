import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITICAL_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "release.yml",
    ROOT / ".github" / "workflows" / "publish.yml",
)
USES_RE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ReleaseWorkflowSupplyChainTests(unittest.TestCase):
    def test_release_critical_actions_are_immutable_sha_pinned(self):
        failures = []
        for workflow in CRITICAL_WORKFLOWS:
            text = workflow.read_text(encoding="utf-8")
            for action in USES_RE.findall(text):
                if action.startswith("./") or action.startswith("docker://"):
                    continue
                if "@" not in action:
                    failures.append(f"{workflow.name}: missing ref for {action}")
                    continue
                name, ref = action.rsplit("@", 1)
                if not FULL_SHA_RE.fullmatch(ref):
                    failures.append(
                        f"{workflow.name}: {name} must use a 40-character commit SHA, got {ref!r}"
                    )
        self.assertEqual(failures, [], "\n".join(failures))

    def test_pypi_publish_is_bound_to_successful_release_workflow(self):
        text = (ROOT / ".github" / "workflows" / "publish.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository", text)
        self.assertIn("ref: ${{ github.event.workflow_run.head_sha }}", text)


if __name__ == "__main__":
    unittest.main()
