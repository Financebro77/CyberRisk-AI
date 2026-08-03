"""Benchmark framework tests."""

from pathlib import Path

import pytest

from cyberrisk.benchmark import (
    _rating_to_score,
    load_benchmark_profiles,
    run_benchmarks,
    run_profile,
)
from cyberrisk.calibration import load_config
from cyberrisk.scoring import load_scoring_weights

REPO = Path(__file__).parent.parent


def _config():
    return load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )


def test_load_five_profiles():
    profiles = load_benchmark_profiles()
    assert len(profiles) == 5
    # spans the risk spectrum
    cats = {p.expected_category for p in profiles}
    assert {"Low", "Medium", "High", "Critical"} & cats  # at least 3 distinct


def test_profile_controls_use_valid_ratings():
    """Every control rating must map through the evidence scales."""
    w = load_scoring_weights()
    for p in load_benchmark_profiles():
        for key, rating in p.controls.items():
            _rating_to_score(w, key, rating)  # raises if invalid


def test_all_profiles_have_complete_controls():
    """Each profile should cover all 18 factors (no gaps -> renormalised)."""
    w = load_scoring_weights()
    all_keys = {f.key for d in w.domains for f in d.factors}
    for p in load_benchmark_profiles():
        assert set(p.controls) == all_keys, f"{p.name} missing factors"


def test_rating_to_score_maps():
    w = load_scoring_weights()
    # low-risk rating -> low score
    assert _rating_to_score(w, "patch_cadence", "continuous") < _rating_to_score(
        w, "patch_cadence", "none"
    )
    assert _rating_to_score(w, "mfa_coverage", "comprehensive") < _rating_to_score(
        w, "mfa_coverage", "none"
    )
    # external_attack_surface is now correctly oriented: extensive -> high risk
    assert _rating_to_score(w, "external_attack_surface", "extensive") > _rating_to_score(
        w, "external_attack_surface", "minimal"
    )


def test_rating_to_score_unknown_rating_rejected():
    w = load_scoring_weights()
    with pytest.raises(ValueError):
        _rating_to_score(w, "patch_cadence", "sometimes")


def test_score_ordering_across_profiles():
    """The 5 profiles must score in a sensible ascending order."""
    w = load_scoring_weights()
    from cyberrisk.benchmark import _rating_to_score
    from cyberrisk.scoring import CompanyProfile, compute_score

    scores = []
    names = []
    for p in load_benchmark_profiles():
        factor_scores = {k: _rating_to_score(w, k, r) for k, r in p.controls.items()}
        c = compute_score(CompanyProfile(firm_name=p.name, factor_scores=factor_scores), w)
        scores.append(c.composite_score)
        names.append(p.name)
    # the set of scores is consistent with the expected categories:
    #   Low profile scores lowest, Critical profile scores highest
    low_idx = names.index("Precision Manufacturing Co")
    crit_idx = names.index("Brightline Consulting LLP")
    assert scores[low_idx] == min(scores)
    assert scores[crit_idx] == max(scores)
    # healthcare (High) out-scores retail (Medium)
    health_idx = names.index("St Helier Health System")
    retail_idx = names.index("Metro Retail Group")
    assert scores[health_idx] > scores[retail_idx]


def test_run_profile_produces_results():
    cfg = _config()
    profiles = load_benchmark_profiles()
    r = run_profile(profiles[0], cfg, n_years=20_000, seed=1)
    assert r.risk_score == pytest.approx(r.scored.composite_score)
    assert r.eal > 0
    assert r.es_99 > r.eal  # ordering invariant
    assert r.p99_9 >= r.es_99


def test_benchmark_expected_outcomes_satisfied():
    """The model must meet the consultant's expected category/score for all 5."""
    cfg = _config()
    results = run_benchmarks(load_benchmark_profiles(), cfg, n_years=100_000, seed=42)
    for r in results:
        assert r.score_ok(), f"{r.profile.name}: score {r.risk_score} outside expected"
        assert r.category_ok(), f"{r.profile.name}: category {r.risk_category} != expected"


def test_benchmark_reproducible():
    cfg = _config()
    a = run_benchmarks(load_benchmark_profiles(), cfg, n_years=20_000, seed=7)
    b = run_benchmarks(load_benchmark_profiles(), cfg, n_years=20_000, seed=7)
    assert [r.eal for r in a] == [r.eal for r in b]


def test_benchmark_full_pipeline_runs():
    """The full Phase-3 config (NegBin + Student-t + clustering) must run all 5."""
    cfg = _config()
    results = run_benchmarks(load_benchmark_profiles(), cfg, n_years=30_000, seed=99)
    assert len(results) == 5
    for r in results:
        assert r.eal > 0
        assert r.es_99 > r.eal
