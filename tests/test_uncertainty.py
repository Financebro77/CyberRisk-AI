"""Parameter uncertainty module tests (Phase 2)."""

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from cyberrisk.calibration import load_config
from cyberrisk.uncertainty import (
    UncertaintySpec,
    _perturb_config,
    load_uncertainty_spec,
    run_uncertainty_analysis,
)

REPO = Path(__file__).parent.parent


def _config():
    return load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )


def test_spec_loads_from_real_config():
    spec = load_uncertainty_spec()
    assert spec.iterations >= 2
    assert spec.lambda_cv > 0
    assert spec.seed > 0


def test_spec_rejects_implausible_spread():
    with pytest.raises(ValidationError):
        UncertaintySpec(iterations=10, lambda_cv=1.5)
    with pytest.raises(ValidationError):
        UncertaintySpec(iterations=1)


def test_perturb_config_preserves_structure():
    cfg = _config()
    rng = np.random.default_rng(0)
    spec = load_uncertainty_spec()
    perturbed = _perturb_config(cfg, rng, spec)
    # same scenario set, valid params
    assert [s.key for s in perturbed.scenarios] == [s.key for s in cfg.scenarios]
    for s in perturbed.scenarios:
        assert s.frequency.lambda_annual > 0
        assert s.severity.scale > 0
        assert s.severity.sigma is not None and s.severity.sigma > 0
        assert -0.95 <= s.copula_loading <= 0.95
    # nu clipped to >= 3
    assert perturbed.copula_nu >= 3.0


def test_perturbation_is_random_and_reproducible():
    cfg = _config()
    spec = load_uncertainty_spec()
    a = _perturb_config(cfg, np.random.default_rng(1), spec)
    b = _perturb_config(cfg, np.random.default_rng(1), spec)
    c = _perturb_config(cfg, np.random.default_rng(2), spec)
    # same seed -> identical perturbation
    assert [s.frequency.lambda_annual for s in a.scenarios] == [
        s.frequency.lambda_annual for s in b.scenarios
    ]
    # different seed -> different
    assert [s.frequency.lambda_annual for s in a.scenarios] != [
        s.frequency.lambda_annual for s in c.scenarios
    ]


def test_perturbation_zero_cv_is_identity():
    """With all CVs zero, perturbation leaves the config exactly unchanged."""
    cfg = _config()
    spec = UncertaintySpec(
        iterations=5, seed=1, lambda_cv=0.0, severity_scale_cv=0.0,
        severity_sigma_cv=0.0, loading_sd=0.0, copula_nu_sd=0.0,
    )
    rng = np.random.default_rng(0)
    perturbed = _perturb_config(cfg, rng, spec)
    assert perturbed.copula_nu == cfg.copula_nu
    for ps, cs in zip(perturbed.scenarios, cfg.scenarios):
        assert ps.frequency.lambda_annual == pytest.approx(cs.frequency.lambda_annual)
        assert ps.severity.scale == pytest.approx(cs.severity.scale)
        assert ps.copula_loading == pytest.approx(cs.copula_loading)


def test_run_uncertainty_analysis_bands():
    cfg = _config()
    spec = UncertaintySpec(
        iterations=15, seed=7, lambda_cv=0.2, severity_scale_cv=0.2,
        severity_sigma_cv=0.1, loading_sd=0.05, copula_nu_sd=0.5,
    )
    res = run_uncertainty_analysis(cfg, spec=spec, n_years=20_000)
    assert res.n_runs == 15
    # every headline metric has a band with median <= p95 and p5 <= median
    for metric in ("eal", "var_99", "es_99", "p99_5", "p99_9"):
        b = res.bands[metric]
        assert b.p5 <= b.median <= b.p95
        assert np.isfinite(b.median)
    # ES band ordering within the band: median es99 > median var99
    assert res.bands["es_99"].median > res.bands["var_99"].median


def test_run_uncertainty_bands_wider_for_tail_metrics():
    """The tail measures (ES99/P99.9) should have WIDER relative bands than EAL."""
    cfg = _config()
    spec = UncertaintySpec(
        iterations=15, seed=7, lambda_cv=0.25, severity_scale_cv=0.25,
        severity_sigma_cv=0.12, loading_sd=0.05, copula_nu_sd=0.5,
    )
    res = run_uncertainty_analysis(cfg, spec=spec, n_years=20_000)
    rel_eal = res.bands["eal"].width / res.bands["eal"].median
    rel_es = res.bands["es_99"].width / res.bands["es_99"].median
    rel_p999 = res.bands["p99_9"].width / res.bands["p99_9"].median
    assert rel_es > rel_eal
    assert rel_p999 > rel_eal


def test_run_uncertainty_seeded_reproducible():
    """Same seed -> identical band medians (audit requirement)."""
    cfg = _config()
    spec = UncertaintySpec(iterations=8, seed=99, lambda_cv=0.2, severity_scale_cv=0.2,
                           severity_sigma_cv=0.1, loading_sd=0.05, copula_nu_sd=0.5)
    a = run_uncertainty_analysis(cfg, spec=spec, n_years=15_000)
    b = run_uncertainty_analysis(cfg, spec=spec, n_years=15_000)
    assert a.bands["eal"].median == b.bands["eal"].median
    assert a.bands["es_99"].median == b.bands["es_99"].median


def test_lambda_bands_reflect_perturbation():
    """Lambda bands should span the base lambda (median near base)."""
    cfg = _config()
    spec = UncertaintySpec(iterations=10, seed=3, lambda_cv=0.3, severity_scale_cv=0.0,
                           severity_sigma_cv=0.0, loading_sd=0.0, copula_nu_sd=0.0)
    res = run_uncertainty_analysis(cfg, spec=spec, n_years=10_000)
    base = next(s.frequency.lambda_annual for s in cfg.scenarios if s.key == "breach")
    band = res.lambda_bands["breach"]
    assert band.p5 <= base <= band.p95
    # with 0.3 CV the band should be meaningfully wide
    assert band.p95 > base * 1.2
