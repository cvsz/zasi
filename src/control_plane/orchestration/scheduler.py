"""Bounded durable schedule poller.

The poller only claims repository work. Executing a claimed task remains the
responsibility of a separately governed worker and cannot be inferred from a
successful poll.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class DurableScheduler:
    """Poll due schedules and atomically acquire their task-run leases."""

    def __init__(self, store: Any, worker_id: str, lease_seconds: int = 60):
        self.store = store
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    def poll(
        self,
        tenant_id: str,
        now: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("tenant_id is required")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        now_dt = datetime.now(timezone.utc) if now is None else now
        if now_dt.tzinfo is None:
            raise ValueError("now must include a timezone")
        now_value = _timestamp(now_dt)
        claims: List[Dict[str, Any]] = []
        schedules = self.store.list_schedules(tenant_id, status="active", limit=limit)
        for schedule in schedules:
            if schedule["next_run_at"] > now_value:
                break
            claim = self.store.claim_due_schedule(
                schedule_id=schedule["schedule_id"],
                tenant_id=tenant_id,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
                now=now_dt,
            )
            if claim is not None:
                claims.append(claim)
        return claims
