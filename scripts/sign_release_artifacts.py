#!/usr/bin/env python3
"""Sign a release's primary artifacts and its checksum manifest with GPG.

The private key must already be imported by the calling release environment.
This module never accepts a key on the command line and never prints a
passphrase, key material, or GPG diagnostic output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable, List, Optional, Sequence


class ReleaseSigningError(RuntimeError):
    """Raised when a release cannot be signed and verified safely."""


_FINGERPRINT_PATTERN = re.compile(r"^[0-9A-Fa-f]{16,64}$")


def _regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def discover_release_artifacts(output_dir: Path) -> List[Path]:
    """Return the required primary release files in deterministic order."""

    if not output_dir.is_dir() or output_dir.is_symlink():
        raise ReleaseSigningError("release output directory is invalid")
    wheels = sorted(
        path for path in output_dir.glob("*.whl") if _regular_file(path)
    )
    sdists = sorted(
        path for path in output_dir.glob("*.tar.gz") if _regular_file(path)
    )
    sbom = output_dir / "zasi-sbom.cdx.json"
    if not wheels or not sdists or not _regular_file(sbom):
        raise ReleaseSigningError(
            "release output must contain a wheel, sdist, and CycloneDX SBOM"
        )
    return wheels + sdists + [sbom]


def build_checksum_manifest(paths: Iterable[Path]) -> str:
    """Build a stable sha256sum-compatible manifest using basenames only."""

    material = sorted(paths, key=lambda path: path.name)
    names = [path.name for path in material]
    if len(names) != len(set(names)):
        raise ReleaseSigningError("release artifact basenames must be unique")
    lines = []
    for path in material:
        if not _regular_file(path):
            raise ReleaseSigningError("release artifact is not a regular file")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    return "\n".join(lines) + "\n"


def _run_gpg(
    arguments: Sequence[str],
    *,
    passphrase: str = "",
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = ["gpg", "--batch", "--no-tty", *arguments]
    try:
        if passphrase:
            command[1:1] = ["--pinentry-mode", "loopback", "--passphrase-fd", "0"]
            return subprocess.run(
                command,
                check=True,
                capture_output=capture_output,
                text=True,
                input=passphrase + "\n",
                timeout=120,
            )
        return subprocess.run(
            command,
            check=True,
            capture_output=capture_output,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseSigningError("GPG release operation failed") from exc


def _require_secret_key(fingerprint: str) -> None:
    result = _run_gpg(
        ["--with-colons", "--list-secret-keys", fingerprint],
    )
    fingerprints = {
        line.split(":")[9].lower()
        for line in result.stdout.splitlines()
        if line.startswith("fpr:") and len(line.split(":")) > 9
    }
    if fingerprint.lower() not in fingerprints:
        raise ReleaseSigningError("configured release signing key is unavailable")


def _sign(path: Path, fingerprint: str, passphrase: str) -> Path:
    signature = path.with_name(path.name + ".asc")
    _run_gpg(
        [
            "--armor",
            "--yes",
            "--local-user",
            fingerprint,
            "--output",
            str(signature),
            "--detach-sign",
            str(path),
        ],
        passphrase=passphrase,
    )
    if not _regular_file(signature):
        raise ReleaseSigningError("GPG did not create a release signature")
    _run_gpg(["--verify", str(signature), str(path)])
    signature.chmod(0o644)
    return signature


def sign_release_artifacts(
    output_dir: Path,
    fingerprint: str,
    *,
    passphrase: str = "",
) -> dict[str, object]:
    """Create and verify public release signatures, returning safe metadata."""

    if not isinstance(fingerprint, str) or not _FINGERPRINT_PATTERN.fullmatch(
        fingerprint.strip()
    ):
        raise ReleaseSigningError("release signing fingerprint is invalid")
    fingerprint = fingerprint.strip()
    if not isinstance(passphrase, str):
        raise ReleaseSigningError("release signing passphrase is invalid")
    _require_secret_key(fingerprint)
    artifacts = discover_release_artifacts(output_dir)
    checksum_path = output_dir / "SHA256SUMS"
    checksum_path.write_text(
        build_checksum_manifest(artifacts), encoding="utf-8"
    )
    checksum_path.chmod(0o644)
    signed_files = artifacts + [checksum_path]
    signatures = [_sign(path, fingerprint, passphrase) for path in signed_files]

    public_key = output_dir / "ZASI_RELEASE_SIGNING_KEY.asc"
    exported = _run_gpg(["--armor", "--export", fingerprint]).stdout
    if not exported.strip():
        raise ReleaseSigningError("GPG did not export the release public key")
    public_key.write_text(exported, encoding="utf-8")
    public_key.chmod(0o644)
    _run_gpg(["--import-options", "show-only", "--import", str(public_key)])
    return {
        "artifact_count": len(artifacts),
        "signature_count": len(signatures),
        "checksum": checksum_path.name,
        "public_key": public_key.name,
        "fingerprint": fingerprint.lower(),
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument(
        "--passphrase-env",
        default="ZASI_RELEASE_GPG_PASSPHRASE",
        help="environment variable containing the optional signing passphrase",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        passphrase = os.environ.get(args.passphrase_env, "")
        report = sign_release_artifacts(
            args.output_dir,
            args.fingerprint,
            passphrase=passphrase,
        )
        print(json.dumps({"status": "signed", **report}, sort_keys=True))
        return 0
    except ReleaseSigningError:
        print(
            json.dumps(
                {"status": "failed", "error": "release_signing_unavailable"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
