import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.sign_release_artifacts import (
    ReleaseSigningError,
    build_checksum_manifest,
    discover_release_artifacts,
)


class ReleaseSigningTests(unittest.TestCase):
    def test_discover_release_artifacts_requires_wheel_sdist_and_sbom(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "zasi-32.0.0-py3-none-any.whl").write_bytes(b"wheel")
            (root / "zasi-32.0.0.tar.gz").write_bytes(b"sdist")
            (root / "zasi-sbom.cdx.json").write_text(
                json.dumps({"bomFormat": "CycloneDX"}), encoding="utf-8"
            )

            artifacts = discover_release_artifacts(root)

        self.assertEqual(
            [path.name for path in artifacts],
            [
                "zasi-32.0.0-py3-none-any.whl",
                "zasi-32.0.0.tar.gz",
                "zasi-sbom.cdx.json",
            ],
        )

    def test_checksum_manifest_is_basename_only_and_sorted(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            first = root / "zasi-b.tar.gz"
            second = root / "zasi-a.whl"
            first.write_bytes(b"b")
            second.write_bytes(b"a")

            manifest = build_checksum_manifest([first, second])

        expected = (
            f"{hashlib.sha256(b'a').hexdigest()}  zasi-a.whl\n"
            f"{hashlib.sha256(b'b').hexdigest()}  zasi-b.tar.gz\n"
        )
        self.assertEqual(manifest, expected)

    def test_discover_release_artifacts_rejects_missing_sbom(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "zasi.whl").write_bytes(b"wheel")
            (root / "zasi.tar.gz").write_bytes(b"sdist")

            with self.assertRaises(ReleaseSigningError):
                discover_release_artifacts(root)


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_workflow_requires_and_publishes_signatures(self):
        workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn("contents: read", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("name: release", workflow)
        self.assertIn("ZASI_RELEASE_GPG_PRIVATE_KEY", workflow)
        self.assertIn("ZASI_RELEASE_GPG_FINGERPRINT", workflow)
        self.assertIn("scripts/sign_release_artifacts.py", workflow)
        self.assertIn("dist/*.asc", workflow)
        self.assertIn("dist/ZASI_RELEASE_SIGNING_KEY.asc", workflow)


if __name__ == "__main__":
    unittest.main()
