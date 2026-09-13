from pathlib import Path
import re


WORKFLOW = Path(".github/workflows/ci.yml")
IMMUTABLE_ACTION = re.compile(r"^\s*uses:\s+[^\s@]+/[^\s@]+(?:/[^\s@]+)?@([0-9a-f]{40})(?:\s+#.*)?$")


def test_primary_ci_workflow_uses_immutable_action_refs() -> None:
    mutable = []
    for line_number, line in enumerate(WORKFLOW.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("uses:"):
            continue
        if not IMMUTABLE_ACTION.match(line):
            mutable.append(f"{WORKFLOW}:{line_number}: {stripped}")

    assert not mutable, "Primary CI workflow contains mutable action refs:\n" + "\n".join(mutable)
