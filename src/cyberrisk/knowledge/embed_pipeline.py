"""Embedding pipeline — embed every chunk, store in the vector DB, incremental.

Runs AFTER the ingest pipeline.  It reads the ingest output
(``derived/chunks/<display_id>.json`` + ``derived/index/index.json`` +
``derived/state/ingest_state.json``) and writes embeddings to
``derived/vector.db`` (SQLite), preserving document metadata on every chunk:

    title, publication_date, source, category (domain), industry, confidence,
    + section_ref, license_tier, char_span

Incremental + dedup (the requirement "re-index only new or modified files"):

    * a chunk is embedded only if it's new, or its content changed, or
      ``force`` is set,
    * a changed chunk upserts over its stale row (same chunk_id primary key),
    * a duplicate document (identical content_hash) is skipped entirely,
    * on a re-embedded changed document, its old rows are deleted first so no
      stale vectors survive.

Embedding state is recorded in ``derived/state/embed_state.json`` as
{doc_id: {chunk_id: content_hash}}, so a second run skips everything that
hasn't changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from cyberrisk.knowledge.config import IngestConfig, load_ingest_config
from cyberrisk.knowledge.document import IngestDocument
from cyberrisk.knowledge.embedders import HashEmbedder, EmbedderRegistry
from cyberrisk.knowledge.pipeline import DEFAULT_MANIFEST, load_corpus_manifest
from cyberrisk.knowledge.vector_store import VectorStore


def chunk_content_hash(content: str) -> str:
    """sha256 of a chunk's content (the dedup key)."""
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def chunk_id(doc_id: str, ordinal: int, content_hash: str) -> str:
    """Stable chunk id matching the ingest writer's scheme (doc#ordinal:hash8).

    The ingest writer (index.py chunk_record) uses the FIRST 8 hex chars of the
    content's sha256 as the suffix.  ``content_hash`` here is the full
    ``sha256:...`` string; its hex is the sha256 of the content, so the suffix
    must be the first 8 hex chars — NOT ``[-8:]`` (the tail), which diverges.
    """
    hex_part = content_hash.removeprefix("sha256:")
    return f"{doc_id}#{ordinal}:{hex_part[:8]}"


def metadata_for_chunk(
    doc: IngestDocument,
    chunk,
) -> dict:
    """Thread the requested document metadata onto one chunk's embedding row.

    Joins IngestDocument metadata with the chunk's own fields.  The vector
    store's metadata JSON carries title, publication_date (fallback acquired_at),
    source, category (domain), industry, confidence, section_ref, license_tier,
    char_span, and the embedder name.
    """
    pub_date = doc.publication_date or doc.acquired_at
    return {
        "doc_id": doc.id,
        "title": doc.title,
        "publication_date": pub_date,
        "source": doc.source,
        "category": doc.domain,
        "industry": doc.industry or "",
        "confidence": doc.confidence,
        "section_ref": chunk.section_ref,
        "license_tier": doc.license_tier,
        "char_span": chunk.char_span,
    }


# ---------------------------------------------------------------------------
# Embedding report
# ---------------------------------------------------------------------------


