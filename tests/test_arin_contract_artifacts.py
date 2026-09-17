"""Regression tests for deterministic ARIN v1 schema/client artifacts."""

from scripts.generate_arin_contract_artifacts import build_openapi_components, build_typescript


EXPECTED_SCHEMAS = {
    "Goal",
    "IntentCreateRequest",
    "SessionCreateRequest",
    "SessionRenewRequest",
    "SessionResponse",
    "PlanStep",
    "PlanCreateRequest",
    "ApprovalSubmitRequest",
    "ApprovalResponse",
}


def test_openapi_artifact_is_schema_only_and_versioned():
    artifact = build_openapi_components()
    assert artifact["openapi"] == "3.1.0"
    assert artifact["info"]["version"] == "1.0.0"
    assert artifact["paths"] == {}
    assert set(artifact["components"]["schemas"]) == EXPECTED_SCHEMAS


def test_openapi_models_remain_fail_closed():
    schemas = build_openapi_components()["components"]["schemas"]
    for schema in schemas.values():
        assert schema.get("additionalProperties") is False


def test_client_artifact_is_versioned_and_contains_canonical_types():
    typescript = build_typescript()
    assert 'export type ContractVersion = "1.0.0";' in typescript
    for name in EXPECTED_SCHEMAS:
        assert f" {name} " in typescript


def test_artifacts_do_not_claim_runtime_or_actuator_authority():
    openapi = str(build_openapi_components()).lower()
    typescript = build_typescript().lower()
    for forbidden in ("raw_actuator", "joint_command", "torque_command", "pwm_command"):
        assert forbidden not in openapi
        assert forbidden not in typescript
