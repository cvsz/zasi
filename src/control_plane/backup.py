"""Authenticated encryption envelope for control-plane backup artifacts."""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_MAGIC = b"ZASI-ENCRYPTED-BACKUP-V1\n"
_MAX_HEADER_BYTES = 16 * 1024
_NONCE_BYTES = 12
_KEY_BYTES = 32
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
PathLike = Union[str, os.PathLike[str]]


class BackupError(ValueError):
    """Raised when a backup envelope is invalid or cannot be authenticated."""


@dataclass(frozen=True)
class BackupMetadata:
    """Non-secret metadata authenticated as part of a backup envelope."""

    format: str
    version: int
    backend: str
    schema_version: int
    created_at: str
    nonce: str
    plaintext_sha256: str


def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != _KEY_BYTES:
        raise BackupError("backup key must be exactly 32 bytes")


def _decode_b64(value: Any, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise BackupError(f"backup header {field} is invalid")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise BackupError(f"backup header {field} is invalid") from exc


def _metadata_from_header(header: Any) -> Tuple[BackupMetadata, bytes]:
    if not isinstance(header, dict):
        raise BackupError("backup header must be an object")
    expected = {
        "format",
        "version",
        "backend",
        "schema_version",
        "created_at",
        "nonce",
        "plaintext_sha256",
    }
    if set(header) != expected:
        raise BackupError("backup header fields are invalid")
    if header["format"] != "zasi-encrypted-backup" or header["version"] != 1:
        raise BackupError("unsupported backup envelope version")
    if not isinstance(header["backend"], str) or header["backend"] not in {
        "sqlite",
        "postgresql",
    }:
        raise BackupError("unsupported backup backend")
    if (
        isinstance(header["schema_version"], bool)
        or not isinstance(header["schema_version"], int)
        or header["schema_version"] < 1
    ):
        raise BackupError("backup schema version is invalid")
    if not isinstance(header["created_at"], str) or not header["created_at"]:
        raise BackupError("backup creation time is invalid")
    nonce = _decode_b64(header["nonce"], "nonce")
    if len(nonce) != _NONCE_BYTES:
        raise BackupError("backup nonce is invalid")
    digest = header["plaintext_sha256"]
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise BackupError("backup plaintext digest is invalid")
    return (
        BackupMetadata(
            format=header["format"],
            version=header["version"],
            backend=header["backend"],
            schema_version=header["schema_version"],
            created_at=header["created_at"],
            nonce=header["nonce"],
            plaintext_sha256=digest,
        ),
        nonce,
    )


def seal(
    payload: bytes,
    *,
    backend: str,
    schema_version: int,
    key: bytes,
    created_at: Optional[str] = None,
) -> bytes:
    """Return an AES-256-GCM authenticated backup envelope."""
    _validate_key(key)
    if not isinstance(payload, bytes):
        raise BackupError("backup payload must be bytes")
    created = (
        created_at
        or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    )
    header: Dict[str, Any] = {
        "format": "zasi-encrypted-backup",
        "version": 1,
        "backend": backend,
        "schema_version": schema_version,
        "created_at": created,
        "nonce": base64.b64encode(secrets.token_bytes(_NONCE_BYTES)).decode("ascii"),
        "plaintext_sha256": hashlib.sha256(payload).hexdigest(),
    }
    metadata, nonce = _metadata_from_header(header)
    header_line = json.dumps(
        {
            "format": metadata.format,
            "version": metadata.version,
            "backend": metadata.backend,
            "schema_version": metadata.schema_version,
            "created_at": metadata.created_at,
            "nonce": metadata.nonce,
            "plaintext_sha256": metadata.plaintext_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    associated_data = _MAGIC + header_line + b"\n"
    ciphertext = AESGCM(key).encrypt(nonce, payload, associated_data)
    return associated_data + ciphertext


def open_sealed(sealed: bytes, key: bytes) -> Tuple[BackupMetadata, bytes]:
    """Authenticate and decrypt an envelope without trusting its header."""
    _validate_key(key)
    if not isinstance(sealed, bytes) or not sealed.startswith(_MAGIC):
        raise BackupError("backup magic is invalid")
    remainder = sealed[len(_MAGIC) :]
    header_end = remainder.find(b"\n")
    if header_end < 1 or header_end > _MAX_HEADER_BYTES:
        raise BackupError("backup header is missing or too large")
    header_line = remainder[:header_end]
    try:
        header = json.loads(header_line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupError("backup header is not valid JSON") from exc
    metadata, nonce = _metadata_from_header(header)
    associated_data = _MAGIC + header_line + b"\n"
    try:
        payload = AESGCM(key).decrypt(
            nonce,
            remainder[header_end + 1 :],
            associated_data,
        )
    except InvalidTag as exc:
        raise BackupError("backup authentication failed") from exc
    if hashlib.sha256(payload).hexdigest() != metadata.plaintext_sha256:
        raise BackupError("backup plaintext digest does not match")
    return metadata, payload


def _atomic_write(path: PathLike, data: bytes, *, replace: bool) -> None:
    target = Path(path).expanduser().resolve()
    if target.exists() and target.is_dir():
        raise BackupError("backup target must be a file")
    parent = target.parent
    if not parent.is_dir():
        raise BackupError("backup target parent directory must exist")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        dir=str(parent),
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError:
                raise
            finally:
                temporary.unlink(missing_ok=True)
        os.chmod(target, 0o600)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def encrypt_file(
    source_path: PathLike,
    destination_path: PathLike,
    *,
    backend: str,
    schema_version: int,
    key: bytes,
) -> BackupMetadata:
    """Encrypt a backup file and atomically create a mode-600 destination."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise BackupError("backup source must be a regular file")
    sealed = seal(
        source.read_bytes(),
        backend=backend,
        schema_version=schema_version,
        key=key,
    )
    metadata, _ = open_sealed(sealed, key)
    _atomic_write(destination_path, sealed, replace=False)
    return metadata


def decrypt_file(
    source_path: PathLike,
    destination_path: PathLike,
    key: bytes,
    *,
    expected_backend: Optional[str] = None,
    expected_schema_version: Optional[int] = None,
    replace: bool = False,
) -> BackupMetadata:
    """Authenticate an encrypted backup and atomically write its plaintext."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise BackupError("encrypted backup must be a regular file")
    metadata, payload = open_sealed(source.read_bytes(), key)
    if expected_backend is not None and metadata.backend != expected_backend:
        raise BackupError("backup backend does not match the requested restore")
    if (
        expected_schema_version is not None
        and metadata.schema_version != expected_schema_version
    ):
        raise BackupError("backup schema version does not match the requested restore")
    _atomic_write(destination_path, payload, replace=replace)
    return metadata
