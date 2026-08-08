"""Automatic knowledge update system.

The requirement: a user places new reports into the knowledge folder, and the
system automatically detects them, parses them, generates embeddings, updates
the vector database, avoids duplicate indexing, logs all updates, and produces
an indexing report — with NO manual code changes.

This module is the orchestrator:

    python -m cyberrisk.knowledge.update          # scan, auto-register, ingest, embed
    python -m cyberrisk.knowledge.update --force  # re-index everything
    python -m cyberrisk.knowledge.update --report # print the last report

Flow:
    1. find_unregistered_files  -> any supported file under corpus/** whose id
                                  isn't already in the manifest
    2. auto_register_file       -> build a manifest entry with defaults inferred
                                  from the path (domain, title, chunking, hash)
    3. IngestPipeline.ingest_corpus  -> parse + chunk (incremental)
    4. EmbedPipeline.embed_corpus   -> embed + update vector DB (incremental, dedup)
    5. write UpdateReport + updates.log

No manual code change: dropping a file into the knowledge folder is all that's
needed.  Auto-registered entries carry default metadata (domain from path,
title from filename, license public) that can be edited later in the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from cyberrisk.knowledge.config import IngestConfig, format_for_path, load_ingest_config
from cyberrisk.knowledge.document import IngestDocument
from cyberrisk.knowledge.embed_pipeline import EmbedPipeline
from cyberrisk.knowledge.logging_util import UpdateLogger
from cyberrisk.knowledge.pipeline import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_MANIFEST,
    IngestPipeline,
    load_corpus_manifest,
)
from cyberrisk.knowledge.vector_store import VectorStore

# Default chunking for an auto-registered file (plain strategy, no headings).
_AUTO_CHUNKING = {"strategy": "plain", "max_chars": 1200, "overlap": 150}
_AUTO_DEFAULTS = {
    "source": "auto-registered",
    "license_tier": "public",
    "version": "1.0",
    "refresh_cadence": "on_revision",
    "status": "active",
}


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _candidate_id(corpus_root: Path, file_path: Path) -> str:
    """A document id for a file: corpus/<relpath without extension>.

    Example: knowledge/corpus/regulatory/foo/report.pdf -> corpus/regulatory/foo/report
    """
    rel = file_path.resolve().relative_to(corpus_root.resolve())
    stem = rel.with_suffix("")  # strip extension
    return "corpus/" + stem.as_posix()


def find_unregistered_files(
    corpus_root: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> list[Path]:
    """All supported-format files under corpus/** NOT already in the manifest.

    Walks the corpus tree, resolves each file to a candidate document id, and
    returns files whose id isn't in the manifest's active set.  This is the
    duplicate-avoidance gate: a file already registered is never re-added.
    """
    corpus_root = Path(corpus_root) if corpus_root is not None else DEFAULT_CORPUS_ROOT
    manifest_path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST

    registered = {doc.id for doc in load_corpus_manifest(manifest_path)}
    unregistered: list[Path] = []
    for path in sorted(corpus_root.rglob("*")):
        if not path.is_file():
            continue
        # Skip files we manage (gitkeep) or don't support.
        if path.name == ".gitkeep":
            continue
        # Skip quality-metadata records (*.metadata.yaml) — they describe a
        # source's quality but are NOT content documents to ingest.
        if path.name.endswith(".metadata.yaml"):
            continue
        fmt = format_for_path(path)
        if fmt is None:
            continue
        if _candidate_id(corpus_root, path) not in registered:
            unregistered.append(path)
    return unregistered


def auto_register_file(
    path: str | Path,
    corpus_root: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> IngestDocument:
    """Build + append a manifest entry for an unregistered file.

    Infers defaults from the path + file (domain = parent folder, title =
    filename, chunking = plain, license = public, content_hash auto).  Appends
    the entry to corpus_manifest.yaml and returns the IngestDocument.

    Raises
        ValueError  if the file is already registered (duplicate).
    """
    path = Path(path)
    corpus_root = Path(corpus_root) if corpus_root is not None else DEFAULT_CORPUS_ROOT
    manifest_path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST

    doc_id = _candidate_id(corpus_root, path)
    if doc_id in {d.id for d in load_corpus_manifest(manifest_path)}:
        raise ValueError(f"{path} is already registered as {doc_id}")

    # Domain/category inferred from the path relative to the corpus root.
    rel = path.resolve().relative_to(corpus_root.resolve())
    parts = rel.parts
    domain = parts[0] if parts else "uncategorized"
    category = parts[1] if len(parts) > 1 else ""

    entry = {
        "id": doc_id,
        "domain": domain,
        "category": category,
        "title": path.name,
        "source": _AUTO_DEFAULTS["source"],
        "license_tier": _AUTO_DEFAULTS["license_tier"],
        "version": _AUTO_DEFAULTS["version"],
        "content_hash": _sha256(path),
        "acquired_at": date.today().isoformat(),
        "refresh_cadence": _AUTO_DEFAULTS["refresh_cadence"],
        "chunking": dict(_AUTO_CHUNKING),
        "tags": [domain],
        "status": _AUTO_DEFAULTS["status"],
    }

    # Append to the manifest.
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    documents = raw.setdefault("documents", [])
    documents.append(entry)
    manifest_path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    return IngestDocument(**entry)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class UpdateReport(BaseModel):
    """Machine-readable summary of an update run."""

    documents_processed: list[str] = Field(default_factory=list)
    chunks_created: int = 0
    embeddings_generated: int = 0
    files_skipped_duplicate: list[str] = Field(default_factory=list)
    parsing_errors: list[dict] = Field(default_factory=list)  # {path, error}
    total_documents: int = 0
    total_chunks: int = 0


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_update(
    corpus_root: str | Path | None = None,
    manifest_path: str | Path | None = None,
    force: bool = False,
    config: IngestConfig | None = None,
) -> UpdateReport:
    """The full automatic update: register -> ingest -> embed -> report.

    Reuses IngestPipeline + EmbedPipeline (no engine changes).  Writes
    derived/update/report.json + derived/update/updates.log.

    Parameters
        corpus_root     corpus root (defaults to the repo knowledge/corpus)
        manifest_path   corpus manifest path (defaults to the repo manifest)
        force           re-index everything (default False = incremental)
        config          IngestConfig override (e.g. a custom derived root for
                        tests); defaults to the repo config
    """
    corpus_root = Path(corpus_root) if corpus_root is not None else DEFAULT_CORPUS_ROOT
    manifest_path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST
    config = config or load_ingest_config()
    report = UpdateReport()

    update_dir = config.derived_path / "update"
    logger = UpdateLogger(update_dir / "updates.log")
    logger.clear()

    # 1. Auto-register unregistered files.
    new_files = find_unregistered_files(corpus_root, manifest_path)
    for path in new_files:
        try:
            doc = auto_register_file(path, corpus_root, manifest_path)
            logger.log(f"registered {doc.id} <- {path.name}")
            report.documents_processed.append(doc.id)
        except Exception as exc:  # noqa: BLE001 — record, don't crash
            report.parsing_errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
            logger.log(f"ERROR registering {path.name}: {type(exc).__name__}: {exc}")

    # 2. Ingest (parse + chunk).
    ingest = IngestPipeline(config=config, corpus_root=corpus_root, manifest_path=manifest_path)
    ingest_report = ingest.ingest_corpus(force=force)
    report.chunks_created = len(ingest_report.ingested)
    report.total_documents = len(ingest_report.ingested) + len(ingest_report.skipped) + len(ingest_report.failed)
    for doc_id in ingest_report.ingested:
        logger.log(f"ingested {doc_id}")
    for doc_id, err in ingest_report.failed:
        report.parsing_errors.append({"path": doc_id, "error": err})
        logger.log(f"ERROR ingesting {doc_id}: {err}")

    # 3. Embed (vector DB, incremental + dedup).
    embed = EmbedPipeline(config=config, corpus_root=corpus_root, manifest_path=manifest_path)
    try:
        embed_report = embed.embed_corpus(force=force)
    finally:
        embed.close()  # release the SQLite lock on vector.db
    report.embeddings_generated = len(embed_report.embedded)
    for chunk_id in embed_report.embedded:
        logger.log(f"embedded {chunk_id}")
    for chunk_id in embed_report.skipped:
        report.files_skipped_duplicate.append(chunk_id)
    for chunk_id, err in embed_report.failed:
        report.parsing_errors.append({"path": chunk_id, "error": err})
        logger.log(f"ERROR embedding {chunk_id}: {err}")

    # 4. Report: count chunks in the store.
    store = VectorStore(config.derived_path / "vector.db")
    try:
        report.total_chunks = store.count()
    finally:
        store.close()

    # Write report.json + log.
    update_dir.mkdir(parents=True, exist_ok=True)
    (update_dir / "report.json").write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m cyberrisk.knowledge.update [--force] [--report]"""
    parser = argparse.ArgumentParser(
        prog="cyberrisk.knowledge.update",
        description="Automatic knowledge update: register, ingest, embed, report",
    )
    parser.add_argument("--force", action="store_true", help="Re-index everything")
    parser.add_argument("--report", action="store_true", help="Print the last report")
    args = parser.parse_args(argv)

    if args.report:
        config = load_ingest_config()
        path = config.derived_path / "update" / "report.json"
        if not path.exists():
            print("no report yet — run an update first")
            return 1
        data = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    report = run_update(force=args.force)
    print(f"documents processed: {len(report.documents_processed)}")
    print(f"chunks created:      {report.chunks_created}")
    print(f"embeddings generated:{report.embeddings_generated}")
    print(f"duplicates skipped:  {len(report.files_skipped_duplicate)}")
    print(f"parsing errors:      {len(report.parsing_errors)}")
    print(f"total chunks in DB:  {report.total_chunks}")
    if report.parsing_errors:
        for e in report.parsing_errors:
            print(f"  ERROR {e['path']}: {e['error']}")
    return 0 if not report.parsing_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
