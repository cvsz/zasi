import unittest
from pathlib import Path


class InstallerHardeningTests(unittest.TestCase):
    def test_installer_installs_only_the_current_build_output(self):
        installer = Path("install.sh").read_text(encoding="utf-8")

        self.assertIn('"${PYTHON_CMD}" -m build --outdir', installer)
        self.assertIn('wheel_file="$(find "${build_output}"', installer)
        self.assertNotIn('find "${REPO_ROOT}/dist"', installer)


if __name__ == "__main__":
    unittest.main()
