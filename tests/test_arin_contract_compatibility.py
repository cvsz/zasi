"""ARIN Task 4 backward-compatibility closure for supported v1 contracts.

The supported contract set currently contains only v1.0.0. These tests pin
wire-compatible payloads and verify that unsupported versions and authority-
expanding fields continue to fail closed.
"""
import unittest

from pydantic import ValidationError

from src.control_plane.contracts import (
    ApprovalSubmitRequest,
    PlanCreateRequest,
    SessionCreateRequest,
    SessionRenewRequest,
)


class SupportedV1CompatibilityTests(unittest.TestCase):
    def test_legacy_v1_payloads_without_explicit_version_remain_accepted(self):
        session = SessionCreateRequest.model_validate({"api_key": "test-key"})
        renew = SessionRenewRequest.model_validate({
            "session_id": "ses-1",
            "new_expires_at": "2026-12-31T23:59:59Z",
        })
        plan = PlanCreateRequest.model_validate({
            "session_id": "ses-1",
            "task": "search knowledge",
            "steps": [{"tool_id": "knowledge.search"}],
            "idempotency_key": "idem-1",
        })
        approval = ApprovalSubmitRequest.model_validate({
            "execution_id": "exec-1",
            "approval_id": "apr-1",
            "decision": "approve",
            "reason": "operator approved",
        })

        self.assertEqual(session.version, "1.0.0")
        self.assertEqual(renew.version, "1.0.0")
        self.assertEqual(plan.version, "1.0.0")
        self.assertEqual(plan.steps[0].version, "1.0.0")
        self.assertEqual(approval.version, "1.0.0")

    def test_explicit_supported_version_remains_accepted(self):
        request = PlanCreateRequest.model_validate({
            "version": "1.0.0",
            "session_id": "ses-1",
            "task": "search knowledge",
            "steps": [{
                "version": "1.0.0",
                "tool_id": "knowledge.search",
                "arguments": {"query": "arin"},
                "risk_tier": "R0",
            }],
            "idempotency_key": "idem-2",
        })
        self.assertEqual(request.version, "1.0.0")

    def test_unsupported_future_version_fails_closed(self):
        with self.assertRaises(ValidationError):
            SessionCreateRequest.model_validate({
                "version": "1.1.0",
                "api_key": "test-key",
            })

    def test_nested_unsupported_version_fails_closed(self):
        with self.assertRaises(ValidationError):
            PlanCreateRequest.model_validate({
                "version": "1.0.0",
                "session_id": "ses-1",
                "task": "search knowledge",
                "steps": [{
                    "version": "2.0.0",
                    "tool_id": "knowledge.search",
                }],
                "idempotency_key": "idem-3",
            })

    def test_authority_expanding_compatibility_field_fails_closed(self):
        with self.assertRaises(ValidationError):
            ApprovalSubmitRequest.model_validate({
                "version": "1.0.0",
                "execution_id": "exec-1",
                "approval_id": "apr-1",
                "decision": "approve",
                "reason": "operator approved",
                "actuate": True,
            })


if __name__ == "__main__":
    unittest.main()
