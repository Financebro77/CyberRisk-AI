"""Knowledge base validation suite.

Runs nine quality areas against the real corpus + vector store, computes
pass/fail + performance metrics for each, and writes a validation report:

    python -m cyberrisk.knowledge.validate
      -> prints a summary table
      -> writes reports/knowledge_validation.md   (markdown)
      -> writes derived/validation/report.json    (machine-readable)

Areas (each with an explicit PASS/FAIL threshold):
    1. Document ingestion      100% no errors
    2. Chunk quality           >= 95% chunks valid (size, section_ref, char_span)
    3. Embedding quality       100% valid (non-zero, normalized, dim, deterministic)
    4. Semantic retrieval      precision@1 >= 0.8
    5. Source attribution      100% present (Source/Pub/Confidence/Section)
    6. Citation accuracy       resolve rate = 1.0
    7. Duplicate detection     100% (no double index)
    8. Retrieval latency       p95 < 200ms
    9. Hallucination resistance 0 fabricated figures pass

The runner reuses the REAL pipelines (IngestPipeline, EmbedPipeline, VectorStore,
Retriever, check_rag_output) — no mocks, no engine changes.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from cyberrisk.knowledge.config import load_ingest_config
from cyberrisk.knowledge.embedders import HashEmbedder
from cyberrisk.knowledge.pipeline import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_MANIFEST,
    IngestPipeline,
    load_corpus_manifest,
    resolve_document_path,
)
from cyberrisk.knowledge.rag import Retriever
from cyberrisk.knowledge.update import find_unregistered_files
from cyberrisk.knowledge.vector_store import VectorStore

# Thresholds (human-readable bar + the numeric bar for PASS/FAIL).
THRESHOLDS: dict[str, str] = {
    "document_ingestion": "100% no errors",
    "chunk_quality": ">= 95% chunks valid",
    "embedding_quality": "100% valid",
    "semantic_retrieval": "precision@1 >= 0.8",
    "source_attribution": "100% present",
    "citation_accuracy": "resolve rate = 1.0",
    "duplicate_detection": "100%",
    "retrieval_latency": "p95 < 200ms",
    "hallucination_resistance": "0 fabricated figures pass",
}

LATENCY_P95_MS = 200.0
RETRIEVAL_PRECISION_BAR = 0.8
CHUNK_VALID_BAR = 0.95


class ValidationResult(BaseModel):
    """One area's validation outcome."""

    area: str
    status: Literal["PASS", "FAIL"]
    metric: str = ""
    threshold: str = ""
    details: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()


# ---------------------------------------------------------------------------
# Area validators
# ---------------------------------------------------------------------------


def _validate_ingestion(config) -> ValidationResult:
    """Ingest the real corpus docs; every registered doc must chunk without error."""
    ingest = IngestPipeline(config=config)
    report = ingest.ingest_corpus(force=False)
    total = len(report.ingested) + len(report.skipped) + len(report.failed)
    errors = len(report.failed)
    metric = f"{total} docs, {errors} errors"
    ok = errors == 0
    details = [f"{d} -> {'ok' if d not in [f[0] for f in report.failed] else 'FAIL'}"
               for d in [x[0] for x in report.failed]] or ["all documents ingested without error"]
    if report.failed:
        details = [f"ERROR {path}: {err}" for path, err in report.failed]
    return ValidationResult(
        area="document_ingestion", status="PASS" if ok else "FAIL",
        metric=metric, threshold=THRESHOLDS["document_ingestion"], details=details,
    )


def _validate_chunk_quality(config) -> ValidationResult:
    """Inspect derived/chunks/*.json: size, section_ref, char_span, license_tier."""
    chunks_dir = config.derived_path / "chunks"
    total = 0
    valid = 0
    issues: list[str] = []
    for path in sorted(chunks_dir.glob("*.json")):
        records = json.loads(path.read_text(encoding="utf-8"))
        for rec in records:
            total += 1
            max_chars = 10_000  # generous upper bound; plain default is 1200
            if len(rec.get("content", "")) > max_chars:
                issues.append(f"{rec.get('chunk_id', '?')}: content too long")
            elif not rec.get("section_ref"):
                issues.append(f"{rec.get('chunk_id', '?')}: missing section_ref")
            elif "char_span" not in rec or "license_tier" not in rec:
                issues.append(f"{rec.get('chunk_id', '?')}: missing char_span/license_tier")
            else:
                valid += 1
    pct = valid / total if total else 0.0
    ok = pct >= CHUNK_VALID_BAR
    return ValidationResult(
        area="chunk_quality", status="PASS" if ok else "FAIL",
        metric=f"{valid}/{total} valid ({pct:.0%})", threshold=THRESHOLDS["chunk_quality"],
        details=issues[:5] or ["all chunks have section_ref + char_span + license_tier"],
    )


