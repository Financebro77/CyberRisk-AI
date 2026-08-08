"""Authoritative knowledge population workflow.

The populate pipeline is the QUALITY-GATED ingestion path for the corpus.  A
document is ingested ONLY if its source is registered as approved in
``authoritative_sources.yaml``.  Unapproved sources are skipped + logged.

The 8-step workflow (per the specification):
    1. identify new documents      find_unregistered_files
    2. validate source metadata    source-registry approval gate
    3. extract text                extractors
    4. clean content               cleaners
    5. generate chunks             chunkers
    6. store processed data        index
    7. generate embeddings         embed_pipeline
    8. update vector database      vector_store

It maintains source attribution, document version, publication date, and
confidence (from the document metadata records / manifest).  It produces a
PopulateReport and writes ``reports/knowledge_population_report.md``.

Reuses the existing machinery (find_unregistered_files, auto_register_file,
IngestPipeline, EmbedPipeline).  No engine changes.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from cyberrisk.knowledge.config import load_ingest_config
from cyberrisk.knowledge.logging_util import UpdateLogger
from cyberrisk.knowledge.pipeline import DEFAULT_CORPUS_ROOT, DEFAULT_MANIFEST, IngestPipeline
from cyberrisk.knowledge.sources import SOURCE_CATEGORIES, load_source_registry
from cyberrisk.knowledge.update import auto_register_file, find_unregistered_files
from cyberrisk.knowledge.embed_pipeline import EmbedPipeline


class PopulateReport(BaseModel):
    """What one populate run did + the Phase-7 report content."""

    sources_added: list[str] = Field(default_factory=list)
    documents_processed: list[str] = Field(default_factory=list)
    documents_skipped_unapproved: list[str] = Field(default_factory=list)
    chunks_created: int = 0
    embeddings_generated: int = 0
    categories_covered: list[str] = Field(default_factory=list)
    missing_domains: list[str] = Field(default_factory=list)
    quality_assessment: list[str] = Field(default_factory=list)
    licensing_concerns: list[str] = Field(default_factory=list)
    recommended_future_additions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Source-name resolution for the approval gate
# ---------------------------------------------------------------------------

# Map a corpus subfolder to an authoritative source name.  When a document is
# placed under a known source folder, its source is resolved for the gate.
_SOURCE_BY_FOLDER = {
    "nist-csf-2.0": "NIST Cybersecurity Framework (CSF)",
    "nist-800-53": "NIST SP 800-53",
    "cis-controls": "CIS Critical Security Controls",
    "iso-27001": "ISO 27001 guidance",
    "cisa-kev": "CISA Known Exploited Vulnerabilities (KEV)",
    "verizon-dbir": "Verizon Data Breach Investigations Report (DBIR)",
    "ibm-codb": "IBM Cost of a Data Breach Report",
    "enisa": "ENISA Threat Landscape Reports",
    "microsoft-security-reports": "Microsoft Security Reports",
    "cyber-claims": "Public cyber insurance claims reports",
}


def _source_for_path(corpus_root: Path, file_path: Path) -> str | None:
    """Resolve a file's authoritative source name from its corpus path.

    Looks for a known source folder anywhere in the file's relative path.
    Returns None if no known source folder matches.
    """
    try:
        rel = file_path.resolve().relative_to(corpus_root.resolve())
    except ValueError:
        return None
    for part in rel.parts:
        if part in _SOURCE_BY_FOLDER:
            return _SOURCE_BY_FOLDER[part]
    return None


# ---------------------------------------------------------------------------
# Populate workflow
# ---------------------------------------------------------------------------


def populate_corpus(
    corpus_root: str | Path | None = None,
    manifest_path: str | Path | None = None,
    force: bool = False,
    config=None,
) -> PopulateReport:
    """The 8-step quality-gated population workflow."""
    corpus_root = Path(corpus_root) if corpus_root is not None else DEFAULT_CORPUS_ROOT
    manifest_path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST
    config = config or load_ingest_config()
    report = PopulateReport()

    registry = load_source_registry()
    report.sources_added = registry.approved_names()
    report.categories_covered = sorted(registry.categories_covered())

    update_dir = config.derived_path / "populate"
    logger = UpdateLogger(update_dir / "populate.log")
    logger.clear()

    # Steps 1-2: identify new documents, validate source (approval gate).
    new_files = find_unregistered_files(corpus_root, manifest_path)
    for path in new_files:
        source = _source_for_path(corpus_root, path)
        if source is None or not registry.is_approved(source):
            report.documents_skipped_unapproved.append(str(path))
            logger.log(f"SKIP (unapproved source) {path.name}")
            continue
        try:
            doc = auto_register_file(path, corpus_root, manifest_path)
            report.documents_processed.append(doc.id)
            logger.log(f"approved source {source!r} -> registered {doc.id}")
        except Exception as exc:  # noqa: BLE001 — record, don't crash
            logger.log(f"ERROR registering {path.name}: {type(exc).__name__}: {exc}")

    # Steps 3-6: ingest (extract -> clean -> chunk -> index).
    ingest = IngestPipeline(config=config, corpus_root=corpus_root, manifest_path=manifest_path)
    ingest_report = ingest.ingest_corpus(force=force)
    report.chunks_created = len(ingest_report.ingested)
    for doc_id in ingest_report.ingested:
        logger.log(f"ingested {doc_id}")

    # Steps 7-8: embed + update vector DB.
    embed = EmbedPipeline(config=config, corpus_root=corpus_root, manifest_path=manifest_path)
    try:
        embed_report = embed.embed_corpus(force=force)
    finally:
        embed.close()
    report.embeddings_generated = len(embed_report.embedded)
    for cid in embed_report.embedded:
        logger.log(f"embedded {cid}")

    # Phase-7 report content.
    report.missing_domains = sorted(set(SOURCE_CATEGORIES) - set(report.categories_covered))
    report.quality_assessment = [
        f"{s.source_name}: reliability={s.reliability_rating}, license={s.licensing_status}"
        for s in registry.sources
    ]
    report.licensing_concerns = [
        f"{s.source_name}: proprietary license — summarised figures only, not full text"
        for s in registry.sources if s.licensing_status == "proprietary"
    ]
    report.recommended_future_additions = [
        "Threat-intelligence feeds (vendor-neutral, licensed)",
        "Sector-specific breach cost tables (industry granularity for calibration)",
        "Additional regulatory guidance (state privacy laws, sector regulators)",
        "Historical incident datasets for severity calibration",
    ]

    # Write report.json.
    json_path = config.derived_path / "populate" / "report.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


# ---------------------------------------------------------------------------
# Report writer (Phase 7)
# ---------------------------------------------------------------------------


def write_population_report(report: PopulateReport) -> Path:
    """Write reports/knowledge_population_report.md."""
    repo = Path(__file__).resolve().parent.parent.parent.parent
    md_path = repo / "reports" / "knowledge_population_report.md"
    lines = [
        "# Knowledge Population Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Sources Added",
        "",
    ]
    lines += [f"- {s}" for s in report.sources_added]
    lines.append("")
    lines.append("## Categories Covered")
    lines.append("")
    lines += [f"- {c}" for c in report.categories_covered]
    lines.append("")
    lines.append("## Missing Domains")
    lines.append("")
    if report.missing_domains:
        lines += [f"- {d}" for d in report.missing_domains]
    else:
        lines.append("- none (all registered categories covered)")
    lines.append("")
    lines.append("## Data Quality Assessment")
    lines.append("")
    lines += [f"- {q}" for q in report.quality_assessment]
    lines.append("")
    lines.append("## Licensing Concerns")
    lines.append("")
    if report.licensing_concerns:
        lines += [f"- {c}" for c in report.licensing_concerns]
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Recommended Future Additions")
    lines.append("")
    lines += [f"- {a}" for a in report.recommended_future_additions]
    lines.append("")
    lines.append("## Populate Run")
    lines.append("")
    lines.append(f"- documents processed: {len(report.documents_processed)}")
    lines.append(f"- documents skipped (unapproved source): {len(report.documents_skipped_unapproved)}")
    lines.append(f"- chunks created: {report.chunks_created}")
    lines.append(f"- embeddings generated: {report.embeddings_generated}")
    lines.append("")
    lines.append("> Governance: external evidence is cited, model output is computed, and")
    lines.append("> professional judgement is labelled. No engine parameter is modified by")
    lines.append("> the knowledge corpus or mappings.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m cyberrisk.knowledge.populate [--force]"""
    parser = argparse.ArgumentParser(
        prog="cyberrisk.knowledge.populate",
        description="Populate the corpus from approved authoritative sources (quality-gated)",
    )
    parser.add_argument("--force", action="store_true", help="Re-index everything")
    args = parser.parse_args(argv)

    report = populate_corpus(force=args.force)
    write_population_report(report)

    print(f"sources added: {len(report.sources_added)}")
    print(f"documents processed: {len(report.documents_processed)}")
    print(f"documents skipped (unapproved): {len(report.documents_skipped_unapproved)}")
    print(f"chunks created: {report.chunks_created}")
    print(f"embeddings generated: {report.embeddings_generated}")
    print(f"report: reports/knowledge_population_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
