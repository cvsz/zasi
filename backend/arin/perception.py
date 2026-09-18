"""ARIN-owned consent-bound voice/perception session contracts.

This module deliberately grants no tool, command, device, or actuator authority.
Tickets are short-lived server-side capabilities and must not contain provider
or service credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from secrets import token_urlsafe


class PerceptionScope(str, Enum):
    VOICE = "voice"
    CAMERA = "camera"
    SCREEN = "screen"


@dataclass(frozen=True)
class PerceptionSessionTicket:
    ticket: str
    tenant_id: str
    session_id: str
    scopes: frozenset[PerceptionScope]
    issued_at: datetime
    expires_at: datetime
    retain_content: bool = False

    def is_valid(self, *, tenant_id: str, session_id: str, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return (
            bool(self.ticket)
            and tenant_id == self.tenant_id
            and session_id == self.session_id
            and self.issued_at <= current < self.expires_at
        )


def issue_perception_ticket(
    *,
    tenant_id: str,
    session_id: str,
    scopes: set[PerceptionScope] | frozenset[PerceptionScope],
    consent_granted: bool,
    ttl_seconds: int = 60,
    retain_content: bool = False,
    now: datetime | None = None,
) -> PerceptionSessionTicket:
    """Issue a bounded ticket only after explicit consent.

    Durable retention is opt-in and is represented separately from consent to
    perceive. Callers must implement deletion/retention policy before storing
    raw audio, images, screen content, or derived transcripts durably.
    """
    if not consent_granted:
        raise PermissionError("explicit perception consent is required")
    if not tenant_id or not session_id:
        raise ValueError("tenant_id and session_id are required")
    bounded_scopes = frozenset(scopes)
    if not bounded_scopes:
        raise ValueError("at least one perception scope is required")
    if ttl_seconds < 1 or ttl_seconds > 300:
        raise ValueError("ticket ttl must be between 1 and 300 seconds")

    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    return PerceptionSessionTicket(
        ticket=token_urlsafe(32),
        tenant_id=tenant_id,
        session_id=session_id,
        scopes=bounded_scopes,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
        retain_content=retain_content,
    )
