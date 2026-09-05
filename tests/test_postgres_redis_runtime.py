import os
import unittest
from unittest.mock import Mock

from src.control_plane.storage.postgres_storage import (
    _POSTGRES_SCHEMA_STATEMENTS,
    _PostgresConnection,
)
from src.control_plane.storage import CURRENT_SCHEMA_VERSION
from src.control_plane.storage.redis_runtime import RedisRuntime


class PostgresRedisRuntimeTests(unittest.TestCase):
    def test_postgres_schema_migrates_pairing_idempotency_column_before_index(self):
        schema = "\n".join(_POSTGRES_SCHEMA_STATEMENTS)
        self.assertIn(
            "ALTER TABLE device_pairing_challenges "
            "ADD COLUMN IF NOT EXISTS idempotency_key TEXT",
            schema,
        )

    def test_postgres_connection_translates_sqlite_compatibility_statements(self):
        raw = Mock()
        raw.execute.return_value = Mock()
        connection = _PostgresConnection(raw)

        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO tenants(id, status, created_at) VALUES(?, 'active', ?)",
            ("tenant", "now"),
        )
        connection.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', '7')"
        )

        calls = [call.args[0] for call in raw.execute.call_args_list]
        self.assertEqual(calls[0], "BEGIN")
        self.assertIn("ON CONFLICT DO NOTHING", calls[1])
        self.assertIn("ON CONFLICT (key) DO UPDATE", calls[2])
        self.assertIn("%s", calls[1])

    def test_redis_rate_limit_is_atomic_and_namespaced(self):
        runtime = object.__new__(RedisRuntime)
        runtime._client = Mock()
        runtime._client.eval.return_value = 1

        allowed, retry_after = runtime.consume_rate_limit(
            "tenant-a", "request:ip:127.0.0.1", 2, 60
        )

        self.assertTrue(allowed)
        self.assertGreaterEqual(retry_after, 0)
        script, key_count, key, window = runtime._client.eval.call_args.args
        self.assertIn("INCRBY", script)
        self.assertEqual(key_count, 1)
        self.assertTrue(key.startswith("zasi:ratelimit:"))
        self.assertEqual(window, "60")

    def test_redis_rate_limit_supports_a_scoped_staging_prefix(self):
        runtime = object.__new__(RedisRuntime)
        runtime._client = Mock()
        runtime._client.eval.return_value = 1
        runtime._key_prefix = "zasi:staging"

        runtime.consume_rate_limit("tenant-a", "subject", 2, 60)

        key = runtime._client.eval.call_args.args[2]
        self.assertTrue(key.startswith("zasi:staging:ratelimit:"))

    @unittest.skipUnless(
        os.environ.get("ZASI_TEST_POSTGRES_URL"),
        "set ZASI_TEST_POSTGRES_URL to run the live PostgreSQL integration check",
    )
    def test_live_postgres_schema_is_available(self):
        from src.control_plane.storage.postgres_storage import PostgresControlPlaneStore

        store = PostgresControlPlaneStore(os.environ["ZASI_TEST_POSTGRES_URL"])
        try:
            store.initialize()
            self.assertEqual(store.schema_version(), CURRENT_SCHEMA_VERSION)
            self.assertTrue(store.integrity_check())
        finally:
            store.close()

    @unittest.skipUnless(
        os.environ.get("ZASI_TEST_REDIS_URL"),
        "set ZASI_TEST_REDIS_URL to run the live Redis integration check",
    )
    def test_live_redis_authentication_is_available(self):
        runtime = RedisRuntime(os.environ["ZASI_TEST_REDIS_URL"])
        try:
            self.assertTrue(runtime.ping())
        finally:
            runtime.close()
