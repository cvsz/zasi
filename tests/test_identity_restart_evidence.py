import datetime as dt
import tempfile
import unittest
from pathlib import Path

from src.control_plane.identity import hash_token
from src.control_plane.storage import ControlPlaneStore


class IdentityRestartEvidenceTests(unittest.TestCase):
    def test_authoritative_identity_approval_and_audit_state_survive_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "control-plane.db")
            token = "durable-session-token"
            expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15)

            store = ControlPlaneStore(database_path)
            store.initialize()
            store.create_tenant("ten-a")
            store.create_principal("usr-a", "ten-a")
            store.create_session(
                session_id="ses-a",
                tenant_id="ten-a",
                principal_id="usr-a",
                device_id=None,
                token_hash=hash_token(token),
                expires_at=expiry,
                scopes=["workspace:read", "workspace:write"],
            )
            store.create_intent(
                intent_id="int-a",
                tenant_id="ten-a",
                principal_id="usr-a",
                source_kind="text",
                source_text="controlled restart evidence",
                goal_json='{"verb":"execute","object":"registry.test.write","parameters":{}}',
                requested_mode="do_this",
                requested_risk_tier="R2",
            )
            store.create_plan(
                plan_id="pln-a",
                tenant_id="ten-a",
                principal_id="usr-a",
                intent_id="int-a",
                digest="sha256:plan-a",
                scope_digest="sha256:scope-a",
                steps_json='[{"tool_id":"registry.test.write","risk_tier":"R2"}]',
                expires_at=expiry,
            )
            store.approve_plan(
                approval_id="apr-a",
                plan_id="pln-a",
                tenant_id="ten-a",
                approver_id="usr-a",
                digest="sha256:plan-a",
                scope_digest="sha256:scope-a",
                required_capability="registry.test.write",
                risk_tier="R2",
                reason="restart durability evidence",
                expires_at=expiry,
            )
            event = store.append_audited_event(
                tenant_id="ten-a",
                actor_kind="principal",
                actor_id="usr-a",
                action="restart.evidence",
                target="pln-a",
                outcome="success",
                event_type="restart.evidence",
                aggregate_kind="plan",
                aggregate_id="pln-a",
                payload={"safe": True},
            )
            sequence_before = event["sequence"]
            self.assertIsNotNone(store.authenticate_session(token))
            self.assertTrue(
                store.has_valid_approval(
                    "pln-a", "ten-a", "sha256:plan-a", "sha256:scope-a"
                )
            )
            store.close()

            restored = ControlPlaneStore(database_path)
            restored.initialize()
            try:
                session = restored.authenticate_session(token)
                self.assertIsNotNone(session)
                self.assertEqual(session["tenant_id"], "ten-a")
                self.assertEqual(session["principal_id"], "usr-a")
                self.assertTrue(
                    restored.has_valid_approval(
                        "pln-a", "ten-a", "sha256:plan-a", "sha256:scope-a"
                    )
                )
                self.assertGreaterEqual(restored.latest_sequence("ten-a"), sequence_before)
                audit = restored.list_audit("ten-a")
                self.assertTrue(
                    any(record["action"] == "restart.evidence" for record in audit)
                )

                restored.revoke_session("ses-a")
                self.assertIsNone(restored.authenticate_session(token))
            finally:
                restored.close()

            revoked_restart = ControlPlaneStore(database_path)
            revoked_restart.initialize()
            try:
                self.assertIsNone(revoked_restart.authenticate_session(token))
            finally:
                revoked_restart.close()

    def test_expired_session_remains_rejected_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "control-plane.db")
            token = "expired-session-token"

            store = ControlPlaneStore(database_path)
            store.initialize()
            store.create_tenant("ten-a")
            store.create_principal("usr-a", "ten-a")
            store.create_session(
                session_id="ses-expired",
                tenant_id="ten-a",
                principal_id="usr-a",
                device_id=None,
                token_hash=hash_token(token),
                expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1),
                scopes=["workspace:read"],
            )
            self.assertIsNone(store.authenticate_session(token))
            store.close()

            restored = ControlPlaneStore(database_path)
            restored.initialize()
            try:
                self.assertIsNone(restored.authenticate_session(token))
            finally:
                restored.close()


if __name__ == "__main__":
    unittest.main()
