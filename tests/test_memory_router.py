import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.control_plane.storage import ControlPlaneStore


class MemoryRouterStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = ControlPlaneStore(":memory:")
        self.store.initialize()
        self.store.create_tenant("tenant-a")
        self.store.create_tenant("tenant-b")
        self.store.create_principal("principal-a", "tenant-a")
        self.store.create_principal("principal-b", "tenant-b")

    def tearDown(self):
        self.store.close()

    def test_project_retrieval_is_scoped_and_provenance_is_visible(self):
        self.store.create_memory(
            memory_id="memory-a",
            tenant_id="tenant-a",
            principal_id="principal-a",
            content="alpha project decision",
            scope="project",
            memory_type="project",
            project_id="project-alpha",
            source_ref="github:cvsz/zasi@abc123",
            provenance={"method": "operator-confirmed"},
            trust="verified_external",
        )
        self.store.create_memory(
            memory_id="memory-b",
            tenant_id="tenant-a",
            principal_id="principal-a",
            content="alpha project decision from another project",
            scope="project",
            memory_type="project",
            project_id="project-beta",
            source_ref="github:cvsz/other@def456",
        )

        alpha = self.store.search_memory(
            "tenant-a", "project decision", project_id="project-alpha"
        )
        self.assertEqual([item["memory_id"] for item in alpha], ["memory-a"])
        self.assertEqual(alpha[0]["provenance"], {"method": "operator-confirmed"})
        self.assertEqual(alpha[0]["source_ref"], "github:cvsz/zasi@abc123")
        self.assertEqual(alpha[0]["trust"], "verified_external")
        self.assertEqual(
            self.store.search_memory("tenant-b", "project decision", project_id="project-alpha"),
            [],
        )

    def test_expired_memory_is_invalidated_and_only_returned_when_requested(self):
        expired = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        self.store.create_memory(
            "memory-stale",
            "tenant-a",
            "principal-a",
            "stale release decision",
            "workspace",
            fresh_until=expired,
            source_ref="local:operator-note",
        )
        self.assertEqual(self.store.search_memory("tenant-a", "stale"), [])
        stale = self.store.search_memory("tenant-a", "stale", include_stale=True)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["status"], "stale")
        self.assertEqual(stale[0]["fresh_until"], expired.isoformat())

    def test_memory_type_requires_project_namespace_for_project_memory(self):
        with self.assertRaises(ValueError):
            self.store.create_memory(
                "memory-invalid",
                "tenant-a",
                "principal-a",
                "missing project namespace",
                "project",
                memory_type="project",
            )

    def test_project_namespace_cannot_be_attached_to_workspace_memory(self):
        with self.assertRaises(ValueError):
            self.store.create_memory(
                "memory-invalid-scope",
                "tenant-a",
                "principal-a",
                "workspace memory with project label",
                "workspace",
                project_id="project-alpha",
            )

    def test_legacy_memory_table_migrates_before_project_index_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy-memory.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE memory_items ("
                "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, principal_id TEXT NOT NULL, "
                "content TEXT NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL, "
                "created_at TEXT NOT NULL, deleted_at TEXT)"
            )
            connection.commit()
            connection.close()
            store = ControlPlaneStore(str(database))
            store.initialize()
            try:
                columns = {
                    row["name"]
                    for row in store._conn().execute("PRAGMA table_info(memory_items)").fetchall()
                }
                self.assertTrue({"project_id", "provenance_json", "fresh_until"}.issubset(columns))
            finally:
                store.close()
