"""Dependence structure for scenario frequencies: one-factor Gaussian copula.

The model couples the *within-year* event counts of different scenarios
with a one-factor Gaussian copula: a single latent market factor M drives
every scenario, and scenario i responds to it with loading rho_i.  This
means a bad "cyber year" (M high) tends to push several scenarios high
simultaneously -- ransomware, supply-chain and cloud outages are positively
correlated in reality, and ignoring that correlation materially understates
the tail of the annual aggregate loss distribution.

A single factor is deliberately chosen for Phase 1: it is the smallest
dependence structure that still generates realistic tail dependence, needs
only N loadings to calibrate, and is trivial to seed.  The output of the
engine is exactly the (n_scenarios, n_years) uniform grid, so any copula
(Student-t, empirical rank) can be substituted later without touching the
simulation engine.

Note on the sign of dependence effects: a positive common factor raises the
probability that a *quiet* latent year pushes every scenario quiet at once,
so P(no loss year) is higher under the dependent model than under the
independent counterfactual, while the annual-loss tail (VaR/ES) is also
heavier.  Both effects are genuine factor-copula behaviour; the marginal
count law of every scenario is unaffected (exactly Poisson / NegBin).
"""

from __future__ import annotations

import numpy as np
from scipy.special import erf
from scipy.stats import t as student_t

from cyberrisk.calibration import ModelConfig

# Copula models supported by the engine.  "gaussian" is the Phase-1 default;
# "student_t" adds genuine upper-tail dependence (the Phase-1 improvement).
CopulaModel = str  # "gaussian" | "student_t"

# Student-t copula degrees of freedom (config.copula_nu).  nu=5 is the default
# recommendation from the validation report; nu -> inf recovers the Gaussian.
DEFAULT_NU = 5.0


def student_t_uniforms(
    loadings: np.ndarray,
    n_years: int,
    rng: np.random.Generator,
    nu: float = DEFAULT_NU,
) -> np.ndarray:
    """Draw a (n_scenarios, n_years) grid of t-copula-coupled uniforms.

    Uses the FACTOR FORM of the multivariate Student-t: draw a shared factor
    chi-square variate W ~ chi2(nu), then condition the one-factor Gaussian
    construction on it:

        Z_i = [ sqrt(1-rho_i^2) * eps_i + rho_i * M ] / sqrt(W / nu)

    Applying the Student-t CDF (scipy.stats.t.cdf) to each Z_i maps to
    U(0,1) with exact uniform marginals.  This factor form:
      * keeps the shared-market-factor interpretation of the Gaussian model;
      * is exact for the factor loadings (no matrix decomposition needed);
      * recovers the Gaussian copula in the limit nu -> inf (the ratio
        converges to a standard normal).

    Unlike the Gaussian copula, the t-copula has non-zero UPPER tail
    dependence (lambda_U > 0 for finite nu), so it can represent
    contagion-correlated cyber extremes (ransomware campaigns, supply-chain
    attacks, shared clouds) that the Gaussian model structurally cannot.
    """
    loadings = np.asarray(loadings, dtype=np.float64)
    n_scenarios = loadings.size

    # Shared chi-square factor: W ~ chi2(nu), one per year (column).
    w = rng.chisquare(df=nu, size=(1, n_years))
    # Gaussian construction (market factor + idiosyncratic), as in the base model.
    market = rng.standard_normal(size=(1, n_years))
    idiosyncratic = rng.standard_normal(size=(n_scenarios, n_years))
    z_gauss = (
        np.sqrt(np.clip(1.0 - loadings[:, None] ** 2, 0.0, 1.0)) * idiosyncratic
        + loadings[:, None] * market
    )
    # Scale by sqrt(nu / W) -> multivariate-t marginals with nu d.o.f.
    z = z_gauss * np.sqrt(nu / w)
    # Student-t CDF -> exact U(0,1) marginals.
    return student_t.cdf(z, df=nu)


def copula_uniforms(
    loadings: np.ndarray,
    n_years: int,
    rng: np.random.Generator,
    model: CopulaModel = "gaussian",
    nu: float | None = None,
) -> np.ndarray:
    """Dispatch to the copula uniform generator for the requested model.

    `model` is "gaussian" (default) or "student_t".  `nu` is the Student-t
    degrees of freedom (defaults to config.copula_nu via DEFAULT_NU).  Both
    generators return a (n_scenarios, n_years) uniform grid with exact
    uniform marginals and the same factor-loading structure, so the rest of
    the engine is agnostic to which copula is in force.
    """
    if model == "student_t":
        return student_t_uniforms(loadings, n_years, rng, nu=DEFAULT_NU if nu is None else nu)
    if model == "gaussian":
        return dependent_uniforms(loadings, n_years, rng)
    raise ValueError(f"unknown copula model: {model!r}")


def dependent_uniforms(
    loadings: np.ndarray,
    n_years: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw a (n_scenarios, n_years) grid of copula-coupled uniforms.

    Z_i = sqrt(1 - rho_i^2) * eps_i + rho_i * M
    where M, eps_i are i.i.d. standard normals.  Applying the standard
    normal CDF maps each Z_i column-wise to U(0,1), so each scenario keeps
    exactly its marginal U(0,1) law while gaining pairwise dependence.

    Pairwise Pearson correlation on the underlying normal scale is
    rho_i * rho_j (positive for same-sign loadings).  This is converted to
    rank correlation on the uniform scale, which the inverse-transform
    step in `frequency.rvs_counts` preserves.
    """
    loadings = np.asarray(loadings, dtype=np.float64)
    n_scenarios = loadings.size

    market = rng.standard_normal(size=(1, n_years))
    idiosyncratic = rng.standard_normal(size=(n_scenarios, n_years))
    z = (
        np.sqrt(np.clip(1.0 - loadings[:, None] ** 2, 0.0, 1.0)) * idiosyncratic
        + loadings[:, None] * market
    )
    # erf-based normal CDF: precise to machine epsilon
    uniforms = 0.5 * (1.0 + erf(z / np.sqrt(2.0)))
    return uniforms


def independent_uniforms(
    loadings: np.ndarray,
    n_years: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw a (n_scenarios, n_years) grid of independent U(0,1) draws.

    Used for the independence counterfactual (all loadings forced to zero)
    so the effect of dependence on the tail can be quantified directly.
    """
    return rng.random(size=(loadings.size, n_years))


def build_loadings(config: ModelConfig) -> np.ndarray:
    """Extract per-scenario copula loadings in config order."""
    return np.array([s.copula_loading for s in config.scenarios], dtype=np.float64)
