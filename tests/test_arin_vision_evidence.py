from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from backend.arin.perception import PerceptionScope, issue_perception_ticket, revoke_perception_ticket
from backend.arin.vision import VisionEvidence, record_vision_evidence


NOW = datetime(2026, 9, 19, 1, 0, tzinfo=timezone.utc)


def camera_ticket():
    return issue_perception_ticket(
        tenant_id="tenant-a",
        session_id="session-a",
        scopes={PerceptionScope.CAMERA},
        consent_granted=True,
        ttl_seconds=60,
        now=NOW,
    )


def test_camera_evidence_requires_active_bound_camera_ticket():
    ticket = camera_ticket()
    evidence = record_vision_evidence(
        ticket=ticket,
        tenant_id="tenant-a",
        session_id="session-a",
        observation_id="obs-1",
        evidence_type="object-detection",
        captured_at=NOW + timedelta(seconds=1),
        source_ref="frame:sha256:abc123",
        now=NOW + timedelta(seconds=2),
    )
    assert evidence.tenant_id == "tenant-a"
    assert evidence.session_id == "session-a"
    assert evidence.observation_id == "obs-1"


@pytest.mark.parametrize(
    ("tenant_id", "session_id"),
    [("tenant-b", "session-a"), ("tenant-a", "session-b")],
)
def test_camera_evidence_rejects_cross_boundary_access(tenant_id, session_id):
    with pytest.raises(PermissionError):
        record_vision_evidence(
            ticket=camera_ticket(),
            tenant_id=tenant_id,
            session_id=session_id,
            observation_id="obs-1",
            evidence_type="object-detection",
            captured_at=NOW,
            source_ref="frame:sha256:abc123",
            now=NOW,
        )


def test_camera_evidence_rejects_missing_scope_expired_or_revoked_ticket():
    voice_ticket = issue_perception_ticket(
        tenant_id="tenant-a",
        session_id="session-a",
        scopes={PerceptionScope.VOICE},
        consent_granted=True,
        now=NOW,
    )
    with pytest.raises(PermissionError):
        record_vision_evidence(
            ticket=voice_ticket,
            tenant_id="tenant-a",
            session_id="session-a",
            observation_id="obs-1",
            evidence_type="object-detection",
            captured_at=NOW,
            source_ref="frame:sha256:abc123",
            now=NOW,
        )

    expired = camera_ticket()
    with pytest.raises(PermissionError):
        record_vision_evidence(
            ticket=expired,
            tenant_id="tenant-a",
            session_id="session-a",
            observation_id="obs-2",
            evidence_type="object-detection",
            captured_at=NOW,
            source_ref="frame:sha256:def456",
            now=NOW + timedelta(seconds=60),
        )

    revoked = revoke_perception_ticket(
        camera_ticket(), tenant_id="tenant-a", session_id="session-a", now=NOW + timedelta(seconds=1)
    )
    with pytest.raises(PermissionError):
        record_vision_evidence(
            ticket=revoked,
            tenant_id="tenant-a",
            session_id="session-a",
            observation_id="obs-3",
            evidence_type="object-detection",
            captured_at=NOW,
            source_ref="frame:sha256:ghi789",
            now=NOW + timedelta(seconds=2),
        )


def test_camera_evidence_rejects_invalid_time_and_unbounded_fields():
    ticket = camera_ticket()
    with pytest.raises(ValueError):
        record_vision_evidence(
            ticket=ticket,
            tenant_id="tenant-a",
            session_id="session-a",
            observation_id="obs-1",
            evidence_type="object-detection",
            captured_at=NOW.replace(tzinfo=None),
            source_ref="frame:sha256:abc123",
            now=NOW,
        )
    with pytest.raises(ValueError):
        record_vision_evidence(
            ticket=ticket,
            tenant_id="tenant-a",
            session_id="session-a",
            observation_id="obs-1",
            evidence_type="x" * 129,
            captured_at=NOW,
            source_ref="frame:sha256:abc123",
            now=NOW,
        )


def test_vision_evidence_schema_grants_no_action_or_actuator_authority():
    assert {field.name for field in fields(VisionEvidence)} == {
        "tenant_id",
        "session_id",
        "observation_id",
        "evidence_type",
        "captured_at",
        "source_ref",
    }
