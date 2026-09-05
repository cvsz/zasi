"""Tests for the AI Futures Project Superintelligence agent platform.

Covers schema v12 migration, strict request contracts, canonical digest
behaviour, agent/version/execution/approval repository semantics, tenant
isolation, idempotent replay, and the expanded event envelope.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from src.control_plane.orchestration.agent_contracts import (
    AgentApprovalDecisionRequest,
    AgentCreateRequest,
    AgentExecutionRequest,
    AgentSandboxRequest,
    AgentVersionCreateRequest,
    BudgetRequest,
)
from src.control_plane.orchestration.agent_models import (
    AgentEventContext,
    AgentVersionSpec,
    BudgetPolicy,
    ModelSelection,
    PlanStep,
    TypedAgentPlan,
    action_digest,
    canonicalize_action_payload,
)
from src.control_plane.storage import (
    CURRENT_SCHEMA_VERSION,
    ConflictError,
    ControlPlaneStore,
    NotFoundError,
    ScopeViolation,
)


class AgentContractTests(unittest.TestCase):
    def test_strict_contracts_reject_unknown_keys(self):
        with self.assertRaises(ValidationError):
            AgentCreateRequest.model_validate({"name": "x", "rogue": True})
        with self.assertRaises(ValidationError):
            AgentVersionCreateRequest.model_validate(
                {"version": "1.0.0", "allowed_tools": ["x"], "rogue": 1}
            )
        with self.assertRaises(ValidationError):
            AgentSandboxRequest.model_validate({"task": ""})
        with self.assertRaises(ValidationError):
            AgentApprovalDecisionRequest.model_validate({"reason": ""})

    def test_contracts_bound_values(self):
        with self.assertRaises(ValidationError):
            AgentCreateRequest.model_validate({"name": "x" * 200})
        with self.assertRaises(ValidationError):
            AgentCreateRequest.model_validate({"name": "x", "version": "1.0"})
        with self.assertRaises(ValidationError):
            BudgetRequest.model_validate({"max_steps": 0})
        with self.assertRaises(ValidationError):
            BudgetRequest.model_validate({"max_runtime_seconds": 0})

    def test_default_creation_request_is_deterministic(self):
        request = AgentCreateRequest.model_validate({"name": "demo"})
        self.assertEqual(request.version, "1.0.0")
        self.assertEqual(request.allowed_tools, ["knowledge.search", "ticket.update"])
        self.assertEqual(request.budget.max_steps, 4)
        self.assertEqual(request.budget.max_tool_calls, 4)
        self.assertEqual(request.budget.max_runtime_seconds, 30)


class AgentModelTests(unittest.TestCase):
    def test_budget_rejects_unknown_keys_and_oversized(self):
        with self.assertRaises(ValueError):
            BudgetPolicy.from_jsonable({"max_steps": 1, "rogue": True})
        with self.assertRaises(ValueError):
            BudgetPolicy.from_jsonable({"max_steps": 0})
        with self.assertRaises(ValueError):
            BudgetPolicy.from_jsonable({"max_steps": 1, "max_runtime_seconds": 9999})

    def test_agent_version_spec_digest_is_canonical(self):
        spec_a = AgentVersionSpec(
            version="1.0.0",
            system_prompt="hello",
            allowed_tools=("knowledge.search", "ticket.update"),
            model_policy={"mode": "deterministic_simulator"},
            budget=BudgetPolicy(),
        )
        spec_b = AgentVersionSpec(
            version="1.0.0",
            system_prompt="hello",
            allowed_tools=("knowledge.search", "ticket.update"),
            model_policy={"mode": "deterministic_simulator"},
            budget=BudgetPolicy(),
        )
        self.assertEqual(spec_a.digest(), spec_b.digest())

    def test_agent_version_spec_digest_changes_with_payload(self):
        spec_a = AgentVersionSpec(
            version="1.0.0",
            system_prompt="hello",
            allowed_tools=("knowledge.search",),
        )
        spec_b = AgentVersionSpec(
            version="1.0.0",
            system_prompt="hello!",
            allowed_tools=("knowledge.search",),
        )
        self.assertNotEqual(spec_a.digest(), spec_b.digest())

    def test_canonicalize_action_payload_sorts_keys(self):
        canonical = canonicalize_action_payload({"b": 2, "a": 1})
        self.assertEqual(json.loads(json.dumps(canonical)), {"a": 1, "b": 2})

    def test_action_digest_is_bound_to_tenant_execution_and_tool(self):
        digest_a = action_digest(
            tenant_id="tenant-a",
            execution_id="exec-1",
            agent_version="1.0.0",
            tool_id="ticket.update",
            tool_version="1.0.0",
            payload={"fields": {"status": "open"}},
        )
        digest_b = action_digest(
            tenant_id="tenant-b",
            execution_id="exec-1",
            agent_version="1.0.0",
            tool_id="ticket.update",
            tool_version="1.0.0",
            payload={"fields": {"status": "open"}},
        )
        digest_c = action_digest(
            tenant_id="tenant-a",
            execution_id="exec-1",
            agent_version="1.0.0",
            tool_id="ticket.update",
            tool_version="1.0.0",
            payload={"fields": {"status": "closed"}},
        )
        self.assertNotEqual(digest_a, digest_b)
        self.assertNotEqual(digest_a, digest_c)

    def test_typed_plan_serialization(self):
        step = PlanStep(
            step_id="s1",
            tool_id="knowledge.search",
            tool_version="1.0.0",
            risk_tier="R0",
            input={"query": "zasi"},
        )
        plan = TypedAgentPlan(steps=(step,), disclosures=("simulated",))
        payload = plan.to_jsonable()
        self.assertEqual(payload["steps"][0]["step_id"], "s1")
        self.assertEqual(payload["disclosures"], ["simulated"])

    def test_model_selection_envelope(self):
        selection = ModelSelection(
            mode="deterministic_simulator",
            model="deterministic_simulator",
            status="ready",
            proposal_digest="abc",
            disclosures=("simulated",),
        )
        self.assertEqual(selection.to_jsonable()["mode"], "deterministic_simulator")

    def test_agent_event_context_envelope(self):
        context = AgentEventContext(
            execution_id="exec-1",
            agent_version="1.0.0",
            correlation_id="corr-1",
        )
        envelope = context.to_envelope()
        self.assertEqual(envelope["execution_id"], "exec-1")
        self.assertEqual(envelope["sensitivity"], "tenant")


class AgentRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_tenant("tenant-b")
        self.store.create_principal("principal-a", "tenant-a")
        self.store.create_principal("principal-b", "tenant-b")
        self.assertEqual(self.store.schema_version(), CURRENT_SCHEMA_VERSION)
        self.assertEqual(CURRENT_SCHEMA_VERSION, 12)

    def tearDown(self):
        self.store.close()

    def test_create_and_get_agent(self):
        agent = self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="desc",
        )
        self.assertEqual(agent["name"], "demo")
        fetched = self.store.get_agent("agent-1", "tenant-a")
        self.assertEqual(fetched["agent_id"], "agent-1")
        with self.assertRaises(NotFoundError):
            self.store.get_agent("agent-1", "tenant-b")
        with self.assertRaises(ScopeViolation.__bases__[0] if False else NotFoundError):
            self.store.get_agent("missing", "tenant-a")

    def test_create_agent_version_and_publish(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        version = self.store.create_agent_version(
            version_id="ver-1",
            agent_id="agent-1",
            tenant_id="tenant-a",
            version="1.0.0",
            system_prompt="you are safe",
            allowed_tools=["knowledge.search", "ticket.update"],
            model_policy={"mode": "deterministic_simulator"},
            budget={"max_steps": 4, "max_tool_calls": 4, "max_runtime_seconds": 30},
            digest="sha256:abc",
        )
        self.assertEqual(version["status"], "draft")
        published = self.store.publish_agent_version(
            agent_id="agent-1",
            version_id="ver-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
        )
        self.assertEqual(published["status"], "published")
        self.assertIsNotNone(published["published_at"])

    def test_duplicate_agent_version_rejected(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        self.store.create_agent_version(
            version_id="ver-1",
            agent_id="agent-1",
            tenant_id="tenant-a",
            version="1.0.0",
            system_prompt="",
            allowed_tools=["knowledge.search"],
            model_policy={},
            budget={},
            digest="d1",
        )
        with self.assertRaises(ConflictError):
            self.store.create_agent_version(
                version_id="ver-2",
                agent_id="agent-1",
                tenant_id="tenant-a",
                version="1.0.0",
                system_prompt="",
                allowed_tools=["knowledge.search"],
                model_policy={},
                budget={},
                digest="d2",
            )

    def test_execution_requires_published_version(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        self.store.create_agent_version(
            version_id="ver-1",
            agent_id="agent-1",
            tenant_id="tenant-a",
            version="1.0.0",
            system_prompt="",
            allowed_tools=["knowledge.search"],
            model_policy={},
            budget={},
            digest="d1",
        )
        with self.assertRaises(ConflictError):
            self.store.create_agent_execution(
                execution_id="exec-1",
                tenant_id="tenant-a",
                principal_id="principal-a",
                agent_id="agent-1",
                agent_version_id="ver-1",
                idempotency_key="k1",
                task="t",
                plan={},
                model={},
            )
        self.store.publish_agent_version(
            agent_id="agent-1",
            version_id="ver-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
        )
        execution = self.store.create_agent_execution(
            execution_id="exec-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id="agent-1",
            agent_version_id="ver-1",
            idempotency_key="k1",
            task="summarize the spec",
            plan={"steps": []},
            model={"mode": "deterministic_simulator"},
        )
        self.assertEqual(execution["status"], "created")

    def test_execution_idempotency_replay(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        self.store.create_agent_version(
            version_id="ver-1",
            agent_id="agent-1",
            tenant_id="tenant-a",
            version="1.0.0",
            system_prompt="",
            allowed_tools=["knowledge.search"],
            model_policy={},
            budget={},
            digest="d1",
        )
        self.store.publish_agent_version(
            agent_id="agent-1",
            version_id="ver-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
        )
        first = self.store.create_agent_execution(
            execution_id="exec-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id="agent-1",
            agent_version_id="ver-1",
            idempotency_key="k1",
            task="t",
            plan={},
            model={},
        )
        with self.assertRaises(ConflictError):
            self.store.create_agent_execution(
                execution_id="exec-2",
                tenant_id="tenant-a",
                principal_id="principal-a",
                agent_id="agent-1",
                agent_version_id="ver-1",
                idempotency_key="k1",
                task="t",
                plan={},
                model={},
            )
        self.assertEqual(
            self.store.get_agent_execution_by_idempotency("tenant-a", "k1")["execution_id"],
            first["execution_id"],
        )

    def test_update_execution_lifecycle(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        self.store.create_agent_version(
            version_id="ver-1",
            agent_id="agent-1",
            tenant_id="tenant-a",
            version="1.0.0",
            system_prompt="",
            allowed_tools=["knowledge.search"],
            model_policy={},
            budget={},
            digest="d1",
        )
        self.store.publish_agent_version(
            agent_id="agent-1",
            version_id="ver-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
        )
        self.store.create_agent_execution(
            execution_id="exec-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id="agent-1",
            agent_version_id="ver-1",
            idempotency_key="k1",
            task="t",
            plan={},
            model={},
        )
        running = self.store.update_agent_execution(
            execution_id="exec-1",
            tenant_id="tenant-a",
            status="running",
        )
        self.assertEqual(running["status"], "running")
        self.assertIsNotNone(running["started_at"])
        completed = self.store.update_agent_execution(
            execution_id="exec-1",
            tenant_id="tenant-a",
            status="completed",
            knowledge_run_id="run-1",
            ticket_run_id="run-2",
            result={"summary": "ok"},
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"], {"summary": "ok"})
        self.assertEqual(completed["knowledge_run_id"], "run-1")
        self.assertIsNotNone(completed["finished_at"])

    def test_approval_uniqueness_and_resolution(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        self.store.create_agent_version(
            version_id="ver-1",
            agent_id="agent-1",
            tenant_id="tenant-a",
            version="1.0.0",
            system_prompt="",
            allowed_tools=["knowledge.search", "ticket.update"],
            model_policy={},
            budget={},
            digest="d1",
        )
        self.store.publish_agent_version(
            agent_id="agent-1",
            version_id="ver-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
        )
        self.store.create_agent_execution(
            execution_id="exec-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id="agent-1",
            agent_version_id="ver-1",
            idempotency_key="k1",
            task="t",
            plan={},
            model={},
        )
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        approval = self.store.create_agent_approval(
            approval_id="ap-1",
            tenant_id="tenant-a",
            execution_id="exec-1",
            agent_version_id="ver-1",
            run_id="run-1",
            tool_id="ticket.update",
            tool_version="1.0.0",
            action_digest="sha256:abc",
            expires_at=expires,
        )
        self.assertEqual(approval["decision"], "pending")
        with self.assertRaises(ConflictError):
            self.store.create_agent_approval(
                approval_id="ap-2",
                tenant_id="tenant-a",
                execution_id="exec-1",
                agent_version_id="ver-1",
                run_id="run-1",
                tool_id="ticket.update",
                tool_version="1.0.0",
                action_digest="sha256:abc",
                expires_at=expires,
            )
        approved = self.store.resolve_agent_approval(
            approval_id="ap-1",
            tenant_id="tenant-a",
            approver_id="principal-a",
            decision="approved",
            reason="ok",
        )
        self.assertEqual(approved["decision"], "approved")
        with self.assertRaises(ConflictError):
            self.store.resolve_agent_approval(
                approval_id="ap-1",
                tenant_id="tenant-a",
                approver_id="principal-a",
                decision="rejected",
                reason="never",
            )

    def test_approval_expiry_marks_revoked(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        self.store.create_agent_version(
            version_id="ver-1",
            agent_id="agent-1",
            tenant_id="tenant-a",
            version="1.0.0",
            system_prompt="",
            allowed_tools=["ticket.update"],
            model_policy={},
            budget={},
            digest="d1",
        )
        self.store.publish_agent_version(
            agent_id="agent-1",
            version_id="ver-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
        )
        self.store.create_agent_execution(
            execution_id="exec-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id="agent-1",
            agent_version_id="ver-1",
            idempotency_key="k1",
            task="t",
            plan={},
            model={},
        )
        self.store.create_agent_approval(
            approval_id="ap-1",
            tenant_id="tenant-a",
            execution_id="exec-1",
            agent_version_id="ver-1",
            run_id="run-1",
            tool_id="ticket.update",
            tool_version="1.0.0",
            action_digest="sha256:abc",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        with self.assertRaises(ConflictError):
            self.store.resolve_agent_approval(
                approval_id="ap-1",
                tenant_id="tenant-a",
                approver_id="principal-a",
                decision="approved",
                reason="ok",
            )
        record = self.store.get_agent_approval("ap-1", "tenant-a")
        self.assertEqual(record["decision"], "revoked")

    def test_tenant_isolation_for_agent_lookups(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        with self.assertRaises(NotFoundError):
            self.store.get_agent("agent-1", "tenant-b")
        self.assertEqual(self.store.list_agents("tenant-b"), [])

    def test_audit_includes_event_envelope_fields(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        events = self.store.list_events("tenant-a")
        self.assertTrue(events)
        envelope_event = next(
            event for event in events if event["type"] == "agent.created"
        )
        self.assertIn("correlation_id", envelope_event)
        self.assertEqual(envelope_event["sensitivity"], "tenant")
        self.assertEqual(envelope_event["schema_version"], 1)

    def test_append_audited_event_records_execution_envelope(self):
        event = self.store.append_audited_event(
            tenant_id="tenant-a",
            actor_kind="principal",
            actor_id="principal-a",
            action="agent.execution.requested",
            target="exec-1",
            outcome="success",
            event_type="agent.execution.requested",
            aggregate_kind="agent_execution",
            aggregate_id="exec-1",
            payload={"task": "demo"},
            execution_id="exec-1",
            agent_version="1.0.0",
            correlation_id="corr-1",
            causation_id="evt_prev",
            sensitivity="tenant",
            idempotency_key="k1",
            schema_version=2,
        )
        self.assertEqual(event["execution_id"], "exec-1")
        self.assertEqual(event["agent_version"], "1.0.0")
        self.assertEqual(event["correlation_id"], "corr-1")
        self.assertEqual(event["causation_id"], "evt_prev")
        self.assertEqual(event["sensitivity"], "tenant")
        self.assertEqual(event["idempotency_key"], "k1")
        self.assertEqual(event["schema_version"], 2)

    def test_list_audit_filters_by_execution_and_sensitivity(self):
        self.store.append_audited_event(
            tenant_id="tenant-a",
            actor_kind="principal",
            actor_id="principal-a",
            action="agent.execution.requested",
            target="exec-1",
            outcome="success",
            event_type="agent.execution.requested",
            aggregate_kind="agent_execution",
            aggregate_id="exec-1",
            payload={},
            execution_id="exec-1",
            agent_version="1.0.0",
            correlation_id="corr-1",
            sensitivity="tenant",
        )
        self.store.append_audited_event(
            tenant_id="tenant-a",
            actor_kind="principal",
            actor_id="principal-a",
            action="intent.created",
            target="intent-1",
            outcome="success",
            event_type="intent.created",
            aggregate_kind="intent",
            aggregate_id="intent-1",
            payload={},
            sensitivity="workspace",
        )
        tenant_a_records = self.store.list_audit("tenant-a", execution_id="exec-1")
        self.assertTrue(tenant_a_records)
        self.assertTrue(
            all(record["execution_id"] == "exec-1" for record in tenant_a_records)
        )
        tenant_b_records = self.store.list_audit("tenant-b", execution_id="exec-1")
        self.assertEqual(tenant_b_records, [])

    def test_agent_summary_projection(self):
        self.store.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-a",
            principal_id="principal-a",
            name="demo",
            description="",
        )
        summary = self.store.agent_summary("tenant-a")
        self.assertEqual(summary["total_agents"], 1)
        self.assertEqual(summary["published_versions"], 0)
        self.assertEqual(summary["active_executions"], 0)
        self.assertEqual(summary["pending_approvals"], 0)


class ModelGatewayTests(unittest.TestCase):
    def test_default_gateway_is_deterministic_simulator(self):
        from src.control_plane.connectors.model_gateway import ModelGateway

        gateway = ModelGateway()
        status = gateway.status()
        self.assertEqual(status["mode"], "deterministic_simulator")
        self.assertEqual(status["status"], "simulator")
        selection = gateway.select({})
        self.assertEqual(selection.mode, "deterministic_simulator")

    def test_invalid_ollama_url_is_rejected(self):
        from src.control_plane.connectors.model_gateway import ModelGateway

        with self.assertRaises(ValueError):
            ModelGateway(base_url="http://example.com")
        with self.assertRaises(ValueError):
            ModelGateway(base_url="https://localhost")
        with self.assertRaises(ValueError):
            ModelGateway(base_url="http://user:pass@localhost")
        with self.assertRaises(ValueError):
            ModelGateway(base_url="http://localhost", timeout_seconds=99)

    def test_proposal_digest_changes_with_input(self):
        from src.control_plane.connectors.model_gateway import ModelGateway

        gateway = ModelGateway()
        proposal_a = gateway.propose(
            task="summarize", context={"k": 1}, policy={}
        )
        proposal_b = gateway.propose(
            task="summarize", context={"k": 2}, policy={}
        )
        self.assertNotEqual(proposal_a["proposal_digest"], proposal_b["proposal_digest"])
        self.assertTrue(proposal_a["proposal_digest"].startswith("sha256:"))

    def test_proposal_reports_simulator_disclosure(self):
        from src.control_plane.connectors.model_gateway import ModelGateway

        gateway = ModelGateway()
        proposal = gateway.propose(task="t", context={}, policy={})
        self.assertIn("simulator", proposal["disclosures"][0].lower())


class AgentPlannerTests(unittest.TestCase):
    def setUp(self):
        from src.control_plane.orchestration.agent_planner import AgentPlanner
        from src.control_plane.execution import ToolDefinition, ToolRegistry
        from src.control_plane.governance.policy import PolicyEngine

        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_principal("principal-a", "tenant-a")
        self.registry = ToolRegistry()
        self.policy = PolicyEngine(self.registry.capabilities())
        self.planner = AgentPlanner(registry=self.registry, policy=self.policy, store=self.store)
        from src.control_plane.orchestration.agent_tools import register_agent_tools
        register_agent_tools(self.registry, self.store)

    def tearDown(self):
        self.store.close()

    def _spec(self, allowed=("knowledge.search", "ticket.update")):
        return AgentVersionSpec(
            version="1.0.0",
            system_prompt="",
            allowed_tools=tuple(allowed),
        )

    def test_deterministic_plan_has_two_steps(self):
        plan = self.planner.plan(
            version=self._spec(),
            task="summarize",
            ticket_id="DEMO-1",
            ticket_fields={"status": "open"},
            scopes=frozenset({"workspace:read", "workspace:write", "plan:create"}),
        )
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].tool_id, "knowledge.search")
        self.assertEqual(plan.steps[1].tool_id, "ticket.update")

    def test_verify_rejects_unknown_tools(self):
        spec = AgentVersionSpec(
            version="1.0.0",
            system_prompt="",
            allowed_tools=("knowledge.search", "ticket.update"),
        )
        plan = self.planner.plan(
            version=spec,
            task="t",
            ticket_id="DEMO-1",
            ticket_fields={},
            scopes=frozenset({"workspace:read", "workspace:write", "plan:create"}),
        )
        bad_step = PlanStep(
            step_id="s1",
            tool_id="unknown.tool",
            tool_version="1.0.0",
            risk_tier="R0",
            input={},
        )
        bad_plan = TypedAgentPlan(steps=(bad_step,), disclosures=())
        ok, reasons = self.planner.verify(
            plan=bad_plan,
            version=spec,
            scopes=frozenset({"workspace:read", "workspace:write", "plan:create"}),
        )
        self.assertFalse(ok)
        self.assertTrue(any("tool_unrecognised" in r for r in reasons))

    def test_verify_rejects_missing_scopes(self):
        spec = self._spec()
        plan = self.planner.plan(
            version=spec,
            task="t",
            ticket_id="DEMO-1",
            ticket_fields={},
            scopes=frozenset({"workspace:read"}),
        )
        ok, reasons = self.planner.verify(
            plan=plan,
            version=spec,
            scopes=frozenset({"workspace:read"}),
        )
        self.assertFalse(ok)
        self.assertTrue(any("scope.missing" in r for r in reasons))


class AgentToolsTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_principal("principal-a", "tenant-a")
        from src.control_plane.execution import ToolRegistry
        from src.control_plane.orchestration.agent_tools import register_agent_tools

        self.registry = ToolRegistry()
        register_agent_tools(self.registry, self.store)

    def tearDown(self):
        self.store.close()

    def test_knowledge_search_is_tenant_scoped(self):
        self.store.create_tenant("tenant-b")
        self.store.create_principal("principal-b", "tenant-b")
        self.store._conn().execute(
            "INSERT INTO memory_items(id, tenant_id, principal_id, content, scope, "
            "memory_type, status, created_at) VALUES(?, ?, ?, ?, ?, ?, 'active', ?)",
            ("mem-1", "tenant-a", "principal-a", "hello zasi", "workspace", "fact",
             "2026-09-04T00:00:00+00:00"),
        )
        self.store._conn().execute(
            "INSERT INTO memory_items(id, tenant_id, principal_id, content, scope, "
            "memory_type, status, created_at) VALUES(?, ?, ?, ?, ?, ?, 'active', ?)",
            ("mem-2", "tenant-b", "principal-b", "other tenant", "workspace", "fact",
             "2026-09-04T00:00:00+00:00"),
        )
        from src.control_plane.execution import ToolExecutionContext
        context = ToolExecutionContext(
            tenant_id="tenant-a",
            principal_id="principal-a",
            run_id="run-1",
            action_id="act-1",
        )
        result = self.registry.get("knowledge.search").handler(
            {"query": "zasi", "limit": 5},
            context=context,
            store=self.store,
        )
        self.assertEqual(result["tenant_id"], "tenant-a")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["snippets"][0]["memory_id"], "mem-1")

    def test_knowledge_search_excludes_stale_memory(self):
        self.store._conn().execute(
            "INSERT INTO memory_items(id, tenant_id, principal_id, content, scope, "
            "memory_type, status, fresh_until, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            ("stale-1", "tenant-a", "principal-a", "stale", "workspace", "fact",
             "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"),
        )
        from src.control_plane.execution import ToolExecutionContext
        context = ToolExecutionContext(
            tenant_id="tenant-a",
            principal_id="principal-a",
            run_id="run-1",
            action_id="act-1",
        )
        result = self.registry.get("knowledge.search").handler(
            {"query": "stale"},
            context=context,
            store=self.store,
        )
        self.assertEqual(result["count"], 0)

    def test_ticket_update_is_simulated_and_no_external_call(self):
        from src.control_plane.execution import ToolExecutionContext
        context = ToolExecutionContext(
            tenant_id="tenant-a",
            principal_id="principal-a",
            run_id="run-1",
            action_id="act-1",
            execution_id="exec-1",
            agent_version="1.0.0",
            approval_id="ap-1",
            action_digest="sha256:abc",
        )
        result = self.registry.get("ticket.update").handler(
            {"ticket_id": "DEMO-1", "fields": {"status": "closed"}},
            context=context,
        )
        self.assertTrue(result["simulated"])
        self.assertFalse(result["external_write"])
        self.assertEqual(result["before"]["fields"], {})
        self.assertEqual(result["after"]["fields"], {"status": "closed"})

    def test_ticket_update_requires_approval_context(self):
        from src.control_plane.execution import ToolExecutionContext
        context = ToolExecutionContext(
            tenant_id="tenant-a",
            principal_id="principal-a",
            run_id="run-1",
            action_id="act-1",
        )
        with self.assertRaises(ValueError):
            self.registry.get("ticket.update").handler(
                {"ticket_id": "DEMO-1", "fields": {"status": "closed"}},
                context=context,
            )

    def test_manifest_records_evidence_status_and_side_effects(self):
        knowledge = self.registry.get("knowledge.search").manifest()
        self.assertEqual(knowledge["risk_tier"], "R0")
        self.assertEqual(knowledge["network_egress"], "none")
        self.assertEqual(knowledge["evidence_status"], "verified")
        ticket = self.registry.get("ticket.update").manifest()
        self.assertEqual(ticket["risk_tier"], "R2")
        self.assertIn("simulated_local", ticket["side_effects"])
        self.assertEqual(ticket["network_egress"], "none")


class AgentRuntimeTests(unittest.TestCase):
    def setUp(self):
        import os
        os.environ.setdefault("ZASI_PROFILE", "local")
        os.environ.setdefault("ZASI_HOST", "127.0.0.1")
        os.environ.setdefault("ZASI_PORT", "8080")
        os.environ.setdefault("ZASI_API_KEY", "test-key")
        from src.control_plane.orchestration.agent_runtime import register_agent_runtime
        from src.control_plane.config import Settings
        from src.control_plane.execution import ToolRegistry

        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_principal("principal-a", "tenant-a")
        self.registry = ToolRegistry()
        self.service = register_agent_runtime(
            store=self.store,
            registry=self.registry,
            settings=Settings.from_mapping(),
        )
        self.scopes = frozenset({"workspace:read", "workspace:write", "plan:create", "approval:write"})

    def tearDown(self):
        self.store.close()

    def test_sandbox_does_not_create_execution(self):
        from src.control_plane.orchestration.agent_contracts import AgentCreateRequest, AgentSandboxRequest

        created = self.service.create_agent(
            tenant_id="tenant-a",
            principal_id="principal-a",
            request=AgentCreateRequest.model_validate({"name": "demo"}),
        )
        self.service.publish_version(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            version_id=created["version"]["version_id"],
        )
        result = self.service.sandbox(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            request=AgentSandboxRequest.model_validate(
                {"task": "summarize", "ticket_id": "T-1", "ticket_fields": {"status": "open"}}
            ),
            scopes=self.scopes,
        )
        self.assertTrue(result["sandbox"])
        self.assertEqual(len(self.store.list_agent_executions("tenant-a")), 0)

    def test_start_execution_creates_pending_approval(self):
        from src.control_plane.orchestration.agent_contracts import (
            AgentCreateRequest,
            AgentExecutionRequest,
        )

        created = self.service.create_agent(
            tenant_id="tenant-a",
            principal_id="principal-a",
            request=AgentCreateRequest.model_validate({"name": "demo"}),
        )
        self.service.publish_version(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            version_id=created["version"]["version_id"],
        )
        result = self.service.start_execution(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            request=AgentExecutionRequest.model_validate(
                {"task": "summarize", "ticket_id": "T-1", "ticket_fields": {"status": "open"}}
            ),
            scopes=self.scopes,
            idempotency_key="run-1",
        )
        self.assertEqual(result["execution"]["status"], "awaiting_approval")
        self.assertEqual(result["approval"]["decision"], "pending")

    def test_approval_replay_returns_original(self):
        from src.control_plane.orchestration.agent_contracts import (
            AgentApprovalDecisionRequest,
            AgentCreateRequest,
            AgentExecutionRequest,
        )

        created = self.service.create_agent(
            tenant_id="tenant-a",
            principal_id="principal-a",
            request=AgentCreateRequest.model_validate({"name": "demo"}),
        )
        self.service.publish_version(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            version_id=created["version"]["version_id"],
        )
        first = self.service.start_execution(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            request=AgentExecutionRequest.model_validate(
                {"task": "t", "ticket_id": "T-1", "ticket_fields": {"status": "open"}}
            ),
            scopes=self.scopes,
            idempotency_key="run-2",
        )
        first_resolved = self.service.resolve_approval(
            tenant_id="tenant-a",
            principal_id="principal-a",
            approval_id=first["approval"]["approval_id"],
            request=AgentApprovalDecisionRequest.model_validate({"reason": "ok"}),
            scopes=self.scopes,
        )
        self.assertEqual(first_resolved["approval"]["decision"], "approved")
        first_execution = first_resolved["execution"]
        self.assertEqual(first_execution["status"], "completed")
        # Replay the same approval resolution.
        replay = self.service.resolve_approval(
            tenant_id="tenant-a",
            principal_id="principal-a",
            approval_id=first["approval"]["approval_id"],
            request=AgentApprovalDecisionRequest.model_validate({"reason": "ok"}),
            scopes=self.scopes,
        )
        self.assertTrue(replay.get("replay", False))
        self.assertEqual(replay["approval"]["decision"], "approved")

    def test_rejection_marks_execution_rejected_without_handler(self):
        from src.control_plane.orchestration.agent_contracts import (
            AgentCreateRequest,
            AgentExecutionRequest,
        )

        created = self.service.create_agent(
            tenant_id="tenant-a",
            principal_id="principal-a",
            request=AgentCreateRequest.model_validate({"name": "demo"}),
        )
        self.service.publish_version(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            version_id=created["version"]["version_id"],
        )
        result = self.service.start_execution(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            request=AgentExecutionRequest.model_validate(
                {"task": "t", "ticket_id": "T-1", "ticket_fields": {"status": "open"}}
            ),
            scopes=self.scopes,
            idempotency_key="run-3",
        )
        # Reject through the resolve path with decision rejected.
        resolved = self.service.resolve_approval(
            tenant_id="tenant-a",
            principal_id="principal-a",
            approval_id=result["approval"]["approval_id"],
            request=__import__("src.control_plane.orchestration.agent_contracts", fromlist=["AgentApprovalDecisionRequest"]).AgentApprovalDecisionRequest.model_validate({"reason": "no"}),
            scopes=self.scopes,
        )
        # Re-issuing the resolve on an already-rejected approval replays.
        replay = self.service.resolve_approval(
            tenant_id="tenant-a",
            principal_id="principal-a",
            approval_id=result["approval"]["approval_id"],
            request=__import__("src.control_plane.orchestration.agent_contracts", fromlist=["AgentApprovalDecisionRequest"]).AgentApprovalDecisionRequest.model_validate({"reason": "no"}),
            scopes=self.scopes,
        )
        self.assertTrue(replay.get("replay", False))

    def test_tenant_isolation_in_service(self):
        from src.control_plane.orchestration.agent_contracts import AgentCreateRequest
        from src.control_plane.storage import NotFoundError

        self.service.create_agent(
            tenant_id="tenant-a",
            principal_id="principal-a",
            request=AgentCreateRequest.model_validate({"name": "demo"}),
        )
        with self.assertRaises(NotFoundError):
            self.service.get_agent(tenant_id="tenant-b", agent_id="any")

    def test_idempotency_replay_returns_existing_execution(self):
        from src.control_plane.orchestration.agent_contracts import (
            AgentCreateRequest,
            AgentExecutionRequest,
        )

        created = self.service.create_agent(
            tenant_id="tenant-a",
            principal_id="principal-a",
            request=AgentCreateRequest.model_validate({"name": "demo"}),
        )
        self.service.publish_version(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            version_id=created["version"]["version_id"],
        )
        first = self.service.start_execution(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            request=AgentExecutionRequest.model_validate(
                {"task": "t", "ticket_id": "T-1", "ticket_fields": {"status": "open"}}
            ),
            scopes=self.scopes,
            idempotency_key="run-4",
        )
        second = self.service.start_execution(
            tenant_id="tenant-a",
            principal_id="principal-a",
            agent_id=created["agent"]["agent_id"],
            request=AgentExecutionRequest.model_validate(
                {"task": "t", "ticket_id": "T-1", "ticket_fields": {"status": "open"}}
            ),
            scopes=self.scopes,
            idempotency_key="run-4",
        )
        self.assertTrue(second.get("replay", False))
        self.assertEqual(
            second["execution"]["execution_id"], first["execution"]["execution_id"]
        )


if __name__ == "__main__":
    unittest.main()
