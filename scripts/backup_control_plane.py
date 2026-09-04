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
import sqlite3
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
    encrypt_file,
    open_sealed,
)
from src.control_plane.storage.postgres_storage import PostgresControlPlaneStore
from src.control_plane.config.secrets import SecretProviderError, read_secret
from src.control_plane.storage import _prepare_private_sqlite_path


def _read_backup_key() -> bytes:
    profile = os.environ.get("ZASI_PROFILE", "local").strip().lower()
    provider = os.environ.get("ZASI_SECRET_PROVIDER", "environment").strip().lower()
    if profile in {"staging", "production"} and provider in {"", "environment"}:
        raise BackupError(
            "staging and production backup keys require an external secret provider"
        )
    try:
        encoded = read_secret("ZASI_BACKUP_KEY_B64")
    except SecretProviderError as exc:
        if not os.environ.get("ZASI_BACKUP_KEY_B64", "").strip():
            raise BackupError(
                "ZASI_BACKUP_KEY_B64 must be injected by the secret provider"
            ) from exc
        raise BackupError(str(exc)) from exc
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


def _sqlite_source_path(source: Optional[str]) -> Path:
    path = source or os.environ.get("ZASI_DATABASE_PATH", "")
    if not path:
        raise BackupError("SQLite backup requires --source or ZASI_DATABASE_PATH")
    source_path = Path(path).expanduser()
    if not source_path.is_file() or source_path.is_symlink():
        raise BackupError("SQLite source must be an existing regular file")
    return source_path


def _postgres_database_url(database_url: Optional[str]) -> str:
    if database_url:
        url = database_url
    else:
        try:
            url = read_secret("ZASI_DATABASE_URL")
        except SecretProviderError as exc:
            raise BackupError(
                "PostgreSQL backup requires a database URL from the configured secret provider"
            ) from exc
    if not url or not url.startswith(("postgresql://", "postgres://")):
        raise BackupError("PostgreSQL backup requires a PostgreSQL database URL")
    return url


def _open_sqlite_readonly(path: Path) -> sqlite3.Connection:
    """Open an existing SQLite file without running application migrations."""
    absolute_path = os.path.abspath(os.fspath(path))
    if os.path.realpath(absolute_path) != absolute_path:
        raise BackupError("SQLite path must not contain symlinks")
    try:
        _prepare_private_sqlite_path(absolute_path)
        uri = f"file:{quote(absolute_path, safe='/')}?mode=ro"
        return sqlite3.connect(uri, uri=True, isolation_level=None)
    except BackupError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise BackupError("SQLite source is unavailable") from exc


def _read_sqlite_schema_version(path: Path) -> int:
    connection = _open_sqlite_readonly(path)
    try:
        try:
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.Error as exc:
            raise BackupError("SQLite schema metadata is unavailable") from exc
        if row is None:
            raise BackupError("SQLite schema metadata is unavailable")
        try:
            schema_version = int(row[0])
        except (TypeError, ValueError) as exc:
            raise BackupError("SQLite schema metadata is invalid") from exc
        if schema_version < 1:
            raise BackupError("SQLite schema metadata is invalid")
        return schema_version
    finally:
        connection.close()


def _backup_sqlite(source_path: Path, destination: Path) -> None:
    """Copy a SQLite snapshot without opening it through the migrating store."""
    if destination.exists():
        raise BackupError("SQLite backup target already exists")
    source = _open_sqlite_readonly(source_path)
    target: Optional[sqlite3.Connection] = None
    try:
        try:
            target = sqlite3.connect(str(destination), isolation_level=None)
            source.backup(target)
        except sqlite3.Error as exc:
            raise BackupError("SQLite backup failed") from exc
    finally:
        source.close()
        if target is not None:
            target.close()
    destination.chmod(0o600)


def _read_postgresql_schema_version(database_url: str) -> int:
    """Read PostgreSQL metadata without running the application's DDL path."""
    try:
        import psycopg

        connection = psycopg.connect(
            database_url,
            autocommit=True,
            connect_timeout=5,
            application_name="zasi-backup-metadata",
        )
    except (ImportError, OSError) as exc:
        raise BackupError("PostgreSQL source is unavailable") from exc
    try:
        try:
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
        except Exception as exc:
            raise BackupError("PostgreSQL schema metadata is unavailable") from exc
        if row is None:
            raise BackupError("PostgreSQL schema metadata is unavailable")
        try:
            schema_version = int(row[0])
        except (TypeError, ValueError) as exc:
            raise BackupError("PostgreSQL schema metadata is invalid") from exc
        if schema_version < 1:
            raise BackupError("PostgreSQL schema metadata is invalid")
        return schema_version
    finally:
        connection.close()


def create_backup(args: argparse.Namespace) -> int:
    key = _read_backup_key()
    destination = Path(args.destination).expanduser().resolve()
    _ensure_parent(destination)
    with tempfile.TemporaryDirectory(prefix="zasi-backup-") as directory:
        raw_path = Path(directory) / (
            "control-plane.dump" if args.backend == "postgresql" else "control-plane.db"
        )
        try:
            if args.backend == "sqlite":
                source_path = _sqlite_source_path(args.source)
                schema_version = _read_sqlite_schema_version(source_path)
                _backup_sqlite(source_path, raw_path)
            else:
                database_url = _postgres_database_url(args.database_url)
                schema_version = _read_postgresql_schema_version(database_url)
                store = PostgresControlPlaneStore(database_url)
                try:
                    store.backup_to(str(raw_path))
                finally:
                    store.close()
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("database backup failed") from exc
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
    connection = _open_sqlite_readonly(raw_path)
    try:
        try:
            schema_row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            if schema_row is None or int(schema_row[0]) != expected_schema_version:
                raise BackupError(
                    "SQLite backup schema version does not match its envelope"
                )
            integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity_row is None or integrity_row[0] != "ok":
                raise BackupError("SQLite backup integrity check failed")
        except BackupError:
            raise
        except (TypeError, ValueError, sqlite3.Error) as exc:
            raise BackupError("SQLite backup validation failed") from exc
    finally:
        connection.close()


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


def _restore_postgresql(
    raw_path: Path,
    database_url: str,
    replace: bool,
    *,
    no_owner: bool = False,
) -> None:
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
    if no_owner:
        # A disposable rehearsal database may be owned by a temporary
        # administrator rather than the application role recorded in the
        # archive. Restore objects to the target owner without granting the
        # temporary role membership in the application role.
        command.append("--no-owner")
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
            database_url = _postgres_database_url(args.database_url)
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
