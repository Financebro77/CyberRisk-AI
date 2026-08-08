"""Automatic knowledge update system tests.

Exercises auto-registration, the update orchestrator, duplicate avoidance,
parsing-error handling, and the report.  Uses a temp corpus + manifest so the
real knowledge/ tree is not mutated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyberrisk.knowledge.config import load_ingest_config
from cyberrisk.knowledge.document import IngestDocument
from cyberrisk.knowledge.pipeline import load_corpus_manifest
from cyberrisk.knowledge.update import (
    auto_register_file,
    find_unregistered_files,
    run_update,
)

REPO = Path(__file__).parent.parent


@pytest.fixture()
def update_env(tmp_path):
    """A temp corpus + manifest + derived root, isolated from the real repo."""
    corpus = tmp_path / "corpus"
    manifest = tmp_path / "manifests"
    derived = tmp_path / "derived"
    corpus.mkdir(parents=True)
    manifest.mkdir(parents=True)
    (manifest / "corpus_manifest.yaml").write_text("documents: []\n", encoding="utf-8")

    # Config with the temp derived root.
    config = load_ingest_config().model_copy(update={"derived_root": str(derived)})

    return {
        "corpus": corpus,
        "manifest": manifest / "corpus_manifest.yaml",
        "config": config,
    }


def _write_sample(corpus: Path, rel: str, text: str) -> Path:
    path = corpus / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# find_unregistered_files
# ---------------------------------------------------------------------------


def test_find_unregistered_returns_new_file(update_env):
    p = _write_sample(update_env["corpus"], "regulatory/new-report.md", "# Title\ncontent")
    files = find_unregistered_files(update_env["corpus"], update_env["manifest"])
    assert p in files


def test_find_unregistered_excludes_registered(update_env):
    p = _write_sample(update_env["corpus"], "regulatory/known.md", "# Title\ncontent")
    auto_register_file(p, update_env["corpus"], update_env["manifest"])
    files = find_unregistered_files(update_env["corpus"], update_env["manifest"])
    assert p not in files


def test_find_unregistered_skips_unsupported(update_env):
    _write_sample(update_env["corpus"], "regulatory/not-a-doc.xyz", "data")
    files = find_unregistered_files(update_env["corpus"], update_env["manifest"])
    assert files == []


# ---------------------------------------------------------------------------
# auto_register_file
# ---------------------------------------------------------------------------


def test_auto_register_builds_valid_doc(update_env):
    p = _write_sample(update_env["corpus"], "threat-intel/campaign.md", "# Campaign\ncontent")
    doc = auto_register_file(p, update_env["corpus"], update_env["manifest"])
    assert isinstance(doc, IngestDocument)
    assert doc.id == "corpus/threat-intel/campaign"
    assert doc.domain == "threat-intel"
    assert doc.title == "campaign.md"
    assert doc.license_tier == "public"
    assert doc.status == "active"
    assert doc.content_hash.startswith("sha256:")
    # Registered in the manifest.
    assert doc.id in {d.id for d in load_corpus_manifest(update_env["manifest"])}


def test_auto_register_duplicate_raises(update_env):
    p = _write_sample(update_env["corpus"], "regulatory/dup.md", "# T\ncontent")
    auto_register_file(p, update_env["corpus"], update_env["manifest"])
    with pytest.raises(ValueError, match="already registered"):
        auto_register_file(p, update_env["corpus"], update_env["manifest"])


# ---------------------------------------------------------------------------
# run_update (end-to-end)
# ---------------------------------------------------------------------------


def test_run_update_processes_new_file(update_env):
    p = _write_sample(update_env["corpus"], "regulatory/dora-nis2.md", "# DORA NIS2\ncontent about regulation")
    config = update_env["config"]

    # run_update uses the default corpus root — monkeypatch via kwargs.
    report = run_update(
        corpus_root=update_env["corpus"], manifest_path=update_env["manifest"],
        force=True, config=update_env["config"],
    )

    assert report.documents_processed == ["corpus/regulatory/dora-nis2"]
    assert report.chunks_created >= 1
    assert report.embeddings_generated >= 1
    assert report.total_chunks >= 1
    assert report.parsing_errors == []
    # Log written.
    log_path = config.derived_path / "update" / "updates.log"
    assert log_path.exists()
    log = log_path.read_text(encoding="utf-8")
    assert "registered corpus/regulatory/dora-nis2" in log
    assert "ingested corpus/regulatory/dora-nis2" in log


def test_run_update_duplicate_skips(update_env):
    _write_sample(update_env["corpus"], "regulatory/report.md", "# Report\ncontent here")
    first = run_update(
        corpus_root=update_env["corpus"], manifest_path=update_env["manifest"],
        force=True, config=update_env["config"],
    )
    assert first.documents_processed  # processed the new file

    # Second run: nothing new to register, ingest+embed skip unchanged.
    second = run_update(
        corpus_root=update_env["corpus"], manifest_path=update_env["manifest"],
        force=False, config=update_env["config"],
    )
    assert second.documents_processed == []  # no new registration
    assert second.chunks_created == 0  # unchanged docs not re-ingested


def test_run_update_parsing_error_recorded(update_env):
    # A corrupt file (garbage named .md is fine; a bad pdf needs pypdf — but a
    # nonexistent-format or corrupt parse should be recorded, not crash).
    bad = update_env["corpus"] / "regulatory" / "bad.pdf"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"not a real pdf at all")
    # Register it first (auto_register works on any supported ext).
    auto_register_file(bad, update_env["corpus"], update_env["manifest"])

    report = run_update(
        corpus_root=update_env["corpus"], manifest_path=update_env["manifest"],
        force=True, config=update_env["config"],
    )
    # The bad pdf should surface as a parsing/ingest error, not crash the run.
    assert any(e["error"] for e in report.parsing_errors), report.parsing_errors


def test_run_update_writes_report_json(update_env):
    _write_sample(update_env["corpus"], "industry-reports/trends.md", "# Trends\nmarket trends content")
    run_update(
        corpus_root=update_env["corpus"], manifest_path=update_env["manifest"],
        force=True, config=update_env["config"],
    )
    config = update_env["config"]
    report_path = config.derived_path / "update" / "report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "documents_processed" in data
    assert "chunks_created" in data
    assert "embeddings_generated" in data
    assert "parsing_errors" in data
    assert data["documents_processed"]
