"""Embedding pipeline tests.

Exercises the embedding layer end-to-end against the real example corpus
(after ingest):
    HashEmbedder -> VectorStore -> EmbedPipeline (incremental, dedup, metadata)

Covers: embedder determinism/dim, store upsert/dedup/delete/query, metadata
threading (title, pub date, source, category, industry, confidence),
incremental re-indexing, and similarity search.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from cyberrisk.knowledge.config import IngestConfig, load_ingest_config
from cyberrisk.knowledge.document import IngestDocument
from cyberrisk.knowledge.embedders import HashEmbedder, EmbedderRegistry
from cyberrisk.knowledge.embed_pipeline import (
    EmbedPipeline,
    chunk_content_hash,
    chunk_id,
    metadata_for_chunk,
)
from cyberrisk.knowledge.pipeline import load_corpus_manifest
from cyberrisk.knowledge.vector_store import VectorStore

REPO = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def docs() -> list[IngestDocument]:
    return load_corpus_manifest()


@pytest.fixture()
def config(tmp_path) -> IngestConfig:
    return load_ingest_config().model_copy(
        update={"derived_root": str(tmp_path / "derived")}
    )


def _dora(docs: list[IngestDocument]) -> IngestDocument:
    return next(d for d in docs if d.id == "corpus/regulatory/dora/ict-risk")


# ---------------------------------------------------------------------------
# HashEmbedder
# ---------------------------------------------------------------------------


def test_embedder_deterministic():
    e = HashEmbedder(dim=768)
    a = e.embed("ransomware extortion data breach")
    b = e.embed("ransomware extortion data breach")
    assert np.array_equal(a, b)
    assert a.shape == (768,)
    assert a.dtype == np.float32


def test_embedder_normalized():
    e = HashEmbedder(dim=768)
    v = e.embed("some longer text about supply chain compromise")
    assert np.allclose(np.linalg.norm(v), 1.0, atol=1e-5)


def test_embedder_distinct_text_differs():
    e = HashEmbedder(dim=768)
    a = e.embed("ransomware is a serious risk")
    b = e.embed("the weather today is pleasant")
    assert not np.array_equal(a, b)


def test_embedding_hash_changes_with_content():
    e = HashEmbedder(dim=768)
    h1 = e.embedding_hash("ransomware campaign")
    h2 = e.embedding_hash("ransomware campaign update")
    assert h1 != h2


def test_embedding_hash_deterministic():
    e = HashEmbedder(dim=768)
    assert e.embedding_hash("same text") == e.embedding_hash("same text")


def test_embedder_registry_default():
    r = EmbedderRegistry()
    e = r.get("default")
    assert isinstance(e, HashEmbedder)
    with pytest.raises(KeyError):
        r.get("does-not-exist")


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------


def test_store_upsert_and_count(tmp_path):
    store = VectorStore(tmp_path / "v.db")
    store.upsert_embedding(
        chunk_id="doc#1:abc", doc_id="doc", vector=np.ones(4, dtype=np.float32),
        content_hash="sha256:111", metadata={"title": "t"},
    )
    assert store.count() == 1
    store.upsert_embedding(
        chunk_id="doc#1:abc", doc_id="doc", vector=np.zeros(4, dtype=np.float32),
        content_hash="sha256:111", metadata={"title": "t"},
    )
    # Upsert on same id replaces, doesn't duplicate.
    assert store.count() == 1
    store.close()


def test_store_delete_document(tmp_path):
    store = VectorStore(tmp_path / "v.db")
    for i in range(3):
        store.upsert_embedding(
            chunk_id=f"doc#{i}:x", doc_id="doc", vector=np.ones(4, dtype=np.float32),
            content_hash=f"sha256:{i}", metadata={},
        )
    assert store.count() == 3
    store.delete_document("doc")
    assert store.count() == 0
    store.close()


def test_store_delete_chunk(tmp_path):
    store = VectorStore(tmp_path / "v.db")
    store.upsert_embedding(
        chunk_id="doc#1:a", doc_id="doc", vector=np.ones(4, dtype=np.float32),
        content_hash="sha256:1", metadata={},
    )
    assert store.delete_chunk("doc#1:a") == 1
    assert store.count() == 0
    store.close()


def test_store_chunk_ids_for_doc(tmp_path):
    store = VectorStore(tmp_path / "v.db")
    for i in range(2):
        store.upsert_embedding(
            chunk_id=f"doc#{i}:x", doc_id="doc", vector=np.ones(4, dtype=np.float32),
            content_hash=f"sha256:{i}", metadata={},
        )
    ids = store.chunk_ids_for_doc("doc")
    assert set(ids) == {"doc#0:x", "doc#1:x"}
    store.close()


# ---------------------------------------------------------------------------
# Metadata threading
# ---------------------------------------------------------------------------


def test_metadata_for_chunk_carries_requested_fields(docs: list[IngestDocument]):
    doc = _dora(docs)
    # A lightweight chunk with the required attrs.
    class _C:
        section_ref = "DORA > Scope"
        license_tier = doc.license_tier
        char_span = {"start": 0, "end": 100}

    meta = metadata_for_chunk(doc, _C())
    assert meta["title"] == doc.title
    assert meta["publication_date"] == "2023-01-16"  # from the manifest
    assert meta["source"] == doc.source
    assert meta["category"] == doc.domain
    assert meta["industry"] == "finance"  # canonical taxonomy key
    assert meta["confidence"] == pytest.approx(0.95)
    assert meta["section_ref"] == "DORA > Scope"


def test_metadata_falls_back_to_acquired_at():
    from cyberrisk.knowledge.document import IngestDocument, ChunkingSpec

    doc = IngestDocument(
        id="corpus/regulatory/dora/x",
        domain="regulatory",
        category="regulation",
        title="No pub date",
        source="Test",
        license_tier="public",
        version="1",
        content_hash="sha256:" + "0" * 64,
        acquired_at="2026-01-01",
        refresh_cadence="annual",
        chunking=ChunkingSpec(strategy="plain", max_chars=500, overlap=50),
        tags=["x"],
        status="active",
    )
    class _C:
        section_ref = "r"
        license_tier = "public"
        char_span = {"start": 0, "end": 10}

    meta = metadata_for_chunk(doc, _C())
    assert meta["publication_date"] == "2026-01-01"  # falls back to acquired_at


# ---------------------------------------------------------------------------
# EmbedPipeline (end-to-end on the real example corpus)
# ---------------------------------------------------------------------------


@pytest.fixture()
def embedded_pipeline(tmp_path, config: IngestConfig):
    """Ingest the example corpus into tmp derived, then embed it."""
    from cyberrisk.knowledge.pipeline import IngestPipeline

    ingest = IngestPipeline(config=config)
    ingest.ingest_corpus(force=True)
    pipe = EmbedPipeline(config=config)
    return pipe


def test_embed_corpus_populates_store(embedded_pipeline):
    report = embedded_pipeline.embed_corpus(force=True)
    assert report.embedded, "expected chunks embedded"
    assert not report.failed
    assert embedded_pipeline.store.count() == len(report.embedded)
    # Every stored row has the requested metadata.
    metas = embedded_pipeline.store.all_metadata()
    assert metas
    required = {"title", "publication_date", "source", "category", "industry", "confidence"}
    for m in metas:
        assert required <= set(m.keys())


def test_embed_corpus_incremental_skips_unchanged(embedded_pipeline):
    embedded_pipeline.embed_corpus(force=True)
    second = embedded_pipeline.embed_corpus(force=False)
    assert second.skipped
    assert not second.embedded
    # Store unchanged.
    count = embedded_pipeline.store.count()
    assert count == len(second.skipped)


def test_embed_corpus_dedup_duplicate_doc(embedded_pipeline, tmp_path, config):
    """Re-embedding the same doc (unchanged content) doesn't duplicate rows."""
    embedded_pipeline.embed_corpus(force=True)
    n1 = embedded_pipeline.store.count()
    embedded_pipeline.embed_corpus(force=False)
    n2 = embedded_pipeline.store.count()
    assert n2 == n1  # dedup: unchanged content not re-added


