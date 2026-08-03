"""Phase 1 case study: run the loss engine end-to-end and report the metrics.

Runs a 100k-year Monte Carlo on the benchmark-calibrated scenario config,
prints the headline risk metrics and per-scenario AAL breakdown, plots the
loss exceedance curve (dependent vs independent copula), and demonstrates
a what-if: doubling the breach frequency.

Usage:  python examples/run_case_study.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe (no GUI backend needed)
import matplotlib.pyplot as plt
import numpy as np

from cyberrisk.metrics import compute_metrics
from cyberrisk.simulation import simulate

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "scenarios.yaml"
SIM_CONFIG_PATH = ROOT / "config" / "simulation_config.yaml"
OUT_DIR = ROOT / "data" / "output"


def fmt_usd(x: float) -> str:
    """Compact US$ formatting (1.23M, 456.7K)."""
    if x >= 1e9:
        return f"${x/1e9:,.2f}B"
    if x >= 1e6:
        return f"${x/1e6:,.2f}M"
    if x >= 1e3:
        return f"${x/1e3:,.1f}K"
    return f"${x:,.0f}"


def print_metrics(result, title: str) -> None:
    m = compute_metrics(result)
    print(f"\n=== {title} ===")
    print(f"  Simulated years : {result.years:,}")
    print(f"  EAL             : {fmt_usd(m.eal)}")
    print(f"  VaR 95%         : {fmt_usd(m.var_95)}")
    print(f"  ES   95%        : {fmt_usd(m.es_95)}")
    print(f"  VaR 99%         : {fmt_usd(m.var_99)}")
    print(f"  ES   99%        : {fmt_usd(m.es_99)}")
    print(f"  PML 1-in-250yr  : {fmt_usd(m.pml_250)}")
    print(f"  Max single year : {fmt_usd(m.max_single_year)}")
    print(f"  P(no loss year) : {m.prob_zero_loss*100:.1f}%")
    print("\n  AAL by scenario:")
    for key, aal in sorted(m.aal_by_scenario.items(), key=lambda kv: -kv[1]):
        share = m.scenario_contribution()[key]
        print(f"    {key:<14} {fmt_usd(aal):>12}  ({share*100:4.1f}%)")


def plot_lecs(dep_losses: np.ndarray, ind_losses: np.ndarray) -> str:
    """Loss exceedance curves: dependent vs independent tail. Returns output path."""
    out_path = OUT_DIR / "loss_exceedance_dependent_vs_independent.png"

    def exceedance(losses: np.ndarray, p_min: float = 1e-5) -> tuple[np.ndarray, np.ndarray]:
        """Return (loss_levels, exceedance_prob) from the empirical CDF tail."""
        sorted_l = np.sort(losses)
        n = len(sorted_l)
        p = 1.0 - np.arange(1, n + 1) / n
        keep = p >= p_min
        return sorted_l[keep], p[keep]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for losses, label, color in (
        (dep_losses, "Dependent (one-factor copula)", "#c0392b"),
        (ind_losses, "Independent (counterfactual)", "#2980b9"),
    ):
        x, y = exceedance(losses)
        ax.plot(x / 1e6, y, label=label, color=color, lw=2)
        ax.set_yscale("log")

    ax.set_xlabel("Annual aggregate loss (US$ millions)")
    ax.set_ylabel("P(Loss >= x) per year")
    ax.set_title("Cyber loss exceedance curves\n(100k simulated years, benchmark calibration)")
    ax.axvline(
        np.quantile(dep_losses, 0.99) / 1e6,
        color="#c0392b",
        ls="--",
        lw=1,
        label="VaR 99% (dependent)",
    )
    ax.axhline(0.01, color="gray", ls=":", lw=1)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return str(out_path)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from cyberrisk.calibration import load_config

    config = load_config(CONFIG_PATH, SIM_CONFIG_PATH)
    print(f"Firm revenue: {fmt_usd(config.firm_revenue_usd)}")
    print(f"Scenarios   : {', '.join(config.scenario_keys)}")

    # --- Base case: dependent (realistic) + independent (counterfactual) ----
    dep = simulate(config, n_years=100_000, dependence="dependent")
    ind = simulate(config, n_years=100_000, dependence="independent")

    print_metrics(dep, "Dependent model (copula)")
    print_metrics(ind, "Independent counterfactual")

    lec_path = plot_lecs(dep.total_losses, ind.total_losses)
    print(f"\nLEC chart written to: {lec_path}")

    # --- What-if: double breach frequency ------------------------------------
    import copy

    whatif = copy.deepcopy(config)
    for s in whatif.scenarios:
        if s.key == "breach":
            s.frequency.lambda_annual *= 2.0
            s.annotation["whatif"] = "breach lambda doubled"
    wi = simulate(whatif, n_years=100_000, dependence="dependent")
    m_base = compute_metrics(dep)
    m_wi = compute_metrics(wi)
    print(f"\n=== What-if: breach frequency doubled ===")
    print(f"  EAL: {fmt_usd(m_base.eal)} -> {fmt_usd(m_wi.eal)} "
          f"(+{(m_wi.eal/m_base.eal - 1)*100:.1f}%)")
    print(f"  VaR 99%: {fmt_usd(m_base.var_99)} -> {fmt_usd(m_wi.var_99)}")


if __name__ == "__main__":
    main()
