"""Cyber risk loss engine: scenario frequency-severity Monte Carlo, VaR/ES metrics.

Public entry points:
    load_config        -> ModelConfig  (from YAML)
    simulate           -> SimulationResult  (aggregate losses + optional events)
    compute_metrics    -> RiskMetrics  (EAL / VaR / ES / LEC)
    dependent_losses   -> np.ndarray (one-factor copula aggregate losses per year)
"""

from cyberrisk.calibration import (
    FrequencySpec,
    SeveritySpec,
    Scenario,
    ModelConfig,
    load_config,
)
from cyberrisk.copulas import (
    copula_uniforms,
    dependent_uniforms,
    independent_uniforms,
    student_t_uniforms,
)
from cyberrisk.credibility import (
    FirmExperience,
    CredibilityResult,
    apply_credibility,
    blend_lambda,
    credibility_weight,
)
from cyberrisk.uncertainty import (
    UncertaintySpec,
    UncertaintyBand,
    UncertaintyResult,
    load_uncertainty_spec,
    run_uncertainty_analysis,
    central_estimate,
)
from cyberrisk.frequency import count_distributions, rvs_counts
from cyberrisk.metrics import BootstrapSE, bootstrap_se, compute_metrics
from cyberrisk.severity import severity_distributions, rvs_severities
from cyberrisk.simulation import SimulationResult, simulate

__version__ = "0.1.0"

__all__ = [
    "FrequencySpec",
    "SeveritySpec",
    "Scenario",
    "ModelConfig",
    "load_config",
    "independent_uniforms",
    "dependent_uniforms",
    "student_t_uniforms",
    "copula_uniforms",
    "FirmExperience",
    "CredibilityResult",
    "apply_credibility",
    "blend_lambda",
    "credibility_weight",
    "UncertaintySpec",
    "UncertaintyBand",
    "UncertaintyResult",
    "load_uncertainty_spec",
    "run_uncertainty_analysis",
    "central_estimate",
    "count_distributions",
    "rvs_counts",
    "severity_distributions",
    "rvs_severities",
    "simulate",
    "SimulationResult",
    "compute_metrics",
    "bootstrap_se",
    "BootstrapSE",
]
