from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parent / "corpus"


class ReferenceCorpusEvidenceTests(unittest.TestCase):
    def load(self, relative: str) -> dict:
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_every_corpus_declares_versioned_evidence_contract(self) -> None:
        paths = [
            "analyzer/reference_cases.json",
            "rag/ranking_cases.json",
            "pr_salvage/reference_cases.json",
            "discussion_triage/reference_cases.json",
            "harness/compatibility.json",
            "ci_failure_modes/reference_cases.json",
        ]
        for relative in paths:
            with self.subTest(relative=relative):
                payload = self.load(relative)
                evidence = payload["evidence_contract"]
                self.assertEqual(evidence["version"], 1)
                self.assertTrue(evidence["runner"])
                self.assertTrue(evidence["deterministic"])
                self.assertTrue(evidence["required_assertions"])

    def test_rag_contract_has_explicit_ranking_threshold(self) -> None:
        evidence = self.load("rag/ranking_cases.json")["evidence_contract"]
        self.assertEqual(evidence["metric"], "exact-order")
        self.assertEqual(evidence["minimum_score"], 1.0)

    def test_harness_contract_requires_all_declared_capabilities(self) -> None:
        payload = self.load("harness/compatibility.json")
        evidence = payload["evidence_contract"]
        self.assertEqual(evidence["metric"], "required-capability-coverage")
        self.assertEqual(evidence["minimum_score"], 1.0)
        self.assertIn("agent", {value.lower() for value in payload["required_capabilities"]})

    def test_ci_failure_contract_forbids_sensitive_fixture_data(self) -> None:
        evidence = self.load("ci_failure_modes/reference_cases.json")["evidence_contract"]
        self.assertTrue(evidence["redaction_required"])
        self.assertEqual(
            set(evidence["forbidden_fixture_data"]),
            {"credentials", "tokens", "secrets", "pii"},
        )


if __name__ == "__main__":
    unittest.main()
