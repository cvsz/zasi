"""ARIN Task 4 — Schema tests for tenant/session isolation and payload rejection.

These tests guard the foundational contracts that all subsequent
canonical ARIN APIs must satisfy:

1. Every read/write operation is tenant-scoped; cross-tenant access
   raises ScopeViolation fail-closed.
2. Request contracts reject incompatible payloads (unknown keys,
   missing fields, invalid enums) before any state mutation occurs.
"""
import unittest

from pydantic import ValidationError

from src.control_plane.contracts import Goal, IntentCreateRequest
from src.control_plane.identity import hash_token
from src.control_plane.storage import ControlPlaneStore, NotFoundError, ScopeViolation


class SessionTenantIsolationTests(unittest.TestCase):
    """Sessions and data are strictly tenant-scoped."""

    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_tenant("tenant-b")
        self.store.create_principal("usr-a", "tenant-a")
        self.store.create_principal("usr-b", "tenant-b")
        self.expires = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ) + __import__("datetime").timedelta(minutes=30)

    def tearDown(self):
        self.store.close()

    def _create_session(self, tenant_id, principal_id, token):
        self.store.create_session(
            session_id=f"ses-{token}",
            tenant_id=tenant_id,
            principal_id=principal_id,
            device_id=None,
            token_hash=hash_token(token),
            expires_at=self.expires,
            scopes=["workspace:read"],
        )

    def test_session_get_with_wrong_tenant_raises_scope_violation(self):
        self._create_session("tenant-a", "usr-a", "token-a")
        with self.assertRaises(ScopeViolation):
            self.store.get_session("ses-token-a", tenant_id="tenant-b")

    def test_session_get_with_correct_tenant_succeeds(self):
        self._create_session("tenant-a", "usr-a", "token-a")
        row = self.store.get_session("ses-token-a", tenant_id="tenant-a")
        self.assertEqual(row["tenant_id"], "tenant-a")

    def test_session_get_without_tenant_ignores_scope(self):
        self._create_session("tenant-a", "usr-a", "token-a")
        row = self.store.get_session("ses-token-a")
        self.assertEqual(row["id"], "ses-token-a")

    def test_authenticated_session_matches_tenant(self):
        self._create_session("tenant-a", "usr-a", "token-a")
        result = self.store.authenticate_session("token-a")
        self.assertIsNotNone(result)
        self.assertEqual(result["tenant_id"], "tenant-a")

    def test_foreign_token_cannot_authenticate(self):
        self._create_session("tenant-a", "usr-a", "token-a")
        self._create_session("tenant-b", "usr-b", "token-b")
        result = self.store.authenticate_session("token-b")
        self.assertIsNotNone(result)
        self.assertEqual(result["tenant_id"], "tenant-b")

    def test_session_id_collision_across_tenants_is_allowed(self):
        self._create_session("tenant-a", "usr-a", "token-a")
        self._create_session("tenant-b", "usr-b", "token-b")
        a = self.store.get_session("ses-token-a", tenant_id="tenant-a")
        b = self.store.get_session("ses-token-b", tenant_id="tenant-b")
        self.assertEqual(a["tenant_id"], "tenant-a")
        self.assertEqual(b["tenant_id"], "tenant-b")

    def test_different_sessions_same_tenant_are_distinct(self):
        self._create_session("tenant-a", "usr-a", "token-a")
        self._create_session("tenant-a", "usr-a", "token-b")
        a = self.store.get_session("ses-token-a", tenant_id="tenant-a")
        b = self.store.get_session("ses-token-b", tenant_id="tenant-a")
        self.assertNotEqual(a["id"], b["id"])
        self.assertNotEqual(a["token_hash"], b["token_hash"])


class IncompatiblePayloadRejectionTests(unittest.TestCase):
    """Strict contracts reject malformed payloads fail-closed."""

    def test_intent_rejects_unknown_keys(self):
        with self.assertRaises(ValidationError):
            IntentCreateRequest.model_validate(
                {
                    "source_kind": "text",
                    "source_text": "hello",
                    "goal": {"verb": "observe", "object": "test"},
                    "requested_mode": "observe",
                    "requested_risk_tier": "R0",
                    "rogue_field": True,
                }
            )

    def test_intent_rejects_missing_required_fields(self):
        with self.assertRaises(ValidationError):
            IntentCreateRequest.model_validate({})

    def test_intent_rejects_invalid_mode(self):
        with self.assertRaises(ValidationError):
            IntentCreateRequest.model_validate(
                {
                    "source_kind": "text",
                    "source_text": "hello",
                    "goal": {"verb": "observe", "object": "test"},
                    "requested_mode": "invalid_mode",
                    "requested_risk_tier": "R0",
                }
            )

    def test_intent_rejects_invalid_risk_tier(self):
        with self.assertRaises(ValidationError):
            IntentCreateRequest.model_validate(
                {
                    "source_kind": "text",
                    "source_text": "hello",
                    "goal": {"verb": "observe", "object": "test"},
                    "requested_mode": "observe",
                    "requested_risk_tier": "R99",
                }
            )

    def test_intent_rejects_invalid_goal_verb(self):
        with self.assertRaises(ValidationError):
            IntentCreateRequest.model_validate(
                {
                    "source_kind": "text",
                    "source_text": "hello",
                    "goal": {"verb": "hack", "object": "test"},
                    "requested_mode": "observe",
                    "requested_risk_tier": "R0",
                }
            )

    def test_intent_rejects_empty_goal_object(self):
        with self.assertRaises(ValidationError):
            IntentCreateRequest.model_validate(
                {
                    "source_kind": "text",
                    "source_text": "hello",
                    "goal": {"verb": "observe", "object": "x"},
                    "requested_mode": "observe",
                    "requested_risk_tier": "R0",
                }
            )

    def test_intent_rejects_non_string_source_text(self):
        with self.assertRaises(ValidationError):
            IntentCreateRequest.model_validate(
                {
                    "source_kind": "text",
                    "source_text": 123,
                    "goal": {"verb": "observe", "object": "test"},
                    "requested_mode": "observe",
                    "requested_risk_tier": "R0",
                }
            )

    def test_intent_accepts_valid_payload(self):
        req = IntentCreateRequest.model_validate(
            {
                "source_kind": "text",
                "source_text": "hello world",
                "goal": {"verb": "observe", "object": "test"},
                "requested_mode": "observe",
                "requested_risk_tier": "R0",
            }
        )
        self.assertEqual(req.source_kind, "text")
        self.assertEqual(req.goal.verb, "observe")

    def test_goal_rejects_invalid_verb(self):
        with self.assertRaises(ValidationError):
            Goal.model_validate({"verb": "inject", "object": "test"})

    def test_goal_rejects_object_too_short(self):
        with self.assertRaises(ValidationError):
            Goal.model_validate({"verb": "observe", "object": "x"})


class SessionRejectBoundaryTests(unittest.TestCase):
    """Session-scoped rejection at the storage layer."""

    def test_get_nonexistent_session_raises_not_found(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("tenant-a")
        with self.assertRaises(NotFoundError):
            store.get_session("ses-missing", tenant_id="tenant-a")
        store.close()

    def test_create_session_requires_active_tenant(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        with self.assertRaises(Exception):
            store.create_session(
                session_id="ses-x",
                tenant_id="nonexistent",
                principal_id="not-a-principal",
                device_id=None,
                token_hash="abc",
                expires_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
            )
        store.close()
