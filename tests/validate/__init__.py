"""Quantitative validation suite for the CyberRiskAI modelling engine.

Each module tests insurance-relevant properties:
    test_scoring_model      monotonicity, category bands, weight invariance
    test_calibration_model  parameter validation, revenue scaling, benchmark translation
    test_frequency_model    convergence to Poisson/NegBin laws
    test_severity_model     heavy-tail behaviour, analytic moments
    test_simulation_model   EAL vs analytic, score/loss monotonicity, reproducibility
    test_metrics_model      ES>=VaR, ordering, subadditivity, reconciliation
    test_policy_model       conservation, no-arbitrage, monotonicity of terms
    test_integration        full pipeline: score -> simulation -> policy -> metrics
"""

from cyberrisk.scoring import CompanyProfile


def make_profile(factor_scores: dict[str, float], name: str = "TestCo") -> CompanyProfile:
    """Build a CompanyProfile from a factor->score dict (shared helper)."""
    return CompanyProfile(firm_name=name, factor_scores=dict(factor_scores))

