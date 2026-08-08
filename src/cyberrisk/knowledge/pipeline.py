"""Document ingestion orchestrator — read, extract, chunk, index.

The entry point to the knowledge pipeline:

    ingest_corpus()          ingest every active document in corpus_manifest.yaml
    IngestPipeline           reusable orchestrator (extract -> clean -> chunk -> index)
    ingest_document()        ingest a single registered document

Incremental & idempotent: ``derived/state/ingest_state.json`` records
{doc_id: content_hash} of what has been indexed.  On re-ingest, a document
whose content_hash is unchanged is skipped; a changed document is re-chunked
and re-indexed.  The full index.json is rebuilt from the chunk store each run,
so it is always consistent.

The manifest (``corpus_manifest.yaml``) is the single source of truth: adding
a document is a file drop + one manifest entry.  No code change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from cyberrisk.knowledge.chunkers import Chunk, chunk_document
from cyberrisk.knowledge.config import IngestConfig, format_for_path, load_ingest_config
from cyberrisk.knowledge.document import IngestDocument
from cyberrisk.knowledge.extractors import (
    extract_docx,
    extract_html,
    extract_markdown,
    extract_pdf,
    extract_txt,
    extract_yaml_incident,
)
from cyberrisk.knowledge.index import write_index

# ---------------------------------------------------------------------------
# Corpus manifest loading (mirrors data/manifest.py, for documents)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_MANIFEST = (
    REPO_ROOT / "knowledge" / "manifests" / "corpus_manifest.yaml"
)
DEFAULT_CORPUS_ROOT = REPO_ROOT / "knowledge" / "corpus"


def default_corpus_root() -> Path:
    return DEFAULT_CORPUS_ROOT


def load_corpus_manifest(path: str | Path | None = None) -> list[IngestDocument]:
    """Load + validate the corpus manifest into IngestDocuments.

    Only ``status: active`` entries are returned; example/deprecated entries
    are excluded (a manifest entry is "live" when its status is active and its
    file exists under the corpus root).
    """
    path = Path(path) if path is not None else DEFAULT_MANIFEST
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "documents" not in raw:
        raise ValueError(f"{path}: manifest must contain a top-level 'documents:' list")

    docs: list[IngestDocument] = []
    for entry in raw.get("documents", []):
        doc = IngestDocument(**entry)
        if doc.is_active:
            docs.append(doc)
    return docs


def resolve_document_path(
    doc: IngestDocument,
    corpus_root: str | Path | None = None,
) -> Path:
    """Resolve a document's id to a real file under the corpus root.

    The id is namespaced by location (corpus/<domain>/<category>/<doc>); the
    file may be any supported extension.  Returns the absolute path.

    Raises
        FileNotFoundError  when no file matching the id exists.
    """
    corpus_root = Path(corpus_root) if corpus_root is not None else DEFAULT_CORPUS_ROOT
    rel = doc.relative_path()
    matches = sorted(corpus_root.glob(f"{rel}.*"))
    if matches:
        doc.source_path = str(matches[0])
        return matches[0]
    raise FileNotFoundError(
        f"no source file for document {doc.id!r} under {corpus_root} "
        f"(expected {corpus_root / rel}.<ext>)"
    )


def verify_document_hash(doc: IngestDocument, path: Path) -> None:
    """Verify the manifest content_hash against the actual file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    actual = f"sha256:{h.hexdigest()}"
    if actual != doc.content_hash:
        raise ValueError(
            f"content hash mismatch for {doc.id}: manifest {doc.content_hash}, "
            f"file {actual}. Update the manifest entry after changing the file."
        )


# ---------------------------------------------------------------------------
# Extractors dispatch
# ---------------------------------------------------------------------------

_EXTRACTORS = {
    "txt": extract_txt,
    "markdown": extract_markdown,
    "html": extract_html,
    "pdf": extract_pdf,
    "docx": extract_docx,
    "yaml": extract_yaml_incident,
}


def _extract(path: Path, fmt: str):
    """Dispatch to the extractor for a canonical format key."""
    extractor = _EXTRACTORS.get(fmt)
    if extractor is None:
        raise ValueError(f"unsupported format {fmt!r}; supported: {', '.join(_EXTRACTORS)}")
    return extractor(path)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class IngestReport:
    """What one ingest run did — for the CLI and callers."""

    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (doc_id, error)

    @property
    def total(self) -> int:
        return len(self.ingested) + len(self.skipped) + len(self.failed)

    def summary(self) -> str:
        return (
            f"ingested {len(self.ingested)}, skipped {len(self.skipped)} "
            f"(unchanged), failed {len(self.failed)}"
        )


