# src/utils/embed_cache.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Sequence, Set, Tuple

import numpy as np 

SCHEMA_SQL = """
-- content -> vector (dedup across docs)
CREATE TABLE IF NOT EXISTS vector_store (
  cache_key TEXT PRIMARY KEY,
  dim INTEGER NOT NULL,
  vec BLOB NOT NULL,
  created_at TEXT NOT NULL
);

-- doc+chunk bookkeeping (idempotency; prevents duplicate JSONL appends on rerun)
CREATE TABLE IF NOT EXISTS doc_vectors (
  doc_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  embedder_id TEXT NOT NULL,
  cache_key TEXT NOT NULL,
  vec_path TEXT NOT NULL,
  dim INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (doc_id, chunk_id, embedder_id)
);

CREATE INDEX IF NOT EXISTS idx_doc_vectors_cache_key ON doc_vectors(cache_key);
CREATE INDEX IF NOT EXISTS idx_doc_vectors_doc_id ON doc_vectors(doc_id);

"""


@dataclass(frozen=True)
class CacheDb:
    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.path), timeout=5.0, isolation_level=None)
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA busy_timeout=5000;")
        con.executescript(SCHEMA_SQL)
        return con


def lookup_existing_vectors(
    con: sqlite3.Connection,
    keys: Sequence[str],
    *,
    chunk_size: int = 800,
) -> Set[str]:
    """Return subset of keys that exist in vector_store."""
    found: Set[str] = set()
    if not keys:
        return found

    i = 0
    while i < len(keys):
        batch = keys[i : i + chunk_size]
        placeholders = ",".join(["?"] * len(batch))
        q = f"SELECT cache_key FROM vector_store WHERE cache_key IN ({placeholders})"
        for (ck,) in con.execute(q, batch):
            found.add(ck)
        i += chunk_size

    return found


def fetch_vectors(
    con: sqlite3.Connection,
    keys: Sequence[str],
    *,
    chunk_size: int = 500,
) -> Dict[str, Tuple[int, list[float]]]:
    """
    Returns: {cache_key: (dim, vector_as_list)}
    """
    out: Dict[str, Tuple[int, list[float]]] = {}
    if not keys:
        return out

    i = 0
    while i < len(keys):
        batch = keys[i : i + chunk_size]
        placeholders = ",".join(["?"] * len(batch))
        q = f"SELECT cache_key, dim, vec FROM vector_store WHERE cache_key IN ({placeholders})"
        for ck, dim, blob in con.execute(q, batch):
            arr = np.frombuffer(blob, dtype=np.float32)
            # safety
            if int(dim) != int(arr.size):
                continue
            out[str(ck)] = (int(dim), arr.tolist())
        i += chunk_size

    return out


def upsert_vectors(
    con: sqlite3.Connection,
    rows: Iterable[tuple[str, int, bytes, str]],
) -> None:
    """
    rows: (cache_key, dim, vec_blob, created_at)
    Idempotent via INSERT OR IGNORE.
    """
    con.execute("BEGIN;")
    try:
        con.executemany(
            """
            INSERT OR IGNORE INTO vector_store(cache_key, dim, vec, created_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")
        raise

def lookup_existing_doc_chunks(
    con: sqlite3.Connection,
    doc_id: str,
    embedder_id: str,
    chunk_ids: Sequence[str],
    *,
    chunk_size: int = 800,
) -> Set[str]:
    found: Set[str] = set()
    if not chunk_ids:
        return found

    i = 0
    while i < len(chunk_ids):
        batch = chunk_ids[i:i+chunk_size]
        placeholders = ",".join(["?"] * len(batch))
        q = f"""
        SELECT chunk_id
        FROM doc_vectors
        WHERE doc_id=? AND embedder_id=? AND chunk_id IN ({placeholders})
        """
        params = [doc_id, embedder_id, *batch]
        for (cid,) in con.execute(q, params):
            found.add(str(cid))
        i += chunk_size

    return found

def insert_doc_vectors(
    con: sqlite3.Connection,
    rows: Iterable[tuple[str, str, str, str, str, int, str]],
) -> None:
    """
    rows: (doc_id, chunk_id, embedder_id, cache_key, vec_path, dim, created_at)
    """
    con.execute("BEGIN;")
    try:
        con.executemany(
            """
            INSERT OR IGNORE INTO doc_vectors
              (doc_id, chunk_id, embedder_id, cache_key, vec_path, dim, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")
        raise
