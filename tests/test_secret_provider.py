import base64
import os
import tempfile
import unittest
from pathlib import Path

from src.control_plane.config.secrets import (
    SecretProviderError,
    resolve_secret_mapping,
)


class SystemdCredentialProviderTests(unittest.TestCase):
    def write_credentials(self, directory: str, content: str) -> Path:
        path = Path(directory) / "zasi-secrets"
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_loads_strict_credentials_without_logging_or_plaintext_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_credentials(
                directory,
                "\n".join(
                    (
                        "ZASI_API_KEY=generated-api-key",
                        "ZASI_DATABASE_URL=postgresql://zasi:db-secret@127.0.0.1:5433/zasi",
                        "ZASI_REDIS_URL=redis://zasi:redis-secret@127.0.0.1:6379/0",
                        "ZASI_BACKUP_KEY_B64="
                        + base64.b64encode(b"b" * 32).decode("ascii"),
                        "",
                    )
                ),
            )
            resolved = resolve_secret_mapping(
                {
                    "ZASI_SECRET_PROVIDER": "systemd-credential",
                    "ZASI_SECRET_CREDENTIAL_FILE": str(path),
                    "ZASI_PROFILE": "staging",
                },
                required={"ZASI_API_KEY", "ZASI_DATABASE_URL", "ZASI_REDIS_URL"},
            )

            self.assertEqual(resolved["ZASI_API_KEY"], "generated-api-key")
            self.assertEqual(resolved["ZASI_PROFILE"], "staging")
            self.assertEqual(resolved["ZASI_DATABASE_URL"].split("@", 1)[0], "postgresql://zasi:db-secret")
            self.assertNotIn("UNTRUSTED", resolved)

    def test_credential_directory_default_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_credentials(directory, "ZASI_API_KEY=generated-api-key\n")
            resolved = resolve_secret_mapping(
                {
                    "ZASI_SECRET_PROVIDER": "systemd-credential",
                    "CREDENTIALS_DIRECTORY": directory,
                },
                required={"ZASI_API_KEY"},
            )
            self.assertEqual(resolved["ZASI_API_KEY"], "generated-api-key")

    def test_rejects_unmanaged_provider_and_missing_required_value(self):
        with self.assertRaises(SecretProviderError):
            resolve_secret_mapping(
                {"ZASI_SECRET_PROVIDER": "vault"},
                required={"ZASI_API_KEY"},
            )

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_credentials(directory, "ZASI_API_KEY=generated-api-key\n")
            with self.assertRaisesRegex(SecretProviderError, "required"):
                resolve_secret_mapping(
                    {
                        "ZASI_SECRET_PROVIDER": "systemd-credential",
                        "ZASI_SECRET_CREDENTIAL_FILE": str(path),
                    },
                    required={"ZASI_API_KEY", "ZASI_REDIS_URL"},
                )

    def test_rejects_relative_weak_symlink_and_malformed_credentials(self):
        with self.assertRaisesRegex(SecretProviderError, "absolute"):
            resolve_secret_mapping(
                {
                    "ZASI_SECRET_PROVIDER": "systemd-credential",
                    "ZASI_SECRET_CREDENTIAL_FILE": "relative-secrets",
                },
                required=set(),
            )

        with tempfile.TemporaryDirectory() as directory:
            weak = self.write_credentials(directory, "ZASI_API_KEY=generated-api-key\n")
            weak.chmod(0o640)
            with self.assertRaisesRegex(SecretProviderError, "permissions"):
                resolve_secret_mapping(
                    {
                        "ZASI_SECRET_PROVIDER": "systemd-credential",
                        "ZASI_SECRET_CREDENTIAL_FILE": str(weak),
                    },
                    required={"ZASI_API_KEY"},
                )

            target = self.write_credentials(directory, "ZASI_API_KEY=generated-api-key\n")
            link = Path(directory) / "credential-link"
            link.symlink_to(target)
            with self.assertRaisesRegex(SecretProviderError, "symlink"):
                resolve_secret_mapping(
                    {
                        "ZASI_SECRET_PROVIDER": "systemd-credential",
                        "ZASI_SECRET_CREDENTIAL_FILE": str(link),
                    },
                    required={"ZASI_API_KEY"},
                )

            malformed = self.write_credentials(directory, "NOT_ALLOWED=value\n")
            with self.assertRaisesRegex(SecretProviderError, "unsupported"):
                resolve_secret_mapping(
                    {
                        "ZASI_SECRET_PROVIDER": "systemd-credential",
                        "ZASI_SECRET_CREDENTIAL_FILE": str(malformed),
                    },
                    required=set(),
                )

    def test_rejects_duplicate_conflicting_and_empty_values(self):
        with tempfile.TemporaryDirectory() as directory:
            duplicate = self.write_credentials(
                directory,
                "ZASI_API_KEY=one\nZASI_API_KEY=two\n",
            )
            with self.assertRaisesRegex(SecretProviderError, "duplicate"):
                resolve_secret_mapping(
                    {
                        "ZASI_SECRET_PROVIDER": "systemd-credential",
                        "ZASI_SECRET_CREDENTIAL_FILE": str(duplicate),
                    },
                    required={"ZASI_API_KEY"},
                )

            conflict = self.write_credentials(directory, "ZASI_API_KEY=from-file\n")
            with self.assertRaisesRegex(SecretProviderError, "conflict"):
                resolve_secret_mapping(
                    {
                        "ZASI_SECRET_PROVIDER": "systemd-credential",
                        "ZASI_SECRET_CREDENTIAL_FILE": str(conflict),
                        "ZASI_API_KEY": "from-environment",
                    },
                    required={"ZASI_API_KEY"},
                )

            empty = self.write_credentials(directory, "ZASI_API_KEY=\n")
            with self.assertRaisesRegex(SecretProviderError, "empty"):
                resolve_secret_mapping(
                    {
                        "ZASI_SECRET_PROVIDER": "systemd-credential",
                        "ZASI_SECRET_CREDENTIAL_FILE": str(empty),
                    },
                    required={"ZASI_API_KEY"},
                )


if __name__ == "__main__":
    unittest.main()
