"""Bounded, transport-neutral ARIN contract for a future ZCoder adapter.

This module validates request/response envelopes only. It does not connect to
ZCoder, execute tools, grant filesystem/network/subprocess authority, or expose
any physical-actuation path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class ToolAdapterError(ValueError):
    """Raised when an adapter envelope violates ARIN's fail-closed contract."""


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolAdapterError(f"{name} is required")
    return value


@dataclass(frozen=True)
class ToolAdapterRequest:
    capability_id: str
    capability_version: str
    tenant_id: str
    session_id: str
    request_id: str
    operation: str
    payload: Mapping[str, Any]
    timeout_seconds: float = 10.0
    service_token: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in (
            "capability_id",
            "capability_version",
            "tenant_id",
            "session_id",
            "request_id",
            "operation",
        ):
            _required(getattr(self, name), name)
        if not isinstance(self.payload, Mapping):
            raise ToolAdapterError("payload must be a mapping")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool):
            raise ToolAdapterError("timeout must be numeric")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 30:
            raise ToolAdapterError("timeout must be within (0, 30] seconds")


@dataclass(frozen=True)
class ToolAdapterResponse:
    tenant_id: str
    session_id: str
    request_id: str
    result: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in ("tenant_id", "session_id", "request_id"):
            _required(getattr(self, name), name)
        if not isinstance(self.result, Mapping):
            raise ToolAdapterError("result must be a mapping")

    def validate_for(self, request: ToolAdapterRequest) -> None:
        if self.tenant_id != request.tenant_id:
            raise ToolAdapterError("response tenant does not match request")
        if self.session_id != request.session_id:
            raise ToolAdapterError("response session does not match request")
        if self.request_id != request.request_id:
            raise ToolAdapterError("response request id does not match request")
