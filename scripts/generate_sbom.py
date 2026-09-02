"""Generate a deterministic CycloneDX SBOM from repository manifests."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
import uuid
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9 compatibility path
    tomllib = None  # type: ignore[assignment]


def _load_toml(path: Path) -> Dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("Python 3.11+ is required to parse pyproject.toml")
    with path.open("rb") as stream:
        return tomllib.load(stream)


def _requirement_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)", requirement)
    if not match:
        raise ValueError(f"invalid Python dependency declaration: {requirement!r}")
    return match.group(1)


def _pypi_purl(name: str, version: str) -> str:
    return f"pkg:pypi/{quote(name.lower().replace('_', '-'), safe='')}@{quote(version, safe='')}"


def _npm_purl(name: str, version: str) -> str:
    return f"pkg:npm/{quote(name, safe='/')}@{quote(version, safe='')}"


def _integrity_hash(integrity: str) -> Optional[Dict[str, str]]:
    algorithm, separator, encoded = integrity.partition("-")
    if not separator or algorithm.lower() != "sha512":
        return None
    try:
        digest = base64.b64decode(encoded, validate=True).hex()
    except (ValueError, binascii.Error):
        return None
    return {"alg": "SHA-512", "content": digest}


def _npm_components(lock_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    packages = lock_data.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("package-lock.json must contain a packages object")
    components: List[Dict[str, Any]] = []
    for package_path, package_data in packages.items():
        if not package_path or not package_path.startswith("node_modules/"):
            continue
        if not isinstance(package_data, dict) or not package_data.get("version"):
            continue
        name = package_path.rsplit("node_modules/", 1)[-1]
        version = str(package_data["version"])
        component: Dict[str, Any] = {
            "type": "library",
            "bom-ref": _npm_purl(name, version),
            "name": name,
            "version": version,
            "purl": _npm_purl(name, version),
            "properties": [
                {"name": "zasi:ecosystem", "value": "npm"},
                {
                    "name": "npm:dev",
                    "value": str(bool(package_data.get("dev", False))).lower(),
                },
            ],
        }
        integrity = package_data.get("integrity")
        if isinstance(integrity, str):
            component["properties"].append(
                {"name": "npm:integrity", "value": integrity}
            )
            digest = _integrity_hash(integrity)
            if digest:
                component["hashes"] = [digest]
        components.append(component)
    return components


def _python_components(
    project_dependencies: Sequence[str], resolve_installed: bool
) -> List[Dict[str, Any]]:
    queue = list(project_dependencies)
    components: Dict[Tuple[str, str], Dict[str, Any]] = {}
    while queue:
        declaration = queue.pop(0)
        name = _requirement_name(declaration)
        normalized_name = name.lower().replace("_", "-")
        spec = declaration[declaration.find(name) + len(name) :].strip()
        resolved_version: Optional[str] = None
        distribution = None
        if resolve_installed:
            try:
                distribution = metadata.distribution(name)
                resolved_version = distribution.version
            except metadata.PackageNotFoundError:
                pass
        version = resolved_version or spec or "unresolved"
        key = (normalized_name, version)
        if key in components:
            continue
        resolution = "installed" if resolved_version else "declared"
        component: Dict[str, Any] = {
            "type": "library",
            "name": name,
            "version": version,
            "properties": [
                {"name": "zasi:resolution", "value": resolution},
                {"name": "zasi:version-spec", "value": spec or "unspecified"},
            ],
        }
        if resolved_version:
            component["bom-ref"] = _pypi_purl(name, resolved_version)
            component["purl"] = _pypi_purl(name, resolved_version)
        components[key] = component

        if distribution is not None:
            for child in distribution.requires or ():
                try:
                    from packaging.requirements import Requirement

                    parsed = Requirement(child)
                    if parsed.marker is not None and not parsed.marker.evaluate():
                        continue
                    queue.append(str(parsed))
                except (ImportError, ValueError):
                    if ";" not in child:
                        queue.append(child)
    return list(components.values())


def build_sbom(
    package_lock_path: Path,
    pyproject_path: Path,
    *,
    resolve_installed: bool = False,
) -> Dict[str, Any]:
    """Build a deterministic CycloneDX 1.5 BOM from project manifests."""
    lock_data = json.loads(package_lock_path.read_text(encoding="utf-8"))
    project_data = _load_toml(pyproject_path).get("project", {})
    project_name = str(project_data.get("name", "zasi"))
    project_version = str(project_data.get("version", "0.0.0"))
    project_dependencies = [
        str(item) for item in project_data.get("dependencies", [])
    ]
    components = _npm_components(lock_data)
    components.extend(_python_components(project_dependencies, resolve_installed))
    components.sort(key=lambda item: (item["type"], item["name"], item["version"]))
    application_ref = f"pkg:generic/{quote(project_name, safe='')}@{quote(project_version, safe='')}"
    canonical = json.dumps(
        {"application": application_ref, "components": components},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    serial = uuid.uuid5(uuid.NAMESPACE_URL, hashlib.sha256(canonical).hexdigest())
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": application_ref,
                "name": project_name,
                "version": project_version,
            },
            "properties": [
                {"name": "zasi:source", "value": "pyproject.toml+package-lock.json"},
                {"name": "zasi:resolution", "value": "installed" if resolve_installed else "declared"},
            ],
        },
        "components": components,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-lock", type=Path, default=Path("package-lock.json"))
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--resolve-installed",
        action="store_true",
        help="resolve Python dependency versions from the current environment",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    bom = build_sbom(
        args.package_lock,
        args.pyproject,
        resolve_installed=args.resolve_installed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(bom['components'])} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
