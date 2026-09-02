import unittest

from src.control_plane.execution import (
    ActionBroker,
    ToolDefinition,
    ToolRegistry,
)
from src.control_plane.policy import PolicyEngine
from src.control_plane.storage import ControlPlaneStore
from src.control_plane.storage import ConflictError


class ControlPlaneBrokerTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("ten-a")
        self.store.create_principal("usr-a", "ten-a")
        self.calls = []
        self.registry = ToolRegistry()

        def read_tool(payload):
            self.calls.append(payload)
            return {"observed": payload["value"]}

        self.registry.register(
            ToolDefinition(
                tool_id="registry.test.read",
                version="1.0.0",
                risk_tier="R0",
                required_scopes=frozenset({"workspace:read"}),
                handler=read_tool,
                evidence_status="simulated",
                disclosure="Test adapter has no external side effect.",
            )
        )
        self.registry.register(
            ToolDefinition(
                tool_id="registry.test.write",
                version="1.0.0",
                risk_tier="R2",
                required_scopes=frozenset({"workspace:write"}),
                handler=read_tool,
                evidence_status="simulated",
                disclosure="Test write adapter is disabled without approval.",
            )
        )
        self.broker = ActionBroker(
            store=self.store,
            registry=self.registry,
            policy=PolicyEngine(self.registry.capabilities()),
        )

    def tearDown(self):
        self.store.close()

    def test_unknown_tool_is_denied_without_invocation(self):
        result = self.broker.execute(
            tenant_id="ten-a",
            principal_id="usr-a",
            tool_id="registry.unknown",
            payload={"value": "blocked"},
            requested_risk_tier="R0",
            principal_scopes=frozenset({"workspace:read"}),
            idempotency_key="unknown-1",
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.decision, "deny")
        self.assertEqual(self.calls, [])

    def test_r2_tool_waits_for_approval(self):
        result = self.broker.execute(
            tenant_id="ten-a",
            principal_id="usr-a",
            tool_id="registry.test.write",
            payload={"value": "blocked"},
            requested_risk_tier="R2",
            principal_scopes=frozenset({"workspace:write"}),
            idempotency_key="write-1",
        )
        self.assertEqual(result.status, "waiting_approval")
        self.assertEqual(result.decision, "allow_with_approval")
        self.assertEqual(self.calls, [])

    def test_approved_risk_bearing_tool_stays_queued_for_separate_worker(self):
        result = self.broker.execute(
            tenant_id="ten-a",
            principal_id="usr-a",
            tool_id="registry.test.write",
            payload={"value": "still-bounded"},
            requested_risk_tier="R2",
            principal_scopes=frozenset({"workspace:write"}),
            idempotency_key="write-approved-1",
            approved=True,
        )
        self.assertEqual(result.status, "queued")
        self.assertEqual(self.store.get_run(result.run_id, "ten-a")["action_status"], "queued")
        self.assertEqual(self.calls, [])

    def test_r0_execution_is_durable_and_idempotent(self):
        first = self.broker.execute(
            tenant_id="ten-a",
            principal_id="usr-a",
            tool_id="registry.test.read",
            payload={"value": "ok"},
            requested_risk_tier="R0",
            principal_scopes=frozenset({"workspace:read"}),
            idempotency_key="read-1",
        )
        second = self.broker.execute(
            tenant_id="ten-a",
            principal_id="usr-a",
            tool_id="registry.test.read",
            payload={"value": "ok"},
            requested_risk_tier="R0",
            principal_scopes=frozenset({"workspace:read"}),
            idempotency_key="read-1",
        )
        self.assertEqual(first.status, "succeeded")
        self.assertEqual(second.status, "succeeded")
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(first.evidence["status"], "simulated")
        self.assertEqual(self.store.latest_sequence("ten-a"), 4)

    def test_idempotency_key_cannot_be_reused_for_another_tool(self):
        first = self.broker.execute(
            tenant_id="ten-a",
            principal_id="usr-a",
            tool_id="registry.test.read",
            payload={"value": "ok"},
            requested_risk_tier="R0",
            principal_scopes=frozenset({"workspace:read"}),
            idempotency_key="reused-key",
        )
        self.assertEqual(first.status, "succeeded")
        with self.assertRaises(ConflictError):
            self.broker.execute(
                tenant_id="ten-a",
                principal_id="usr-a",
                tool_id="registry.test.write",
                payload={"value": "must-not-run"},
                requested_risk_tier="R2",
                principal_scopes=frozenset({"workspace:write"}),
                idempotency_key="reused-key",
            )
        with self.assertRaises(ConflictError):
            self.broker.execute(
                tenant_id="ten-a",
                principal_id="usr-a",
                tool_id="registry.test.read",
                payload={"value": "different"},
                requested_risk_tier="R0",
                principal_scopes=frozenset({"workspace:read"}),
                idempotency_key="reused-key",
            )
        self.assertEqual(self.calls, [{"value": "ok"}])


if __name__ == "__main__":
    unittest.main()
