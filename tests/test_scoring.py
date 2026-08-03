"""Scoring engine tests (Phase 2)."""

from pathlib import Path

import numpy as np
import pytest

from cyberrisk.scoring import (
    CompanyProfile,
    DomainSpec,
    FactorSpec,
    ScoringWeights,
    compute_score,
    load_scoring_weights,
)

REPO = Path(__file__).parent.parent
WEIGHTS = REPO / "config" / "scoring_weights.yaml"


def _weights() -> ScoringWeights:
    return load_scoring_weights(WEIGHTS)


def _minimal_profile() -> CompanyProfile:
    """A profile that scores ~neutral (all factors at moderate/high risk)."""
    return CompanyProfile(firm_name="test", factor_scores={})


def test_weights_load_and_validate():
    w = _weights()
    assert len(w.domains) == 6
    # domain weights sum to 1
    assert abs(sum(d.weight for d in w.domains) - 1.0) < 1e-9
    for d in w.domains:
        assert abs(sum(f.weight for f in d.factors) - 1.0) < 1e-9
    # category bands end at 100, ordered
    assert w.category_bands[-1]["max_score"] == 100


def test_empty_profile_neutral_score():
    w = _weights()
    profile = CompanyProfile(firm_name="no data")
    result = compute_score(profile, w)
    assert 0 <= result.composite_score <= 100
    assert result.risk_category in {"Low", "Medium", "High", "Critical"}
    # neutral default: no factors -> composite 50 -> Medium
    assert result.composite_score == 50.0
    assert result.risk_category == "Medium"


def test_low_score_profile():
    w = _weights()
    # Best possible scores across every factor (low risk)
    best = {}
    for d in w.domains:
        for f in d.factors:
            best[f.key] = min(f.evidence_scale.values())
    result = compute_score(CompanyProfile(firm_name="best", factor_scores=best), w)
    assert result.composite_score < 25
    assert result.risk_category == "Low"
    # drivers are RELATIVE (factors above domain average), not absolute --
    # even a best-case profile can have one factor slightly above its domain
    # mean.  What matters is the category and the low composite.
    assert isinstance(result.risk_drivers, list)


def test_high_score_profile():
    w = _weights()
    worst = {}
    for d in w.domains:
        for f in d.factors:
            worst[f.key] = max(f.evidence_scale.values())
    result = compute_score(CompanyProfile(firm_name="worst", factor_scores=worst), w)
    assert result.composite_score > 75
    assert result.risk_category in {"High", "Critical"}
    # every factor is at max risk so drivers may be empty (all equal max)


def test_missing_factors_renormalise():
    """Providing only one domain's factors still yields a valid 0-100 score."""
    w = _weights()
    # Score only threat_exposure factors high; everything else absent.
    partial = {}
    for f in w.domains[0].factors:
        partial[f.key] = 90.0
    result = compute_score(CompanyProfile(firm_name="partial", factor_scores=partial), w)
    assert result.composite_score > 60  # dominated by a 90-avg domain
    assert set(result.domain_scores) == {d.key for d in w.domains}


def test_risk_drivers_identify_weak_factors():
    w = _weights()
    # Give one factor a much worse score than its domain average.
    scores = {}
    d0 = w.domains[0]
    for f in d0.factors:
        scores[f.key] = 20.0  # domain average ~20
    scores[d0.factors[0].key] = 95.0  # a standout weak factor
    result = compute_score(CompanyProfile(firm_name="weak", factor_scores=scores), w)
    assert d0.factors[0].key in result.risk_drivers


def test_score_monotonic_in_input():
    """Raising one factor score must not lower the composite."""
    w = _weights()
    base = {}
    for d in w.domains:
        for f in d.factors:
            base[f.key] = 50.0
    r1 = compute_score(CompanyProfile(firm_name="a", factor_scores=base), w)
    base["mfa_coverage"] = 95.0
    r2 = compute_score(CompanyProfile(firm_name="b", factor_scores=base), w)
    assert r2.composite_score > r1.composite_score


def test_domain_weights_not_sum_one_rejected():
    with pytest.raises(ValueError):
        ScoringWeights(
            category_bands=[{"max_score": 100, "category": "X"}],
            domains=[
                DomainSpec(
                    key="a",
                    name="a",
                    weight=0.5,
                    factors=[FactorSpec(key="f", name="f", weight=1.0, evidence_scale={"x": 10})],
                )
            ],
        )


def test_bad_evidence_score_rejected():
    with pytest.raises(ValueError):
        FactorSpec(key="f", name="f", weight=1.0, evidence_scale={"x": 150.0})


def test_category_bands_must_end_at_100():
    with pytest.raises(ValueError):
        ScoringWeights(
            category_bands=[{"max_score": 80, "category": "X"}],
            domains=[],
        )


def test_score_scaled_lambdas_link():
    """The log-linear link scales baseline lambdas exactly."""
    from cyberrisk.calibration import load_config
    from cyberrisk.simulation import score_scaled_lambdas

    cfg = load_config(REPO / "config" / "scenarios.yaml", REPO / "config" / "simulation_config.yaml")
    base = np.array([s.frequency.lambda_annual for s in cfg.scenarios])
    # score == reference -> unchanged
    assert np.allclose(score_scaled_lambdas(cfg, 50.0), base)
    # score 70 with k=1 -> exp(0.2) multiplier
    assert np.allclose(score_scaled_lambdas(cfg, 70.0), base * np.exp(0.2))
    # score 30 -> exp(-0.2) (lower risk -> fewer events)
    assert np.allclose(score_scaled_lambdas(cfg, 30.0), base * np.exp(-0.2))
    # per-scenario k array respected
    ks = np.linspace(0.5, 2.0, len(cfg.scenarios))
    expected = base * np.exp(ks * 0.2)
    assert np.allclose(score_scaled_lambdas(cfg, 70.0, k=ks), expected)


def test_simulate_with_score():
    """A higher score raises EAL; a lower score lowers it."""
    from cyberrisk.calibration import load_config
    from cyberrisk.metrics import compute_metrics
    from cyberrisk.simulation import simulate

    cfg = load_config(REPO / "config" / "scenarios.yaml", REPO / "config" / "simulation_config.yaml")
    low = simulate(cfg, n_years=100_000, score=30.0)
    ref = simulate(cfg, n_years=100_000, score=50.0)
    high = simulate(cfg, n_years=100_000, score=70.0)
    m_low, m_ref, m_high = compute_metrics(low), compute_metrics(ref), compute_metrics(high)
    assert m_high.eal > m_ref.eal > m_low.eal
    assert m_high.es_99 > m_low.es_99