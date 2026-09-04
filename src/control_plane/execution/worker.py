"""Bounded worker loop for durable control-plane outbox delivery."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Optional

from ..events import DispatchReport, OutboxDispatcher, OutboxHandler


@dataclass(frozen=True)
class WorkerReport:
    """Cumulative delivery counts for one bounded worker invocation."""

    iterations: int
    claimed: int
    delivered: int
    retried: int


class OutboxWorker:
    """Poll and deliver committed outbox records until explicitly stopped.

    The worker owns no domain authorization and never executes a task or
    connector by itself. It only claims durable outbox rows and delegates
    delivery to the configured handler. In the reference profile,
    ``event_stream`` is already durable in the events table and may be
    acknowledged without an external handler; every other destination fails
    closed when no handler is configured.
    """

    def __init__(
        self,
        store: Any,
        handler: Optional[OutboxHandler] = None,
        stop_event: Optional[threading.Event] = None,
        poll_interval_seconds: float = 1.0,
        batch_size: int = 100,
        worker_id: str = "zasi-outbox-worker",
    ):
        if (
            not isinstance(worker_id, str)
            or not worker_id
            or len(worker_id) > 128
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in worker_id)
        ):
            raise ValueError("worker_id must be non-empty and bounded")
        if isinstance(poll_interval_seconds, bool):
            raise ValueError("poll_interval_seconds must be positive")
        try:
            interval = float(poll_interval_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("poll_interval_seconds must be positive") from exc
        if not 0 < interval <= 3600:
            raise ValueError("poll_interval_seconds must be between 0 and 3600")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        if handler is not None and not callable(handler):
            raise TypeError("handler must be callable")
        self.store = store
        self.worker_id = worker_id
        self.handler = handler
        self.stop_event = stop_event or threading.Event()
        self.poll_interval_seconds = interval
        self.batch_size = batch_size
        self.dispatcher = OutboxDispatcher(store)

    def request_stop(self) -> None:
        """Request an interruptible shutdown after the current delivery."""

        self.stop_event.set()

    def _handle_item(self, item: dict[str, object]) -> None:
        """Invoke the handler with bounded worker identity metadata."""

        if self.handler is None:
            return
        enriched_item = dict(item)
        enriched_item["worker_id"] = self.worker_id
        self.handler(enriched_item)

    def run_once(self) -> DispatchReport:
        """Claim and process one bounded batch of durable outbox rows."""

        return self.dispatcher.dispatch_once(
            handler=self._handle_item if self.handler is not None else None,
            limit=self.batch_size,
        )

    def run_forever(self, max_iterations: Optional[int] = None) -> WorkerReport:
        """Poll until stopped, optionally bounding iterations for validation.

        Storage failures are intentionally allowed to propagate to the process
        supervisor. Continuing to spin after a durable-store failure can hide
        queue loss and produce misleading health signals.
        """

        if max_iterations is not None and (
            isinstance(max_iterations, bool)
            or not isinstance(max_iterations, int)
            or max_iterations < 0
        ):
            raise ValueError("max_iterations must be a non-negative integer")

        iterations = claimed = delivered = retried = 0
        while not self.stop_event.is_set():
            if max_iterations is not None and iterations >= max_iterations:
                break
            report = self.run_once()
            iterations += 1
            claimed += report.claimed
            delivered += report.delivered
            retried += report.retried
            if max_iterations is not None and iterations >= max_iterations:
                break
            if self.stop_event.wait(self.poll_interval_seconds):
                break
        return WorkerReport(
            iterations=iterations,
            claimed=claimed,
            delivered=delivered,
            retried=retried,
        )
