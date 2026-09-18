from datetime import datetime, timedelta, timezone

import pytest

from backend.arin.perception import PerceptionScope, issue_perception_ticket


NOW = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)


def test_ticket_requires_explicit_consent():
    with pytest.raises(PermissionError):
        issue_perception_ticket(
            tenant_id="tenant-a",
            session_id="session-a",
            scopes={PerceptionScope.VOICE},
            consent_granted=False,
            now=NOW,
        )


def test_ticket_is_short_lived_and_session_tenant_bound():
    ticket = issue_perception_ticket(
        tenant_id="tenant-a",
        session_id="session-a",
        scopes={PerceptionScope.VOICE, PerceptionScope.CAMERA},
        consent_granted=True,
        ttl_seconds=60,
        now=NOW,
    )
    assert ticket.is_valid(tenant_id="tenant-a", session_id="session-a", now=NOW)
    assert not ticket.is_valid(tenant_id="tenant-b", session_id="session-a", now=NOW)
    assert not ticket.is_valid(tenant_id="tenant-a", session_id="session-b", now=NOW)
    assert not ticket.is_valid(
        tenant_id="tenant-a", session_id="session-a", now=NOW + timedelta(seconds=60)
    )


def test_ticket_ttl_is_bounded():
    with pytest.raises(ValueError):
        issue_perception_ticket(
            tenant_id="tenant-a",
            session_id="session-a",
            scopes={PerceptionScope.VOICE},
            consent_granted=True,
            ttl_seconds=301,
            now=NOW,
        )


def test_retention_is_opt_in_and_ticket_contains_no_action_authority():
    ticket = issue_perception_ticket(
        tenant_id="tenant-a",
        session_id="session-a",
        scopes={PerceptionScope.SCREEN},
        consent_granted=True,
        now=NOW,
    )
    assert ticket.retain_content is False
    assert set(ticket.__dataclass_fields__) == {
        "ticket",
        "tenant_id",
        "session_id",
        "scopes",
        "issued_at",
        "expires_at",
        "retain_content",
    }
