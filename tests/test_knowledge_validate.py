"""Knowledge base validation suite — hermetic smoke tests.

Runs the full validation runner against the REAL corpus + vector store and
asserts all nine areas execute and produce PASS/FAIL results with metrics.
These are smoke tests for the runner itself (not re-tests of each pipeline,
which are covered by the per-module test files).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cyberrisk.knowledge.config import load_ingest_config
from cyberrisk.knowledge.validate import (
    THRESHOLDS,
    validate_knowledge_base,
)

REPO = Path(__file__).parent.parent

# The nine areas the suite must cover.
EXPECTED_AREAS = {
    "document_ingestion", "chunk_quality", "embedding_quality",
    "semantic_retrieval", "source_attribution", "citation_accuracy",
    "duplicate_detection", "retrieval_latency", "hallucination_resistance",
}


@pytest.fixture(scope="module")
def results():
    config = load_ingest_config()
    return validate_knowledge_base(config)


def test_all_nine_areas_run(results):
    areas = {r.area for r in results}
    assert areas == EXPECTED_AREAS


def test_every_area_has_status(results):
    for r in results:
        assert r.status in ("PASS", "FAIL")
        assert r.metric, f"{r.area} missing metric"
        assert r.threshold, f"{r.area} missing threshold"


def test_every_area_has_a_defined_threshold():
    # The THRESHOLDS map covers all nine areas.
    assert set(THRESHOLDS.keys()) == EXPECTED_AREAS


def test_results_are_serialisable(results):
    for r in results:
        d = r.to_dict()
        assert d["area"] and d["status"]
        assert isinstance(d["details"], list)


def test_no_validator_crashed(results):
    # A validator crash surfaces as status=FAIL with metric "validator crashed".
    crashed = [r for r in results if r.metric == "validator crashed"]
    assert not crashed, f"validators crashed: {crashed}"


def test_report_generation_writes_files(tmp_path):
    """validate_knowledge_base + report writer produce md + json (via CLI path)."""
    import json as _json
    from cyberrisk.knowledge.validate import _write_report

    config = load_ingest_config().model_copy(update={"derived_root": str(tmp_path / "derived")})
    results = validate_knowledge_base(config)
    _write_report(results, config)

    # The report.json is written under the (temp) derived root.
    json_path = tmp_path / "derived" / "validation" / "report.json"
    assert json_path.exists()
    data = _json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["results"]) == 9
    # The markdown report goes to the real reports/ dir (committed artifact).
    md_path = REPO / "reports" / "knowledge_validation.md"
    assert md_path.exists()
