from pathlib import Path
import re


WORKFLOW = Path(".github/workflows/ci.yml")
ACTION_LINE = re.compile(r"^\s*-?\s*uses:\s+")
IMMUTABLE_ACTION = re.compile(
    r"^\s*-?\s*uses:\s+[^\s@]+/[^\s@]+(?:/[^\s@]+)?@([0-9a-f]{40})(?:\s+#.*)?$"
)


def test_primary_ci_workflow_uses_immutable_action_refs() -> None:
    mutable = []
    action_count = 0
    for line_number, line in enumerate(WORKFLOW.read_text(encoding="utf-8").splitlines(), start=1):
        if not ACTION_LINE.match(line):
            continue
        action_count += 1
        if not IMMUTABLE_ACTION.match(line):
            mutable.append(f"{WORKFLOW}:{line_number}: {line.strip()}")

    assert action_count > 0, "Primary CI workflow must contain third-party action invocations"
    assert not mutable, "Primary CI workflow contains mutable action refs:\n" + "\n".join(mutable)
