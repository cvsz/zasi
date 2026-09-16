"""ARIN Task 4 — Versioned contract tests for Session, Plan, Approval.

These tests verify that versioned contracts:
1. Accept valid v1.0.0 payloads with correct fields.
2. Reject incompatible payloads fail-closed:
   - Unknown keys (extra="forbid")
   - Missing required fields
   - Invalid enum values
   - Invalid version strings
   - Pattern mismatches
3. All contracts carry a version field for forward compatibility.
"""
import unittest

from pydantic import ValidationError

from src.control_plane.contracts import (
    ApprovalDecision,
    ApprovalResponse,
    ApprovalSubmitRequest,
    Goal,
    GoalVerb,
    IntentCreateRequest,
    Mode,
    PlanCreateRequest,
    PlanStep,
    PlanStatus,
    RiskTier,
    SessionCreateRequest,
    SessionRenewRequest,
    SessionResponse,
    SessionStatus,
    VersionedModel,
)


class VersionedModelTests(unittest.TestCase):
    """All versioned models carry version v1.0.0 by default."""

    def test_versioned_model_has_default_version(self):
        m = SessionCreateRequest(api_key="test-key")
        self.assertEqual(m.version, "1.0.0")

    def test_versioned_model_accepts_explicit_version(self):
        m = SessionCreateRequest(api_key="test-key", version="1.0.0")
        self.assertEqual(m.version, "1.0.0")

    def test_versioned_model_rejects_other_versions(self):
        with self.assertRaises(ValidationError):
            SessionCreateRequest(api_key="test-key", version="2.0.0")

    def test_strict_model_rejects_unknown_keys(self):
        with self.assertRaises(ValidationError):
            Goal.model_validate({"verb": "observe", "object": "test", "rogue": True})


class SessionContractTests(unittest.TestCase):
    """Session v1.0.0 contract validation."""

    def test_session_create_accepts_valid(self):
        req = SessionCreateRequest.model_validate({"api_key": "secret-token"})
        self.assertEqual(req.api_key, "secret-token")
        self.assertEqual(req.version, "1.0.0")

    def test_session_create_rejects_missing_api_key(self):
        with self.assertRaises(ValidationError):
            SessionCreateRequest.model_validate({})

    def test_session_create_rejects_empty_api_key(self):
        with self.assertRaises(ValidationError):
            SessionCreateRequest.model_validate({"api_key": ""})

    def test_session_create_rejects_unknown_keys(self):
        with self.assertRaises(ValidationError):
            SessionCreateRequest.model_validate(
                {"api_key": "token", "extra_field": True}
            )

    def test_session_renew_accepts_valid(self):
        req = SessionRenewRequest.model_validate({
            "session_id": "ses-abc",
            "new_expires_at": "2026-12-31T23:59:59Z",
            "version": "1.0.0",
        })
        self.assertEqual(req.session_id, "ses-abc")

    def test_session_renew_rejects_invalid_timestamp(self):
        with self.assertRaises(ValidationError):
            SessionRenewRequest.model_validate({
                "session_id": "ses-abc",
                "new_expires_at": "not-a-date",
            })

    def test_session_response_accepts_valid(self):
        resp = SessionResponse.model_validate({
            "session_id": "ses-abc",
            "access_token": "tok",
            "token_type": "Bearer",
            "tenant_id": "local",
            "principal_id": "local-op",
            "scopes": ["workspace:read"],
            "expires_at": "2026-12-31T23:59:59Z",
            "version": "1.0.0",
        })
        self.assertEqual(resp.status, "active")
        self.assertEqual(resp.token_type, "Bearer")


class PlanContractTests(unittest.TestCase):
    """Plan v1.0.0 contract validation."""

    def test_plan_step_accepts_valid(self):
        step = PlanStep.model_validate({
            "tool_id": "knowledge.search",
            "arguments": {"query": "test"},
            "risk_tier": "R0",
            "version": "1.0.0",
        })
        self.assertEqual(step.tool_id, "knowledge.search")

    def test_plan_step_rejects_invalid_tool_id(self):
        with self.assertRaises(ValidationError):
            PlanStep.model_validate({"tool_id": "UPPERCASE", "version": "1.0.0"})

    def test_plan_step_rejects_invalid_risk_tier(self):
        with self.assertRaises(ValidationError):
            PlanStep.model_validate({
                "tool_id": "knowledge.search",
                "risk_tier": "R99",
                "version": "1.0.0",
            })

    def test_plan_step_rejects_missing_tool_id(self):
        with self.assertRaises(ValidationError):
            PlanStep.model_validate({"version": "1.0.0"})

    def test_plan_create_accepts_valid(self):
        req = PlanCreateRequest.model_validate({
            "session_id": "ses-abc",
            "task": "search for test",
            "steps": [{"tool_id": "knowledge.search", "version": "1.0.0"}],
            "idempotency_key": "idem-1",
            "version": "1.0.0",
        })
        self.assertEqual(len(req.steps), 1)

    def test_plan_create_rejects_empty_steps(self):
        with self.assertRaises(ValidationError):
            PlanCreateRequest.model_validate({
                "session_id": "ses-abc",
                "task": "test",
                "steps": [],
                "idempotency_key": "idem-1",
                "version": "1.0.0",
            })

    def test_plan_create_rejects_missing_task(self):
        with self.assertRaises(ValidationError):
            PlanCreateRequest.model_validate({
                "session_id": "ses-abc",
                "steps": [{"tool_id": "t", "version": "1.0.0"}],
                "idempotency_key": "idem-1",
                "version": "1.0.0",
            })


