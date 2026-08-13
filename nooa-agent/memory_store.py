"""
Long-term memory store with typed knowledge graph.

NOOA capability #5 (explicit object state) + #6 (model-callable APIs):
- Entities with types, importance, tags
- Typed relations: supports, contradicts, derived-from, related-to
- Observations attached to entities
- Background consolidation: merge duplicates, link records, prune stale
- Single SQLite file — inspectable, backupable, reviewable

Filosofía NOOA: el agente cura su propia memoria mediante tools.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).parent / "agent_memory.db"


@dataclass
class Entity:
    """Nodo del knowledge graph."""
    name: str
    entity_type: str
    observations: list[str] = field(default_factory=list)
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Relation:
    """Arco dirigido entre entidades."""
    from_entity: str
    to_entity: str
    relation_type: str  # supports, contradicts, derived-from, related-to
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)


class MemoryStore:
    """
    Knowledge graph persistente en SQLite.

    Uso:
        store = MemoryStore(":memory:")  # o path a .db
        store.create_entity("earthquake_001", "event", ["M6.2 en Bogotá"], importance=0.9)
        store.create_relation("earthquake_001", "hospital_norte", "related-to")
        results = store.search("earthquake")
    """

    def __init__(self, db_path: str | Path | None = None):
        path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._db_path = str(path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                name TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                observations TEXT NOT NULL DEFAULT '[]',
                importance REAL NOT NULL DEFAULT 0.5,
                tags TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_entity TEXT NOT NULL,
                to_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                created_at REAL NOT NULL,
                FOREIGN KEY (from_entity) REFERENCES entities(name) ON DELETE CASCADE,
                FOREIGN KEY (to_entity) REFERENCES entities(name) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_entities_importance ON entities(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_entity);
            CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_entity);
            CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
        """)
        self._conn.commit()

    # ─── CRUD: Entities ──────────────────────────────────────────

    def create_entity(
        self,
        name: str,
        entity_type: str,
        observations: list[str] | None = None,
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> Entity:
        now = time.time()
        obs_json = json.dumps(observations or [], ensure_ascii=False)
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        self._conn.execute(
            """INSERT OR REPLACE INTO entities (name, entity_type, observations, importance, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM entities WHERE name=?), ?), ?)""",
            (name, entity_type, obs_json, importance, tags_json, name, now, now),
        )
        self._conn.commit()
        logger.debug("Entity created: %s (%s)", name, entity_type)
        return self.get_entity(name)

    def get_entity(self, name: str) -> Entity | None:
        row = self._conn.execute("SELECT * FROM entities WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        return Entity(
            name=row["name"],
            entity_type=row["entity_type"],
            observations=json.loads(row["observations"]),
            importance=row["importance"],
            tags=json.loads(row["tags"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_observations(self, name: str, observations: list[str]) -> Entity | None:
        entity = self.get_entity(name)
        if not entity:
            return None
        entity.observations.extend(observations)
        entity.updated_at = time.time()
        self._conn.execute(
            "UPDATE entities SET observations=?, updated_at=? WHERE name=?",
            (json.dumps(entity.observations, ensure_ascii=False), entity.updated_at, name),
        )
        self._conn.commit()
        return entity

    def delete_entity(self, name: str) -> bool:
        cur = self._conn.execute("DELETE FROM entities WHERE name=?", (name,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_entities(self, entity_type: str | None = None, min_importance: float = 0.0) -> list[Entity]:
        if entity_type:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE entity_type=? AND importance>=? ORDER BY importance DESC",
                (entity_type, min_importance),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE importance>=? ORDER BY importance DESC",
                (min_importance,),
            ).fetchall()
        return [Entity(
            name=r["name"], entity_type=r["entity_type"],
            observations=json.loads(r["observations"]),
            importance=r["importance"], tags=json.loads(r["tags"]),
            created_at=r["created_at"], updated_at=r["updated_at"],
        ) for r in rows]

    # ─── CRUD: Relations ─────────────────────────────────────────

    def create_relation(self, from_entity: str, to_entity: str, relation_type: str, weight: float = 1.0) -> Relation | None:
        # Verify both entities exist
        if not self.get_entity(from_entity) or not self.get_entity(to_entity):
            logger.warning("Relation skipped: %s or %s not found", from_entity, to_entity)
            return None
        now = time.time()
        self._conn.execute(
            "INSERT INTO relations (from_entity, to_entity, relation_type, weight, created_at) VALUES (?, ?, ?, ?, ?)",
            (from_entity, to_entity, relation_type, weight, now),
        )
        self._conn.commit()
        return Relation(from_entity=from_entity, to_entity=to_entity, relation_type=relation_type, weight=weight, created_at=now)

    def get_relations(self, entity_name: str, relation_type: str | None = None) -> list[Relation]:
        if relation_type:
            rows = self._conn.execute(
                "SELECT * FROM relations WHERE (from_entity=? OR to_entity=?) AND relation_type=?",
                (entity_name, entity_name, relation_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM relations WHERE from_entity=? OR to_entity=?",
                (entity_name, entity_name),
            ).fetchall()
        return [Relation(
            from_entity=r["from_entity"], to_entity=r["to_entity"],
            relation_type=r["relation_type"], weight=r["weight"],
            created_at=r["created_at"],
        ) for r in rows]

    def delete_relation(self, from_entity: str, to_entity: str, relation_type: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM relations WHERE from_entity=? AND to_entity=? AND relation_type=?",
            (from_entity, to_entity, relation_type),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ─── Search ───────────────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[Entity]:
        """Full-text search across entity names, types, observations, and tags.

        Accent-insensitive: "bogota" matches "Bogotá".
        Uses SQL LIKE for initial candidate fetch, then Python-side
        accent-insensitive filtering for precise matching.
        """
        query_normalized = _strip_accents(query).lower()

        # Fetch candidates: try SQL LIKE first, fall back to all entities
        like = f"%{query}%"
        rows = self._conn.execute(
            """SELECT DISTINCT e.* FROM entities e
               LEFT JOIN relations r ON e.name = r.from_entity OR e.name = r.to_entity
               WHERE e.name LIKE ? OR e.entity_type LIKE ? OR e.observations LIKE ? OR e.tags LIKE ?
                  OR r.relation_type LIKE ?
               ORDER BY e.importance DESC
               LIMIT ?""",
            (like, like, like, like, like, limit * 5),
        ).fetchall()

        # If SQL LIKE missed (e.g., accent mismatch), fetch all as fallback
        if not rows:
            rows = self._conn.execute(
                "SELECT * FROM entities ORDER BY importance DESC LIMIT ?",
                (limit * 5,),
            ).fetchall()

        # Filter in Python for accent-insensitive matching
        results = []
        for r in rows:
            entity = Entity(
                name=r["name"], entity_type=r["entity_type"],
                observations=json.loads(r["observations"]),
                importance=r["importance"], tags=json.loads(r["tags"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            searchable = _strip_accents(
                f"{entity.name} {entity.entity_type} {' '.join(entity.observations)} {' '.join(entity.tags)}"
            ).lower()
            if query_normalized in searchable:
                results.append(entity)
                if len(results) >= limit:
                    break

        return results

    # ─── Consolidation ────────────────────────────────────────────

    def consolidate(self, min_importance: float = 0.1) -> dict[str, int]:
        """
        Background pass: merge duplicates, prune stale low-importance records.

        Returns stats dict with counts of operations performed.
        """
        stats = {"merged": 0, "pruned": 0, "linked": 0}

        # Prune low-importance entities older than 30 days with no relations
        cutoff = time.time() - 30 * 86400
        stale = self._conn.execute(
            """SELECT e.name FROM entities e
               LEFT JOIN relations r ON e.name = r.from_entity OR e.name = r.to_entity
               WHERE e.importance < ? AND e.updated_at < ? AND r.id IS NULL""",
            (min_importance, cutoff),
        ).fetchall()
        for row in stale:
            self.delete_entity(row["name"])
            stats["pruned"] += 1

        # Merge entities with same name (case-insensitive duplicates)
        dupes = self._conn.execute(
            "SELECT LOWER(name) as ln, COUNT(*) as cnt FROM entities GROUP BY ln HAVING cnt > 1"
        ).fetchall()
        for row in dupes:
            entities = self._conn.execute(
                "SELECT name FROM entities WHERE LOWER(name)=? ORDER BY updated_at DESC", (row["ln"],)
            ).fetchall()
            keeper = entities[0]["name"]
            for dup in entities[1:]:
                # Move observations to keeper
                dup_obs = self.get_entity(dup["name"])
                if dup_obs:
                    self.add_observations(keeper, dup_obs.observations)
                # Move relations to keeper
                for rel in self.get_relations(dup["name"]):
                    if rel.from_entity == dup["name"]:
                        self.create_relation(keeper, rel.to_entity, rel.relation_type, rel.weight)
                    else:
                        self.create_relation(rel.from_entity, keeper, rel.relation_type, rel.weight)
                self.delete_entity(dup["name"])
                stats["merged"] += 1

        # Link entities sharing observations (derived-from)
        # Simple heuristic: if two entities share >= 2 observation substrings, link them
        all_entities = self.list_entities()
        for i, e1 in enumerate(all_entities):
            for e2 in all_entities[i + 1:]:
                shared = set(e1.observations) & set(e2.observations)
                if len(shared) >= 2:
                    existing = self._conn.execute(
                        "SELECT id FROM relations WHERE from_entity=? AND to_entity=? AND relation_type='derived-from'",
                        (e1.name, e2.name),
                    ).fetchone()
                    if not existing:
                        self.create_relation(e1.name, e2.name, "derived-from", weight=0.5)
                        stats["linked"] += 1

        self._conn.commit()
        if any(stats.values()):
            logger.info("Consolidation: merged=%d pruned=%d linked=%d", stats["merged"], stats["pruned"], stats["linked"])
        return stats

    # ─── Graph export ─────────────────────────────────────────────

    def export_graph(self) -> dict[str, Any]:
        """Export full knowledge graph as dict (for LLM inspection)."""
        entities = self.list_entities()
        seen_relations: set[tuple[str, str, str]] = set()
        relations = []
        for e in entities:
            for r in self.get_relations(e.name):
                key = (r.from_entity, r.to_entity, r.relation_type)
                if key not in seen_relations:
                    seen_relations.add(key)
                    relations.append(r)
        return {
            "entities": [
                {
                    "name": e.name,
                    "type": e.entity_type,
                    "observations": e.observations,
                    "importance": e.importance,
                    "tags": e.tags,
                }
                for e in entities
            ],
            "relations": [
                {"from": r.from_entity, "to": r.to_entity, "type": r.relation_type, "weight": r.weight}
                for r in relations
            ],
        }

    def close(self):
        self._conn.close()


def _strip_accents(text: str) -> str:
    """Remove accents from unicode text: 'Bogotá' → 'Bogota'."""
    return ''.join(
        c for c in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(c)
    )
