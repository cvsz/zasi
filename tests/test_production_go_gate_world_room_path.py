import unittest
from datetime import datetime, timezone

from scripts.production_go_gate import GateError, REQUIRED_PRODUCTION_CHECKS, validate_evidence


COMMIT = "a" * 40
PREVIOUS_COMMIT = "d" * 40
CANDIDATE = "ghcr.io/cvsz/zasi@sha256:" + "b" * 64
PREVIOUS = "ghcr.io/cvsz/zasi@sha256:" + "c" * 64
NOW = datetime(2026, 9, 13, 1, 0, 0, tzinfo=timezone.utc)


def rulesets():
    return [{
        "id": 123,
        "name": "production-main",
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {"required_review_thread_resolution": True}},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [{"context": item} for item in sorted(REQUIRED_PRODUCTION_CHECKS)],
            }},
        ],
    }]


def evidence():
    return {
        "schema_version": 1,
        "candidate_commit": COMMIT,
        "previous_commit": PREVIOUS_COMMIT,
        "candidate_image": CANDIDATE,
        "previous_image": PREVIOUS,
        "staging_url": "https://staging.example.com",
        "observed_at": "2026-09-13T00:00:00Z",
        "runtime": {"status": "passed", "observed_at": "2026-09-12T23:40:00Z", "inspector": "docker", "observed_image": CANDIDATE},
        "health": {"status": "passed", "observed_at": "2026-09-12T23:45:00Z", "ready_url": "https://staging.example.com/health/ready", "observed_commit": COMMIT, "identity_source": "artifact"},
        "world_room": {"status": "passed", "observed_at": "2026-09-12T23:50:00Z", "smoke_case": "join, speak, receive realtime response", "endpoint_url": "https://staging.example.com/world-room", "image": CANDIDATE},
        "canary": {"status": "passed", "observed_at": "2026-09-12T23:55:00Z", "endpoint_url": "https://staging.example.com/health/ready", "image": CANDIDATE, "request_count": 100, "error_rate": 0.0, "p95_ms": 250},
        "rollback": {"status": "passed", "observed_at": "2026-09-13T00:00:00Z", "ready_url": "https://staging.example.com/health/ready", "image": PREVIOUS, "inspector": "docker", "observed_image": PREVIOUS, "observed_commit": PREVIOUS_COMMIT, "identity_source": "artifact", "world_room_endpoint_url": "https://staging.example.com/world-room", "world_room_smoke_case": "join, speak, receive realtime response after rollback", "world_room_status": "passed", "world_room_image": PREVIOUS, "duration_seconds": 45},
    }


class WorldRoomEndpointBindingTests(unittest.TestCase):
    def validate(self, item):
        return validate_evidence(item, expected_commit=COMMIT, rulesets=rulesets(), now=NOW)

    def test_candidate_world_room_cannot_reuse_readiness_endpoint(self):
        item = evidence()
        item["world_room"]["endpoint_url"] = "https://staging.example.com/health/ready"
        with self.assertRaisesRegex(GateError, "world_room.endpoint_url must target /world-room"):
            self.validate(item)

    def test_candidate_world_room_rejects_query_string(self):
        item = evidence()
        item["world_room"]["endpoint_url"] = "https://staging.example.com/world-room?status=passed"
        with self.assertRaisesRegex(GateError, "world_room.endpoint_url must not contain a query string"):
            self.validate(item)

    def test_rollback_world_room_cannot_reuse_readiness_endpoint(self):
        item = evidence()
        item["rollback"]["world_room_endpoint_url"] = "https://staging.example.com/health/ready"
        with self.assertRaisesRegex(GateError, "rollback.world_room_endpoint_url must target /world-room"):
            self.validate(item)

    def test_canonical_world_room_paths_remain_valid(self):
        self.assertEqual(self.validate(evidence())["decision"], "GO")


if __name__ == "__main__":
    unittest.main()
