import unittest
from datetime import datetime, timezone

from scripts.production_go_gate import GateError, REQUIRED_PRODUCTION_CHECKS, validate_evidence


COMMIT = "a" * 40
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
                "required_status_checks": [
                    {"context": context}
                    for context in sorted(REQUIRED_PRODUCTION_CHECKS)
                ],
            }},
        ],
    }]


def evidence():
    return {
        "schema_version": 1,
        "candidate_commit": COMMIT,
        "candidate_image": CANDIDATE,
        "previous_image": PREVIOUS,
        "staging_url": "https://staging.example.com",
        "observed_at": "2026-09-13T00:00:00Z",
        "health": {
            "status": "passed",
            "ready_url": "https://staging.example.com/health/ready",
            "observed_commit": COMMIT,
            "observed_image": CANDIDATE,
        },
        "world_room": {
            "status": "passed",
            "smoke_case": "join, speak, receive realtime response",
            "endpoint_url": "https://staging.example.com/world-room",
            "image": CANDIDATE,
        },
        "canary": {
            "status": "passed",
            "endpoint_url": "https://staging.example.com/health/ready",
            "image": CANDIDATE,
            "request_count": 100,
            "error_rate": 0.0,
            "p95_ms": 250,
        },
        "rollback": {
            "status": "passed",
            "endpoint_url": "https://staging.example.com/health/ready",
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
            rulesets=kwargs.pop("rulesets", rulesets()),
            now=kwargs.pop("now", NOW),
            **kwargs,
        )

    def test_valid_external_evidence_is_go(self):
        result = self.validate(evidence())
        self.assertEqual(result["decision"], "GO")
        self.assertEqual(result["checks"]["main_governance"], "passed")
        self.assertEqual(
            result["governance"]["required_production_checks"],
            sorted(REQUIRED_PRODUCTION_CHECKS),
        )

    def test_explicit_default_https_port_is_same_origin(self):
        item = evidence()
        item["health"]["ready_url"] = "https://staging.example.com:443/health/ready"
        item["world_room"]["endpoint_url"] = "https://staging.example.com:443/world-room"
        item["canary"]["endpoint_url"] = "https://staging.example.com:443/health/ready"
        item["rollback"]["endpoint_url"] = "https://staging.example.com:443/health/ready"
        result = self.validate(item)
        self.assertEqual(result["decision"], "GO")

    def test_nondefault_port_is_different_origin(self):
        item = evidence()
        item["canary"]["endpoint_url"] = "https://staging.example.com:8443/health/ready"
        with self.assertRaisesRegex(GateError, "same origin"):
            self.validate(item)

    def test_invalid_url_port_is_rejected(self):
        item = evidence()
        item["canary"]["endpoint_url"] = "https://staging.example.com:notaport/health/ready"
        with self.assertRaisesRegex(GateError, "invalid port"):
            self.validate(item)

    def test_malformed_url_is_rejected_as_gate_error(self):
        item = evidence()
        item["canary"]["endpoint_url"] = "https://[broken"
        with self.assertRaisesRegex(GateError, "valid URL"):
            self.validate(item)

    def test_missing_ruleset_is_no_go(self):
        with self.assertRaisesRegex(GateError, "no active GitHub ruleset"):
            self.validate(evidence(), rulesets=[])

    def test_ruleset_must_require_pull_requests(self):
        item = rulesets()
        item[0]["rules"] = [rule for rule in item[0]["rules"] if rule["type"] != "pull_request"]
        with self.assertRaisesRegex(GateError, "missing rules"):
            self.validate(evidence(), rulesets=item)

    def test_ruleset_must_resolve_review_threads(self):
        item = rulesets()
        item[0]["rules"][2]["parameters"]["required_review_thread_resolution"] = False
        with self.assertRaisesRegex(GateError, "review-thread resolution"):
            self.validate(evidence(), rulesets=item)

    def test_ruleset_must_block_force_push_and_deletion(self):
        item = rulesets()
        item[0]["rules"] = [rule for rule in item[0]["rules"] if rule["type"] not in {"deletion", "non_fast_forward"}]
        with self.assertRaisesRegex(GateError, "missing rules"):
            self.validate(evidence(), rulesets=item)

    def test_ruleset_must_require_full_production_check_set(self):
        item = rulesets()
        checks = item[0]["rules"][3]["parameters"]["required_status_checks"]
        item[0]["rules"][3]["parameters"]["required_status_checks"] = [
            check for check in checks if check["context"] != "Build security evidence"
        ]
        with self.assertRaisesRegex(GateError, "missing required production checks"):
            self.validate(evidence(), rulesets=item)

    def test_ruleset_must_require_strict_status_checks(self):
        item = rulesets()
        item[0]["rules"][3]["parameters"]["strict_required_status_checks_policy"] = False
        with self.assertRaisesRegex(GateError, "up to date"):
            self.validate(evidence(), rulesets=item)

    def test_ruleset_bypass_is_rejected(self):
        item = rulesets()
        item[0]["bypass_actors"] = [{"actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "always"}]
        with self.assertRaisesRegex(GateError, "bypass actors"):
            self.validate(evidence(), rulesets=item)

    def test_commit_must_match_release(self):
        with self.assertRaisesRegex(GateError, "does not match"):
            self.validate(evidence(), expected_commit="d" * 40)

    def test_mutable_image_reference_is_rejected(self):
        item = evidence()
        item["candidate_image"] = "ghcr.io/cvsz/zasi:latest"
        with self.assertRaisesRegex(GateError, "immutable GHCR"):
            self.validate(item)

    def test_health_must_use_staging_origin(self):
        item = evidence()
        item["health"]["ready_url"] = "https://other.example.com/health/ready"
        with self.assertRaisesRegex(GateError, "same origin"):
            self.validate(item)

    def test_health_must_target_canonical_readiness_path(self):
        item = evidence()
        item["health"]["ready_url"] = "https://staging.example.com/health"
        with self.assertRaisesRegex(GateError, "/health/ready"):
            self.validate(item)

    def test_health_must_observe_candidate_commit(self):
        item = evidence()
        item["health"]["observed_commit"] = "d" * 40
        with self.assertRaisesRegex(GateError, "health.observed_commit"):
            self.validate(item)

    def test_health_must_observe_candidate_digest(self):
        item = evidence()
        item["health"]["observed_image"] = PREVIOUS
        with self.assertRaisesRegex(GateError, "health.observed_image"):
            self.validate(item)

    def test_self_asserted_health_image_does_not_replace_observed_identity(self):
        item = evidence()
        del item["health"]["observed_image"]
        item["health"]["image"] = CANDIDATE
        with self.assertRaisesRegex(GateError, "health.observed_image"):
            self.validate(item)

    def test_world_room_must_bind_to_staging_origin(self):
        item = evidence()
        item["world_room"]["endpoint_url"] = "https://other.example.com/world-room"
        with self.assertRaisesRegex(GateError, "same origin"):
            self.validate(item)

    def test_world_room_must_prove_candidate_digest(self):
        item = evidence()
        item["world_room"]["image"] = PREVIOUS
        with self.assertRaisesRegex(GateError, "world_room.image"):
            self.validate(item)

    def test_canary_must_bind_to_staging_origin(self):
        item = evidence()
        item["canary"]["endpoint_url"] = "https://other.example.com/health/ready"
        with self.assertRaisesRegex(GateError, "same origin"):
            self.validate(item)

    def test_canary_must_prove_candidate_digest(self):
        item = evidence()
        item["canary"]["image"] = PREVIOUS
        with self.assertRaisesRegex(GateError, "canary.image"):
            self.validate(item)

    def test_rollback_must_bind_to_staging_origin(self):
        item = evidence()
        item["rollback"]["endpoint_url"] = "https://other.example.com/health/ready"
        with self.assertRaisesRegex(GateError, "same origin"):
            self.validate(item)

    def test_url_credentials_are_rejected(self):
        item = evidence()
        item["staging_url"] = "https://user:secret@staging.example.com"
        with self.assertRaisesRegex(GateError, "URL credentials"):
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
