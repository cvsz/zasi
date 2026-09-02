import datetime as dt
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.control_plane.config import ConfigurationError, Settings
from src.control_plane.contracts import Goal, IntentCreateRequest
from src.control_plane.events import OutboxDispatcher
from src.control_plane.identity import hash_token
from src.control_plane.policy import PolicyEngine
from src.control_plane.storage import ConflictError, ControlPlaneStore, ScopeViolation


class ControlPlaneCoreTests(unittest.TestCase):
    def test_production_configuration_requires_secret_and_explicit_origin(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_mapping(
                {
                    "ZASI_PROFILE": "production",
                    "ZASI_API_KEY": "",
                    "ZASI_CORS_ORIGINS": "https://cockpit.example",
                }
            )

        with self.assertRaises(ConfigurationError):
            Settings.from_mapping(
                {
                    "ZASI_PROFILE": "production",
                    "ZASI_API_KEY": "test-secret",
                    "ZASI_CORS_ORIGINS": "*",
                }
            )

        with self.assertRaises(ConfigurationError):
            Settings.from_mapping(
                {
                    "ZASI_PROFILE": "production",
                    "ZASI_API_KEY": "test-secret",
                    "ZASI_CORS_ORIGINS": "https://cockpit.example",
                }
            )
        settings = Settings.from_mapping(
            {
                "ZASI_PROFILE": "production",
                "ZASI_API_KEY": "test-secret",
                "ZASI_CORS_ORIGINS": "https://cockpit.example",
                "ZASI_DATABASE_BACKEND": "postgresql",
                "ZASI_DATABASE_URL": "postgresql://db.example/zasi",
                "ZASI_SECRET_PROVIDER": "vault",
                "ZASI_BACKUP_POLICY": "managed-encrypted",
            }
        )
        self.assertEqual(settings.profile, "production")
        self.assertEqual(settings.database_backend, "postgresql")
        self.assertNotEqual(settings.api_key_digest, b"test-secret")
        self.assertEqual(len(settings.api_key_digest), 32)

    def test_local_configuration_does_not_create_implicit_credential(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_mapping({"ZASI_PROFILE": "local"})

    def test_intent_contract_excludes_client_authorization_scope(self):
        request = IntentCreateRequest(
            source_kind="text",
            source_text="show system status",
            goal=Goal(verb="observe", object="system.status", parameters={}),
            requested_mode="observe",
            requested_risk_tier="R0",
        )
        self.assertEqual(request.goal.object, "system.status")
        self.assertFalse(hasattr(request, "tenant_id"))

        with self.assertRaises(ValidationError):
            IntentCreateRequest(
                source_kind="text",
                source_text="x",
                goal=Goal(verb="observe", object="system.status", parameters={}),
                requested_mode="untrusted",
                requested_risk_tier="R0",
            )

    def test_unknown_policy_decision_denies_side_effect(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            capability_id="registry.tool.unknown",
            requested_risk_tier="R3",
            principal_scopes={"workspace:read"},
        )
        self.assertEqual(decision.decision, "deny")
        self.assertIn("capability.unavailable", decision.reasons)

    def test_event_and_audit_are_scoped_and_cursored(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("ten-a")
        store.create_tenant("ten-b")
        store.create_principal("usr-a", "ten-a")
        store.create_principal("usr-b", "ten-b")
        expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
        store.create_session(
            session_id="ses-a",
            tenant_id="ten-a",
            principal_id="usr-a",
            device_id=None,
            token_hash=hash_token("session-a"),
            expires_at=expiry,
        )
        store.create_session(
            session_id="ses-b",
            tenant_id="ten-b",
            principal_id="usr-b",
            device_id=None,
            token_hash=hash_token("session-b"),
            expires_at=expiry,
        )

        store.append_audited_event(
            tenant_id="ten-a",
            actor_kind="principal",
            actor_id="usr-a",
            action="intent.created",
            target="int-1",
            outcome="success",
            event_type="intent.created",
            aggregate_kind="intent",
            aggregate_id="int-1",
            payload={"status": "created"},
        )
        store.append_audited_event(
            tenant_id="ten-b",
            actor_kind="principal",
            actor_id="usr-b",
            action="intent.created",
            target="int-2",
            outcome="success",
            event_type="intent.created",
            aggregate_kind="intent",
            aggregate_id="int-2",
            payload={"status": "created"},
        )

        events_a = store.list_events("ten-a", after=0, limit=10)
        events_b = store.list_events("ten-b", after=0, limit=10)
        self.assertEqual(events_a[-1]["tenant_id"], "ten-a")
        self.assertEqual(events_b[-1]["tenant_id"], "ten-b")
        self.assertEqual(events_a[-1]["sequence"], 2)
        self.assertEqual(events_b[-1]["sequence"], 2)
        self.assertEqual(events_a[-1]["type"], "intent.created")
        self.assertEqual(store.latest_sequence("ten-a"), 2)
        self.assertEqual(store.latest_sequence("ten-b"), 2)
        self.assertEqual(len(store.list_outbox()), 4)

        with self.assertRaises(ScopeViolation):
            store.get_session("ses-b", tenant_id="ten-a")
        store.close()

    def test_revoked_session_cannot_authenticate(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("ten-a")
        store.create_principal("usr-a", "ten-a")
        store.create_session(
            session_id="ses-a",
            tenant_id="ten-a",
            principal_id="usr-a",
            device_id=None,
            token_hash=hash_token("session-a"),
            expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5),
        )
        self.assertIsNotNone(store.authenticate_session("session-a"))
        store.revoke_session("ses-a")
        self.assertIsNone(store.authenticate_session("session-a"))
        store.close()

    def test_retention_gap_is_detectable_before_stream_replay(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("ten-a")
        for index in range(3):
            store.append_audited_event(
                tenant_id="ten-a",
                actor_kind="system",
                actor_id="test",
                action=f"event-{index}",
                target="test",
                outcome="success",
                event_type="test.event",
                aggregate_kind="test",
                aggregate_id=str(index),
                payload={"index": index},
            )
        for outbox in store.list_outbox():
            store.claim_outbox(outbox["id"])
            store.finish_outbox(outbox["id"], success=True)
        store.prune_events("ten-a", retain_latest=1)
        self.assertEqual(store.oldest_sequence("ten-a"), 3)
        self.assertTrue(store.cursor_requires_resync("ten-a", after=0))
        self.assertFalse(store.cursor_requires_resync("ten-a", after=2))
        store.close()

    def test_approval_binds_exact_plan_digest_and_can_be_revoked(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("ten-a")
        store.create_principal("usr-a", "ten-a")
        store.create_intent(
            intent_id="int-a",
            tenant_id="ten-a",
            principal_id="usr-a",
            source_kind="text",
            source_text="controlled test",
            goal_json='{"verb":"execute","object":"registry.test.write","parameters":{}}',
            requested_mode="do_this",
            requested_risk_tier="R2",
        )
        expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)
        plan = store.create_plan(
            plan_id="pln-a",
            tenant_id="ten-a",
            principal_id="usr-a",
            intent_id="int-a",
            digest="sha256:plan-a",
            scope_digest="sha256:scope-a",
            steps_json='[{"tool_id":"registry.test.write","risk_tier":"R2"}]',
            expires_at=expiry,
        )
        approval = store.approve_plan(
            approval_id="apr-a",
            plan_id=plan["plan_id"],
            tenant_id="ten-a",
            approver_id="usr-a",
            digest="sha256:plan-a",
            scope_digest="sha256:scope-a",
            required_capability="registry.test.write",
            risk_tier="R2",
            reason="approved for controlled test",
            expires_at=expiry,
        )
        self.assertEqual(approval["decision"], "approved")
        self.assertTrue(
            store.has_valid_approval("pln-a", "ten-a", "sha256:plan-a", "sha256:scope-a")
        )
        with self.assertRaises(ConflictError):
            store.approve_plan(
                approval_id="apr-tampered",
                plan_id="pln-a",
                tenant_id="ten-a",
                approver_id="usr-a",
                digest="sha256:tampered",
                scope_digest="sha256:scope-a",
                required_capability="registry.test.write",
                risk_tier="R2",
                reason="must fail closed",
                expires_at=expiry,
            )
        revoked = store.revoke_approval("apr-a", "ten-a", "usr-a")
        self.assertEqual(revoked["decision"], "revoked")
        self.assertFalse(
            store.has_valid_approval("pln-a", "ten-a", "sha256:plan-a", "sha256:scope-a")
        )
        self.assertEqual(store.get_plan("pln-a", "ten-a")["status"], "awaiting_approval")
        store.close()

    def test_outbox_claim_is_durable_and_idempotent(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("ten-a")
        event = store.append_audited_event(
            tenant_id="ten-a",
            actor_kind="system",
            actor_id="test",
            action="test.event",
            target="test",
            outcome="success",
            event_type="test.event",
            aggregate_kind="test",
            aggregate_id="test",
            payload={"safe": True},
        )
        pending = store.list_outbox()
        self.assertEqual(len(pending), 1)
        claimed = store.claim_outbox(pending[0]["id"])
        self.assertEqual(claimed["event_id"], event["event_id"])
        self.assertIsNone(store.claim_outbox(pending[0]["id"]))
        store.finish_outbox(pending[0]["id"], success=True)
        self.assertEqual(store.list_outbox(status="delivered")[0]["status"], "delivered")
        store.close()

    def test_outbox_lease_token_prevents_stale_worker_completion(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("ten-a")
        store.append_audited_event(
            tenant_id="ten-a",
            actor_kind="system",
            actor_id="test",
            action="test.event",
            target="test",
            outcome="success",
            event_type="test.event",
            aggregate_kind="test",
            aggregate_id="test",
            payload={"safe": True},
        )
        outbox_id = store.list_outbox()[0]["id"]
        first = store.claim_outbox(outbox_id, lease_seconds=60)
        self.assertIsNotNone(first["claim_token"])
        store._conn().execute(
            "UPDATE outbox SET lease_until = ? WHERE id = ?",
            ((dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat(), outbox_id),
        )
        second = store.claim_outbox(outbox_id, lease_seconds=60)
        self.assertNotEqual(first["claim_token"], second["claim_token"])
        store.finish_outbox(outbox_id, success=True, claim_token=first["claim_token"])
        self.assertEqual(store.list_outbox(status="processing")[0]["status"], "processing")
        store.finish_outbox(outbox_id, success=True, claim_token=second["claim_token"])
        self.assertEqual(store.list_outbox(status="delivered")[0]["status"], "delivered")
        store.close()

    def test_outbox_dispatcher_dead_letters_after_bounded_attempts(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("ten-a")
        store.append_audited_event(
            tenant_id="ten-a",
            actor_kind="system",
            actor_id="test",
            action="test.event",
            target="test",
            outcome="success",
            event_type="test.event",
            aggregate_kind="test",
            aggregate_id="test",
            payload={"safe": True},
        )
        outbox_id = store.list_outbox()[0]["id"]
        store._conn().execute("UPDATE outbox SET max_attempts = 1 WHERE id = ?", (outbox_id,))

        def failing_handler(_item):
            raise RuntimeError("TOP-SECRET-123")

        report = OutboxDispatcher(store).dispatch_once(failing_handler)
        self.assertEqual(report.claimed, 1)
        self.assertEqual(report.retried, 1)
        dead = store.list_outbox(status="dead_letter")
        self.assertEqual(len(dead), 1)
        self.assertNotIn("TOP-SECRET-123", dead[0]["last_error"])
        store.close()

    def test_file_backup_restores_schema_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "source.db")
            backup_path = str(Path(directory) / "backup.db")
            store = ControlPlaneStore(source_path)
            store.initialize()
            store.create_tenant("ten-a")
            store.append_audited_event(
                tenant_id="ten-a",
                actor_kind="system",
                actor_id="test",
                action="test.event",
                target="test",
                outcome="success",
                event_type="test.event",
                aggregate_kind="test",
                aggregate_id="test",
                payload={"safe": True},
            )
            store.backup_to(backup_path)
            restored = ControlPlaneStore(backup_path)
            restored.initialize()
            self.assertEqual(restored.schema_version(), 7)
            self.assertTrue(restored.integrity_check())
            self.assertEqual(restored.latest_sequence("ten-a"), 1)
            restored.close()
            store.close()

    def test_rate_limit_counter_is_stored_in_repository(self):
        store = ControlPlaneStore(":memory:")
        store.initialize()
        store.create_tenant("ten-a")
        allowed, _ = store.consume_rate_limit("ten-a", "session", limit=2, window_seconds=60)
        self.assertTrue(allowed)
        allowed, _ = store.consume_rate_limit("ten-a", "session", limit=2, window_seconds=60)
        self.assertTrue(allowed)
        allowed, retry_after = store.consume_rate_limit("ten-a", "session", limit=2, window_seconds=60)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 0)
        store.close()


if __name__ == "__main__":
    unittest.main()