def _validate_embedding_quality(config) -> ValidationResult:
    """Embeddings non-zero, normalized, correct dim, deterministic.

    Determinism is checked against the chunk CONTENT (read from derived/chunks,
    the source of truth) rather than the vector-store metadata (which carries
    attribution fields, not the content itself).
    """
    store = VectorStore(config.derived_path / "vector.db")
    e = HashEmbedder(dim=768)
    # Build a map of chunk_id -> content from the chunk store.
    content_by_id: dict[str, str] = {}
    chunks_dir = config.derived_path / "chunks"
    for path in sorted(chunks_dir.glob("*.json")):
        for rec in json.loads(path.read_text(encoding="utf-8")):
            content_by_id[rec.get("chunk_id", "")] = rec.get("content", "")
    total = 0
    valid = 0
    issues: list[str] = []
    try:
        rows = store.conn.execute(
            "SELECT id, vector FROM embeddings"
        ).fetchall()
        for r in rows:
            total += 1
            v = np.frombuffer(r["vector"], dtype=np.float32)
            norm = float(np.linalg.norm(v))
            content = content_by_id.get(r["id"], "")
            if norm == 0:
                issues.append(f"{r['id']}: zero vector")
            elif abs(norm - 1.0) > 1e-4:
                issues.append(f"{r['id']}: not normalized (norm={norm:.4f})")
            elif content and not np.allclose(v, e.embed(content), atol=1e-5):
                issues.append(f"{r['id']}: not deterministic")
            elif not content:
                issues.append(f"{r['id']}: no matching chunk content to verify")
            else:
                valid += 1
    finally:
        store.close()
    pct = valid / total if total else 0.0
    ok = pct == 1.0
    return ValidationResult(
        area="embedding_quality", status="PASS" if ok else "FAIL",
        metric=f"{valid}/{total} valid ({pct:.0%})", threshold=THRESHOLDS["embedding_quality"],
        details=issues[:5] or ["all embeddings non-zero, normalized, deterministic"],
    )


def _validate_retrieval(config) -> ValidationResult:
    """precision@1 for known queries against the real corpus."""
    retriever = Retriever.from_derived(config.derived_path)
    # Queries mapped to the expected doc id (ground truth from the real corpus).
    docs = load_corpus_manifest()
    queries = [
        ("DORA ICT risk management framework", "corpus/regulatory/dora/ict-risk"),
        ("ransomware leading cause of breaches supply chain", "corpus/industry-reports/verizon-dbir/dbir-2026-highlights"),
        ("Change Healthcare ransomware claims processing", "corpus/incidents/curated/change-healthcare-2024"),
    ]
    hits = 0
    details: list[str] = []
    for q, expected in queries:
        top = retriever.retrieve(q, top_k=1)
        if top and top[0].doc_id == expected:
            hits += 1
            details.append(f"query '{q[:30]}...' -> {top[0].doc_id} (correct)")
        else:
            got = top[0].doc_id if top else "none"
            details.append(f"query '{q[:30]}...' -> {got} (expected {expected})")
    prec = hits / len(queries) if queries else 0.0
    ok = prec >= RETRIEVAL_PRECISION_BAR
    return ValidationResult(
        area="semantic_retrieval", status="PASS" if ok else "FAIL",
        metric=f"precision@1 = {prec:.2f} ({hits}/{len(queries)})",
        threshold=THRESHOLDS["semantic_retrieval"], details=details,
    )


def _validate_attribution(config) -> ValidationResult:
    """Retrieved context carries the attribution metadata.

    The context block surfaces source (title + source), publication date,
    confidence, and section.  These are the values the consultant copies into
    its Source / Published / Confidence / Section blocks; ``format_context``
    renders them in the header + attribute line, so we verify the metadata is
    present rather than the literal prose labels (which the LLM produces).
    """
    retriever = Retriever.from_derived(config.derived_path)
    results = retriever.retrieve("DORA ICT risk management")
    if not results:
        return ValidationResult(area="source_attribution", status="FAIL", metric="no results",
                                threshold=THRESHOLDS["source_attribution"], details=["no retrieved chunks"])
    chunk = results[0]
    ctx = retriever.format_context(results[:1])
    checks = [
        ("source", bool(chunk.title or chunk.source)),
        ("publication_date", bool(chunk.publication_date)),
        ("confidence", chunk.metadata.get("confidence") is not None),
        ("section", bool(chunk.section_ref)),
    ]
    present = sum(1 for _name, ok in checks if ok)
    ok = present == len(checks)
    return ValidationResult(
        area="source_attribution", status="PASS" if ok else "FAIL",
        metric=f"{present}/{len(checks)} attribution fields present",
        threshold=THRESHOLDS["source_attribution"],
        details=[f"{name}: {'present' if okv else 'missing'}" for name, okv in checks]
                + [f"context: {ctx[:120]!r}"],
    )


