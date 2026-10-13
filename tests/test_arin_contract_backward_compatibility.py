"""Backward-compatibility regression tests for the supported ARIN v1 contract surface.

These tests intentionally lock the public schema shape that was admitted as v1.0.0.
Changes that remove required fields, widen fail-closed models, change discriminator enums,
or silently change the supported contract version must fail before release.
"""

import unittest

from scripts.generate_arin_contract_artifacts import build_openapi_components


SUPPORTED_VERSION = "1.0.0"
EXPECTED_REQUIRED = {
    "Goal": {"verb", "object"},
    "IntentCreateRequest": {"source_kind", "source_text", "goal", "requested_mode", "requested_risk_tier"},
    "SessionCreateRequest": {"api_key"},
    "SessionRenewRequest": {"session_id", "new_expires_at"},
    "SessionResponse": {"session_id", "access_token", "tenant_id", "principal_id", "scopes", "expires_at"},
    "PlanStep": {"tool_id"},
    "PlanCreateRequest": {"session_id", "task", "steps", "idempotency_key"},
    "ApprovalSubmitRequest": {"execution_id", "approval_id", "decision", "reason"},
    "ApprovalResponse": {"approval_id", "execution_id", "decision", "reason", "approver_id"},
}
EXPECTED_ENUMS = {
    ("Goal", "verb"): {"observe", "explain", "draft", "execute", "connect", "verify"},
    ("IntentCreateRequest", "source_kind"): {"text", "voice", "vision", "api", "sequence"},
    ("IntentCreateRequest", "requested_risk_tier"): {"R0", "R1", "R2", "R3", "R4", "R5"},
    ("ApprovalSubmitRequest", "decision"): {"approve", "reject"},
}


class ArinV1BackwardCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = build_openapi_components()
        cls.schemas = cls.artifact["components"]["schemas"]

    def test_supported_version_remains_v1_0_0(self):
        self.assertEqual(self.artifact["info"]["version"], SUPPORTED_VERSION)

    def test_supported_v1_models_remain_present(self):
        self.assertEqual(set(self.schemas), set(EXPECTED_REQUIRED))

    def test_required_v1_fields_are_not_removed(self):
        for model, required in EXPECTED_REQUIRED.items():
            with self.subTest(model=model):
                self.assertTrue(required.issubset(set(self.schemas[model].get("required", []))))

    def test_v1_models_remain_fail_closed(self):
        for model, schema in self.schemas.items():
            with self.subTest(model=model):
                self.assertIs(schema.get("additionalProperties"), False)

    def test_v1_discriminator_enums_do_not_drop_supported_values(self):
        for (model, field), expected in EXPECTED_ENUMS.items():
            with self.subTest(model=model, field=field):
                prop = self.schemas[model]["properties"][field]
                values = set(prop.get("enum", []))
                self.assertTrue(expected.issubset(values), f"{model}.{field} lost supported values: {expected - values}")

    def test_versioned_models_accept_only_supported_contract_version(self):
        for model in (
            "SessionCreateRequest",
            "SessionRenewRequest",
            "SessionResponse",
            "PlanStep",
            "PlanCreateRequest",
            "ApprovalSubmitRequest",
            "ApprovalResponse",
        ):
            with self.subTest(model=model):
                version = self.schemas[model]["properties"]["version"]
                self.assertEqual(version.get("const"), SUPPORTED_VERSION)

    def test_schema_artifact_remains_non_executable(self):
        self.assertEqual(self.artifact["paths"], {})


if __name__ == "__main__":
    unittest.main()
