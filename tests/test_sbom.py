import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_sbom import build_sbom


class SBOMGenerationTests(unittest.TestCase):
    def test_build_sbom_emits_cyclonedx_components_from_project_manifests(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "package-lock.json").write_text(
                json.dumps(
                    {
                        "lockfileVersion": 3,
                        "packages": {
                            "": {"name": "zasi-cockpit", "version": "32.0.0"},
                            "node_modules/react": {
                                "version": "18.3.1",
                                "integrity": "sha512-react",
                            },
                            "node_modules/@scope/tool": {"version": "2.1.0"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                """
[project]
name = "zasi"
version = "32.0.0"
dependencies = ["fastapi>=0.115.0,<1.0.0", "uvicorn>=0.34.0,<1.0.0"]
""",
                encoding="utf-8",
            )

            bom = build_sbom(root / "package-lock.json", root / "pyproject.toml")

        self.assertEqual(bom["bomFormat"], "CycloneDX")
        self.assertEqual(bom["specVersion"], "1.5")
        components = {component["name"]: component for component in bom["components"]}
        self.assertEqual(components["react"]["version"], "18.3.1")
        self.assertEqual(components["@scope/tool"]["version"], "2.1.0")
        self.assertEqual(components["fastapi"]["properties"][0]["value"], "declared")
        self.assertEqual(components["uvicorn"]["properties"][0]["value"], "declared")

    def test_build_sbom_uses_deterministic_serial_number_for_same_manifests(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "package-lock.json").write_text(
                '{"lockfileVersion":3,"packages":{"":{"name":"zasi-cockpit","version":"32.0.0"}}}',
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                '[project]\nname="zasi"\nversion="32.0.0"\ndependencies=[]\n',
                encoding="utf-8",
            )

            first = build_sbom(root / "package-lock.json", root / "pyproject.toml")
            second = build_sbom(root / "package-lock.json", root / "pyproject.toml")

        self.assertEqual(first["serialNumber"], second["serialNumber"])


if __name__ == "__main__":
    unittest.main()
