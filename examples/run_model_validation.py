"""Actuarial model validation harness for the cyber loss simulation engine.

Runs the validation protocol and prints a structured summary:

    A. RNG / distribution tests      (reproducibility, count/severity convergence)
    B. Convergence with iterations    (1k / 10k / 100k / 500k years)
    C. Risk-measure ordering          (EAL < VaR < ES at 95% and 99%)
    D. Loss distribution shape        (heavy tail, Pareto concentration)
    E. Extreme event / tail analysis  (Hill estimator, GPD fit, LEC, max)
    F. Dependence                     (dependent vs independent tail)

Every number printed is produced live by the engine on the current config.
Usage:  python examples/run_model_validation.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics, expected_shortfall
from cyberrisk.simulation import simulate

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "output" / "validation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fmt_usd(x: float) -> str:
    if x >= 1e9:
        return f"${x/1e9:,.2f}B"
    if x >= 1e6:
        return f"${x/1e6:,.2f}M"
    if x >= 1e3:
        return f"${x/1e3:,.1f}K"
    return f"${x:,.0f}"


def sec(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


# ---------------------------------------------------------------------------
# A. RNG / distribution tests
# ---------------------------------------------------------------------------


def test_reproducibility(config) -> bool:
    sec("A. RANDOM NUMBER GENERATION & DISTRIBUTIONS")
    a = simulate(config, n_years=50_000)
    b = simulate(config, n_years=50_000)
    identical = np.array_equal(a.total_losses, b.total_losses)
    print(f"A1  Same seed twice -> bit-identical loss array     : {'PASS' if identical else 'FAIL'}")

    # chunk-size independence
    cfg_big = config.model_copy(update={"chunk_size": 50_000})
    chunked = simulate(cfg_big, n_years=50_000)
    chunk_ok = np.array_equal(a.total_losses, chunked.total_losses)
    print(f"A2  Same seed, different chunk_size -> identical     : {'PASS' if chunk_ok else 'FAIL'}")

    # different seed -> different stream
    c = simulate(config, n_years=50_000, seed=999)
    diff_seed = not np.array_equal(a.total_losses, c.total_losses)
    print(f"A3  Different seed -> different stream               : {'PASS' if diff_seed else 'FAIL'}")

    # marginal law check: simulated count mean must converge to lambda
    from cyberrisk.frequency import count_distributions

    lambdas = [s.frequency.lambda_annual for s in config.scenarios]
    ok_marginal = True
    print("A4  Simulated count mean vs calibrated lambda (200k draws each):")
    for i, s in enumerate(config.scenarios):
        dists, _, _ = count_distributions([s.frequency])
        rng = np.random.default_rng(10 + i)
        draws = np.asarray(dists[0].rvs(size=200_000, random_state=rng), dtype=np.float64)
        err = abs(draws.mean() - lambdas[i]) / lambdas[i]
        status = "PASS" if err < 0.02 else "FAIL"
        ok_marginal = ok_marginal and status == "PASS"
        print(f"      {s.key:<14} lambda={lambdas[i]:<5} sim mean={draws.mean():.4f} "
              f"rel err={err:.3%}  {status}")

    return identical and chunk_ok and diff_seed and ok_marginal


# ---------------------------------------------------------------------------
# B. Convergence with iterations
# ---------------------------------------------------------------------------


def run_convergence(config) -> dict:
    sec("B. CONVERGENCE WITH SIMULATION ITERATIONS")
    n_sizes = [1_000, 10_000, 100_000, 500_000]
    table = []
    for n in n_sizes:
        r = simulate(config, n_years=n, seed=config.seed)
        m = compute_metrics(r)
        table.append(
            {
                "n": n,
                "eal": m.eal,
                "var_99": m.var_99,
                "es_99": m.es_99,
                "p99_5": m.p99_5,
                "p99_9": m.p99_9,
                "max": m.max_single_year,
                "p0": m.prob_zero_loss,
            }
        )

    print(
        f"{'years':>9} {'EAL':>11} {'VaR99':>11} {'ES99':>11} "
        f"{'P99.5':>11} {'P99.9':>11} {'P(0)':>7}"
    )
    for row in table:
        print(
            f"{row['n']:>9,} {fmt_usd(row['eal']):>11} {fmt_usd(row['var_99']):>11} "
            f"{fmt_usd(row['es_99']):>11} {fmt_usd(row['p99_5']):>11} "
            f"{fmt_usd(row['p99_9']):>11} {row['p0']*100:>6.1f}%"
        )

    # stability: relative change in ES99 and P99.9 between largest runs
    if len(table) >= 2:
        es_prev, es_cur = table[-2]["es_99"], table[-1]["es_99"]
        rel_es = abs(es_cur - es_prev) / es_prev
        p_prev, p_cur = table[-2]["p99_9"], table[-1]["p99_9"]
        rel_p = abs(p_cur - p_prev) / p_prev
        print(f"\nB.1  |ES99(500k)-ES99(100k)|/ES99(100k) = {rel_es:.2%} "
              f"({'CONVERGED' if rel_es < 0.05 else 'NOT CONVERGED'})")
        print(f"     |P99.9(500k)-P99.9(100k)|/P99.9(100k) = {rel_p:.2%} "
              f"({'CONVERGED' if rel_p < 0.10 else 'NOT CONVERGED'})")

    # bootstrap SE of the headline measures from the largest run
    from cyberrisk.metrics import bootstrap_se

    r = simulate(config, n_years=500_000, seed=config.seed)
    se = bootstrap_se(r.total_losses, n_boot=50, rng=np.random.default_rng(2024))
    print(
        f"\nB.2  Bootstrap SE (500k years, 50 resamples):\n"
        f"       EAL {fmt_usd(se.eal)} ({se.eal/r.total_losses.mean():.2%} rel)\n"
        f"       ES99 {fmt_usd(se.es_99)} ({se.es_99/ (r.total_losses[r.total_losses>=np.quantile(r.total_losses,0.99)]).mean():.2%} rel)\n"
        f"       P99.5 {fmt_usd(se.p99_5)} ({se.p99_5/np.quantile(r.total_losses,0.995):.2%} rel)\n"
        f"       P99.9 {fmt_usd(se.p99_9)} ({se.p99_9/np.quantile(r.total_losses,0.999):.2%} rel)"
    )
    return table[-1]


# ---------------------------------------------------------------------------
# C. Risk-measure ordering
# ---------------------------------------------------------------------------


def test_ordering(config, ref: dict) -> bool:
    sec("C. RISK-MEASURE ORDERING (EAL < VaR < ES)")
    ok = True
    # Use the largest-run metrics
    r = simulate(config, n_years=500_000, seed=config.seed)
    m = compute_metrics(r)
    checks = [
        ("EAL < VaR95", m.eal < m.var_95),
        ("EAL < ES95", m.eal < m.es_95),
        ("VaR95 < ES95", m.var_95 < m.es_95),
        ("EAL < VaR99", m.eal < m.var_99),
        ("VaR99 < ES99", m.var_99 < m.es_99),
        ("VaR95 < VaR99", m.var_95 < m.var_99),
        ("ES95 < ES99", m.es_95 < m.es_99),
        ("ES99 < max (sample bound)", m.es_99 < m.max_single_year),
    ]
    for name, passed in checks:
        ok = ok and passed
        print(f"C    {name:<28}: {'PASS' if passed else 'FAIL'}")
    return ok


# ---------------------------------------------------------------------------
# D. Loss distribution shape
# ---------------------------------------------------------------------------


def test_distribution_shape(config) -> None:
    sec("D. LOSS DISTRIBUTION SHAPE")
    r = simulate(config, n_years=500_000, seed=config.seed)
    losses = r.total_losses
    m = compute_metrics(r)
    mean = losses.mean()
    median = np.median(losses)
    print(f"D    Mean  = {fmt_usd(mean)}")
    print(f"D    Median= {fmt_usd(median)}")
    print(f"D    Mean/Median = {mean/median:.2f}  (heavy right skew when >> 1)")

    # Pareto concentration: top k% of years carry share of total loss
    order = np.argsort(losses)
    for k in (0.01, 0.05, 0.10):
        share = losses[order[-int(k * len(losses)):]].sum() / losses.sum()
        print(f"D    Top {k*100:.0f}% of years carry {share*100:.1f}% of total loss")

    # zero-loss mass
    print(f"D    P(no loss) = {m.prob_zero_loss*100:.1f}%")

    # histogram of log10 loss
    fig, ax = plt.subplots(figsize=(8, 4.5))
    pos = losses[losses > 0]
    ax.hist(np.log10(pos), bins=60, color="#2980b9", alpha=0.8)
    ax.set_xlabel("log10(annual loss USD)")
    ax.set_ylabel("count")
    ax.set_title("Annual aggregate loss distribution (log scale), 500k years")
    path = OUT_DIR / "loss_distribution_log.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"D    Histogram written: {path.name}")


# ---------------------------------------------------------------------------
# E. Extreme event / tail analysis
# ---------------------------------------------------------------------------


def hill_estimator(sorted_tail: np.ndarray, k: int) -> float:
    """Hill tail-index estimate xi from the top-k order statistics.

    Standard Hill: xi = (1/k) * sum_{i=1..k} log(x_(n-i+1) / x_(n-k)).
    Here `sorted_tail` is ascending; the top-k are the last k entries.
    Returns the tail index xi (alpha = 1/xi).  Uses the classical estimator
    (average of log ratios to the k-th largest).
    """
    # reference = the order statistic just below the top-k block
    reference = sorted_tail[-k - 1]
    top = sorted_tail[-k:]
    xi = (np.log(top) - np.log(reference)).mean()
    return float(max(xi, 1e-12))


def test_extreme_events(config) -> None:
    sec("E. EXTREME EVENT / TAIL BEHAVIOUR")
    r = simulate(config, n_years=500_000, seed=config.seed)
    losses = r.total_losses
    m = compute_metrics(r)

    # Return-period PML basis (Phase-1 replacement for the sample max)
    print(f"E    Max single-year loss (500k years): {fmt_usd(m.max_single_year)}  [sample artifact, NOT a PML]")
    print(f"E    Return-period PML:")
    print(f"E      P99.0 (1-in-100 yr)  : {fmt_usd(m.p99_0)}")
    print(f"E      P99.5 (1-in-200 yr)  : {fmt_usd(m.p99_5)}")
    print(f"E      P99.9 (1-in-1000 yr) : {fmt_usd(m.p99_9)}")
    print(f"E    ES99 / EAL = {m.es_99/m.eal:.1f}x  (tail mean as multiple of mean)")

    # Hill tail index from top 2% of losses
    tail = np.sort(losses[losses > 0])
    k = int(0.02 * len(tail))
    xi = hill_estimator(tail, k)
    print(f"E    Hill index (top 2%): alpha = {1/xi:.2f} (xi = {xi:.2f})")
    print(f"E      -> alpha < 2 implies infinite variance / very heavy tail")
    print(f"E      -> alpha ~ 2-4 implies heavy but finite-var tail")

    # LEC with markers at VaR95/99 and P99.5
    from cyberrisk.metrics import exceedance_curve

    lec = exceedance_curve(losses)
    x, p = lec
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.semilogy(x / 1e6, p, lw=2, color="#c0392b")
    ax.axvline(m.var_95 / 1e6, color="#2980b9", ls="--", lw=1, label="VaR95")
    ax.axvline(m.var_99 / 1e6, color="#27ae60", ls="--", lw=1, label="VaR99")
    ax.axvline(m.p99_5 / 1e6, color="#8e44ad", ls="--", lw=1, label="P99.5 (1-in-200)")
    ax.set_xlabel("Annual loss (US$ millions)")
    ax.set_ylabel("P(Loss >= x)")
    ax.set_title("Loss exceedance curve (log P), 500k years")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    path = OUT_DIR / "loss_exceedance_validation.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"E    LEC written: {path.name}")


# ---------------------------------------------------------------------------
# F. Dependence
# ---------------------------------------------------------------------------


def test_dependence(config) -> None:
    sec("F. DEPENDENCE EFFECT ON TAIL (Gaussian vs Student-t)")

    # F1: dependent vs independent (same copula model)
    dep = simulate(config, n_years=200_000, dependence="dependent")
    ind = simulate(config, n_years=200_000, dependence="independent")
    m_dep = compute_metrics(dep)
    m_ind = compute_metrics(ind)
    print(f"F1   dependent {config.copula_model} vs independent (200k years):")
    print(f"     EAL   {fmt_usd(m_dep.eal)}  | {fmt_usd(m_ind.eal)}")
    print(f"     ES99  {fmt_usd(m_dep.es_99)}  | {fmt_usd(m_ind.es_99)}")
    print(f"     P99.9 {fmt_usd(m_dep.p99_9)}  | {fmt_usd(m_ind.p99_9)}")

    # F2: Student-t vs Gaussian (same loadings, marginal-preserving)
    g_cfg = config.model_copy(update={"copula_model": "gaussian"})
    t_cfg = config.model_copy(update={"copula_model": "student_t", "copula_nu": 5.0})
    m_g = compute_metrics(simulate(g_cfg, n_years=200_000, dependence="dependent"))
    m_t = compute_metrics(simulate(t_cfg, n_years=200_000, dependence="dependent"))
    print(f"\nF2   Student-t(nu=5) vs Gaussian (200k years, same loadings):")
    print(f"     EAL   t {fmt_usd(m_t.eal)}  | g {fmt_usd(m_g.eal)}  "
          f"(ratio {m_t.eal/m_g.eal:.4f})")
    print(f"     ES99  t {fmt_usd(m_t.es_99)}  | g {fmt_usd(m_g.es_99)}  "
          f"(ratio {m_t.es_99/m_g.es_99:.4f})")
    print(f"     P99.9 t {fmt_usd(m_t.p99_9)}  | g {fmt_usd(m_g.p99_9)}  "
          f"(ratio {m_t.p99_9/m_g.p99_9:.4f})")

    # F3: copula-level upper-tail dependence chi(0.99)
    from scipy.stats import rankdata
    from cyberrisk.copulas import dependent_uniforms, student_t_uniforms

    loadings = np.array([s.copula_loading for s in config.scenarios])
    rng = np.random.default_rng(0)
    n = 1_000_000
    ug = dependent_uniforms(loadings, n, rng)
    ut = student_t_uniforms(loadings, n, rng, nu=5)

    def chi(u, q=0.99):
        m1 = u[0] > q
        m2 = u[1] > q
        return np.mean(m2 & m1) / np.mean(m1)

    chi_g = np.mean([chi(ug) for _ in range(1)])
    chi_t = np.mean([chi(ut) for _ in range(1)])
    print(f"\nF3   Copula upper-tail dependence chi(0.99) (same loadings):")
    print(f"     Gaussian {chi_g:.4f}  |  Student-t(nu=5) {chi_t:.4f}  "
          f"(ratio {chi_t/chi_g:.2f}x)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    config = load_config(
        ROOT / "config" / "scenarios.yaml",
        ROOT / "config" / "simulation_config.yaml",
    )
    print(f"Validation config: {len(config.scenarios)} scenarios, "
          f"revenue {fmt_usd(config.firm_revenue_usd)}, seed {config.seed}")
    print(f"Scenario lambdas: {[s.frequency.lambda_annual for s in config.scenarios]}")

    ok_rng = test_reproducibility(config)
    ref = run_convergence(config)
    ok_order = test_ordering(config, ref)
    test_distribution_shape(config)
    test_extreme_events(config)
    test_dependence(config)

    sec("VALIDATION SUMMARY")
    print(f"A  RNG / distributions     : {'PASS' if ok_rng else 'FAIL'}")
    print(f"B  Convergence             : see table (target |ES drift|<5%)")
    print(f"C  EAL < VaR < ES ordering : {'PASS' if ok_order else 'FAIL'}")
    print("D  Shape / E  tail / F dependence : see sections above")
    print(f"F2 Student-t vs Gaussian tail ratios: see F section "
          f"(EAL ~1.00, ES99/P99.9 > 1 expected at deep quantiles)")


if __name__ == "__main__":
    main()
