import configparser
import unittest
from pathlib import Path


class SystemdDeploymentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.unit_path = (
            Path(__file__).resolve().parents[1]
            / "deploy"
            / "systemd"
            / "zasi-staging.service"
        )

    def test_staging_unit_requires_encrypted_credentials_and_private_runtime(self):
        self.assertTrue(self.unit_path.is_file())
        parser = configparser.ConfigParser(
            delimiters=("="),
            comment_prefixes=("#", ";"),
            strict=False,
        )
        parser.optionxform = str
        parser.read(self.unit_path, encoding="utf-8")
        service = parser["Service"]
        text = self.unit_path.read_text(encoding="utf-8")
        self.assertEqual(service["User"], "zasi")
        self.assertEqual(service["Group"], "zasi")
        self.assertIn(
            "zasi-secrets:/etc/zasi/staging/zasi-secrets.cred",
            service["LoadCredentialEncrypted"],
        )
        self.assertEqual(service["NoNewPrivileges"], "yes")
        self.assertEqual(service["ProtectSystem"], "strict")
        self.assertEqual(service["ProtectHome"], "read-only")
        self.assertEqual(service["PrivateTmp"], "yes")
        self.assertEqual(service["CapabilityBoundingSet"], "")
        self.assertIn("Environment=ZASI_SECRET_PROVIDER=systemd-credential", text)
        self.assertIn("Environment=ZASI_PROFILE=staging", text)
        self.assertIn("Environment=ZASI_ENABLE_EXTERNAL_EGRESS=no", text)
        self.assertIn("Environment=ZASI_ENABLE_PHYSICAL_ACTUATION=no", text)

    def test_staging_unit_is_loopback_only_and_bounded(self):
        text = self.unit_path.read_text(encoding="utf-8")
        self.assertIn("ZASI_HOST=127.0.0.1", text)
        self.assertIn("ZASI_ALLOW_PUBLIC_BIND=no", text)
        self.assertIn("MemoryMax=512M", text)
        self.assertIn("TasksMax=128", text)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", text)
        self.assertNotIn("0.0.0.0", text)
        self.assertNotIn("bash -c", text)


if __name__ == "__main__":
    unittest.main()
