from dataclasses import fields

import pytest

from backend.arin.local_voice import (
    LocalVoiceDirection,
    LocalVoiceRequest,
    LocalVoiceResult,
    execute_local_voice,
)
from backend.arin.perception import PerceptionScope, issue_perception_ticket
from tests.test_arin_perception import NOW


def _ticket():
    return issue_perception_ticket(
        tenant_id="tenant-a",
        session_id="session-a",
        scopes={PerceptionScope.VOICE},
        consent_granted=True,
        now=NOW,
    )


def test_local_stt_requires_valid_voice_ticket_and_preserves_identity():
    request = LocalVoiceRequest(
        tenant_id="tenant-a",
        session_id="session-a",
        direction=LocalVoiceDirection.STT,
        payload=b"local-audio",
    )
    result = execute_local_voice(
        request=request,
        ticket=_ticket(),
        now=NOW,
        local_stt=lambda audio: "hello",
    )
    assert result == LocalVoiceResult(
        tenant_id="tenant-a",
        session_id="session-a",
        direction=LocalVoiceDirection.STT,
        content="hello",
    )


def test_local_tts_uses_local_callback_without_provider_credentials():
    request = LocalVoiceRequest(
        tenant_id="tenant-a",
        session_id="session-a",
        direction=LocalVoiceDirection.TTS,
        payload="hello",
    )
    result = execute_local_voice(
        request=request,
        ticket=_ticket(),
        now=NOW,
        local_tts=lambda text: b"local-wave",
    )
    assert result.content == b"local-wave"
    assert "provider" not in {field.name for field in fields(LocalVoiceRequest)}
    assert "credential" not in {field.name for field in fields(LocalVoiceRequest)}


def test_cross_tenant_or_session_voice_fails_closed_before_callback():
    called = False

    def stt(_: bytes) -> str:
        nonlocal called
        called = True
        return "unexpected"

    for tenant_id, session_id in (("tenant-b", "session-a"), ("tenant-a", "session-b")):
        with pytest.raises(PermissionError):
            execute_local_voice(
                request=LocalVoiceRequest(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    direction=LocalVoiceDirection.STT,
                    payload=b"audio",
                ),
                ticket=_ticket(),
                now=NOW,
                local_stt=stt,
            )
    assert called is False


def test_direction_and_payload_type_are_fail_closed():
    with pytest.raises(ValueError):
        execute_local_voice(
            request=LocalVoiceRequest(
                tenant_id="tenant-a",
                session_id="session-a",
                direction=LocalVoiceDirection.STT,
                payload="not-audio",
            ),
            ticket=_ticket(),
            now=NOW,
            local_stt=lambda _: "unexpected",
        )

    with pytest.raises(ValueError):
        execute_local_voice(
            request=LocalVoiceRequest(
                tenant_id="tenant-a",
                session_id="session-a",
                direction=LocalVoiceDirection.TTS,
                payload=b"not-text",
            ),
            ticket=_ticket(),
            now=NOW,
            local_tts=lambda _: b"unexpected",
        )


def test_missing_local_engine_does_not_fall_back_to_cloud():
    with pytest.raises(RuntimeError, match="local STT engine unavailable"):
        execute_local_voice(
            request=LocalVoiceRequest(
                tenant_id="tenant-a",
                session_id="session-a",
                direction=LocalVoiceDirection.STT,
                payload=b"audio",
            ),
            ticket=_ticket(),
            now=NOW,
        )
