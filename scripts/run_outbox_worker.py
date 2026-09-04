"""Run the bounded durable control-plane outbox worker."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from typing import Optional, Sequence

from src.control_plane.config import ConfigurationError, Settings
from src.control_plane.storage.postgres_storage import PostgresControlPlaneStore
from src.control_plane.storage import ControlPlaneStore
from src.control_plane.execution.worker import OutboxWorker


def _build_store(settings: Settings):
    if settings.database_backend == "postgresql":
        if not settings.database_url:
            raise ConfigurationError("PostgreSQL profiles require ZASI_DATABASE_URL")
        return PostgresControlPlaneStore(settings.database_url)
    return ControlPlaneStore(settings.database_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll and deliver committed ZASI outbox records."
    )
    parser.add_argument(
        "--worker-id",
        default="zasi-outbox-worker",
        help="bounded operational worker identifier",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="seconds between polls (0 < value <= 3600)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="maximum outbox rows per poll (1..1000)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="process one bounded batch and exit",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings.from_mapping()
        store = _build_store(settings)
        store.initialize()
        stop_event = threading.Event()
        worker = OutboxWorker(
            store=store,
            stop_event=stop_event,
            poll_interval_seconds=args.poll_interval,
            batch_size=args.batch_size,
            worker_id=args.worker_id,
        )

        def request_shutdown(_signum, _frame) -> None:
            worker.request_stop()

        signal.signal(signal.SIGINT, request_shutdown)
        signal.signal(signal.SIGTERM, request_shutdown)
        report = worker.run_forever(max_iterations=1 if args.once else None)
        print(
            json.dumps(
                {
                    "status": "stopped",
                    "worker_id": worker.worker_id,
                    "profile": settings.profile,
                    "database_backend": settings.database_backend,
                    "iterations": report.iterations,
                    "claimed": report.claimed,
                    "delivered": report.delivered,
                    "retried": report.retried,
                },
                sort_keys=True,
            )
        )
        return 0
    except (ConfigurationError, TypeError, ValueError):
        print(
            json.dumps(
                {"status": "failed", "error": "worker_configuration_invalid"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception:
        # Do not expose driver errors, connection strings, or handler payloads
        # from a long-running service command. A supervisor can restart it.
        print(
            json.dumps(
                {"status": "failed", "error": "worker_runtime_unavailable"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if "store" in locals():
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
