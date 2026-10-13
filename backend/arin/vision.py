"""ARIN camera/vision evidence boundary.

Vision evidence is descriptive only. It carries no command, tool, device, motion,
or actuator authority and is accepted only under an active consent-bound CAMERA
ticket for the same tenant/session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.arin.perception import PerceptionScope, PerceptionSessionTicket


@dataclass(frozen=True)
class VisionEvidence:
    tenant_id: str
    session_id: str
    observation_id: str
    evidence_type: str
    captured_at: datetime
    source_ref: str


def record_vision_evidence(
    *,
    ticket: PerceptionSessionTicket,
    tenant_id: str,
    session_id: str,
    observation_id: str,
    evidence_type: str,
    captured_at: datetime,
    source_ref: str,
    now: datetime | None = None,
) -> VisionEvidence:
    """Validate and bind descriptive camera evidence without granting authority."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or captured_at.tzinfo is None:
        raise ValueError("vision evidence timestamps must be timezone-aware")
    if not ticket.is_valid(tenant_id=tenant_id, session_id=session_id, now=current):
        raise PermissionError("active tenant/session-bound perception ticket is required")
    if PerceptionScope.CAMERA not in ticket.scopes:
        raise PermissionError("camera scope is required")
    if not observation_id or len(observation_id) > 128:
        raise ValueError("observation_id must be between 1 and 128 characters")
    if not evidence_type or len(evidence_type) > 128:
        raise ValueError("evidence_type must be between 1 and 128 characters")
    if not source_ref or len(source_ref) > 512:
        raise ValueError("source_ref must be between 1 and 512 characters")
    if captured_at < ticket.issued_at or captured_at > current:
        raise ValueError("captured_at must fall within the active observation interval")

    return VisionEvidence(
        tenant_id=tenant_id,
        session_id=session_id,
        observation_id=observation_id,
        evidence_type=evidence_type,
        captured_at=captured_at,
        source_ref=source_ref,
    )