class ApprovalContractTests(unittest.TestCase):
    """Approval v1.0.0 contract validation."""

    def test_decision_literal_accepts_approve(self):
        req = ApprovalSubmitRequest.model_validate({
            "execution_id": "e",
            "approval_id": "a",
            "decision": "approve",
            "reason": "test",
            "version": "1.0.0",
        })
        self.assertEqual(req.decision, "approve")

    def test_decision_literal_rejects_invalid(self):
        with self.assertRaises(ValidationError):
            ApprovalSubmitRequest.model_validate({
                "execution_id": "e",
                "approval_id": "a",
                "decision": "execute",
                "reason": "test",
                "version": "1.0.0",
            })

    def test_approval_submit_accepts_valid(self):
        req = ApprovalSubmitRequest.model_validate({
            "execution_id": "exec-1",
            "approval_id": "apr-1",
            "decision": "approve",
            "reason": "safe to proceed",
            "version": "1.0.0",
        })
        self.assertEqual(req.decision, "approve")

    def test_approval_submit_rejects_invalid_decision(self):
        with self.assertRaises(ValidationError):
            ApprovalSubmitRequest.model_validate({
                "execution_id": "exec-1",
                "approval_id": "apr-1",
                "decision": "execute",
                "reason": "test",
                "version": "1.0.0",
            })

    def test_approval_submit_rejects_empty_reason(self):
        with self.assertRaises(ValidationError):
            ApprovalSubmitRequest.model_validate({
                "execution_id": "exec-1",
                "approval_id": "apr-1",
                "decision": "approve",
                "reason": "",
                "version": "1.0.0",
            })

    def test_approval_response_accepts_valid(self):
        resp = ApprovalResponse.model_validate({
            "approval_id": "apr-1",
            "execution_id": "exec-1",
            "decision": "approve",
            "reason": "accepted",
            "approver_id": "usr-a",
            "status": "resolved",
            "version": "1.0.0",
        })
        self.assertEqual(resp.status, "resolved")


class GoalContractTests(unittest.TestCase):
    """Goal v1.0.0 contract validation (existing, regression guard)."""

    def test_goal_accepts_valid_verb(self):
        for verb in GoalVerb.__args__:
            g = Goal.model_validate({"verb": verb, "object": "test"})
            self.assertEqual(g.verb, verb)

    def test_goal_rejects_invalid_verb(self):
        with self.assertRaises(ValidationError):
            Goal.model_validate({"verb": "inject", "object": "test"})

    def test_goal_rejects_empty_object(self):
        with self.assertRaises(ValidationError):
            Goal.model_validate({"verb": "observe", "object": "x"})


class IntentContractTests(unittest.TestCase):
    """Intent v1.0.0 contract validation (existing, regression guard)."""

    def test_intent_accepts_valid(self):
        req = IntentCreateRequest.model_validate({
            "source_kind": "text",
            "source_text": "hello",
            "goal": {"verb": "observe", "object": "test"},
            "requested_mode": "observe",
            "requested_risk_tier": "R0",
        })
        self.assertEqual(req.source_kind, "text")

    def test_intent_rejects_unknown_keys(self):
        with self.assertRaises(ValidationError):
            IntentCreateRequest.model_validate({
                "source_kind": "text",
                "source_text": "hello",
                "goal": {"verb": "observe", "object": "test"},
                "requested_mode": "observe",
                "requested_risk_tier": "R0",
                "rogue": True,
            })


class EnumContractTests(unittest.TestCase):
    """Enum contracts are correctly defined."""

    def test_mode_enum_has_all_values(self):
        expected = {"observe", "assist", "do_this", "advanced", "engineering", "humanoid", "mobile_link"}
        self.assertEqual(set(Mode.__args__), expected)

    def test_risk_tier_enum_has_all_values(self):
        expected = {"R0", "R1", "R2", "R3", "R4", "R5"}
        self.assertEqual(set(RiskTier.__args__), expected)

    def test_plan_status_enum(self):
        expected = {"pending", "approved", "rejected", "executed", "cancelled"}
        self.assertEqual(set(PlanStatus.__args__), expected)

    def test_session_status_enum(self):
        expected = {"active", "revoked", "expired"}
        self.assertEqual(set(SessionStatus.__args__), expected)
