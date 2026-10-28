"""Regression tests for the production-main governance contract."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RULESET_PATH = ROOT / ".github" / "rulesets" / "production-main.json"
CODEOWNERS_PATH = ROOT / ".github" / "CODEOWNERS"

EXPECTED_CHECKS = {
    "Test (Python 3.11)",
    "Test (Python 3.12)",
    "Build Distribution",
    "Docker Build Check",
    "Dependency Review",
    "Python Syntax & React TypeScript Validation",
    "Analyze (actions)",
    "Analyze (javascript-typescript)",
    "Analyze (python)",
    "Build and Security Scan Docker Image",
    "Build security evidence",
    "Clean PostgreSQL backup restore rehearsal",
    "Local two-replica canary and failure rehearsal",
    "Base to candidate to immutable rollback",
    "Validate production GO evidence contract",
}


class ProductionMainRulesetContractTests(unittest.TestCase):
    def setUp(self):
        self.ruleset = json.loads(RULESET_PATH.read_text(encoding="utf-8"))
        self.rules = {rule["type"]: rule for rule in self.ruleset["rules"]}

    def test_ruleset_requires_independent_review_and_has_no_bypass(self):
        self.assertEqual(self.ruleset["enforcement"], "active")
        self.assertEqual(self.ruleset["bypass_actors"], [])
        pull_request = self.rules["pull_request"]["parameters"]
        self.assertGreaterEqual(pull_request["required_approving_review_count"], 1)
        self.assertTrue(pull_request["dismiss_stale_reviews_on_push"])
        self.assertTrue(pull_request["require_code_owner_review"])
        self.assertTrue(pull_request["require_last_push_approval"])
        self.assertTrue(pull_request["required_review_thread_resolution"])

    def test_required_status_checks_remain_complete_and_strict(self):
        parameters = self.rules["required_status_checks"]["parameters"]
        actual = {item["context"] for item in parameters["required_status_checks"]}
        self.assertTrue(EXPECTED_CHECKS.issubset(actual))
        self.assertTrue(parameters["strict_required_status_checks_policy"])
        self.assertFalse(parameters["do_not_enforce_on_create"])

    def test_codeowners_require_policedbc_for_all_changes(self):
        lines = CODEOWNERS_PATH.read_text(encoding="utf-8").splitlines()
        self.assertIn("* @policedbc", [line.strip() for line in lines])


if __name__ == "__main__":
    unittest.main()
