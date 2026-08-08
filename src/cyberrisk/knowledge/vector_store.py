"""SQLite vector store — persist chunk embeddings + metadata.

The knowledge index lives in ``derived/vector.db`` (a gitignored, regenerable
SQLite file — zero dependencies, SQL queryable, matches the architecture's D1
recommendation).  Each row is one embedded chunk:

    id            chunk_id (stable, content-hash-suffixed) — PRIMARY KEY
    doc_id        the source document
    chunk_id      the chunk's stable id
    vector        float32 bytes (numpy .tobytes())
    content_hash  sha256 of the chunk's *content* (dedup: identical content
                  is never indexed twice)
    metadata      JSON: title, publication_date, source, category (domain),
                  industry, confidence, section_ref, license_tier, char_span
    indexed_at    ISO timestamp of when the vector was written

Dedup is by content_hash: ``INSERT OR REPLACE`` on id, and the caller skips a
chunk whose content_hash already exists.  A changed chunk (same id, new
content) upserts over the stale row.  A duplicate document (identical chunks)
therefore never appears twice.

The store is thread-safe (one connection per thread via check_same_thread).
``similarity`` is the future RAG retrieval query path — built now, used later.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    vector BLOB NOT NULL,
    content_hash TEXT NOT NULL,
    metadata TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emb_doc ON embeddings(doc_id);
CREATE INDEX IF NOT EXISTS idx_emb_hash ON embeddings(content_hash);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VectorStore:
    """SQLite-backed vector store for chunk embeddings."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so a store opened once can be used from
        # any thread; the pipeline is single-threaded but this is safe.
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert_embedding(
        self,
        *,
        chunk_id: str,
        doc_id: str,
        vector: np.ndarray,
        content_hash: str,
        metadata: dict,
    ) -> None:
        """Insert or replace one embedding row.

        ``chunk_id`` is the primary key, so re-embedding a chunk (changed
        content) replaces its stale row rather than duplicating it.
        """
        self.conn.execute(
            """
            INSERT OR REPLACE INTO embeddings
                (id, doc_id, chunk_id, vector, content_hash, metadata, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                doc_id,
                chunk_id,
                np.asarray(vector, dtype=np.float32).tobytes(),
                content_hash,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                _now_iso(),
            ),
        )
        self.conn.commit()

    def delete_document(self, doc_id: str) -> int:
        """Delete all embedding rows for a document (on re-index of a changed doc).

        Returns the number of rows deleted.
        """
        cur = self.conn.execute("DELETE FROM embeddings WHERE doc_id = ?", (doc_id,))
        self.conn.commit()
        return cur.rowcount

    def delete_chunk(self, chunk_id: str) -> int:
        """Delete one embedding row by chunk_id (removes a stale vector).

        Returns the number of rows deleted (0 or 1).
        """
        cur = self.conn.execute("DELETE FROM embeddings WHERE id = ?", (chunk_id,))
        self.conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Read / query
    # ------------------------------------------------------------------

    def has_chunk(self, chunk_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM embeddings WHERE id = ?", (chunk_id,)
        ).fetchone()
        return row is not None

    def chunk_ids_for_doc(self, doc_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT id FROM embeddings WHERE doc_id = ?", (doc_id,)
        ).fetchall()
        return [r["id"] for r in rows]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])

    def by_doc_id(self, doc_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM embeddings WHERE doc_id = ?", (doc_id,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def all_metadata(self) -> list[dict]:
        """All stored metadata (for inspection / the future retrieval layer)."""
        rows = self.conn.execute("SELECT metadata FROM embeddings").fetchall()
        return [json.loads(r["metadata"]) for r in rows]

    def similarity(self, query_vec: np.ndarray, k: int = 10) -> list[dict]:
        """Top-k chunks by cosine similarity to ``query_vec``.

        This is the future RAG retrieval query path: brute-force cosine over
        the stored float32 BLOBs.  For a small corpus this is fine; a larger
        corpus can swap in an ANN index behind the same API.

        Returns a list of dicts (metadata + score) sorted by similarity desc.
        """
        q = np.asarray(query_vec, dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        rows = self.conn.execute(
            "SELECT id, doc_id, vector, metadata FROM embeddings"
        ).fetchall()
        scored = []
        for r in rows:
            v = np.frombuffer(r["vector"], dtype=np.float32)
            denom = float(np.linalg.norm(v))
            if denom == 0:
                continue
            score = float(np.dot(q, v) / (qn * denom))
            meta = json.loads(r["metadata"])
            # The metadata JSON doesn't carry the row's doc_id/chunk_id (they
            # are columns); attach them so a caller can resolve citations.
            meta["doc_id"] = r["doc_id"]
            meta["chunk_id"] = r["id"]
            meta["score"] = score
            scored.append(meta)
        scored.sort(key=lambda m: m["score"], reverse=True)
        return scored[:k]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "doc_id": row["doc_id"],
            "chunk_id": row["chunk_id"],
            "content_hash": row["content_hash"],
            "metadata": json.loads(row["metadata"]),
            "indexed_at": row["indexed_at"],
        }

    def __enter__(self) -> "VectorStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
