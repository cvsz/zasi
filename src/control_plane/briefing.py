"""Source-backed executive brief aggregation for the governed local slice."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from .connectors import ConnectorRegistry


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class BriefingAggregator:
    """Build a bounded brief from repository state and connector health.

    The aggregator is intentionally deterministic and read-only with respect
    to domain state. Persisting the resulting brief remains an explicit API
    operation, and every generated claim carries a source/evidence reference.
    """

    def __init__(self, store: Any, connectors: Optional[ConnectorRegistry] = None):
        self.store = store
        self.connectors = connectors or ConnectorRegistry()

    @staticmethod
    def _evidence(
        source_ref: str,
        status: str,
        observed_at: Optional[str],
        fresh_until: Optional[str],
        disclosure: str,
    ) -> Dict[str, Any]:
        return {
            "source_ref": source_ref,
            "status": status,
            "observed_at": observed_at,
            "fresh_until": fresh_until,
            "disclosure": disclosure,
        }

    @staticmethod
    def _claim(
        claim_id: str,
        text: str,
        evidence: Dict[str, Any],
        kind: str = "confirmed",
    ) -> Dict[str, Any]:
        return {
            "claim_id": claim_id,
            "text": text,
            "kind": kind,
            "evidence": [evidence],
        }

    @staticmethod
    def _safe_error(error: Any) -> Dict[str, Any]:
        """Expose only bounded error classification, never worker error text."""
        if not isinstance(error, dict):
            return {}
        safe: Dict[str, Any] = {}
        code = error.get("code")
        if isinstance(code, str) and 0 < len(code) <= 64 and all(
            char.isalnum() or char in "._:-" for char in code
        ):
            safe["code"] = code
        if isinstance(error.get("retryable"), bool):
            safe["retryable"] = error["retryable"]
        return safe

    def build(
        self,
        tenant_id: str,
        principal_id: str,
        sources: Optional[Iterable[str]] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        now_dt = datetime.now(timezone.utc) if now is None else now
        if now_dt.tzinfo is None:
            raise ValueError("now must include a timezone")
        now_dt = now_dt.astimezone(timezone.utc)
        observed_at = _timestamp(now_dt)
        fresh_until = _timestamp(now_dt + timedelta(minutes=5))
        control_source = f"control-plane://tenant/{tenant_id}"
        control_evidence = self._evidence(
            control_source,
            "verified_local",
            observed_at,
            fresh_until,
            "Read from the authenticated tenant-scoped control-plane repository.",
        )

        goals = self.store.list_goals(tenant_id, limit=1000)
        completed: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        blocked: List[Dict[str, Any]] = []
        today: List[Dict[str, Any]] = []
        claims: List[Dict[str, Any]] = []
        for goal in goals:
            tasks = self.store.list_tasks(goal["goal_id"], tenant_id, limit=1000)
            task_by_id = {task["task_id"]: task for task in tasks}
            for task in tasks:
                dependencies_pending = [
                    dependency_id
                    for dependency_id in task["dependencies"]
                    if task_by_id.get(dependency_id, {}).get("status") != "completed"
                ]
                task_source = f"{control_source}/task/{task['task_id']}"
                task_evidence = self._evidence(
                    task_source,
                    "verified_local",
                    observed_at,
                    fresh_until,
                    "Task state and dependency edges were read from durable repository state.",
                )
                if dependencies_pending and task["status"] not in {"completed", "failed"}:
                    item = {
                        "goal_id": goal["goal_id"],
                        "task_id": task["task_id"],
                        "title": task["title"],
                        "status": "blocked",
                        "blocked_by": dependencies_pending,
                        "evidence": [task_evidence],
                    }
                    blocked.append(item)
                    claims.append(
                        self._claim(
                            f"blocked:{task['task_id']}",
                            f"Task {task['title']} is blocked by unfinished dependencies.",
                            task_evidence,
                        )
                    )
                if task["status"] in {"queued", "running", "retry"}:
                    item = {
                        "goal_id": goal["goal_id"],
                        "task_id": task["task_id"],
                        "title": task["title"],
                        "status": task["status"],
                        "evidence": [task_evidence],
                    }
                    today.append(item)
                for run in self.store.list_task_runs(task["task_id"], tenant_id, limit=100):
                    run_evidence = self._evidence(
                        f"{control_source}/task-run/{run['run_id']}",
                        "verified_local",
                        run["finished_at"] or run["started_at"] or observed_at,
                        fresh_until,
                        "Task-run status was read from durable execution history.",
                    )
                    if run["status"] == "succeeded":
                        item = {
                            "goal_id": goal["goal_id"],
                            "task_id": task["task_id"],
                            "run_id": run["run_id"],
                            "title": task["title"],
                            "status": run["status"],
                            "evidence": [run_evidence],
                        }
                        completed.append(item)
                        claims.append(
                            self._claim(
                                f"completed:{run['run_id']}",
                                f"Task {task['title']} completed successfully.",
                                run_evidence,
                            )
                        )
                    elif run["status"] in {"failed", "dead_lettered"}:
                        item = {
                            "goal_id": goal["goal_id"],
                            "task_id": task["task_id"],
                            "run_id": run["run_id"],
                            "title": task["title"],
                            "status": run["status"],
                            "error": self._safe_error(run["error"]),
                            "evidence": [run_evidence],
                        }
                        failed.append(item)
                        claims.append(
                            self._claim(
                                f"failed:{run['run_id']}",
                                f"Task {task['title']} requires attention after a failed run.",
                                run_evidence,
                            )
                        )

        pending_approvals = []
        for approval in self.store.list_pending_approvals(tenant_id, limit=100):
            approval_evidence = self._evidence(
                approval["source_ref"],
                "verified_local",
                approval["observed_at"],
                approval["expires_at"],
                "Approval state was read from the tenant-scoped plans repository.",
            )
            pending_approvals.append({**approval, "evidence": [approval_evidence]})
            claims.append(
                self._claim(
                    f"approval:{approval['plan_id']}",
                    f"Plan {approval['plan_id']} is waiting for approval.",
                    approval_evidence,
                )
            )

        connector_statuses = self.connectors.statuses(sources)
        missing_sources: List[Dict[str, Any]] = []
        source_freshness: Dict[str, Dict[str, Any]] = {"control-plane": control_evidence}
        for status in connector_statuses:
            status_record = status.as_dict()
            source_freshness[status.connector_id] = status_record
            if status.status != "available":
                missing = {
                    "source_ref": status.connector_id,
                    "status": status.status,
                    "observed_at": status.last_success_at,
                    "fresh_until": None,
                    "disclosure": status.disclosure,
                }
                missing_sources.append(missing)
                claims.append(
                    self._claim(
                        f"connector:{status.connector_id}",
                        f"Connector {status.connector_id} is unavailable.",
                        self._evidence(
                            status.connector_id,
                            status.status,
                            status.last_success_at,
                            None,
                            status.disclosure,
                        ),
                        kind="availability",
                    )
                )

        priorities = [
            {
                "goal_id": goal["goal_id"],
                "title": goal["title"],
                "priority": goal["priority"],
                "status": goal["status"],
                "evidence": [control_evidence],
            }
            for goal in goals
            if goal["status"] == "active"
        ]
        priorities.sort(key=lambda item: (item["priority"], item["goal_id"]))
        status = "complete" if not missing_sources else "partial"
        return {
            "status": status,
            "brief_id": None,
            "generated_at": observed_at,
            "coverage": {
                "from": _timestamp(now_dt - timedelta(hours=12)),
                "to": observed_at,
            },
            "completed": completed,
            "failed": failed,
            "blocked": blocked,
            "pending_approvals": pending_approvals,
            "today": today,
            "important_messages": [],
            "repository_changes": [],
            "system_alerts": failed,
            "priorities": priorities,
            "risks": blocked + failed + pending_approvals,
            "claims": claims,
            "source_freshness": source_freshness,
            "missing_sources": missing_sources,
            "disclosure": (
                "This brief contains only authenticated local control-plane state. "
                "Unavailable connector sources were not queried and have no invented values."
            ),
        }
