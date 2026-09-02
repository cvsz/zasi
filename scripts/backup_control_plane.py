#!/usr/bin/env python3
"""Create, validate, and explicitly restore encrypted control-plane backups.

The backup key is read from ``ZASI_BACKUP_KEY_B64`` so a secret provider can
inject it at process start. It is never written to the backup or printed by
this command. Restore is destructive only when ``--replace`` is supplied.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from dataclasses import asdict
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Optional, Sequence, Tuple
from urllib.parse import quote, unquote, urlsplit, urlunsplit

# Allow the checked-in CLI to run directly from a source checkout without
# requiring an editable install.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.control_plane.backup import (
    BackupError,
    BackupMetadata,
    decrypt_file,
    encrypt_file,
    open_sealed,
)
from src.control_plane.postgres_storage import PostgresControlPlaneStore
from src.control_plane.storage import ControlPlaneStore


def _read_backup_key() -> bytes:
    profile = os.environ.get("ZASI_PROFILE", "local").strip().lower()
    provider = os.environ.get("ZASI_SECRET_PROVIDER", "environment").strip().lower()
    if profile in {"staging", "production"} and provider in {"", "environment"}:
        raise BackupError(
            "staging and production backup keys require an external secret provider"
        )
    encoded = os.environ.get("ZASI_BACKUP_KEY_B64", "").strip()
    if not encoded:
        raise BackupError("ZASI_BACKUP_KEY_B64 must be injected by the secret provider")
    try:
        key = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise BackupError("ZASI_BACKUP_KEY_B64 is not valid base64") from exc
    if len(key) != 32:
        raise BackupError("ZASI_BACKUP_KEY_B64 must decode to exactly 32 bytes")
    return key


def _ensure_parent(path: Path) -> None:
    parent = path.expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not parent.is_dir():
        raise BackupError("backup destination parent must be a directory")


def _metadata_report(metadata: BackupMetadata, **extra: Any) -> str:
    report = asdict(metadata)
    report.update(extra)
    return json.dumps(report, sort_keys=True)


def _source_for_backend(
    backend: str, source: Optional[str], database_url: Optional[str]
):
    if backend == "sqlite":
        path = source or os.environ.get("ZASI_DATABASE_PATH", "")
        if not path:
            raise BackupError("SQLite backup requires --source or ZASI_DATABASE_PATH")
        source_path = Path(path).expanduser().resolve()
        if not source_path.is_file():
            raise BackupError("SQLite source must be an existing regular file")
        store = ControlPlaneStore(str(source_path))
        try:
            store.initialize()
        except Exception as exc:
            store.close()
            raise BackupError("SQLite source is unavailable") from exc
        return store
    url = database_url or os.environ.get("ZASI_DATABASE_URL", "")
    if not url or not url.startswith(("postgresql://", "postgres://")):
        raise BackupError("PostgreSQL backup requires a PostgreSQL database URL")
    store = PostgresControlPlaneStore(url)
    try:
        store.initialize()
    except Exception as exc:
        store.close()
        raise BackupError("PostgreSQL source is unavailable") from exc
    return store


def create_backup(args: argparse.Namespace) -> int:
    key = _read_backup_key()
    destination = Path(args.destination).expanduser().resolve()
    _ensure_parent(destination)
    with tempfile.TemporaryDirectory(prefix="zasi-backup-") as directory:
        raw_path = Path(directory) / (
            "control-plane.dump" if args.backend == "postgresql" else "control-plane.db"
        )
        store = _source_for_backend(args.backend, args.source, args.database_url)
        try:
            try:
                schema_version = store.schema_version()
                store.backup_to(str(raw_path))
            except Exception as exc:
                raise BackupError("database backup failed") from exc
        finally:
            store.close()
        metadata = encrypt_file(
            raw_path,
            destination,
            backend=args.backend,
            schema_version=schema_version,
            key=key,
        )
    print(_metadata_report(metadata, operation="create", destination=str(destination)))
    return 0


def _validate_sqlite(raw_path: Path, expected_schema_version: int) -> None:
    store = ControlPlaneStore(str(raw_path))
    try:
        try:
            store.initialize()
            if store.schema_version() != expected_schema_version:
                raise BackupError(
                    "SQLite backup schema version does not match its envelope"
                )
            if not store.integrity_check():
                raise BackupError("SQLite backup integrity check failed")
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("SQLite backup validation failed") from exc
    finally:
        store.close()


def _validate_postgresql_archive(raw_path: Path) -> None:
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        raise BackupError("pg_restore is required to validate PostgreSQL backups")
    try:
        subprocess.run(
            [pg_restore, "--list", str(raw_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupError("PostgreSQL backup archive validation failed") from exc


def validate_backup(args: argparse.Namespace) -> int:
    key = _read_backup_key()
    backup = Path(args.backup).expanduser().resolve()
    metadata, payload = open_sealed(backup.read_bytes(), key)
    if args.backend and metadata.backend != args.backend:
        raise BackupError("backup backend does not match the requested validation")
    with tempfile.TemporaryDirectory(prefix="zasi-backup-validate-") as directory:
        raw_path = Path(directory) / (
            "control-plane.dump"
            if metadata.backend == "postgresql"
            else "control-plane.db"
        )
        raw_path.write_bytes(payload)
        raw_path.chmod(0o600)
        if metadata.backend == "sqlite":
            _validate_sqlite(raw_path, metadata.schema_version)
        else:
            _validate_postgresql_archive(raw_path)
    print(_metadata_report(metadata, operation="validate", result="passed"))
    return 0


def _redacted_postgres_url(database_url: str) -> Tuple[str, str]:
    try:
        parsed = urlsplit(database_url)
        password = unquote(parsed.password or "")
        username_value = unquote(parsed.username or "")
        hostname = parsed.hostname or ""
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise BackupError("PostgreSQL database URL is invalid") from exc
    if not password:
        return database_url, ""
    username = quote(username_value, safe="")
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if port is not None:
        hostname = f"{hostname}:{port}"
    return (
        urlunsplit(
            (parsed.scheme, f"{username}@{hostname}", parsed.path, parsed.query, "")
        ),
        password,
    )


def _restore_postgresql(raw_path: Path, database_url: str, replace: bool) -> None:
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise BackupError("PostgreSQL restore requires a PostgreSQL database URL")
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        raise BackupError("pg_restore is required for PostgreSQL restore")
    safe_url, password = _redacted_postgres_url(database_url)
    environment = os.environ.copy()
    if password:
        environment["PGPASSWORD"] = password
    command = [pg_restore, "--exit-on-error"]
    if replace:
        command.extend(["--clean", "--if-exists"])
    command.extend(["--dbname", safe_url, str(raw_path)])
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupError("PostgreSQL restore failed") from exc


def restore_backup(args: argparse.Namespace) -> int:
    key = _read_backup_key()
    backup = Path(args.backup).expanduser().resolve()
    metadata, payload = open_sealed(backup.read_bytes(), key)
    if metadata.backend != args.backend:
        raise BackupError("backup backend does not match the requested restore")
    if (
        args.schema_version is not None
        and metadata.schema_version != args.schema_version
    ):
        raise BackupError("backup schema version does not match the requested restore")

    with tempfile.TemporaryDirectory(prefix="zasi-backup-restore-") as directory:
        raw_path = Path(directory) / (
            "control-plane.dump" if args.backend == "postgresql" else "control-plane.db"
        )
        raw_path.write_bytes(payload)
        raw_path.chmod(0o600)
        if args.backend == "sqlite":
            _validate_sqlite(raw_path, metadata.schema_version)
            target = Path(args.target).expanduser().resolve()
            if target == backup:
                raise BackupError(
                    "SQLite restore target must differ from the encrypted backup"
                )
            _ensure_parent(target)
            if target.exists() and target.is_dir():
                raise BackupError("SQLite restore target must be a file")
            if target.exists() and not args.replace:
                raise FileExistsError(str(target))
            os.replace(raw_path, target)
            target.chmod(0o600)
        else:
            _validate_postgresql_archive(raw_path)
            database_url = args.database_url or os.environ.get("ZASI_DATABASE_URL", "")
            if not database_url:
                raise BackupError(
                    "PostgreSQL restore requires --database-url or ZASI_DATABASE_URL"
                )
            _restore_postgresql(raw_path, database_url, args.replace)
    print(_metadata_report(metadata, operation="restore", result="passed"))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    create = subparsers.add_parser("create", help="create an encrypted backup")
    create.add_argument("--backend", choices=("sqlite", "postgresql"), required=True)
    create.add_argument("--source", help="SQLite database path")
    create.add_argument("--database-url", help="PostgreSQL source URL")
    create.add_argument("--destination", required=True, help="encrypted backup path")
    create.set_defaults(handler=create_backup)

    validate = subparsers.add_parser(
        "validate", help="decrypt and validate without restoring"
    )
    validate.add_argument("--backup", required=True, help="encrypted backup path")
    validate.add_argument("--backend", choices=("sqlite", "postgresql"))
    validate.set_defaults(handler=validate_backup)

    restore = subparsers.add_parser("restore", help="restore an authenticated backup")
    restore.add_argument("--backup", required=True, help="encrypted backup path")
    restore.add_argument("--backend", choices=("sqlite", "postgresql"), required=True)
    restore.add_argument("--target", help="SQLite restore path")
    restore.add_argument("--database-url", help="PostgreSQL target URL")
    restore.add_argument("--schema-version", type=int)
    restore.add_argument(
        "--replace",
        action="store_true",
        help="explicitly replace a SQLite file or clean PostgreSQL objects before restore",
    )
    restore.set_defaults(handler=restore_backup)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.operation == "restore":
        if args.backend == "sqlite" and not args.target:
            raise SystemExit("restore --backend sqlite requires --target")
        if args.backend == "postgresql" and args.target:
            raise SystemExit("restore --backend postgresql does not accept --target")
    try:
        return args.handler(args)
    except (
        BackupError,
        FileNotFoundError,
        FileExistsError,
        OSError,
        RuntimeError,
    ) as exc:
        print(f"backup operation rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