class IngestPipeline:
    """Reusable document ingestion orchestrator.

    Usage:
        pipeline = IngestPipeline(config=load_ingest_config())
        report = pipeline.ingest_corpus()
        # or a single document:
        docs = load_corpus_manifest()
        chunks = pipeline.ingest_document(docs[0])
    """

    def __init__(
        self,
        config: IngestConfig | None = None,
        corpus_root: str | Path | None = None,
        manifest_path: str | Path | None = None,
    ) -> None:
        self.config = config or load_ingest_config()
        self.corpus_root = Path(corpus_root) if corpus_root is not None else DEFAULT_CORPUS_ROOT
        self.manifest_path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST
        self._state_path = self.config.derived_path / "state" / "ingest_state.json"

    # ------------------------------------------------------------------
    # State (incremental)
    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, str]:
        if self._state_path.exists():
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        return {}

    def _save_state(self, state: dict[str, str]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Single document
    # ------------------------------------------------------------------

    def ingest_document(self, doc: IngestDocument) -> tuple[list[Chunk], dict]:
        """Extract, clean, chunk, and index one document.

        Returns (chunks, index_record) where index_record is what belongs in
        index.json, built from the SAME chunk_records that were written to
        derived/chunks/.  Raises on a missing file, hash mismatch, unsupported
        format, or a disabled format — loud errors, never silent skips (except
        an optional-dep-absent PDF/DOCX, which raises a clear RuntimeError).
        """
        path = resolve_document_path(doc, self.corpus_root)
        fmt = doc.fmt or format_for_path(path)
        if fmt is None:
            raise ValueError(f"unsupported format for {path.name}")
        if not self.config.is_format_enabled(fmt):
            raise RuntimeError(
                f"format {fmt!r} is disabled in the ingest config for {doc.id}"
            )
        verify_document_hash(doc, path)

        extracted = _extract(path, fmt)
        title = doc.title or extracted.title
        chunks = chunk_document(
            doc=extracted,
            doc_id=doc.id,
            title=title,
            license_tier=doc.license_tier,
            strategy=doc.chunking.strategy,
            max_chars=doc.chunking.max_chars,
            overlap=doc.chunking.overlap,
            config=self.config,
        )
        from cyberrisk.knowledge.index import write_document

        record = write_document(
            derived_root=self.config.derived_path,
            doc=doc,
            chunks=chunks,
            sections=extracted.sections,
            source_path=str(path),
        )
        return chunks, record

    # ------------------------------------------------------------------
    # Full corpus
    # ------------------------------------------------------------------

    def ingest_corpus(self, force: bool | None = None) -> IngestReport:
        """Ingest every active document in the corpus manifest.

        Incremental: unchanged documents (same content_hash) are skipped unless
        ``force`` (or config.force_reingest) is set.  The full index.json is
        rebuilt from the chunk store at the end.
        """
        docs = load_corpus_manifest(self.manifest_path)
        state = self._load_state()
        report = IngestReport()
        records: list[dict] = []

        force = bool(force) if force is not None else self.config.force_reingest

        for doc in docs:
            if not force and state.get(doc.id) == doc.content_hash:
                report.skipped.append(doc.id)
                # Preserve the doc's existing index record.
                existing = self._read_existing_index_record(doc.id)
                if existing is not None:
                    records.append(existing)
                continue
            try:
                _chunks, record = self.ingest_document(doc)
                state[doc.id] = doc.content_hash
                records.append(record)
                report.ingested.append(doc.id)
            except Exception as exc:  # noqa: BLE001 — collect per-doc failures
                report.failed.append((doc.id, f"{type(exc).__name__}: {exc}"))

        self._save_state(state)
        if records:
            write_index(self.config.derived_path, records)
        return report

    # ------------------------------------------------------------------
    # Index record helpers
    # ------------------------------------------------------------------

    def _read_existing_index_record(self, doc_id: str) -> dict | None:
        """Read a document's index record from the existing index.json."""
        index_path = self.config.derived_path / "index" / "index.json"
        if not index_path.exists():
            return None
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        for rec in data.get("documents", []):
            if rec.get("doc_id") == doc_id:
                return rec
        return None

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m cyberrisk.knowledge.pipeline [--config PATH] [--force] [--doc ID]"""
    parser = argparse.ArgumentParser(
        prog="cyberrisk.knowledge.pipeline",
        description="CyberRisk AI knowledge document ingestion pipeline",
    )
    parser.add_argument("--config", default=None, help="IngestConfig YAML path")
    parser.add_argument("--force", action="store_true", help="Re-ingest all docs, ignoring state")
    parser.add_argument("--doc", default=None, help="Ingest only this document id")
    parser.add_argument(
        "--corpus",
        default=None,
        help="Corpus root (default knowledge/corpus)",
    )
    args = parser.parse_args(argv)

    config = load_ingest_config(args.config)
    pipeline = IngestPipeline(
        config=config,
        corpus_root=args.corpus,
    )
    if args.doc:
        docs = load_corpus_manifest()
        doc = next((d for d in docs if d.id == args.doc), None)
        if doc is None:
            print(f"document {args.doc!r} not found in manifest")
            return 1
        chunks = pipeline.ingest_document(doc)
        print(f"ingested {doc.id}: {len(chunks)} chunks")
        return 0

    report = pipeline.ingest_corpus(force=args.force)
    print(report.summary())
    for doc_id in report.ingested:
        print(f"  ingested  {doc_id}")
    for doc_id in report.skipped:
        print(f"  skipped   {doc_id} (unchanged)")
    for doc_id, err in report.failed:
        print(f"  FAILED    {doc_id}: {err}")
    return 0 if not report.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
