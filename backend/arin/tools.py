"""Fail-closed ARIN tool capability contracts.

Descriptors declare bounded authority only. They do not execute tools, grant host
permissions, or provide any physical-actuation path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Tuple


class ToolCapabilityError(ValueError):
    """Raised when a capability descriptor violates ARIN's security boundary."""


class OperationClass(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"


class ToolRiskClass(str, Enum):
    LOW = "low"
    PRIVILEGED = "privileged"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ToolCapabilityDescriptor:
    capability_id: str
    version: str
    operation: OperationClass
    risk_class: ToolRiskClass
    filesystem_roots: Tuple[str, ...] = ()
    filesystem_write: bool = False
    network_destinations: Tuple[str, ...] = ()
    subprocess_allowed: bool = False
    required_scopes: FrozenSet[str] = frozenset()
    tenant_bound: bool = True
    session_bound: bool = True
    approval_required: bool = False
    timeout_seconds: float = 10.0
    max_input_bytes: int = 64 * 1024
    max_output_bytes: int = 256 * 1024
    max_retries: int = 0

    def __post_init__(self) -> None:
        if not self.capability_id.strip() or not self.version.strip():
            raise ToolCapabilityError("capability id and version are required")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 30:
            raise ToolCapabilityError("timeout must be within (0, 30] seconds")
        if self.max_input_bytes <= 0 or self.max_output_bytes <= 0:
            raise ToolCapabilityError("input/output bounds must be positive")
        if self.max_retries < 0 or self.max_retries > 3:
            raise ToolCapabilityError("retries must be within [0, 3]")
        if not self.tenant_bound or not self.session_bound:
            raise ToolCapabilityError("ARIN tools must be tenant and session bound")
        if self.filesystem_write and not self.filesystem_roots:
            raise ToolCapabilityError("filesystem write requires explicit roots")
        if self.operation is OperationClass.NETWORK and not self.network_destinations:
            raise ToolCapabilityError("network operation requires explicit destinations")
        if self.operation is OperationClass.EXECUTE and not self.subprocess_allowed:
            raise ToolCapabilityError("execute operation requires explicit subprocess authority")
        if self.risk_class in {ToolRiskClass.PRIVILEGED, ToolRiskClass.CRITICAL} and not self.approval_required:
            raise ToolCapabilityError("privileged/critical capabilities require approval")

    @property
    def filesystem_allowed(self) -> bool:
        return bool(self.filesystem_roots)

    @property
    def network_allowed(self) -> bool:
        return bool(self.network_destinations)


@dataclass(frozen=True)
class ToolExecutionAuthorization:
    policy_allowed: bool
    approval_evidence: str | None = None


def authorize_tool_execution(
    descriptor: ToolCapabilityDescriptor,
    authorization: ToolExecutionAuthorization,
) -> None:
    """Validate policy/approval prerequisites without executing the capability."""
    if not authorization.policy_allowed:
        raise ToolCapabilityError("server-side policy denied capability")
    if descriptor.approval_required and not (authorization.approval_evidence or "").strip():
        raise ToolCapabilityError("approval evidence is required")
