import json
import re
import unittest

from scripts.rollback_drill import (
    RollbackDrillError,
    RollbackDrillResult,
    create_ephemeral_database_name,
    quote_ephemeral_database_identifier,
    require_local_rehearsal,
    _require_local_postgresql_url,
    _url_for_database,
)


class RollbackDrillSafetyTests(unittest.TestCase):
    def test_local_rehearsal_requires_explicit_opt_in(self):
        with self.assertRaises(RollbackDrillError):
            require_local_rehearsal("local", acknowledged=False)

        self.assertEqual(
            require_local_rehearsal("local", acknowledged=True),
            "local-rehearsal",
        )

    def test_staging_and_production_profiles_are_rejected(self):
        for profile in ("staging", "production"):
            with self.subTest(profile=profile):
                with self.assertRaises(RollbackDrillError):
                    require_local_rehearsal(profile, acknowledged=True)

    def test_ephemeral_database_identifier_is_scoped_and_quoted(self):
        name = create_ephemeral_database_name()

        self.assertRegex(name, re.compile(r"^zasi_rollback_drill_[0-9a-f]{16}$"))
        self.assertEqual(quote_ephemeral_database_identifier(name), f'"{name}"')

        with self.assertRaises(RollbackDrillError):
            quote_ephemeral_database_identifier("zasi_rollback_drill_not-operator-input")

    def test_result_has_explicit_rehearsal_disclosure_and_no_target_name(self):
        result = RollbackDrillResult(
            schema_version=10,
            source_observation_unchanged=True,
            restored_integrity=True,
            cleanup_passed=True,
        )

        encoded = json.dumps(result.as_dict(), sort_keys=True)

        self.assertIn('"mode": "local-rehearsal"', encoded)
        self.assertIn('"status": "passed"', encoded)
        self.assertNotIn("rollback_drill_", encoded)

    def test_database_url_rewrite_preserves_socket_url_authority(self):
        rewritten = _url_for_database(
            "postgresql:///postgres?host=/var/run/postgresql&port=5433",
            "zasi_rollback_drill_0123456789abcdef",
        )

        self.assertEqual(
            rewritten,
            "postgresql:///zasi_rollback_drill_0123456789abcdef?host=/var/run/postgresql&port=5433",
        )

    def test_local_rehearsal_rejects_remote_database_hosts(self):
        with self.assertRaises(RollbackDrillError):
            _require_local_postgresql_url(
                "postgresql://db.example/zasi",
                "source URL",
            )

        _require_local_postgresql_url(
            "postgresql://127.0.0.1:5433/zasi",
            "source URL",
        )
        _require_local_postgresql_url(
            "postgresql:///postgres?host=/var/run/postgresql&port=5433",
            "administrator URL",
        )


if __name__ == "__main__":
    unittest.main()
