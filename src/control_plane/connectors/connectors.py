"""Connector contracts and truthful reference-profile availability.

The registry deliberately does not make network calls. A real adapter must be
registered by a separately governed deployment profile before it can report
anything other than unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


KNOWN_CONNECTORS = ("github", "email", "calendar", "files", "web")


@dataclass(frozen=True)
class ConnectorStatus:
    connector_id: str
    status: str
    configured: bool
    authenticated: bool
    reachable: bool
    last_success_at: Optional[str]
    last_error: Optional[str]
    capabilities: tuple[str, ...]
    disclosure: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "connector_id": self.connector_id,
            "status": self.status,
            "configured": self.configured,
            "authenticated": self.authenticated,
            "reachable": self.reachable,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "capabilities": list(self.capabilities),
            "disclosure": self.disclosure,
        }


class ConnectorRegistry:
    """Return connector health without fabricating source records."""

    def __init__(self, enabled: Optional[Iterable[ConnectorStatus]] = None):
        self._enabled = {
            item.connector_id: item for item in (enabled or ())
        }

    def status(self, connector_id: str) -> ConnectorStatus:
        if connector_id in self._enabled:
            return self._enabled[connector_id]
        return ConnectorStatus(
            connector_id=connector_id,
            status="unavailable",
            configured=False,
            authenticated=False,
            reachable=False,
            last_success_at=None,
            last_error="adapter_not_enabled",
            capabilities=(),
            disclosure=(
                "No governed adapter is enabled in the reference profile; "
                "the source was not queried."
            ),
        )

    def statuses(self, requested: Optional[Iterable[str]] = None) -> List[ConnectorStatus]:
        connector_ids = tuple(requested) if requested is not None else KNOWN_CONNECTORS
        deduplicated = list(dict.fromkeys(connector_ids))
        return [self.status(connector_id) for connector_id in deduplicated if connector_id]
