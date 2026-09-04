"""Fail-closed runtime secret loading.

The local profile may use the process environment.  Staging and production
may use a systemd encrypted credential that is decrypted into the service's
private credential directory by systemd.  The provider never prints secret
values, accepts only the secret names used by the control plane, rejects
symlinks and weak file permissions, and refuses ambiguous environment/file
configuration.
"""

from __future__ import annotations

import os
import re
import stat
import errno
from pathlib import Path
from typing import FrozenSet, Mapping, Optional


SYSTEMD_CREDENTIAL_PROVIDER = "systemd-credential"
_ALLOWED_SECRET_NAMES: FrozenSet[str] = frozenset(
    {
        "ZASI_API_KEY",
        "ZASI_DATABASE_URL",
        "ZASI_REDIS_URL",
        "ZASI_BACKUP_KEY_B64",
    }
)
_MAX_CREDENTIAL_BYTES = 64 * 1024
_MAX_SECRET_VALUE_BYTES = 16 * 1024
_SECRET_NAME_RE = re.compile(r"^ZASI_[A-Z0-9_]+$")


class SecretProviderError(ValueError):
    """Raised when runtime secret material cannot be loaded safely."""


def _credential_path(source: Mapping[str, str]) -> Path:
    configured = str(source.get("ZASI_SECRET_CREDENTIAL_FILE", "")).strip()
    if configured:
        path = Path(configured)
    else:
        credentials_directory = str(
            source.get("CREDENTIALS_DIRECTORY", "")
        ).strip()
        if not credentials_directory:
            raise SecretProviderError(
                "systemd credential provider requires a credential directory"
            )
        path = Path(credentials_directory) / "zasi-secrets"
    if not path.is_absolute():
        raise SecretProviderError("systemd credential file path must be absolute")
    return path


def _read_credential_file(path: Path, *, systemd_materialized: bool = False) -> bytes:
    flags = os.O_RDONLY | os.O_CLOEXEC
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    flags |= no_follow
    try:
        descriptor = os.open(os.fspath(path), flags)
    except FileNotFoundError as exc:
        raise SecretProviderError("systemd credential file is missing") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SecretProviderError("systemd credential file must not be a symlink") from exc
        raise SecretProviderError("systemd credential file cannot be opened") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SecretProviderError("systemd credential file must be regular")
        mode = stat.S_IMODE(metadata.st_mode)
        if systemd_materialized:
            parent = path.parent
            parent_metadata = os.stat(parent)
            parent_mode = stat.S_IMODE(parent_metadata.st_mode)
            manager_owned = (
                metadata.st_uid == 0
                and mode in {0o400, 0o440}
                and parent_metadata.st_uid == 0
                and parent_mode in {0o500, 0o550, 0o700}
            )
            private_test_or_user_owned = (
                metadata.st_uid == os.getuid()
                and mode in {0o400, 0o600}
                and parent_metadata.st_uid == os.getuid()
                and parent_mode == 0o700
            )
            if (
                not (manager_owned or private_test_or_user_owned)
                or not os.access(path, os.R_OK)
                or not os.access(parent, os.X_OK)
            ):
                raise SecretProviderError(
                    "systemd credential file permissions are not manager-controlled"
                )
        elif mode & 0o077:
            raise SecretProviderError("systemd credential file permissions are too broad")
        if metadata.st_size > _MAX_CREDENTIAL_BYTES:
            raise SecretProviderError("systemd credential file is too large")
        payload = os.read(descriptor, _MAX_CREDENTIAL_BYTES + 1)
        if len(payload) > _MAX_CREDENTIAL_BYTES:
            raise SecretProviderError("systemd credential file is too large")
        return payload
    finally:
        os.close(descriptor)


def _parse_credential_file(payload: bytes) -> dict[str, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretProviderError("systemd credential file is not UTF-8") from exc

    credentials: dict[str, str] = {}
    for line_number, line in enumerate(text.split("\n"), start=1):
        if line.endswith("\r"):
            line = line[:-1]
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SecretProviderError(
                f"systemd credential line {line_number} is malformed"
            )
        name, value = line.split("=", 1)
        if not _SECRET_NAME_RE.fullmatch(name) or name not in _ALLOWED_SECRET_NAMES:
            raise SecretProviderError(
                f"systemd credential line {line_number} uses an unsupported secret"
            )
        if name in credentials:
            raise SecretProviderError(
                f"systemd credential line {line_number} is a duplicate"
            )
        value = value.strip()
        if not value:
            raise SecretProviderError(
                f"systemd credential line {line_number} contains an empty secret"
            )
        if len(value.encode("utf-8")) > _MAX_SECRET_VALUE_BYTES:
            raise SecretProviderError(
                f"systemd credential line {line_number} is too large"
            )
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
            raise SecretProviderError(
                f"systemd credential line {line_number} contains control characters"
            )
        credentials[name] = value
    return credentials


def _systemd_credentials(source: Mapping[str, str]) -> dict[str, str]:
    use_materialized_credential = not str(
        source.get("ZASI_SECRET_CREDENTIAL_FILE", "")
    ).strip()
    path = _credential_path(source)
    return _parse_credential_file(
        _read_credential_file(path, systemd_materialized=use_materialized_credential)
    )


def resolve_secret_mapping(
    source: Mapping[str, str],
    *,
    required: set[str] | FrozenSet[str] = frozenset(),
) -> dict[str, str]:
    """Resolve provider-managed values into a configuration mapping.

    ``required`` is checked after provider resolution.  Environment values
    remain valid only for the local/reference provider.  A production-like
    service must therefore prove that its declared provider actually supplied
    the required values.
    """
    resolved = dict(source)
    provider = str(source.get("ZASI_SECRET_PROVIDER", "environment")).strip().lower()
    if provider == "environment":
        values = {
            name: str(value).strip()
            for name, value in resolved.items()
            if name in _ALLOWED_SECRET_NAMES and value is not None
        }
    elif provider == SYSTEMD_CREDENTIAL_PROVIDER:
        values = _systemd_credentials(source)
        for name, value in values.items():
            existing = source.get(name)
            if existing is not None and str(existing).strip():
                raise SecretProviderError(
                    f"systemd credential conflicts with environment value for {name}"
                )
        resolved.update(values)
    else:
        raise SecretProviderError("unsupported runtime secret provider")

    missing = sorted(
        name for name in required if not str(resolved.get(name, "")).strip()
    )
    if missing:
        raise SecretProviderError(
            "required runtime secrets are missing: " + ", ".join(missing)
        )
    return resolved


def read_secret(name: str, source: Optional[Mapping[str, str]] = None) -> str:
    """Read one named runtime secret without exposing provider internals."""
    if name not in _ALLOWED_SECRET_NAMES:
        raise SecretProviderError("unsupported runtime secret name")
    mapping = dict(os.environ if source is None else source)
    resolved = resolve_secret_mapping(mapping, required={name})
    return resolved[name]
