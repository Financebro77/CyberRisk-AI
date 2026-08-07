"""Dataset loader tests — manifest parsing, format reads, mapping, calibration.

Exercises the manifest-driven dataset loader end-to-end against the real
repo manifests and the example datasets under knowledge/datasets/:
    load_dataset_manifest -> load_dataset -> to_benchmarks
        -> datasets_to_benchmarks -> build_calibrated_config

The severity example must drive the engine's severity (closing the mock
severity gap); the frequency example must drive scenario lambdas through the
existing calibration seam.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from cyberrisk.calibration import load_config
from cyberrisk.data.manifest import (
    DatasetManifest,
    DatasetManifestEntry,
    load_dataset_manifest,
    resolve_dataset_path,
    sha256_file,
    verify_content_hash,
)
from cyberrisk.data.dataset_loaders import (
    build_calibrated_config,
    datasets_to_benchmarks,
    load_dataset,
    to_benchmarks,
)
from cyberrisk.data.schemas import BenchmarkRecord, BenchmarkSet

REPO = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def manifest() -> DatasetManifest:
    return load_dataset_manifest(REPO / "knowledge" / "manifests" / "dataset_manifest.yaml")


@pytest.fixture(scope="module")
def base_config():
    return load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )


def _calibrated_from_records(config, benchmarks):
    """Apply frequency + severity overrides from an explicit BenchmarkSet.

    Mirrors build_calibrated_config but without re-reading the manifest —
    used to test mu/sigma overrides with an inline table.
    """
    from cyberrisk.calibration import apply_benchmarks

    calibrated = apply_benchmarks(config, benchmarks, sector="All")
    scenario_by_key = {s.key: s for s in calibrated.scenarios}
    for rec in benchmarks.records:
        metric = rec.metric
        if not metric.startswith("severity"):
            continue
        rest = metric[len("severity"):].lstrip("_")
        if rest.startswith("mu_"):
            scenario_key, field = rest[3:], "mu"
        elif rest.startswith("sigma_"):
            scenario_key, field = rest[6:], "sigma"
        elif rest.startswith("revenue_exp_"):
            scenario_key, field = rest[12:], "revenue_exponent"
        else:
            scenario_key, field = rest, "scale"
        if scenario_key not in scenario_by_key:
            raise ValueError(f"unknown scenario {scenario_key!r}")
        from cyberrisk.data.dataset_loaders import _apply_severity_override

        _apply_severity_override(calibrated, scenario_key, field, rec.value)
    return calibrated


def _entry(manifest: DatasetManifest, dataset_id: str) -> DatasetManifestEntry:
    matches = [d for d in manifest.active() if d.id == dataset_id]
    assert len(matches) == 1, f"expected exactly one active entry for {dataset_id}"
    return matches[0]


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------


def test_load_manifest_valid(manifest: DatasetManifest):
    assert isinstance(manifest, DatasetManifest)
    assert len(manifest.datasets) >= 2
    # The two example benchmark entries are active.
    ids = {d.id for d in manifest.active()}
    assert "datasets/benchmarks/severity/ibm-codb-2026-sector" in ids
    assert "datasets/benchmarks/frequency/dbir-2026-sector" in ids


def test_manifest_default_path():
    m = load_dataset_manifest()
    assert len(m.datasets) >= 2


def test_content_hash_mismatch_raises(manifest: DatasetManifest):
    entry = _entry(manifest, "datasets/benchmarks/severity/ibm-codb-2026-sector")
    path = resolve_dataset_path(entry)
    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_content_hash(entry.model_copy(update={"content_hash": "sha256:" + "0" * 64}), path)


def test_content_hash_matches(manifest: DatasetManifest):
    entry = _entry(manifest, "datasets/benchmarks/severity/ibm-codb-2026-sector")
    path = resolve_dataset_path(entry)
    # sha256_file returns the sha256:... form; the manifest entry must match.
    assert entry.content_hash == sha256_file(path)
    # verify_content_hash should not raise.
    verify_content_hash(entry, path)


def test_unknown_target_raises():
    with pytest.raises(ValidationError):
        DatasetManifestEntry(
            id="datasets/benchmarks/severity/bad",
            domain="benchmarks",
            category="severity",
            title="Bad target",
            source="test",
            license_tier="public",
            format="csv",
            schema="severity_sector_table",
            version="1.0",
            content_hash="sha256:" + "0" * 64,
            acquired_at="2026-08-08",
            refresh_cadence="annual",
            tags=["x"],
            targets=["no.such.seam"],
        )


def test_resolve_dataset_path_missing_raises():
    with pytest.raises(FileNotFoundError):
        resolve_dataset_path(
            DatasetManifestEntry(
                id="datasets/benchmarks/severity/does-not-exist",
                domain="benchmarks",
                category="severity",
                title="Missing",
                source="test",
                license_tier="public",
                format="csv",
                schema="severity_sector_table",
                version="1.0",
                content_hash="sha256:" + "0" * 64,
                acquired_at="2026-08-08",
                refresh_cadence="annual",
                tags=["x"],
                targets=["calibration.apply_benchmarks"],
            )
        )


# ---------------------------------------------------------------------------
# Format reads
# ---------------------------------------------------------------------------


def test_load_dataset_csv(manifest: DatasetManifest):
    entry = _entry(manifest, "datasets/benchmarks/severity/ibm-codb-2026-sector")
    df = load_dataset(entry)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"source", "sector", "metric", "value", "units", "notes"} <= set(df.columns)


def test_load_dataset_frequency_csv(manifest: DatasetManifest):
    entry = _entry(manifest, "datasets/benchmarks/frequency/dbir-2026-sector")
    df = load_dataset(entry)
    assert not df.empty
    assert "metric" in df.columns


def test_load_dataset_parquet_roundtrip(tmp_path, manifest: DatasetManifest):
    """The loader reads parquet when a dataset is registered as such."""
    entry = _entry(manifest, "datasets/benchmarks/severity/ibm-codb-2026-sector")
    df = load_dataset(entry)
    pq = tmp_path / "sev.parquet"
    df.to_parquet(pq)
    # Read the parquet copy via the same loader path (verify=False — the
    # tmp copy won't match the committed manifest hash).
    loaded = load_dataset(
        entry.model_copy(update={"format": "parquet", "path": str(pq)}),
        verify=False,
    )
    assert list(loaded.columns) == list(df.columns)
    assert len(loaded) == len(df)


# ---------------------------------------------------------------------------
# Row -> BenchmarkRecord mapping
# ---------------------------------------------------------------------------


def test_to_benchmarks_maps_rows(manifest: DatasetManifest):
    entry = _entry(manifest, "datasets/benchmarks/severity/ibm-codb-2026-sector")
    df = load_dataset(entry)
    records = to_benchmarks(df, entry)
    assert len(records) == len(df)
    for rec in records:
        assert isinstance(rec, BenchmarkRecord)
        assert rec.source
        assert rec.sector
        assert rec.metric.startswith("severity")
        assert rec.value > 0
        assert rec.units


def test_to_benchmarks_normalises_metric():
    """A human metric label ('Ransomware frequency') normalises to canonical."""
    df = pd.DataFrame(
        [
            {"source": "X", "sector": "All", "metric": "Ransomware frequency",
             "value": 0.4, "units": "events_per_year", "notes": ""},
        ]
    )
    entry = DatasetManifestEntry(
        id="datasets/benchmarks/frequency/test",
        domain="benchmarks",
        category="frequency",
        title="Test frequency",
        source="Test",
        license_tier="public",
        format="csv",
        schema="frequency_sector_table",
        version="1",
        content_hash="sha256:" + "0" * 64,
        acquired_at="2026-08-08",
        refresh_cadence="annual",
        tags=["x"],
        targets=["calibration.apply_benchmarks"],
        status="example",
    )
    records = to_benchmarks(df, entry)
    assert records[0].metric == "ransomware_frequency"


def test_to_benchmarks_bad_row_raises(manifest: DatasetManifest):
    entry = _entry(manifest, "datasets/benchmarks/severity/ibm-codb-2026-sector")
    df = pd.DataFrame(
        [
            {"source": "X", "sector": "All", "metric": "severity_breach",
             "value": "not-a-number", "units": "usd", "notes": ""},
        ]
    )
    with pytest.raises(ValueError):
        to_benchmarks(df, entry)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_datasets_to_benchmarks_aggregates(manifest: DatasetManifest):
    bs = datasets_to_benchmarks(manifest, domain="benchmarks")
    assert isinstance(bs, BenchmarkSet)
    assert len(bs.records) >= 2
    # severity + frequency records both present
    metrics = {r.metric for r in bs.records}
    assert any(m.startswith("severity") for m in metrics)
    assert any("_frequency" in m for m in metrics)


# ---------------------------------------------------------------------------
# Calibration: frequency + severity overrides
# ---------------------------------------------------------------------------


def test_build_calibrated_config_severity(manifest: DatasetManifest, base_config):
    """The severity dataset must change the engine's breach severity."""
    cfg = build_calibrated_config(base_config, manifest, domain="benchmarks")
    base_breach = next(s for s in base_config.scenarios if s.key == "breach")
    cal_breach = next(s for s in cfg.scenarios if s.key == "breach")
    # The IBM severity table sets severity_breach -> new scale.
    assert cal_breach.severity.scale != base_breach.severity.scale
    # And it's the value from the dataset.
    assert cal_breach.severity.scale == pytest.approx(465_000.0)


