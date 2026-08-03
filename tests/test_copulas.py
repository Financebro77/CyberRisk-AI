"""Copula tests: marginal uniformity, correlation, independence, tail dependence."""

import numpy as np

from cyberrisk.copulas import (
    copula_uniforms,
    dependent_uniforms,
    independent_uniforms,
    student_t_uniforms,
)


def test_marginals_uniform():
    loadings = np.array([0.5, -0.2, 0.8])
    u = dependent_uniforms(loadings, 200_000, np.random.default_rng(0))
    assert u.shape == (3, 200_000)
    for row in u:
        # mean ~0.5, values in (0,1)
        assert np.isclose(row.mean(), 0.5, atol=0.01)
        assert row.min() > 0.0 and row.max() < 1.0


def test_positive_loading_positive_correlation():
    rng = np.random.default_rng(1)
    u = dependent_uniforms(np.array([0.8, 0.8]), 100_000, rng)
    # Spearman rank correlation on uniform scale should be strongly positive
    from scipy.stats import rankdata

    rho = np.corrcoef(rankdata(u[0]), rankdata(u[1]))[0, 1]
    assert rho > 0.55


def test_opposite_loadings_negative_correlation():
    rng = np.random.default_rng(2)
    u = dependent_uniforms(np.array([0.8, -0.8]), 100_000, rng)
    from scipy.stats import rankdata

    rho = np.corrcoef(rankdata(u[0]), rankdata(u[1]))[0, 1]
    assert rho < -0.55


def test_independent_uniforms_uncorrelated():
    rng = np.random.default_rng(3)
    u = independent_uniforms(np.array([0.8, 0.8]), 200_000, rng)
    from scipy.stats import rankdata

    rho = np.corrcoef(rankdata(u[0]), rankdata(u[1]))[0, 1]
    assert abs(rho) < 0.02


# ---------------------------------------------------------------- Student-t copula
def test_student_t_marginals_uniform():
    u = student_t_uniforms(np.array([0.5, -0.2, 0.8]), 200_000, np.random.default_rng(4), nu=5)
    assert u.shape == (3, 200_000)
    for row in u:
        assert np.isclose(row.mean(), 0.5, atol=0.01)
        assert row.min() > 0.0 and row.max() < 1.0


def test_student_t_positive_correlation():
    u = student_t_uniforms(np.array([0.8, 0.8]), 100_000, np.random.default_rng(5), nu=5)
    from scipy.stats import rankdata

    rho = np.corrcoef(rankdata(u[0]), rankdata(u[1]))[0, 1]
    assert rho > 0.55


def test_student_t_has_upper_tail_dependence():
    """The t-copula must show STRONGER upper-tail dependence than Gaussian.

    At equal rank correlation, chi(q) = P(U2>q | U1>q) must be higher for
    the t-copula -- this is the whole point of the Phase-1 improvement.
    """
    rng = np.random.default_rng(6)
    loadings = np.array([0.7, 0.7])
    n = 2_000_000
    ug = dependent_uniforms(loadings, n, rng)
    ut = student_t_uniforms(loadings, n, rng, nu=5)

    def chi(u, q=0.99):
        m1 = u[0] > q
        m2 = u[1] > q
        return np.mean(m2 & m1) / np.mean(m1)

    chi_g = chi(ug)
    chi_t = chi(ut)
    assert chi_t > chi_g
    assert chi_t > 0.20  # t-copula at nu=5, rho=0.7
    assert chi_g < chi_t  # strictly


def test_student_t_reduces_to_gaussian_high_nu():
    """As nu -> large, the t-copula should approach the Gaussian copula.

    Rank correlation should converge; at nu=100 the difference is small.
    """
    rng = np.random.default_rng(7)
    loadings = np.array([0.8, 0.8])
    n = 200_000
    ug = dependent_uniforms(loadings, n, rng)
    ut_hi = student_t_uniforms(loadings, n, rng, nu=100)
    from scipy.stats import rankdata

    rho_g = np.corrcoef(rankdata(ug[0]), rankdata(ug[1]))[0, 1]
    rho_t = np.corrcoef(rankdata(ut_hi[0]), rankdata(ut_hi[1]))[0, 1]
    assert abs(rho_t - rho_g) < 0.05


def test_copula_uniforms_dispatch():
    rng = np.random.default_rng(8)
    loadings = np.array([0.5, 0.5])
    g = copula_uniforms(loadings, 10_000, rng, model="gaussian")
    t = copula_uniforms(loadings, 10_000, rng, model="student_t", nu=5)
    assert g.shape == (2, 10_000)
    assert t.shape == (2, 10_000)
    assert np.isclose(g.mean(), 0.5, atol=0.02)
    assert np.isclose(t.mean(), 0.5, atol=0.02)