def test_chunk_id_and_hash_stable():
    h = chunk_content_hash("some content")
    assert h.startswith("sha256:")
    cid1 = chunk_id("corpus/x/doc", 1, h)
    cid2 = chunk_id("corpus/x/doc", 1, h)
    assert cid1 == cid2
    # The suffix is the FIRST 8 hex chars of the content sha256 — matching the
    # ingest writer's scheme (index.py chunk_record), not the tail.
    assert cid1 == "corpus/x/doc#1:" + h.removeprefix("sha256:")[:8]


# ---------------------------------------------------------------------------
# Similarity (future RAG query path)
# ---------------------------------------------------------------------------


def test_similarity_returns_nearest(tmp_path):
    store = VectorStore(tmp_path / "v.db")
    e = HashEmbedder(dim=32)
    texts = ["ransomware extortion payment", "supply chain compromise software", "weather forecast sunny"]
    for i, t in enumerate(texts):
        store.upsert_embedding(
            chunk_id=f"doc#{i}:x", doc_id="doc", vector=e.embed(t),
            content_hash=f"sha256:{i}", metadata={"title": f"chunk {i}", "content": t},
        )
    q = e.embed("ransomware payment")
    hits = store.similarity(q, k=1)
    assert hits
    # The ransomware chunk is the nearest neighbor.
    assert hits[0]["title"] == "chunk 0"
    store.close()
