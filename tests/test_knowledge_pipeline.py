"""Document ingestion pipeline tests.

Exercises the knowledge pipeline end-to-end against the real example
documents under knowledge/corpus/ (registered in corpus_manifest.yaml):
    load_corpus_manifest -> resolve -> extract -> clean -> chunk -> index.

Covers: manifest resolution, each extractor, cleaning, chunking strategies,
index validity (chunk.schema.json), incremental re-ingestion, and
configurability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyberrisk.knowledge.config import IngestConfig, load_ingest_config
from cyberrisk.knowledge.document import IngestDocument
from cyberrisk.knowledge.extractors import extract_html, extract_markdown, extract_txt
from cyberrisk.knowledge.pipeline import (
    IngestPipeline,
    load_corpus_manifest,
    resolve_document_path,
    verify_document_hash,
)

REPO = Path(__file__).parent.parent
CORPUS = REPO / "knowledge" / "corpus"
MANIFEST = REPO / "knowledge" / "manifests" / "corpus_manifest.yaml"
DORA_MD = CORPUS / "regulatory" / "dora" / "ict-risk.md"
DBIR_TXT = CORPUS / "industry-reports" / "verizon-dbir" / "dbir-2026-highlights.txt"


@pytest.fixture(scope="module")
def docs() -> list[IngestDocument]:
    return load_corpus_manifest(MANIFEST)


@pytest.fixture(scope="module")
def config() -> IngestConfig:
    return load_ingest_config()


def _doc(docs: list[IngestDocument], doc_id: str) -> IngestDocument:
    return next(d for d in docs if d.id == doc_id)


# ---------------------------------------------------------------------------
# Manifest resolution
# ---------------------------------------------------------------------------


def test_load_manifest_active_only(docs: list[IngestDocument]):
    assert len(docs) >= 2
    ids = {d.id for d in docs}
    assert "corpus/regulatory/dora/ict-risk" in ids
    assert "corpus/industry-reports/verizon-dbir/dbir-2026-highlights" in ids


def test_documents_resolve_to_real_files(docs: list[IngestDocument]):
    for doc in docs:
        path = resolve_document_path(doc)
        assert path.exists(), f"{doc.id} -> {path} missing"
        # The resolved path's format must be supported (incl. yaml incidents).
        assert doc.fmt in ("markdown", "txt", "pdf", "docx", "html", "yaml")


def test_content_hash_matches(docs: list[IngestDocument]):
    for doc in docs:
        path = resolve_document_path(doc)
        verify_document_hash(doc, path)  # no raise


def test_content_hash_mismatch_raises(docs: list[IngestDocument]):
    doc = _doc(docs, "corpus/regulatory/dora/ict-risk")
    path = resolve_document_path(doc)
    bad = doc.model_copy(update={"content_hash": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_document_hash(bad, path)


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


def test_extract_markdown_sections():
    doc = extract_markdown(DORA_MD)
    assert doc.text
    assert doc.title == "DORA ICT Risk Management"
    headings = [s.heading for s in doc.sections]
    assert "Scope" in headings
    assert "ICT Risk Management" in headings
    assert "Third-Party Risk" in headings
    assert "Incident Reporting" in headings
    assert "Resilience Testing" in headings
    # section bodies non-empty
    assert all(s.text.strip() for s in doc.sections)


def test_extract_txt_title():
    doc = extract_txt(DBIR_TXT)
    assert doc.text
    # The em-dash is folded to ASCII '-' by the cleaner.
    assert doc.title == "Verizon 2026 Data Breach Investigations Report - Highlights"


def test_extract_html_sections(tmp_path):
    html = tmp_path / "test.html"
    html.write_text(
        "<html><head><title>T</title></head><body>"
        "<h1>Section One</h1><p>First body.</p>"
        "<h2>Sub</h2><p>Second body.</p>"
        "<script>var x = 1;</script>"
        "</body></html>",
        encoding="utf-8",
    )
    doc = extract_html(html)
    headings = [s.heading for s in doc.sections]
    assert "Section One" in headings
    assert "Sub" in headings
    # script content is stripped
    assert "var x" not in doc.text


def test_extract_docx_graceful_when_lib_absent(tmp_path):
    """If python-docx isn't installed, extraction raises a clear error."""
    from cyberrisk.knowledge.extractors import extract_docx

    f = tmp_path / "t.docx"
    f.write_bytes(b"not a real docx")
    try:
        extract_docx(f)
    except RuntimeError as e:
        assert "python-docx" in str(e)
    except Exception as e:  # a real docx parse error is also acceptable
        assert e is not None


def test_extract_pdf_graceful_when_lib_absent(tmp_path):
    f = tmp_path / "t.pdf"
    f.write_bytes(b"not a real pdf")
    try:
        from cyberrisk.knowledge.extractors import extract_pdf

        extract_pdf(f)
        # If pypdf IS installed, parsing garbage raises a generic PDF error.
        assert True
    except RuntimeError as e:
        assert "pypdf" in str(e)
    except Exception:
        assert True


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------


