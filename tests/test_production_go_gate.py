import unittest
from copy import deepcopy
from datetime import datetime, timezone

from scripts.production_go_gate import GateError, validate_evidence


COMMIT = "a" * 40
CANDIDATE = "ghcr.io/cvsz/zasi@sha256:" + "b" * 64
PREVIOUS = "ghcr.io/cvsz/zasi@sha256:" + "c" * 64
NOW = datetime(2026, 9, 13, 1, 0, 0, tzinfo=timezone.utc)


def evidence():
    return {
        "schema_version": 1,
        "candidate_commit": COMMIT,
        "candidate_image": CANDIDATE,
        "previous_image": PREVIOUS,
        "staging_url": "https://staging.example.com",
        "observed_at": "2026-09-13T00:00:00Z",
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
    def validate(self, item, **kwargs):
        return validate_evidence(
            item,
            expected_commit=kwargs.pop("expected_commit", COMMIT),
            main_protected=kwargs.pop("main_protected", True),
            now=kwargs.pop("now", NOW),
            **kwargs,
        )

    def test_valid_external_evidence_is_go(self):
        result = self.validate(evidence())
        self.assertEqual(result["decision"], "GO")
        self.assertEqual(result["checks"]["freshness"], "passed")

    def test_unprotected_main_is_no_go(self):
        with self.assertRaisesRegex(GateError, "not protected"):
            self.validate(evidence(), main_protected=False)

    def test_commit_must_match_release(self):
        with self.assertRaisesRegex(GateError, "does not match"):
            self.validate(evidence(), expected_commit="d" * 40)

    def test_mutable_image_reference_is_rejected(self):
        item = evidence()
        item["candidate_image"] = "ghcr.io/cvsz/zasi:latest"
        with self.assertRaisesRegex(GateError, "immutable GHCR"):
            self.validate(item)

    def test_failed_world_room_is_rejected(self):
        item = evidence()
        item["world_room"]["status"] = "failed"
        with self.assertRaisesRegex(GateError, "world_room.status"):
            self.validate(item)

    def test_canary_thresholds_fail_closed(self):
        item = evidence()
        item["canary"]["error_rate"] = 0.02
        with self.assertRaisesRegex(GateError, "error_rate"):
            self.validate(item)

    def test_rollback_must_use_previous_digest(self):
        item = evidence()
        item["rollback"]["image"] = CANDIDATE
        with self.assertRaisesRegex(GateError, "rollback.image"):
            self.validate(item)

    def test_boolean_is_not_accepted_as_numeric_evidence(self):
        item = evidence()
        item["canary"]["request_count"] = True
        with self.assertRaisesRegex(GateError, "request_count"):
            self.validate(item)

    def test_stale_evidence_is_rejected(self):
        item = evidence()
        item["observed_at"] = "2026-09-12T18:59:59Z"
        with self.assertRaisesRegex(GateError, "stale"):
            self.validate(item)

    def test_six_hour_old_evidence_is_still_valid(self):
        item = evidence()
        item["observed_at"] = "2026-09-12T19:00:00Z"
        result = self.validate(item)
        self.assertEqual(result["decision"], "GO")

    def test_future_evidence_is_rejected(self):
        item = evidence()
        item["observed_at"] = "2026-09-13T01:00:01Z"
        with self.assertRaisesRegex(GateError, "future"):
            self.validate(item)


if __name__ == "__main__":
    unittest.main()
