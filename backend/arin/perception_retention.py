"""ARIN-owned retained perception content deletion contract.

This module models deletion authorization only. It deliberately contains no raw
perception payload, provider credential, tool authority, device authority, or
actuator authority. Persistence transports must implement the same fail-closed
checks before deleting durable content.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum


class RetainedContentState(str, Enum):
    RETAINED = "retained"
    DELETED = "deleted"


@dataclass(frozen=True)
class RetainedPerceptionContent:
    content_id: str
    tenant_id: str
    session_id: str
    retained_at: datetime
    state: RetainedContentState = RetainedContentState.RETAINED
    deleted_at: datetime | None = None


def delete_retained_perception_content(
    content: RetainedPerceptionContent,
    *,
    authenticated: bool,
    tenant_id: str,
    session_id: str,
    now: datetime | None = None,
) -> RetainedPerceptionContent:
    """Authorize a durable-content deletion request and fail closed otherwise."""
    if not authenticated:
        raise PermissionError("authentication is required for retained-content deletion")
    if tenant_id != content.tenant_id or session_id != content.session_id:
        raise PermissionError("retained content tenant/session binding mismatch")
    if content.state is not RetainedContentState.RETAINED:
        raise ValueError("retained content is already deleted")
    if not content.content_id or not content.tenant_id or not content.session_id:
        raise ValueError("retained content identity is incomplete")
    if content.retained_at.tzinfo is None:
        raise ValueError("retained_at must be timezone-aware")

    deleted_at = now or datetime.now(timezone.utc)
    if deleted_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if deleted_at < content.retained_at:
        raise ValueError("content cannot be deleted before it was retained")

    return replace(content, state=RetainedContentState.DELETED, deleted_at=deleted_at)
