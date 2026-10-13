"""ARIN v1 vendor-neutral contract primitives.

This module defines the smallest stable versioned envelope shared by future
ARIN domain contracts. It intentionally grants no execution or actuator
authority.
"""

from typing import Literal

from pydantic import Field

from .contracts import StrictModel


ARIN_CONTRACT_VERSION = "arin.v1"
ArinContractVersion = Literal["arin.v1"]


class ArinContractEnvelope(StrictModel):
    """Tenant/session-bound envelope for canonical ARIN v1 payloads."""

    contract_version: ArinContractVersion = ARIN_CONTRACT_VERSION
    tenant_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
