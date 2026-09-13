"""Durable event/outbox primitives used by the authoritative control plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from ..storage import ControlPlaneStore


OutboxHandler = Callable[[Dict[str, object]], None]


class _OutboxConfigurationError(RuntimeError):
    """Raised when a non-reference outbox destination has no adapter."""


@dataclass(frozen=True)
class DispatchReport:
    claimed: int
    delivered: int
    retried: int


def _handler_record(claimed_item: Dict[str, object]) -> Dict[str, object]:
    """Return only non-credential outbox state to an external delivery adapter.

    The claim token is an internal lease credential used exclusively to finish
    the claimed row. Passing it to a handler widens the credential boundary and
    makes accidental logging/telemetry exposure possible. Keep lease ownership
    private to the dispatcher while preserving the identifiers and delivery
    metadata an adapter needs.
    """
    safe_item = dict(claimed_item)
    safe_item.pop("claim_token", None)
    return safe_item


class OutboxDispatcher:
    """Drain committed outbox rows without creating a second domain action.

    The reference profile uses the durable event table as the stream source. The
    dispatcher exists so external sinks can be added behind one retry boundary;
    handlers receive a non-credential outbox record and never receive the
    dispatcher's internal claim token or a raw client callback.
    """

    def __init__(self, store: ControlPlaneStore):
        self.store = store

    def dispatch_once(
        self,
        handler: Optional[OutboxHandler] = None,
        limit: int = 100,
    ) -> DispatchReport:
        claimed = delivered = retried = 0
        for item in self.store.list_claimable_outbox(limit=limit):
            claimed_item = self.store.claim_outbox(item["id"])
            if claimed_item is None:
                continue
            claimed += 1
            try:
                destination = str(claimed_item.get("destination") or "")
                if handler is None and destination != "event_stream":
                    # The durable event table is the reference profile's
                    # stream sink. Any other destination must have an
                    # explicitly configured delivery adapter; acknowledging
                    # it without one would silently lose an external event.
                    raise _OutboxConfigurationError("outbox handler is not configured")
                if handler is not None:
                    handler(_handler_record(claimed_item))
                self.store.finish_outbox(
                    item["id"],
                    success=True,
                    claim_token=str(claimed_item.get("claim_token") or "") or None,
                )
                delivered += 1
            except _OutboxConfigurationError:
                self.store.finish_outbox(
                    item["id"],
                    success=False,
                    error="outbox handler is not configured",
                    claim_token=str(claimed_item.get("claim_token") or "") or None,
                )
                retried += 1
            except Exception:
                self.store.finish_outbox(
                    item["id"],
                    success=False,
                    # Handler exceptions may contain credentials or response
                    # bodies. Persist only a stable operational category.
                    error="outbox handler failed",
                    claim_token=str(claimed_item.get("claim_token") or "") or None,
                )
                retried += 1
        return DispatchReport(claimed=claimed, delivered=delivered, retried=retried)
