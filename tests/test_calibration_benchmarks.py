"""Phase 3 calibration framework tests: benchmark loading + translation."""

from pathlib import Path

import pytest

from cyberrisk.calibration import apply_benchmarks, load_config
from cyberrisk.data.loaders import load_benchmarks
from cyberrisk.data.schemas import BenchmarkRecord, BenchmarkSet

REPO = Path(__file__).parent.parent


def _benchmarks() -> BenchmarkSet:
    return load_benchmarks(REPO / "config" / "calibration_benchmarks.csv")


def test_load_real_benchmarks():
    b = _benchmarks()
    assert len(b.records) >= 10
    sources = {r.source for r in b.records}
    assert "Verizon DBIR" in sources
    assert "IBM CODB" in sources
    assert "Hiscox" in sources


def test_first_value_lookup():
    b = _benchmarks()
    v = b.first_value("IBM CODB", "avg_total_cost")
    assert v == pytest.approx(4.88)


def test_filter_by_source_and_metric():
    b = _benchmarks()
    breach = b.filter(metric="breach_frequency")
    assert len(breach) == 1
    assert breach[0].source == "Verizon DBIR"
    # case-insensitive source
    hiscox = b.filter(source="hiscox")
    assert all("hiscox" in r.source.lower() for r in hiscox)


def test_benchmark_validation_rejects_bad_values():
    with pytest.raises(Exception):
        BenchmarkRecord(source="X", sector="All", metric="m", value=-5.0, units="u")
    with pytest.raises(Exception):
        BenchmarkRecord(source="X", sector="All", metric="m", value=0.0, units="u")


def test_from_csv_missing_file():
    with pytest.raises(FileNotFoundError):
        load_benchmarks(REPO / "config" / "does_not_exist.csv")


def test_apply_benchmarks_translates_lambdas():
    cfg = load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )
    b = _benchmarks()

    before = {s.key: s.frequency.lambda_annual for s in cfg.scenarios}
    calibrated = apply_benchmarks(cfg, b, sector="All")

    # input config is not mutated
    assert {s.key: s.frequency.lambda_annual for s in cfg.scenarios} == before

    after = {s.key: s.frequency.lambda_annual for s in calibrated.scenarios}
    # Scenarios with a frequency benchmark in the CSV get overridden.
    assert after["breach"] == pytest.approx(0.75)  # from Verizon DBIR
    assert after["ransomware"] == pytest.approx(0.40)  # from DBIR
    assert after["bec"] == pytest.approx(1.10)  # from FBI IC3
    # Scenarios with NO frequency benchmark keep their config baseline.
    assert after["supply_chain"] == before["supply_chain"]

    # Calibration annotation is recorded for auditability.
    assert "calibrated_lambda_from" in calibrated.scenarios[0].annotation
    assert "calibrated_lambda" in calibrated.scenarios[0].annotation


def test_apply_benchmarks_sector_override():
    cfg = load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )
    b = _benchmarks()
    # A sector-specific record overrides "All" when that sector is requested.
    sector_cfg = apply_benchmarks(cfg, b, sector="BEC")
    for s in sector_cfg.scenarios:
        if s.key == "bec":
            assert s.frequency.lambda_annual == pytest.approx(1.10)
            break
    else:  # pragma: no cover
        pytest.fail("no bec scenario")


def test_benchmark_translation_reproducible():
    """Applying benchmarks twice yields the same lambdas (pure function)."""
    cfg = load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )
    b = _benchmarks()
    c1 = apply_benchmarks(cfg, b, sector="All")
    c2 = apply_benchmarks(cfg, b, sector="All")
    assert [s.frequency.lambda_annual for s in c1.scenarios] == [
        s.frequency.lambda_annual for s in c2.scenarios
    ]
