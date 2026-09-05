import hashlib
import base64
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.control_plane.storage.backup import (
    BackupError,
    decrypt_file,
    encrypt_file,
    open_sealed,
    seal,
)
from src.control_plane.storage import ControlPlaneStore
from scripts.backup_control_plane import _restore_postgresql


class EncryptedBackupTests(unittest.TestCase):
    KEY = bytes(range(32))

    def test_seal_round_trip_records_digest_and_rejects_tampering(self):
        payload = b"zasi backup payload"
        sealed = seal(payload, backend="sqlite", schema_version=7, key=self.KEY)

        metadata, restored = open_sealed(sealed, self.KEY)

        self.assertEqual(restored, payload)
        self.assertEqual(metadata.backend, "sqlite")
        self.assertEqual(metadata.schema_version, 7)
        self.assertEqual(metadata.plaintext_sha256, hashlib.sha256(payload).hexdigest())

        tampered = bytearray(sealed)
        tampered[-1] ^= 1
        with self.assertRaises(BackupError):
            open_sealed(bytes(tampered), self.KEY)

    def test_wrong_key_and_invalid_key_are_rejected(self):
        with self.assertRaises(BackupError):
            seal(b"payload", backend="sqlite", schema_version=7, key=b"short")
        with self.assertRaises(BackupError):
            seal(b"payload", backend=[], schema_version=7, key=self.KEY)

        sealed = seal(b"payload", backend="sqlite", schema_version=7, key=self.KEY)
        with self.assertRaises(BackupError):
            open_sealed(sealed, bytes(reversed(self.KEY)))

    def test_file_round_trip_is_atomic_and_mode_600(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            encrypted = root / "backup.zasi"
            restored = root / "restored.bin"
            source.write_bytes(b"durable encrypted state")

            metadata = encrypt_file(
                source,
                encrypted,
                backend="sqlite",
                schema_version=7,
                key=self.KEY,
            )
            self.assertEqual(
                metadata.plaintext_sha256,
                hashlib.sha256(source.read_bytes()).hexdigest(),
            )
            self.assertEqual(encrypted.stat().st_mode & 0o777, 0o600)

            decrypt_file(encrypted, restored, self.KEY, expected_backend="sqlite")
            self.assertEqual(restored.read_bytes(), source.read_bytes())
            self.assertEqual(restored.stat().st_mode & 0o777, 0o600)

            with self.assertRaises(FileExistsError):
                decrypt_file(encrypted, restored, self.KEY, expected_backend="sqlite")

    def test_sqlite_backup_round_trip_restores_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            raw_backup = root / "raw.db"
            encrypted = root / "backup.zasi"
            restored = root / "restored.db"
            store = ControlPlaneStore(str(source))
            store.initialize()
            store.create_tenant("tenant-a")
            store.close()

            source_store = ControlPlaneStore(str(source))
            source_store.initialize()
            source_store.backup_to(str(raw_backup))
            source_store.close()
            encrypt_file(
                raw_backup,
                encrypted,
                backend="sqlite",
                schema_version=7,
                key=self.KEY,
            )
            decrypt_file(
                encrypted,
                restored,
                self.KEY,
                expected_backend="sqlite",
            )

            restored_store = ControlPlaneStore(str(restored))
            restored_store.initialize()
            self.assertTrue(restored_store.integrity_check())
            tenant = (
                restored_store._conn()
                .execute("SELECT id FROM tenants WHERE id = ?", ("tenant-a",))
                .fetchone()
            )
            self.assertIsNotNone(tenant)
            restored_store.close()

    def test_backup_cli_creates_validates_and_restores_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            encrypted = root / "backup.zasi"
            restored = root / "restored.db"
            store = ControlPlaneStore(str(source))
            store.initialize()
            store.create_tenant("tenant-cli")
            store.close()
            environment = os.environ.copy()
            environment["ZASI_BACKUP_KEY_B64"] = base64.b64encode(self.KEY).decode(
                "ascii"
            )
            script = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "backup_control_plane.py"
            )

            create = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "create",
                    "--backend",
                    "sqlite",
                    "--source",
                    str(source),
                    "--destination",
                    str(encrypted),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(create.returncode, 0, create.stderr)

            validate = subprocess.run(
                [sys.executable, str(script), "validate", "--backup", str(encrypted)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertIn('"result": "passed"', validate.stdout)

            restore = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "restore",
                    "--backend",
                    "sqlite",
                    "--backup",
                    str(encrypted),
                    "--target",
                    str(restored),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(restore.returncode, 0, restore.stderr)
            restored_store = ControlPlaneStore(str(restored))
            restored_store.initialize()
            tenant = (
                restored_store._conn()
                .execute("SELECT id FROM tenants WHERE id = ?", ("tenant-cli",))
                .fetchone()
            )
            self.assertIsNotNone(tenant)
            restored_store.close()

    def test_backup_and_validation_preserve_an_older_sqlite_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "legacy.db"
            encrypted = root / "legacy-backup.zasi"
            connection = sqlite3.connect(source)
            try:
                connection.execute(
                    "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', '10')"
                )
                connection.commit()
            finally:
                connection.close()
            source.chmod(0o600)

            environment = os.environ.copy()
            environment["ZASI_BACKUP_KEY_B64"] = base64.b64encode(self.KEY).decode(
                "ascii"
            )
            script = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "backup_control_plane.py"
            )

            create = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "create",
                    "--backend",
                    "sqlite",
                    "--source",
                    str(source),
                    "--destination",
                    str(encrypted),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            metadata, _ = open_sealed(encrypted.read_bytes(), self.KEY)
            self.assertEqual(metadata.schema_version, 10)

            validate = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "validate",
                    "--backup",
                    str(encrypted),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)

            connection = sqlite3.connect(source)
            try:
                row = connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row[0], "10")

    def test_backup_cli_fails_closed_without_injected_key(self):
        environment = os.environ.copy()
        environment.pop("ZASI_BACKUP_KEY_B64", None)
        script = (
            Path(__file__).resolve().parents[1] / "scripts" / "backup_control_plane.py"
        )
        result = subprocess.run(
            [sys.executable, str(script), "validate", "--backup", "/tmp/missing.zasi"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("secret provider", result.stderr)
        self.assertNotIn("backup authentication failed", result.stderr)

    def test_postgresql_restore_can_skip_archive_ownership_for_rehearsal(self):
        with tempfile.TemporaryDirectory() as directory:
            raw_backup = Path(directory) / "control-plane.dump"
            raw_backup.write_bytes(b"archive")
            with patch(
                "scripts.backup_control_plane.shutil.which",
                return_value="/usr/bin/pg_restore",
            ), patch("scripts.backup_control_plane.subprocess.run") as run:
                _restore_postgresql(
                    raw_backup,
                    "postgresql://restore-user:secret@127.0.0.1:5433/target",
                    replace=False,
                    no_owner=True,
                )

            command = run.call_args.args[0]
            self.assertIn("--no-owner", command)
            self.assertNotIn("secret", command)

    def test_backup_cli_does_not_clobber_restore_target_without_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            encrypted = root / "backup.zasi"
            restored = root / "restored.db"
            store = ControlPlaneStore(str(source))
            store.initialize()
            store.create_tenant("tenant-safe-restore")
            store.close()
            environment = os.environ.copy()
            environment["ZASI_BACKUP_KEY_B64"] = base64.b64encode(self.KEY).decode(
                "ascii"
            )
            script = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "backup_control_plane.py"
            )

            create = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "create",
                    "--backend",
                    "sqlite",
                    "--source",
                    str(source),
                    "--destination",
                    str(encrypted),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            restored.write_bytes(b"operator-owned-target")

            rejected = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "restore",
                    "--backend",
                    "sqlite",
                    "--backup",
                    str(encrypted),
                    "--target",
                    str(restored),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertEqual(restored.read_bytes(), b"operator-owned-target")

            replaced = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "restore",
                    "--backend",
                    "sqlite",
                    "--backup",
                    str(encrypted),
                    "--target",
                    str(restored),
                    "--replace",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            restored_store = ControlPlaneStore(str(restored))
            restored_store.initialize()
            tenant = (
                restored_store._conn()
                .execute(
                    "SELECT id FROM tenants WHERE id = ?", ("tenant-safe-restore",)
                )
                .fetchone()
            )
            self.assertIsNotNone(tenant)
            restored_store.close()

    def test_backup_cli_rejects_missing_sqlite_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            encrypted = root / "backup.zasi"
            environment = os.environ.copy()
            environment["ZASI_BACKUP_KEY_B64"] = base64.b64encode(self.KEY).decode(
                "ascii"
            )
            script = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "backup_control_plane.py"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "create",
                    "--backend",
                    "sqlite",
                    "--source",
                    str(root / "missing.db"),
                    "--destination",
                    str(encrypted),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("existing regular file", result.stderr)
            self.assertFalse(encrypted.exists())

    def test_backup_cli_rejects_restore_target_equal_to_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.db"
            encrypted = root / "backup.zasi"
            store = ControlPlaneStore(str(source))
            store.initialize()
            store.create_tenant("tenant-preserve-archive")
            store.close()
            environment = os.environ.copy()
            environment["ZASI_BACKUP_KEY_B64"] = base64.b64encode(self.KEY).decode(
                "ascii"
            )
            script = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "backup_control_plane.py"
            )
            create = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "create",
                    "--backend",
                    "sqlite",
                    "--source",
                    str(source),
                    "--destination",
                    str(encrypted),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            original_archive = encrypted.read_bytes()
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "restore",
                    "--backend",
                    "sqlite",
                    "--backup",
                    str(encrypted),
                    "--target",
                    str(encrypted),
                    "--replace",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("differ from the encrypted backup", result.stderr)
            self.assertEqual(encrypted.read_bytes(), original_archive)

    def test_backup_cli_rejects_environment_key_in_production_profile(self):
        environment = os.environ.copy()
        environment["ZASI_PROFILE"] = "production"
        environment["ZASI_BACKUP_KEY_B64"] = base64.b64encode(self.KEY).decode("ascii")
        environment.pop("ZASI_SECRET_PROVIDER", None)
        script = (
            Path(__file__).resolve().parents[1] / "scripts" / "backup_control_plane.py"
        )
        result = subprocess.run(
            [sys.executable, str(script), "validate", "--backup", "/tmp/missing.zasi"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("external secret provider", result.stderr)


if __name__ == "__main__":
    unittest.main()
