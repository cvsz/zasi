from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parent / "corpus"


class ReferenceCorpusTests(unittest.TestCase):
    def load(self, relative: str) -> dict:
        payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        self.assertEqual(payload.get("schema_version"), 1)
        return payload

    def test_analyzer_cases_are_unique_and_actionable(self) -> None:
        data = self.load("analyzer/reference_cases.json")
        ids = [case["id"] for case in data["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        for case in data["cases"]:
            self.assertIn(case["expected"]["severity"], {"none", "low", "medium", "high", "critical"})
            self.assertIsInstance(case["expected"]["findings"], list)

    def test_rag_cases_define_complete_rankings(self) -> None:
        data = self.load("rag/ranking_cases.json")
        for case in data["cases"]:
            document_ids = [doc["id"] for doc in case["documents"]]
            self.assertEqual(sorted(document_ids), sorted(case["expected_order"]))
            self.assertEqual(len(document_ids), len(set(document_ids)))

    def test_pr_salvage_actions_are_closed_set(self) -> None:
        data = self.load("pr_salvage/reference_cases.json")
        allowed = {"salvage-review", "repair-before-merge", "block-merge", "re-review"}
        for case in data["cases"]:
            self.assertIn(case["expected_action"], allowed)

    def test_discussion_triage_classes_are_covered(self) -> None:
        data = self.load("discussion_triage/reference_cases.json")
        classes = {case["expected_class"] for case in data["cases"]}
        self.assertEqual(classes, {"informational", "answered", "no-response"})

    def test_harness_matrix_covers_required_surfaces(self) -> None:
        data = self.load("harness/compatibility.json")
        names = {entry["name"] for entry in data["harnesses"]}
        self.assertTrue({"claude", "codex", "opencode", "zed", "dmux"}.issubset(names))
        self.assertTrue(data["required_capabilities"])
        for entry in data["harnesses"]:
            self.assertEqual(entry["expected"], "compatible")

    def test_ci_failure_modes_include_security_governance_and_dr(self) -> None:
        data = self.load("ci_failure_modes/reference_cases.json")
        classifications = {case["expected"]["classification"] for case in data["cases"]}
        self.assertTrue({"security-gate", "governance-gap", "dr-blocker"}.issubset(classifications))


if __name__ == "__main__":
    unittest.main()