def test_build_calibrated_config_frequency(manifest: DatasetManifest, base_config):
    """The frequency dataset must reach the calibration seam (lambda annotation)."""
    cfg = build_calibrated_config(base_config, manifest, domain="benchmarks")
    base_breach = next(s for s in base_config.scenarios if s.key == "breach")
    cal_breach = next(s for s in cfg.scenarios if s.key == "breach")
    # The DBIR frequency table sets breach_frequency; the calibration seam
    # annotates the scenario with the source.  (Baseline breach lambda is also
    # 0.75, so the value is unchanged — the annotation proves it went through.)
    assert "calibrated_lambda" in cal_breach.annotation or "calibrated_lambda_from" in cal_breach.annotation
    assert cal_breach.frequency.lambda_annual == pytest.approx(base_breach.frequency.lambda_annual)


def test_build_calibrated_config_severity_mu_sigma(manifest: DatasetManifest, base_config):
    """A severity table with mu/sigma rows drives those parameters too."""
    from cyberrisk.data.manifest import DatasetManifestEntry
    from cyberrisk.data.dataset_loaders import to_benchmarks

    df = pd.DataFrame(
        [
            {"source": "X", "sector": "All", "metric": "severity_mu_breach",
             "value": 0.5, "units": "", "notes": ""},
            {"source": "X", "sector": "All", "metric": "severity_sigma_breach",
             "value": 1.2, "units": "", "notes": ""},
        ]
    )
    entry = DatasetManifestEntry(
        id="datasets/benchmarks/severity/mu-sigma-test",
        domain="benchmarks",
        category="severity",
        title="Test mu/sigma severity",
        source="Test",
        license_tier="public",
        format="csv",
        schema="severity_sector_table",
        version="1",
        content_hash="sha256:" + "0" * 64,
        acquired_at="2026-08-08",
        refresh_cadence="annual",
        tags=["x"],
        targets=["calibration.apply_benchmarks"],
        status="example",
    )
    bs = BenchmarkSet(records=to_benchmarks(df, entry))
    cfg = _calibrated_from_records(base_config, bs)
    breach = next(s for s in cfg.scenarios if s.key == "breach")
    assert breach.severity.mu == pytest.approx(0.5)
    assert breach.severity.sigma == pytest.approx(1.2)


def test_build_calibrated_config_does_not_mutate_input(manifest: DatasetManifest, base_config):
    """The input config is never mutated — reproducible from the manifest."""
    before_scale = {s.key: s.severity.scale for s in base_config.scenarios}
    build_calibrated_config(base_config, manifest, domain="benchmarks")
    after_scale = {s.key: s.severity.scale for s in base_config.scenarios}
    assert before_scale == after_scale


def test_build_calibrated_config_reproducible(manifest: DatasetManifest, base_config):
    a = build_calibrated_config(base_config, manifest, domain="benchmarks")
    b = build_calibrated_config(base_config, manifest, domain="benchmarks")
    assert a == b


# ---------------------------------------------------------------------------
# Registered examples resolve against the repo
# ---------------------------------------------------------------------------


def test_example_files_exist_and_registered():
    """The example datasets committed under knowledge/datasets resolve."""
    m = load_dataset_manifest()
    for entry in m.active():
        if entry.domain == "benchmarks":
            path = resolve_dataset_path(entry)
            assert path.exists(), f"{entry.id} -> {path} missing"
