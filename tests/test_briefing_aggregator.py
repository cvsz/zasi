import datetime as dt
import unittest

from src.control_plane.briefing import BriefingAggregator
from src.control_plane.connectors import ConnectorRegistry
from src.control_plane.storage import ControlPlaneStore


class BriefingAggregatorTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_principal("principal-a", "tenant-a")
        self.store.create_goal("goal-a", "tenant-a", "principal-a", "Prepare brief")

    def tearDown(self):
        self.store.close()

    def test_brief_uses_durable_state_and_marks_missing_connectors(self):
        # Add the dependency after the task so the fixture can construct a blocked DAG
        # with the same repository validation used by the API.
        self.store.close()
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_principal("principal-a", "tenant-a")
        self.store.create_goal("goal-a", "tenant-a", "principal-a", "Prepare brief")
        self.store.create_task(
            "task-source",
            "goal-a",
            "tenant-a",
            "principal-a",
            "Source task",
            "Observe a local source.",
            "brief-source",
        )
        self.store.create_task(
            "task-a",
            "goal-a",
            "tenant-a",
            "principal-a",
            "Blocked task",
            "Wait for the source task.",
            "brief-task-a",
            depends_on=["task-source"],
        )
        now = dt.datetime(2026, 9, 2, 9, 0, tzinfo=dt.timezone.utc)
        brief = BriefingAggregator(
            self.store, ConnectorRegistry()
        ).build(
            tenant_id="tenant-a",
            principal_id="principal-a",
            sources=["github", "calendar"],
            now=now,
        )

        self.assertEqual(brief["status"], "partial")
        self.assertEqual(len(brief["blocked"]), 1)
        self.assertEqual(brief["blocked"][0]["task_id"], "task-a")
        self.assertEqual(
            {item["source_ref"] for item in brief["missing_sources"]},
            {"github", "calendar"},
        )
        self.assertTrue(brief["source_freshness"]["control-plane"]["observed_at"])
        self.assertTrue(brief["claims"])
        for claim in brief["claims"]:
            self.assertTrue(claim["evidence"])
            self.assertTrue(claim["evidence"][0]["source_ref"])

    def test_failed_task_run_and_pending_approval_are_explicit(self):
        self.store.create_task(
            "task-fail",
            "goal-a",
            "tenant-a",
            "principal-a",
            "Failure task",
            "Fail once.",
            "brief-failure",
            max_attempts=1,
        )
        claimed = self.store.claim_due_task("task-fail", "tenant-a", "worker-a")
        self.store.complete_task_run(
            claimed["task_run_id"],
            "tenant-a",
            "worker-a",
            claimed["lease_token"],
            status="failed",
            result={},
            error={"code": "source_failed", "message": "do-not-expose-secret"},
        )
        self.store.create_intent(
            "intent-a",
            "tenant-a",
            "principal-a",
            "text",
            "needs approval",
            '{"verb":"observe"}',
            "assist",
            "R2",
        )
        self.store.create_plan(
            "plan-a",
            "tenant-a",
            "principal-a",
            "intent-a",
            "sha256:" + "a" * 64,
            "[]",
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
            status="awaiting_approval",
        )
        brief = BriefingAggregator(self.store, ConnectorRegistry()).build(
            "tenant-a", "principal-a", now=dt.datetime.now(dt.timezone.utc)
        )
        self.assertEqual(brief["failed"][0]["status"], "dead_lettered")
        self.assertNotIn("do-not-expose-secret", str(brief))
        self.assertEqual(brief["pending_approvals"][0]["plan_id"], "plan-a")
