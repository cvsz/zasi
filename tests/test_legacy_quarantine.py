"""Quarantine boundary enforcement for src/legacy/.

The authoritative application MUST NOT import from src.legacy unless the
import is wrapped by a typed adapter and listed in the capability registry.
This test verifies that core modules do not directly depend on quarantined
legacy adapters.
"""

import ast
import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_PATHS = [
    os.path.join(PROJECT_ROOT, "backend", "app.py"),
    os.path.join(PROJECT_ROOT, "src", "control_plane"),
]
LEGACY_PREFIX = "src.legacy"


class LegacyQuarantineTests(unittest.TestCase):
    def test_core_does_not_import_legacy(self):
        violations = []
        for root_path in CORE_PATHS:
            if os.path.isfile(root_path):
                candidates = [root_path]
            else:
                candidates = []
                for dirpath, _, filenames in os.walk(root_path):
                    for filename in filenames:
                        if filename.endswith(".py"):
                            candidates.append(os.path.join(dirpath, filename))
            for candidate in candidates:
                with open(candidate, "r", encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        if module == LEGACY_PREFIX or module.startswith(LEGACY_PREFIX + "."):
                            violations.append(
                                f"{os.path.relpath(candidate, PROJECT_ROOT)}:{node.lineno}:{module}"
                            )
        self.assertEqual(
            [],
            violations,
            f"Core code imports from src.legacy: {violations}",
        )
