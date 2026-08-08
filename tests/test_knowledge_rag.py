"""RAG retrieval + guard tests.

Exercises the retrieval side (Retriever, format_context) and the
hallucination-aware RAG output check (check_rag_output in src/agent/safety.py).

Covers: retrieval ranking/filtering, context formatting with citations, and
the guard's three RAG checks (citation resolution, document-figure grounding,
document-fact-without-citation).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cyberrisk.knowledge.config import load_ingest_config
from cyberrisk.knowledge.embedders import HashEmbedder
from cyberrisk.knowledge.rag import RetrievedChunk, Retriever
from cyberrisk.knowledge.vector_store import VectorStore

REPO = Path(__file__).parent.parent


def _make_retriever(tmp_path) -> Retriever:
    """A Retriever over a small hand-built vector store (no manifest needed)."""
    store = VectorStore(tmp_path / "v.db")
    e = HashEmbedder(dim=64)
    docs = {
        "dora": "DORA requires financial entities to establish an ICT risk management framework covering identification, protection, detection, response and recovery. Third-party ICT providers supporting critical functions are in scope. Major incidents must be reported to the competent authority.",
        "dbir": "The Verizon DBIR reports that ransomware remains the leading cause of breaches, featuring in roughly a quarter of incidents. Supply chain compromise and business email compromise are persistent threats.",
    }
    for i, (k, content) in enumerate(docs.items()):
        store.upsert_embedding(
            chunk_id=f"{k}#1:abc",
            doc_id=f"corpus/{k}",
            vector=e.embed(content),
            content_hash=f"sha256:{i}",
            metadata={
                "title": k.upper(),
                "publication_date": "2026-01-01",
                "source": "Test",
                "category": "regulatory",
                "industry": "Financial Services",
                "confidence": 0.9,
                "content": content,
            },
        )
    return Retriever(store=store, embedder=e, top_k=5, min_score=0.1)


def _chunk(chunk_id, content):
    return RetrievedChunk(
        doc_id="corpus/dora",
        chunk_id=chunk_id,
        content=content,
        metadata={"title": "DORA", "source": "EUR-Lex", "category": "regulatory",
                  "publication_date": "2023-01-16", "industry": "Financial Services",
                  "confidence": 0.95},
        score=0.5,
    )


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def test_retrieve_ranks_by_similarity(tmp_path):
    r = _make_retriever(tmp_path)
    hits = r.retrieve("ICT risk management framework incident reporting")
    assert hits
    # The DORA chunk should be most relevant to an ICT-risk query.
    assert hits[0].doc_id == "corpus/dora"
    assert hits[0].score > 0


def test_retrieve_two_distinct_queries_rank_differently(tmp_path):
    r = _make_retriever(tmp_path)
    dora_top = r.retrieve("ICT risk management framework incident reporting")[0]
    dbir_top = r.retrieve("ransomware leading cause of breaches supply chain")[0]
    # Two clearly different queries should rank different documents first.
    assert dora_top.doc_id == "corpus/dora"
    assert dbir_top.doc_id == "corpus/dbir"


def test_retrieve_filters_by_min_score(tmp_path):
    r = _make_retriever(tmp_path)
    r.min_score = 0.99  # nothing above this
    assert r.retrieve("anything at all") == []


def test_retrieve_top_k(tmp_path):
    r = _make_retriever(tmp_path)
    assert len(r.retrieve("regulatory framework", top_k=1)) <= 1


def test_retrieve_returns_metadata(tmp_path):
    r = _make_retriever(tmp_path)
    hit = r.retrieve("ransomware leading cause of breaches")[0]
    assert hit.title
    assert hit.publication_date
    assert hit.source
    assert hit.category
    assert hit.industry


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------


def test_format_context_renders_citations():
    r = _make_retriever(Path(__import__("tempfile").mkdtemp()))
    chunk = _chunk("dora#1:abc", "DORA ICT risk framework text")
    block = r.format_context([chunk])
    assert "DORA" in block
    assert "EUR-Lex" in block
    assert "[citation: dora#1:abc]" in block
    assert "Financial Services" in block  # industry preserved


def test_format_context_empty():
    r = _make_retriever(Path(__import__("tempfile").mkdtemp()))
    assert r.format_context([]) == ""


# ---------------------------------------------------------------------------
# RAG output guard
# ---------------------------------------------------------------------------


def test_rag_check_valid_citation_passes():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA requires an ICT risk management framework. Major incidents are reported.")
    text = "DORA requires an ICT risk management framework [citation: dora#1:abc]. The model's EAL for this client is $5M."
    check = check_rag_output(text, validated_metrics={"EAL": 5_000_000}, retrieved_chunks=[chunk])
    assert check.ok, check.reason


def test_rag_check_invalid_citation_flags():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA content")
    text = "DORA requires X [citation: dora#99:zzz]."  # citation to nothing
    check = check_rag_output(text, validated_metrics={}, retrieved_chunks=[chunk])
    assert not check.ok
    assert any("citation does not resolve" in o for o in check.offending)


def test_rag_check_document_figure_unsupported_flags():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA requires an ICT risk management framework.")
    # A claim-framed figure that matches neither an engine metric nor the doc.
    text = "According to the retrieved document, the fine is $7M [citation: dora#1:abc]."
    check = check_rag_output(text, validated_metrics={"EAL": 5_000_000}, retrieved_chunks=[chunk])
    assert not check.ok
    assert any("unsupported document figure" in o for o in check.offending)


def test_rag_check_document_figure_matches_doc_passes():
    from agent.safety import check_rag_output

    # The document actually contains the figure 2022/2554 (regulation number).
    chunk = _chunk("dora#1:abc", "Regulation (EU) 2022/2554 establishes the framework.")
    text = "According to the retrieved document, the regulation is 2022/2554 [citation: dora#1:abc]."
    check = check_rag_output(text, validated_metrics={}, retrieved_chunks=[chunk])
    assert check.ok, check.reason


def test_rag_check_document_fact_without_citation_flags():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA requires an ICT risk management framework.")
    # A document-framed assertion with NO citation -> unverifiable.
    text = "The regulation requires entities to establish a framework."
    check = check_rag_output(text, validated_metrics={}, retrieved_chunks=[chunk])
    assert not check.ok
    assert any("document fact without citation" in o for o in check.offending)


def test_rag_check_no_retrieval_passes_through():
    from agent.safety import check_rag_output

    # No retrieved chunks -> base check only (nothing extra to verify).
    check = check_rag_output("No document claims here.", validated_metrics={"EAL": 5_000_000})
    assert check.ok


# ---------------------------------------------------------------------------
# Three-way tag guard (industry evidence / model output / professional judgement)
# ---------------------------------------------------------------------------


def test_rag_check_model_output_matching_metric_passes():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA requires an ICT risk management framework.")
    text = ("[MODEL OUTPUT] The modelled EAL for this client is $5M "
            "[citation: dora#1:abc].")
    check = check_rag_output(text, validated_metrics={"EAL": 5_000_000}, retrieved_chunks=[chunk])
    assert check.ok, check.reason


def test_rag_check_model_output_not_in_metrics_flags():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA content")
    # [MODEL OUTPUT] figure that doesn't match a tool metric -> fabricated model fig.
    text = "[MODEL OUTPUT] The modelled loss is $99M."
    check = check_rag_output(text, validated_metrics={"EAL": 5_000_000}, retrieved_chunks=[chunk])
    assert not check.ok
    assert any("MODEL OUTPUT figure not in tool results" in o for o in check.offending)


def test_rag_check_industry_evidence_with_citation_passes():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA requires an ICT risk management framework. Major incidents are reported.")
    text = "[INDUSTRY EVIDENCE] DORA requires an ICT risk framework [citation: dora#1:abc]."
    check = check_rag_output(text, validated_metrics={}, retrieved_chunks=[chunk])
    assert check.ok, check.reason


def test_rag_check_industry_evidence_without_grounding_flags():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA content.")
    # [INDUSTRY EVIDENCE] with no resolvable citation and no matching doc figure.
    text = "[INDUSTRY EVIDENCE] The industry average ransom is $7M."
    check = check_rag_output(text, validated_metrics={"EAL": 5_000_000}, retrieved_chunks=[chunk])
    assert not check.ok
    assert any("INDUSTRY EVIDENCE claim without" in o for o in check.offending)


def test_rag_check_assumption_presented_as_fact_flags():
    from agent.safety import check_rag_output

    chunk = _chunk("dora#1:abc", "DORA content.")
    # An unsourced $ figure that matches neither a tool metric nor a doc.
    text = "[PROFESSIONAL JUDGEMENT] I estimate the response cost around $12M."
    check = check_rag_output(text, validated_metrics={"EAL": 5_000_000}, retrieved_chunks=[chunk])
    # The judgement figure is an assumption; it doesn't match a metric or doc.
    assert not check.ok
    assert any("assumption presented as fact" in o for o in check.offending)


def test_rag_check_properly_attributed_passes():
    from agent.safety import check_rag_output

    chunk = _chunk(
        "dora#1:abc",
        "DORA requires an ICT risk management framework. Financial entities must report major incidents.",
    )
    # A fully-attributed answer with source block + three-way tags.
    text = (
        "[INDUSTRY EVIDENCE] DORA requires an ICT risk management framework "
        "[citation: dora#1:abc]. Source: DORA. Published: 2023-01-16. "
        "Confidence: 0.95. Section: ICT Risk Management.\n"
        "[MODEL OUTPUT] The modelled EAL for this client is $5M."
    )
    check = check_rag_output(text, validated_metrics={"EAL": 5_000_000}, retrieved_chunks=[chunk])
    assert check.ok, check.reason


# ---------------------------------------------------------------------------
# Context attribution (confidence + section surfaced)
# ---------------------------------------------------------------------------


def test_format_context_surfaces_confidence_and_section(tmp_path):
    r = _make_retriever(tmp_path)
    chunk = RetrievedChunk(
        doc_id="corpus/dora",
        chunk_id="dora#1:abc",
        content="DORA ICT risk framework text",
        metadata={
            "title": "DORA", "source": "EUR-Lex", "publication_date": "2023-01-16",
            "category": "regulatory", "industry": "finance", "confidence": 0.95,
            "section_ref": "ICT Risk Management",
        },
        score=0.5,
    )
    block = r.format_context([chunk])
    assert "Confidence: 0.95" in block
    assert "Section: ICT Risk Management" in block


def test_incident_narrative_has_attribution():
    from cyberrisk.knowledge.incidents import load_incident

    inc = load_incident(REPO / "knowledge" / "corpus" / "incidents" / "curated" / "change-healthcare-2024.yaml")
    text = inc.narrative()
    assert "Source:" in text
    assert "Published:" in text
    assert "2024-02-21" in text


# ---------------------------------------------------------------------------
# Retriever against the real derived store (if populated)
# ---------------------------------------------------------------------------


def test_retriever_from_derived_skips_when_absent():
    from cyberrisk.knowledge.rag import Retriever

    # A derived root that doesn't exist -> FileNotFoundError.
    with pytest.raises(FileNotFoundError):
        Retriever.from_derived(derived_root=REPO / "does-not-exist")
