"""Shared fixtures for the CyberRiskAI validation suite.

Keeps every test module DRY: repo paths, a realistic multi-scenario config,
a minimal single-scenario config (fast), prebuilt scoring weights, profile
helpers, and the full benchmark set.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cyberrisk.calibration import (
    FrequencySpec,
    ModelConfig,
    Scenario,
    SeveritySpec,
    load_config,
)
from cyberrisk.scoring import CompanyProfile, load_scoring_weights

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO


@pytest.fixture(scope="session")
def weights():
    """Alias for scoring_weights (shorter name for test modules)."""
    return load_scoring_weights(REPO / "config" / "scoring_weights.yaml")


@pytest.fixture(scope="session")
def config() -> ModelConfig:
    """The realistic 7-scenario calibration used in production runs."""
    return load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )


@pytest.fixture(scope="session")
def scoring_weights():
    return load_scoring_weights(REPO / "config" / "scoring_weights.yaml")


def _single_scenario_config(
    lam: float,
    scale: float = 100_000.0,
    mu: float = 0.4,
    sigma: float = 0.9,
    loading: float = 0.0,
    revenue_exp: float = 0.0,
) -> ModelConfig:
    """Deterministic single-scenario config for fast analytic checks."""
    return ModelConfig(
        firm_revenue_usd=1_000_000_000.0,
        revenue_reference_usd=1_000_000_000.0,
        scenarios=[
            Scenario(
                key="breach",
                name="breach",
                frequency=FrequencySpec(model="poisson", lambda_annual=lam),
                severity=SeveritySpec(model="lognormal", scale=scale, mu=mu, sigma=sigma),
                copula_loading=loading,
                revenue_exponent=revenue_exp,
            )
        ],
        default_years=50_000,
        chunk_size=20_000,
        seed=20240817,
        tail_quantile=0.99,
    )


@pytest.fixture
def single_config() -> ModelConfig:
    """Fast single-scenario config with known analytic EAL."""
    return _single_scenario_config(lam=0.8, scale=100_000.0, mu=0.4, sigma=0.9)


def make_profile(factor_scores: dict[str, float], name: str = "TestCo") -> CompanyProfile:
    """Helper: build a CompanyProfile from a factor->score dict."""
    return CompanyProfile(firm_name=name, factor_scores=dict(factor_scores))


@pytest.fixture
def make_profile_fixture():
    """Fixture exposing make_profile (usable in test signatures)."""
    return make_profile


@pytest.fixture(scope="session")
def benchmark_set():
    from cyberrisk.data.loaders import load_benchmarks

    return load_benchmarks(REPO / "config" / "calibration_benchmarks.csv")


@pytest.fixture(scope="session")
def all_low_profile(scoring_weights) -> dict[str, float]:
    """Best-case (lowest risk) factor scores from the configured evidence scales."""
    return {
        f.key: min(f.evidence_scale.values())
        for d in scoring_weights.domains
        for f in d.factors
    }


@pytest.fixture(scope="session")
def all_high_profile(scoring_weights) -> dict[str, float]:
    """Worst-case (highest risk) factor scores."""
    return {
        f.key: max(f.evidence_scale.values())
        for d in scoring_weights.domains
        for f in d.factors
    }


@pytest.fixture(scope="session")
def neutral_profile(scoring_weights) -> dict[str, float]:
    """Every factor at the midpoint of its evidence scale -> near-50 composite."""
    return {
        f.key: np.mean(list(f.evidence_scale.values()))
        for d in scoring_weights.domains
        for f in d.factors
    }
