from datetime import datetime, timedelta, timezone

import pytest

from backend.arin.perception_retention import (
    RetainedContentState,
    RetainedPerceptionContent,
    delete_retained_perception_content,
)


NOW = datetime(2026, 9, 18, 14, 0, tzinfo=timezone.utc)


def retained_content() -> RetainedPerceptionContent:
    return RetainedPerceptionContent(
        content_id="content-a",
        tenant_id="tenant-a",
        session_id="session-a",
        retained_at=NOW,
    )


def test_deletion_requires_authentication():
    with pytest.raises(PermissionError):
        delete_retained_perception_content(
            retained_content(),
            authenticated=False,
            tenant_id="tenant-a",
            session_id="session-a",
            now=NOW + timedelta(seconds=1),
        )


@pytest.mark.parametrize(
    ("tenant_id", "session_id"),
    [("tenant-b", "session-a"), ("tenant-a", "session-b")],
)
def test_deletion_fails_closed_for_cross_tenant_or_cross_session(tenant_id, session_id):
    with pytest.raises(PermissionError):
        delete_retained_perception_content(
            retained_content(),
            authenticated=True,
            tenant_id=tenant_id,
            session_id=session_id,
            now=NOW + timedelta(seconds=1),
        )


def test_authorized_deletion_records_tombstone_without_payload_or_authority():
    deleted = delete_retained_perception_content(
        retained_content(),
        authenticated=True,
        tenant_id="tenant-a",
        session_id="session-a",
        now=NOW + timedelta(seconds=1),
    )
    assert deleted.state is RetainedContentState.DELETED
    assert deleted.deleted_at == NOW + timedelta(seconds=1)
    assert set(deleted.__dataclass_fields__) == {
        "content_id",
        "tenant_id",
        "session_id",
        "retained_at",
        "state",
        "deleted_at",
    }


def test_repeated_deletion_fails_closed():
    deleted = delete_retained_perception_content(
        retained_content(),
        authenticated=True,
        tenant_id="tenant-a",
        session_id="session-a",
        now=NOW + timedelta(seconds=1),
    )
    with pytest.raises(ValueError):
        delete_retained_perception_content(
            deleted,
            authenticated=True,
            tenant_id="tenant-a",
            session_id="session-a",
            now=NOW + timedelta(seconds=2),
        )


def test_deletion_rejects_naive_or_pre_retention_time():
    with pytest.raises(ValueError):
        delete_retained_perception_content(
            retained_content(),
            authenticated=True,
            tenant_id="tenant-a",
            session_id="session-a",
            now=NOW.replace(tzinfo=None),
        )
    with pytest.raises(ValueError):
        delete_retained_perception_content(
            retained_content(),
            authenticated=True,
            tenant_id="tenant-a",
            session_id="session-a",
            now=NOW - timedelta(seconds=1),
        )
