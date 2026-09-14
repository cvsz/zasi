import json
from pathlib import Path

from scripts.production_go_gate import validate_governance


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_main_ruleset_satisfies_production_go_governance_policy():
    manifest = json.loads(
        (ROOT / ".github" / "rulesets" / "production-main.json").read_text(encoding="utf-8")
    )

    result = validate_governance([manifest])

    assert result["status"] == "passed"
    assert result["ruleset_name"] == "production-main"
    assert result["required_check_count"] >= 15