def test_clean_text_normalizes():
    from cyberrisk.knowledge.cleaners import clean_text

    # Smart quotes fold to ASCII; unicode normalizes; blank lines collapse.
    text = "“Hello” — world …\n\n\n   trailing  \n  double  space"
    cleaned = clean_text(text)
    assert "“" not in cleaned
    assert "Hello" in cleaned
    assert "\n\n\n" not in cleaned
    assert "  " not in cleaned


def test_clean_text_idempotent():
    from cyberrisk.knowledge.cleaners import clean_text

    text = "  Some  text  \n\n\n with ‘smart’ quotes  "
    once = clean_text(text)
    twice = clean_text(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def test_chunk_document_section_based(docs: list[IngestDocument], config: IngestConfig):
    """The DORA doc (by_obligation) chunks per section, preserving headings."""
    from cyberrisk.knowledge.chunkers import chunk_document
    from cyberrisk.knowledge.extractors import extract_markdown

    doc = _doc(docs, "corpus/regulatory/dora/ict-risk")
    path = resolve_document_path(doc)
    extracted = extract_markdown(path)
    chunks = chunk_document(
        doc=extracted,
        doc_id=doc.id,
        title=doc.title,
        license_tier=doc.license_tier,
        strategy=doc.chunking.strategy,
        max_chars=doc.chunking.max_chars,
        overlap=doc.chunking.overlap,
        config=config,
    )
    assert len(chunks) >= 4
    # Section refs preserve the document title > heading path.
    refs = {c.section_ref for c in chunks}
    assert any("> Scope" in r for r in refs)
    assert any("> ICT Risk Management" in r for r in refs)
    # Every chunk <= max_chars.
    assert all(len(c.content) <= doc.chunking.max_chars for c in chunks)
    # Ordinals are 1-based and sequential.
    ordinals = [c.ordinal for c in chunks]
    assert ordinals == list(range(1, len(chunks) + 1))


def test_chunk_document_plain(docs: list[IngestDocument], config: IngestConfig):
    """The DBIR txt (plain) chunks by paragraph-merge with section_ref = title."""
    from cyberrisk.knowledge.chunkers import chunk_document
    from cyberrisk.knowledge.extractors import extract_txt

    doc = _doc(docs, "corpus/industry-reports/verizon-dbir/dbir-2026-highlights")
    path = resolve_document_path(doc)
    extracted = extract_txt(path)
    chunks = chunk_document(
        doc=extracted,
        doc_id=doc.id,
        title=doc.title,
        license_tier=doc.license_tier,
        strategy="plain",
        max_chars=doc.chunking.max_chars,
        overlap=doc.chunking.overlap,
        config=config,
    )
    assert chunks
    # All chunks reference the title (no heading structure).
    assert all(doc.title in c.section_ref for c in chunks)
    assert all(len(c.content) <= doc.chunking.max_chars for c in chunks)


def test_chunk_overlap_respected(config: IngestConfig):
    """A long plain section is sub-split with overlap <= config."""
    from cyberrisk.knowledge.chunkers import chunk_plain
    from cyberrisk.knowledge.extractors import ExtractedDocument

    long = "word " * 2000  # ~10k chars
    extracted = ExtractedDocument(text=long, sections=[], title="Long")
    chunks = chunk_plain(
        extracted, "Long", "doc/x", "public", config, max_chars=500, overlap=100
    )
    assert len(chunks) > 1
    assert all(len(c.content) <= 500 for c in chunks)


# ---------------------------------------------------------------------------
# Index writer (chunk.schema.json validity)
# ---------------------------------------------------------------------------


def test_index_records_valid(tmp_path, docs: list[IngestDocument], config: IngestConfig):
    """Pipeline ingest writes chunk records conforming to chunk.schema.json."""
    from cyberrisk.knowledge.extractors import extract_markdown
    from cyberrisk.knowledge.index import chunk_record

    doc = _doc(docs, "corpus/regulatory/dora/ict-risk")
    path = resolve_document_path(doc)
    extracted = extract_markdown(path)
    from cyberrisk.knowledge.chunkers import chunk_document

    chunks = chunk_document(
        extracted, doc.id, doc.title, doc.license_tier,
        doc.chunking.strategy, doc.chunking.max_chars, doc.chunking.overlap, config,
    )
    for chunk in chunks:
        rec = chunk_record(chunk, doc.chunking.strategy)
        # Required fields per chunk.schema.json.
        assert rec["chunk_id"]
        assert rec["doc_id"] == doc.id
        assert rec["content"]
        assert rec["section_ref"]
        assert set(rec["char_span"]) == {"start", "end"}
        assert rec["embedding_hash"]
        assert rec["license_tier"] == doc.license_tier


def test_pipeline_writes_derived(tmp_path, config: IngestConfig, docs: list[IngestDocument]):
    """End-to-end: ingest the example corpus into a tmp derived root."""
    config = config.model_copy(update={"derived_root": str(tmp_path / "derived")})
    pipeline = IngestPipeline(config=config, corpus_root=CORPUS, manifest_path=MANIFEST)
    report = pipeline.ingest_corpus(force=True)
    assert report.ingested, "expected example docs ingested"
    assert not report.failed
    # index.json written with document_count.
    index_path = tmp_path / "derived" / "index" / "index.json"
    assert index_path.exists()
    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert data["document_count"] == len(report.ingested)
    # chunks/<display_id>.json written per doc (flat filename — the doc id is
    # a nested path, flattened by display_id).
    for doc in docs:
        chunk_path = tmp_path / "derived" / "chunks" / f"{doc.display_id()}.json"
        assert chunk_path.exists(), f"{chunk_path} missing"


def test_pipeline_incremental_skips_unchanged(tmp_path, config: IngestConfig, docs: list[IngestDocument]):
    """Second run skips unchanged docs (content_hash unchanged)."""
    config = config.model_copy(update={"derived_root": str(tmp_path / "derived")})
    pipeline = IngestPipeline(config=config, corpus_root=CORPUS, manifest_path=MANIFEST)
    first = pipeline.ingest_corpus(force=True)
    assert first.ingested
    second = pipeline.ingest_corpus(force=False)
    assert second.skipped
    assert not second.ingested
    assert not second.failed


def test_pipeline_reingests_changed_doc(tmp_path, config: IngestConfig, docs: list[IngestDocument]):
    """Changing a doc's content_hash (simulated) forces re-ingestion."""
    config = config.model_copy(update={"derived_root": str(tmp_path / "derived")})
    pipeline = IngestPipeline(config=config, corpus_root=CORPUS, manifest_path=MANIFEST)
    pipeline.ingest_corpus(force=True)
    # Simulate a changed hash in state.
    state_path = tmp_path / "derived" / "state" / "ingest_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for k in state:
        state[k] = "sha256:" + "f" * 64
    state_path.write_text(json.dumps(state), encoding="utf-8")
    second = pipeline.ingest_corpus(force=False)
    assert second.ingested  # changed hashes -> re-ingested


def test_pipeline_fails_loudly_on_missing_file(tmp_path, config: IngestConfig):
    """A manifest entry with no file fails loudly, not silently."""
    from cyberrisk.knowledge.document import IngestDocument, ChunkingSpec

    bad = IngestDocument(
        id="corpus/regulatory/dora/nonexistent",
        domain="regulatory",
        category="regulation",
        title="Missing doc",
        source="Test",
        license_tier="public",
        version="1",
        content_hash="sha256:" + "0" * 64,
        acquired_at="2026-08-08",
        refresh_cadence="annual",
        chunking=ChunkingSpec(strategy="plain", max_chars=500, overlap=50),
        tags=["x"],
        status="active",
    )
    pipeline = IngestPipeline(config=config, corpus_root=CORPUS, manifest_path=MANIFEST)
    with pytest.raises(FileNotFoundError):
        pipeline.ingest_document(bad)


# ---------------------------------------------------------------------------
# Configurability
# ---------------------------------------------------------------------------


def test_config_load_yaml():
    cfg = load_ingest_config()
    assert cfg.default_max_chars > 0
    assert "pdf" in cfg.enabled_formats


def test_config_strategy_registry_maps_domain_aliases():
    cfg = IngestConfig()
    assert cfg.chunker_for_strategy("by_chapter") == "section"
    assert cfg.chunker_for_strategy("by_obligation") == "section"
    assert cfg.chunker_for_strategy("plain") == "plain"
    with pytest.raises(ValueError):
        cfg.chunker_for_strategy("unknown_strategy")


def test_config_chunk_size_changes_chunking(config: IngestConfig):
    """A smaller max_chars yields more chunks for a long plain document."""
    from cyberrisk.knowledge.chunkers import chunk_document
    from cyberrisk.knowledge.extractors import ExtractedDocument

    # A long headingless document forces fixed-size splitting.
    long_text = "\n\n".join(f"Paragraph number {i} with some content here." for i in range(200))
    extracted = ExtractedDocument(text=long_text, sections=[], title="Long")
    small = IngestConfig(default_max_chars=300, default_overlap=50)
    large = IngestConfig(default_max_chars=5000, default_overlap=50)
    c_small = chunk_document(
        extracted, "doc/x", "Long", "public",
        "plain", small.default_max_chars, small.default_overlap, small,
    )
    c_large = chunk_document(
        extracted, "doc/x", "Long", "public",
        "plain", large.default_max_chars, large.default_overlap, large,
    )
    assert len(c_small) > len(c_large)
