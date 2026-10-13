from datetime import datetime, timedelta, timezone

import pytest

from backend.arin.perception import (
    PerceptionScope,
    PerceptionSessionState,
    disconnect_perception_ticket,
    issue_perception_ticket,
    revoke_perception_ticket,
)


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
        "state",
        "ended_at",
    }


def test_revocation_invalidates_ticket_and_requires_matching_tenant_session():
    ticket = issue_perception_ticket(
        tenant_id="tenant-a",
        session_id="session-a",
        scopes={PerceptionScope.VOICE},
        consent_granted=True,
        now=NOW,
    )
    with pytest.raises(PermissionError):
        revoke_perception_ticket(ticket, tenant_id="tenant-b", session_id="session-a", now=NOW)
    revoked = revoke_perception_ticket(
        ticket, tenant_id="tenant-a", session_id="session-a", now=NOW + timedelta(seconds=1)
    )
    assert revoked.state is PerceptionSessionState.REVOKED
    assert revoked.ended_at == NOW + timedelta(seconds=1)
    assert not revoked.is_valid(tenant_id="tenant-a", session_id="session-a", now=NOW + timedelta(seconds=1))


def test_disconnect_invalidates_ticket_fail_closed():
    ticket = issue_perception_ticket(
        tenant_id="tenant-a",
        session_id="session-a",
        scopes={PerceptionScope.CAMERA},
        consent_granted=True,
        now=NOW,
    )
    disconnected = disconnect_perception_ticket(
        ticket, tenant_id="tenant-a", session_id="session-a", now=NOW + timedelta(seconds=1)
    )
    assert disconnected.state is PerceptionSessionState.DISCONNECTED
    assert not disconnected.is_valid(
        tenant_id="tenant-a", session_id="session-a", now=NOW + timedelta(seconds=1)
    )


def test_lifecycle_transition_rejects_naive_or_preissue_time():
    ticket = issue_perception_ticket(
        tenant_id="tenant-a",
        session_id="session-a",
        scopes={PerceptionScope.VOICE},
        consent_granted=True,
        now=NOW,
    )
    with pytest.raises(ValueError):
        revoke_perception_ticket(
            ticket, tenant_id="tenant-a", session_id="session-a", now=NOW.replace(tzinfo=None)
        )
    with pytest.raises(ValueError):
        disconnect_perception_ticket(
            ticket,
            tenant_id="tenant-a",
            session_id="session-a",
            now=NOW - timedelta(seconds=1),
        )
