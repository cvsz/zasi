"""
Persistent Hypergraph Database Layer with SQLite
"""
import sqlite3
import json
from typing import Dict, List, Any, Optional
from .memory_hypergraph import DynamicHypergraphMemory

class PersistentHypergraphStorage:
    def __init__(self, db_path: str = "/home/cvsz/zasi/zasi_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    attributes TEXT,
                    embedding TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hyperedges (
                    id TEXT PRIMARY KEY,
                    nodes TEXT,
                    relation TEXT,
                    weight REAL
                )
            """)
            conn.commit()

    def sync_to_disk(self, memory: DynamicHypergraphMemory):
        """Serializes in-memory hypergraph to SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Sync nodes
            for entity_id, data in memory.nodes.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO entities (id, attributes, embedding) VALUES (?, ?, ?)",
                    (entity_id, json.dumps(data["attributes"]), json.dumps(data["embedding"]))
                )
            # Sync hyperedges
            for edge_id, edge in memory.edges.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO hyperedges (id, nodes, relation, weight) VALUES (?, ?, ?, ?)",
                    (edge_id, json.dumps(list(edge.nodes)), edge.relation, edge.weight)
                )
            conn.commit()

    def load_from_disk(self) -> DynamicHypergraphMemory:
        """Restores in-memory hypergraph from SQLite."""
        memory = DynamicHypergraphMemory()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, attributes, embedding FROM entities")
            for row in cursor.fetchall():
                entity_id, attrs, embed = row[0], json.loads(row[1]), json.loads(row[2])
                memory.insert_entity(entity_id, attrs, embed)

            cursor.execute("SELECT id, nodes, relation, weight FROM hyperedges")
            for row in cursor.fetchall():
                edge_id, nodes, rel, weight = row[0], set(json.loads(row[1])), row[2], row[3]
                memory.create_hyperedge(edge_id, nodes, rel, weight)
        return memory
