import unittest
from copy import deepcopy

from scripts.production_go_gate import GateError, validate_evidence


COMMIT = "a" * 40
CANDIDATE = "ghcr.io/cvsz/zasi@sha256:" + "b" * 64
PREVIOUS = "ghcr.io/cvsz/zasi@sha256:" + "c" * 64


def evidence():
    return {
        "schema_version": 1,
        "candidate_commit": COMMIT,
        "candidate_image": CANDIDATE,
        "previous_image": PREVIOUS,
        "staging_url": "https://staging.example.com",
        "observed_at": "2026-09-01T00:00:00Z",
        "health": {"status": "passed", "ready_url": "https://staging.example.com/health/ready"},
        "world_room": {"status": "passed", "smoke_case": "join, speak, receive realtime response"},
        "canary": {"status": "passed", "request_count": 100, "error_rate": 0.0, "p95_ms": 250},
        "rollback": {
            "status": "passed",
            "image": PREVIOUS,
            "health_status": "passed",
            "world_room_status": "passed",
            "duration_seconds": 45,
        },
    }


class ProductionGoGateTests(unittest.TestCase):
    def test_valid_external_evidence_is_go(self):
        result = validate_evidence(evidence(), expected_commit=COMMIT, main_protected=True)
        self.assertEqual(result["decision"], "GO")

    def test_unprotected_main_is_no_go(self):
        with self.assertRaisesRegex(GateError, "not protected"):
            validate_evidence(evidence(), expected_commit=COMMIT, main_protected=False)

    def test_commit_must_match_release(self):
        with self.assertRaisesRegex(GateError, "does not match"):
            validate_evidence(evidence(), expected_commit="d" * 40, main_protected=True)

    def test_mutable_image_reference_is_rejected(self):
        item = evidence()
        item["candidate_image"] = "ghcr.io/cvsz/zasi:latest"
        with self.assertRaisesRegex(GateError, "immutable GHCR"):
            validate_evidence(item, expected_commit=COMMIT, main_protected=True)

    def test_failed_world_room_is_rejected(self):
        item = evidence()
        item["world_room"]["status"] = "failed"
        with self.assertRaisesRegex(GateError, "world_room.status"):
            validate_evidence(item, expected_commit=COMMIT, main_protected=True)

    def test_canary_thresholds_fail_closed(self):
        item = evidence()
        item["canary"]["error_rate"] = 0.02
        with self.assertRaisesRegex(GateError, "error_rate"):
            validate_evidence(item, expected_commit=COMMIT, main_protected=True)

    def test_rollback_must_use_previous_digest(self):
        item = evidence()
        item["rollback"]["image"] = CANDIDATE
        with self.assertRaisesRegex(GateError, "rollback.image"):
            validate_evidence(item, expected_commit=COMMIT, main_protected=True)

    def test_boolean_is_not_accepted_as_numeric_evidence(self):
        item = evidence()
        item["canary"]["request_count"] = True
        with self.assertRaisesRegex(GateError, "request_count"):
            validate_evidence(item, expected_commit=COMMIT, main_protected=True)


if __name__ == "__main__":
    unittest.main()
