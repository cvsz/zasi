import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.generate_sbom import _python_components, build_sbom


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

    def test_build_sbom_emits_unique_npm_bom_refs_and_merges_install_locations(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "package-lock.json").write_text(
                json.dumps(
                    {
                        "lockfileVersion": 3,
                        "packages": {
                            "": {},
                            "node_modules/example": {
                                "version": "1.2.3",
                                "dev": True,
                                "integrity": "sha512-example",
                            },
                            "node_modules/parent/node_modules/example": {
                                "version": "1.2.3",
                                "dev": False,
                                "integrity": "sha512-example",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                '[project]\nname="zasi"\nversion="32.0.0"\ndependencies=[]\n',
                encoding="utf-8",
            )

            bom = build_sbom(root / "package-lock.json", root / "pyproject.toml")

        refs = [component["bom-ref"] for component in bom["components"]]
        self.assertEqual(len(refs), len(set(refs)))
        npm_components = [
            component for component in bom["components"] if component["name"] == "example"
        ]
        self.assertEqual(len(npm_components), 1)
        self.assertIn(
            {"name": "npm:dev", "value": "false"}, npm_components[0]["properties"]
        )

    def test_python_resolution_includes_selected_distribution_extras(self):
        class FakeDistribution:
            def __init__(self, version, requires):
                self.version = version
                self.requires = requires

        distributions = {
            "psycopg": FakeDistribution(
                "3.3.4",
                [
                    'typing-extensions>=4.6; python_version >= "3.0"',
                    'psycopg-binary==3.3.4; extra == "binary"',
                    'psycopg-pool; extra == "pool"',
                ],
            ),
            "typing-extensions": FakeDistribution("4.15.0", []),
            "psycopg-binary": FakeDistribution("3.3.4", []),
        }

        with patch(
            "scripts.generate_sbom.metadata.distribution",
            side_effect=lambda name: distributions[name],
        ):
            components = _python_components(["psycopg[binary]>=3.2.0"], True)

        names = {component["name"] for component in components}
        self.assertIn("psycopg", names)
        self.assertIn("typing-extensions", names)
        self.assertIn("psycopg-binary", names)
        self.assertNotIn("psycopg-pool", names)


if __name__ == "__main__":
    unittest.main()
