"""Knowledge index writer — persist chunks + document metadata to derived/.

Writes two things under ``derived/`` (the gitignored, regenerable build
artifact):

    index.json                  document-level metadata + the section tree +
                                the ordered chunk_ids per document.  This is
                                the "structured knowledge index" a future RAG
                                retrieval layer queries.
    chunks/<doc_id>.json        one file per document holding its chunk
                                records, each conforming to
                                knowledge/schemas/chunk.schema.json.

The writer is deterministic: the same document + config produces identical
bytes, so re-ingestion is idempotent.  ``embedding_hash`` is left empty (the
embedding step is a separate, later pipeline stage) but the field is present
to honor the schema.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cyberrisk.knowledge.chunkers import Chunk
from cyberrisk.knowledge.document import IngestDocument
from cyberrisk.knowledge.extractors import Section


def _embedding_hash_placeholder(content: str) -> str:
    """Deterministic placeholder for the embedding_hash field.

    The embedding pipeline (future work) replaces this with the real vector
    hash; until then a content-derived value keeps chunk.schema.json valid and
    changes when content changes.
    """
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def chunk_record(
    chunk: Chunk,
    chunking_strategy: str,
) -> dict:
    """Build a chunk.schema.json-compliant record for one Chunk."""
    return {
        "chunk_id": (
            f"{chunk.doc_id}#{chunk.ordinal}"
            f":{hashlib.sha256(chunk.content.encode('utf-8')).hexdigest()[:8]}"
        ),
        "doc_id": chunk.doc_id,
        "content": chunk.content,
        "section_ref": chunk.section_ref,
        "char_span": chunk.char_span,
        "embedding_hash": _embedding_hash_placeholder(chunk.content),
        "license_tier": chunk.license_tier,
        "chunking_strategy": chunking_strategy,
    }


def section_tree(sections: list[Section]) -> list[dict]:
    """Serialize the document's section structure for the index."""
    return [
        {
            "heading": s.heading,
            "char_start": s.start_char,
            "char_end": s.start_char + len(s.text),
        }
        for s in sections
    ]


def write_document(
    derived_root: Path,
    doc: IngestDocument,
    chunks: list[Chunk],
    sections: list[Section],
    source_path: str,
) -> dict:
    """Write one document's chunks + return its index record.

    Writes derived/chunks/<display_id>.json (flat filename — the doc id is a
    nested path).  Returns the record to append to index.json (the caller
    manages the full index), built from the SAME chunk_records that were
    written, so the record and the chunk store never diverge.
    """
    chunk_dir = derived_root / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    records = [chunk_record(c, doc.chunking.strategy) for c in chunks]
    chunk_path = chunk_dir / f"{doc.display_id()}.json"
    chunk_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "doc_id": doc.id,
        "title": doc.title,
        "source": doc.source,
        "license_tier": doc.license_tier,
        "version": doc.version,
        "content_hash": doc.content_hash,
        "acquired_at": doc.acquired_at,
        "format": doc.fmt,
        "status": doc.status,
        "chunking_strategy": doc.chunking.strategy,
        "chunk_count": len(records),
        "chunk_ids": [r["chunk_id"] for r in records],
        "section_tree": section_tree(sections),
        "source_path": source_path,
    }


def write_index(derived_root: Path, records: list[dict]) -> Path:
    """Write derived/index/index.json from per-document index records.

    Returns the path written.  Indexing is rebuilt from the chunk store each
    time (idempotent).
    """
    index_dir = derived_root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    path = index_dir / "index.json"
    payload = {
        "schema": "https://cyberrisk.ai/schemas/index.schema.json",
        "document_count": len(records),
        "documents": records,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