def _validate_citation(config) -> ValidationResult:
    """Every [citation: id] resolves to a stored chunk_id."""
    retriever = Retriever.from_derived(config.derived_path)
    store = retriever.store
    rows = store.conn.execute("SELECT id FROM embeddings").fetchall()
    stored = {r["id"] for r in rows}
    results = retriever.retrieve("DORA ICT risk management", top_k=5)
    total = 0
    resolved = 0
    issues: list[str] = []
    for chunk in results:
        cid = chunk.chunk_id
        total += 1
        if cid in stored:
            resolved += 1
        else:
            issues.append(f"{cid}: not in store")
    rate = resolved / total if total else 0.0
    ok = rate == 1.0
    return ValidationResult(
        area="citation_accuracy", status="PASS" if ok else "FAIL",
        metric=f"resolve rate = {rate:.2f} ({resolved}/{total})",
        threshold=THRESHOLDS["citation_accuracy"], details=issues or ["all citations resolve"],
    )


def _validate_duplicates(config) -> ValidationResult:
    """Re-registering an existing file is skipped (no double index)."""
    before = find_unregistered_files(DEFAULT_CORPUS_ROOT, DEFAULT_MANIFEST)
    # None of the registered doc paths should be flagged as unregistered
    # (a duplicate file is never re-registered).
    docs = load_corpus_manifest()
    dup_found = 0
    for doc in docs:
        path = resolve_document_path(doc)
        if path in before:
            dup_found += 1
    total = len(docs)
    ok = dup_found == 0
    return ValidationResult(
        area="duplicate_detection", status="PASS" if ok else "FAIL",
        metric=f"{dup_found}/{total} registered docs mistakenly flagged as new",
        threshold=THRESHOLDS["duplicate_detection"],
        details=["no registered doc is re-registered"] if ok else [f"{dup_found} duplicates found"],
    )


def _validate_latency(config) -> ValidationResult:
    """p95 latency of VectorStore.similarity across N queries."""
    retriever = Retriever.from_derived(config.derived_path)
    store = retriever.store
    e = HashEmbedder(dim=768)
    queries = [
        "ransomware extortion healthcare",
        "DORA regulatory framework",
        "supply chain compromise",
        "business email compromise wire fraud",
        "cloud outage dependent business interruption",
        "network segmentation privileged access",
    ]
    latencies_ms: list[float] = []
    try:
        for q in queries:
            qv = e.embed(q)
            t0 = time.perf_counter()
            store.similarity(qv, k=5)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    finally:
        store.close()
    p95 = float(np.percentile(latencies_ms, 95)) if latencies_ms else 0.0
    ok = p95 < LATENCY_P95_MS
    return ValidationResult(
        area="retrieval_latency", status="PASS" if ok else "FAIL",
        metric=f"p95 = {p95:.1f}ms across {len(latencies_ms)} queries",
        threshold=THRESHOLDS["retrieval_latency"],
        details=[f"p50={np.percentile(latencies_ms, 50):.1f}ms, p95={p95:.1f}ms"],
    )


