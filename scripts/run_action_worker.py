"""Run the bounded, code-owned ZASI action worker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import threading
from typing import Optional, Sequence

# Allow the checked-in CLI to run directly from a source checkout without
# requiring an editable install.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from src.control_plane.config import ConfigurationError, Settings
from src.control_plane.execution import ActionWorker
from src.control_plane.storage.postgres_storage import PostgresControlPlaneStore
from src.control_plane.storage import ControlPlaneStore


def _build_store(settings: Settings):
    if settings.database_backend == "postgresql":
        if not settings.database_url:
            raise ConfigurationError("PostgreSQL profiles require ZASI_DATABASE_URL")
        return PostgresControlPlaneStore(settings.database_url)
    return ControlPlaneStore(settings.database_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Claim and execute bounded, code-owned ZASI actions."
    )
    parser.add_argument(
        "--worker-id",
        default="zasi-action-worker",
        help="bounded operational worker identifier",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="seconds between polls (0 < value <= 3600)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="process at most one claim and exit",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if not 0 < args.poll_interval <= 3600:
        print(
            json.dumps(
                {"status": "failed", "error": "worker_configuration_invalid"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        settings = Settings.from_mapping()
        store = _build_store(settings)
        application = create_app(settings=settings, store=store)
        store.initialize()
        store.create_tenant("local")
        store.create_principal("local-operator", "local")
        for definition in application.state.registry.definitions():
            store.upsert_capability(definition.manifest())
        stop_event = threading.Event()
        worker = ActionWorker(
            store=store,
            registry=application.state.registry,
            worker_id=args.worker_id,
        )

        def request_shutdown(_signum, _frame) -> None:
            stop_event.set()

        signal.signal(signal.SIGINT, request_shutdown)
        signal.signal(signal.SIGTERM, request_shutdown)
        iterations = processed = 0
        while not stop_event.is_set():
            result = worker.run_once("local")
            iterations += 1
            if result is not None:
                processed += 1
            if args.once:
                break
            if stop_event.wait(args.poll_interval):
                break
        print(
            json.dumps(
                {
                    "status": "stopped",
                    "worker_id": worker.worker_id,
                    "profile": settings.profile,
                    "database_backend": settings.database_backend,
                    "iterations": iterations,
                    "processed": processed,
                    "allowed_risk_tiers": ["R0", "R1"],
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
        print(
            json.dumps(
                {"status": "failed", "error": "worker_runtime_unavailable"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if "application" in locals():
            runtime = getattr(application.state, "redis_runtime", None)
            if runtime is not None:
                runtime.close()
        if "store" in locals():
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