@dataclass
class EmbedReport:
    embedded: list[str] = field(default_factory=list)  # chunk ids embedded
    skipped: list[str] = field(default_factory=list)  # chunk ids unchanged
    failed: list[tuple[str, str]] = field(default_factory=list)  # (chunk_id, error)

    @property
    def total(self) -> int:
        return len(self.embedded) + len(self.skipped) + len(self.failed)

    def summary(self) -> str:
        return (
            f"embedded {len(self.embedded)}, skipped {len(self.skipped)} "
            f"(unchanged), failed {len(self.failed)}"
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class EmbedPipeline:
    """Incremental embedding orchestrator over the ingest output."""

    def __init__(
        self,
        config: IngestConfig | None = None,
        embedder=None,
        vector_store: VectorStore | None = None,
        corpus_root: str | Path | None = None,
        manifest_path: str | Path | None = None,
    ) -> None:
        self.config = config or load_ingest_config()
        self.embedder = embedder or EmbedderRegistry().get("default")
        self.manifest_path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST
        if vector_store is None:
            vector_store = VectorStore(self.config.derived_path / "vector.db")
        self.store = vector_store
        self._state_path = self.config.derived_path / "state" / "embed_state.json"

    def close(self) -> None:
        """Close the underlying vector store (releases the SQLite lock)."""
        self.store.close()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, dict[str, str]]:
        if self._state_path.exists():
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        return {}

    def _save_state(self, state: dict[str, dict[str, str]]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Single document
    # ------------------------------------------------------------------

    def embed_document(
        self,
        doc: IngestDocument,
        chunks: list,
        force: bool = False,
    ) -> tuple[list[str], list[str]]:
        """Embed a document's chunks into the store.

        Returns (embedded_ids, skipped_ids).  A changed document has its old
        rows deleted first (no stale vectors).  Each chunk's embedding is
        upserted (INSERT OR REPLACE on chunk_id), so a duplicate never stacks.
        """
        state = self._load_state()
        doc_state = state.get(doc.id, {})
        embedded: list[str] = []
        skipped: list[str] = []
        current_ids: set[str] = set()

        for chunk in chunks:
            h = chunk_content_hash(chunk.content)
            cid = chunk_id(doc.id, chunk.ordinal, h)
            current_ids.add(cid)
            if not force and doc_state.get(cid) == h:
                skipped.append(cid)
                continue
            vec = self.embedder.embed(chunk.content)
            self.store.upsert_embedding(
                chunk_id=cid,
                doc_id=doc.id,
                vector=vec,
                content_hash=h,
                metadata=metadata_for_chunk(doc, chunk),
            )
            doc_state[cid] = h
            embedded.append(cid)

        # Remove any stored rows for this doc that are NOT part of the current
        # chunk set (stale ids from a previous embedding, e.g. an old hash
        # scheme).  This keeps the vector DB in sync with the chunk store even
        # when chunk_ids change across re-embeds.
        stored_ids = set(self.store.chunk_ids_for_doc(doc.id))
        stale = stored_ids - current_ids
        for cid in stale:
            self.store.delete_chunk(cid)
        state[doc.id] = doc_state
        self._save_state(state)
        return embedded, skipped

    # ------------------------------------------------------------------
    # Corpus
    # ------------------------------------------------------------------

    def embed_corpus(self, force: bool = False) -> EmbedReport:
        """Embed every active document's chunks from the ingest output.

        Reads chunks from ``derived/chunks/<display_id>.json`` and document
        metadata from ``self.manifest_path`` (the manifest the pipeline was
        built with).  Incremental: unchanged chunks are skipped.
        """
        docs = load_corpus_manifest(self.manifest_path)
        report = EmbedReport()
        chunks_dir = self.config.derived_path / "chunks"

        for doc in docs:
            chunk_file = chunks_dir / f"{doc.display_id()}.json"
            if not chunk_file.exists():
                report.failed.append((doc.id, "no chunk file (run ingest first)"))
                continue
            try:
                chunk_records = json.loads(chunk_file.read_text(encoding="utf-8"))
                chunks = self._records_to_chunks(doc, chunk_records)
                embedded, skipped = self.embed_document(doc, chunks, force=force)
                report.embedded.extend(embedded)
                report.skipped.extend(skipped)
            except Exception as exc:  # noqa: BLE001 — collect per-doc failures
                report.failed.append((doc.id, f"{type(exc).__name__}: {exc}"))

        return report

    @staticmethod
    def _records_to_chunks(doc: IngestDocument, records: list[dict]):
        """Rebuild Chunk-like objects from the stored chunk records."""
        from cyberrisk.knowledge.chunkers import Chunk

        chunks = []
        for i, rec in enumerate(records, start=1):
            chunks.append(
                Chunk(
                    doc_id=doc.id,
                    ordinal=i,
                    content=rec["content"],
                    section_ref=rec["section_ref"],
                    char_start=rec["char_span"]["start"],
                    char_end=rec["char_span"]["end"],
                    license_tier=rec["license_tier"],
                )
            )
        return chunks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m cyberrisk.knowledge.embed_pipeline [--config PATH] [--force] [--doc ID]"""
    parser = argparse.ArgumentParser(
        prog="cyberrisk.knowledge.embed_pipeline",
        description="CyberRisk AI knowledge embedding pipeline (run after ingest)",
    )
    parser.add_argument("--config", default=None, help="IngestConfig YAML path")
    parser.add_argument("--force", action="store_true", help="Re-embed all chunks")
    parser.add_argument("--doc", default=None, help="Embed only this document id")
    parser.add_argument("--db", default=None, help="Vector DB path override")
    args = parser.parse_args(argv)

    config = load_ingest_config(args.config)
    store = VectorStore(args.db) if args.db else VectorStore(config.derived_path / "vector.db")
    pipeline = EmbedPipeline(config=config, vector_store=store)

    if args.doc:
        docs = load_corpus_manifest()
        doc = next((d for d in docs if d.id == args.doc), None)
        if doc is None:
            print(f"document {args.doc!r} not found in manifest")
            return 1
        chunk_file = config.derived_path / "chunks" / f"{doc.display_id()}.json"
        if not chunk_file.exists():
            print(f"no chunk file for {doc.id} (run ingest first)")
            return 1
        records = json.loads(chunk_file.read_text(encoding="utf-8"))
        chunks = pipeline._records_to_chunks(doc, records)
        embedded, skipped = pipeline.embed_document(doc, chunks, force=args.force)
        print(f"embedded {len(embedded)}, skipped {len(skipped)} (unchanged)")
        return 0

    report = pipeline.embed_corpus(force=args.force)
    print(report.summary())
    for cid in report.embedded:
        print(f"  embedded  {cid}")
    for cid in report.skipped:
        print(f"  skipped   {cid} (unchanged)")
    for cid, err in report.failed:
        print(f"  FAILED    {cid}: {err}")
    return 0 if not report.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