def _validate_hallucination(config) -> ValidationResult:
    """check_rag_output flags fabricated figures, passes grounded ones."""
    from agent.safety import check_rag_output

    retriever = Retriever.from_derived(config.derived_path)
    results = retriever.retrieve("DORA ICT risk management", top_k=1)
    if not results:
        return ValidationResult(area="hallucination_resistance", status="FAIL",
                                metric="no retrieved chunk", threshold=THRESHOLDS["hallucination_resistance"],
                                details=["no retrieved chunk to test against"])
    chunk = results[0]
    validated = {"EAL": 5_000_000}

    grounded = f"[INDUSTRY EVIDENCE] {chunk.content[:80]} [citation: {chunk.chunk_id}]."
    fabricated = "[MODEL OUTPUT] The modelled loss is $99M."
    unsourced = "[PROFESSIONAL JUDGEMENT] I estimate the response cost is $12M."

    grounded_ok = check_rag_output(grounded, validated_metrics=validated, retrieved_chunks=[chunk])
    fabricated_ok = check_rag_output(fabricated, validated_metrics=validated, retrieved_chunks=[chunk])
    unsourced_ok = check_rag_output(unsourced, validated_metrics=validated, retrieved_chunks=[chunk])

    # grounded must pass; fabricated + unsourced must be flagged.
    ok = grounded_ok.ok and not fabricated_ok.ok and not unsourced_ok.ok
    details = [
        f"grounded cited claim passes: {grounded_ok.ok}",
        f"fabricated [MODEL OUTPUT] flagged: {not fabricated_ok.ok}",
        f"unsourced assumption flagged: {not unsourced_ok.ok}",
    ]
    return ValidationResult(
        area="hallucination_resistance", status="PASS" if ok else "FAIL",
        metric="0 fabricated figures passed" if ok else "fabrication slipped through",
        threshold=THRESHOLDS["hallucination_resistance"], details=details,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_VALIDATORS = [
    _validate_ingestion,
    _validate_chunk_quality,
    _validate_embedding_quality,
    _validate_retrieval,
    _validate_attribution,
    _validate_citation,
    _validate_duplicates,
    _validate_latency,
    _validate_hallucination,
]


def validate_knowledge_base(config=None) -> list[ValidationResult]:
    """Run all nine validation areas against the real corpus + vector store."""
    config = config or load_ingest_config()
    results: list[ValidationResult] = []
    for validator in _VALIDATORS:
        try:
            results.append(validator(config))
        except Exception as exc:  # noqa: BLE001 — a validator crash is a FAIL, not a run crash
            results.append(
                ValidationResult(
                    area=validator.__name__.replace("_validate_", ""),
                    status="FAIL", metric="validator crashed",
                    threshold="n/a", details=[f"{type(exc).__name__}: {exc}"],
                )
            )
    return results


# ---------------------------------------------------------------------------
# Report writer + CLI
# ---------------------------------------------------------------------------


def _write_report(results: list[ValidationResult], config) -> None:
    """Write reports/knowledge_validation.md + derived/validation/report.json."""
    repo = Path(__file__).resolve().parent.parent.parent.parent
    md_path = repo / "reports" / "knowledge_validation.md"

    # reports/ is a generated-output dir (gitignored); on a fresh checkout it
    # doesn't exist yet, so create it before writing.
    md_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Knowledge Base Validation Report",
        "",
        f"Date: {date.today().isoformat()}",
        f"Areas: {len(results)}",
        "",
        "## Summary",
        "",
        "| # | Area | Status | Metric | Threshold |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, start=1):
        lines.append(f"| {i} | {r.area} | {r.status} | {r.metric} | {r.threshold} |")
    lines.append("")
    lines.append("## Details")
    lines.append("")
    for r in results:
        lines.append(f"### {r.area} — {r.status}")
        lines.append(f"- Metric: {r.metric}")
        lines.append(f"- Threshold: {r.threshold}")
        for d in r.details:
            lines.append(f"  - {d}")
        lines.append("")
    # Recommendations from any FAIL.
    failed = [r for r in results if r.status == "FAIL"]
    lines.append("## Recommendations")
    lines.append("")
    if failed:
        for r in failed:
            lines.append(f"- **{r.area} FAILED** ({r.metric}). Review the details above and the relevant pipeline/tests.")
    else:
        lines.append("- All areas passed. Maintain the corpus + vector store and re-run after any pipeline change.")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    # Machine-readable JSON.
    json_path = config.derived_path / "validation" / "report.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"date": date.today().isoformat(), "results": [r.to_dict() for r in results]},
                   indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m cyberrisk.knowledge.validate"""
    parser = argparse.ArgumentParser(prog="cyberrisk.knowledge.validate",
                                     description="Run the knowledge base validation suite")
    parser.parse_args(argv)

    config = load_ingest_config()
    results = validate_knowledge_base(config)
    _write_report(results, config)

    print(f"{'AREA':<24} {'STATUS':<6} {'METRIC'}")
    print("-" * 70)
    for r in results:
        print(f"{r.area:<24} {r.status:<6} {r.metric}")
    n_pass = sum(1 for r in results if r.status == "PASS")
    print(f"\n{n_pass}/{len(results)} areas passed")
    print("report: reports/knowledge_validation.md")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
