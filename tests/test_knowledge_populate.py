"""Authoritative populate workflow tests.

Exercises the quality-gated population workflow: approved sources are
ingested, unapproved sources are skipped, and the report is produced.
Uses a temp corpus + manifest so the real knowledge tree is not mutated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyberrisk.knowledge.config import load_ingest_config
from cyberrisk.knowledge.populate import (
    _source_for_path,
    populate_corpus,
    write_population_report,
)

REPO = Path(__file__).parent.parent


@pytest.fixture()
def pop_env(tmp_path):
    """Temp corpus + manifest + derived, with the real source registry."""
    corpus = tmp_path / "corpus"
    manifest = tmp_path / "manifests"
    derived = tmp_path / "derived"
    corpus.mkdir(parents=True)
    manifest.mkdir(parents=True)
    (manifest / "corpus_manifest.yaml").write_text("documents: []\n", encoding="utf-8")
    config = load_ingest_config().model_copy(update={"derived_root": str(derived)})
    return {"corpus": corpus, "manifest": manifest / "corpus_manifest.yaml", "config": config}


def _place(pop_env, rel: str, text: str) -> Path:
    path = pop_env["corpus"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------


def test_source_for_path_known_folder(pop_env):
    path = _place(pop_env, "standards/nist-csf-2.0/framework.md", "# NIST\ncontent")
    src = _source_for_path(pop_env["corpus"], path)
    assert src == "NIST Cybersecurity Framework (CSF)"


def test_source_for_path_unknown_folder(pop_env):
    path = _place(pop_env, "unknown-folder/doc.md", "# X\ncontent")
    assert _source_for_path(pop_env["corpus"], path) is None


# ---------------------------------------------------------------------------
# Populate workflow
# ---------------------------------------------------------------------------


def test_populate_ingests_approved_source(pop_env):
    _place(pop_env, "standards/nist-csf-2.0/framework.md", "# NIST CSF\ncontent about framework")
    report = populate_corpus(
        corpus_root=pop_env["corpus"], manifest_path=pop_env["manifest"],
        config=pop_env["config"], force=True,
    )
    assert report.documents_processed
    assert "corpus/standards/nist-csf-2.0/framework" in report.documents_processed
    assert report.chunks_created >= 1
    assert report.embeddings_generated >= 1


def test_populate_skips_unapproved_source(pop_env):
    # A file under an unknown folder -> source unknown -> skipped.
    _place(pop_env, "unknown-folder/blog.md", "# Blog\ncontent")
    report = populate_corpus(
        corpus_root=pop_env["corpus"], manifest_path=pop_env["manifest"],
        config=pop_env["config"], force=True,
    )
    assert report.documents_skipped_unapproved
    assert not report.documents_processed  # nothing approved to process


def test_populate_report_fields(pop_env):
    _place(pop_env, "industry-reports/verizon-dbir/dbir.md", "# DBIR\nbreach content")
    report = populate_corpus(
        corpus_root=pop_env["corpus"], manifest_path=pop_env["manifest"],
        config=pop_env["config"], force=True,
    )
    # Phase-7 fields.
    assert report.sources_added
    assert report.categories_covered
    assert isinstance(report.missing_domains, list)
    assert report.quality_assessment
    assert report.recommended_future_additions
    assert "cybersecurity_framework" in report.categories_covered


def test_populate_writes_report_json(pop_env):
    _place(pop_env, "standards/cis-controls/cis.md", "# CIS\ncontent")
    report = populate_corpus(
        corpus_root=pop_env["corpus"], manifest_path=pop_env["manifest"],
        config=pop_env["config"], force=True,
    )
    json_path = pop_env["config"].derived_path / "populate" / "report.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "sources_added" in data
    assert "missing_domains" in data


def test_write_population_report(pop_env):
    _place(pop_env, "regulatory/gdpr/gdpr.md", "# GDPR\ncontent")
    report = populate_corpus(
        corpus_root=pop_env["corpus"], manifest_path=pop_env["manifest"],
        config=pop_env["config"], force=True,
    )
    path = write_population_report(report)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Knowledge Population Report" in text
    assert "Sources Added" in text
    assert "Categories Covered" in text
    assert "Missing Domains" in text
    assert "Licensing Concerns" in text
    assert "Recommended Future Additions" in text
