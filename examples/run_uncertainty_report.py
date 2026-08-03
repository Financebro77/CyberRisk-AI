"""Phase 2 CFO report: credibility + parameter-uncertainty on a worked firm.

Shows how a Marsh consultant would present the model to a CFO:

  1. Take the firm's own incident history and blend it with the industry
     baseline (credibility) -- show the BEFORE/AFTER table.
  2. Run the model 200 times with perturbed assumptions (uncertainty) and
     show the central estimate plus a 90% band for each headline metric.
  3. Add a systemic stress (nu=2, the heaviest allowed tail) to show how
     the P99.9 / ES99 move if the world gets worse.
  4. Print the plain-English summary a CFO would read.

Usage:  python examples/run_uncertainty_report.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from cyberrisk.calibration import load_config
from cyberrisk.credibility import FirmExperience, apply_credibility
from cyberrisk.metrics import compute_metrics
from cyberrisk.simulation import simulate
from cyberrisk.uncertainty import (
    UncertaintySpec,
    load_uncertainty_spec,
    run_uncertainty_analysis,
)

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fmt_usd(x: float) -> str:
    if x >= 1e9:
        return f"${x/1e9:,.2f}B"
    if x >= 1e6:
        return f"${x/1e6:,.2f}M"
    if x >= 1e3:
        return f"${x/1e3:,.1f}K"
    return f"${x:,.0f}"


def sec(title: str) -> None:
    # ASCII-only header (Windows console safe)
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main() -> None:
    # --- 1. Load config + apply credibility --------------------------------
    cfg = load_config(
        ROOT / "config" / "scenarios.yaml",
        ROOT / "config" / "simulation_config.yaml",
    )

    firm_history = [
        FirmExperience(scenario_key="breach", incidents=1, years=5),
        FirmExperience(scenario_key="ransomware", incidents=2, years=5),
        FirmExperience(scenario_key="bec", incidents=1, years=5),
        FirmExperience(scenario_key="cloud_outage", incidents=0, years=5),
    ]
    cred = apply_credibility(cfg, firm_history, k=3)

    sec("1. CREDIBILITY - YOUR HISTORY vs THE INDUSTRY BASELINE")
    print("   (K = 3 years: at 3 years of history, your data and the "
          "industry baseline each count 50%)")
    print(f"{'scenario':<14} {'baseline lambda':>10} {'your lambda':>8} {'cred Z':>7} {'credible lambda':>10}")
    for s in cred.config.scenarios:
        if s.key in {e.scenario_key for e in firm_history}:
            ann = s.annotation
            print(
                f"{s.key:<14} {ann['lambda_baseline']:>10} {ann['lambda_firm_observed']:>8} "
                f"{ann['credibility_weight']:>7} {ann['lambda_credible']:>10}"
            )
    print("\n   Plain English:")
    for note in cred.notes:
        print(f"   * {note}")

    # --- 2. Uncertainty on the credibility-adjusted model ------------------
    spec = load_uncertainty_spec()
    print(f"\n   Running {spec.iterations} perturbed simulations "
          f"({spec.iterations} x {cfg.default_years:,} years)...")
    uncer = run_uncertainty_analysis(cred.config, spec=spec, n_years=cfg.default_years)

    sec("2. PARAMETER UNCERTAINTY - CENTRAL ESTIMATE + 90% BAND")
    print("   'We varied each assumption within a plausible range and re-ran "
          "the model.  The band is the middle 90% of outcomes.'")
    print(f"{'metric':<8} {'central':>12} {'5th':>12} {'95th':>12} {'width':>12}")
    for metric in ("eal", "var_99", "es_99", "p99_5", "p99_9"):
        b = uncer.bands[metric]
        print(
            f"{metric:<8} {fmt_usd(b.median):>12} {fmt_usd(b.p5):>12} "
            f"{fmt_usd(b.p95):>12} {fmt_usd(b.width):>12}"
        )

    # --- 3. Systemic stress (nu = 2, heaviest allowed t-tail) ---------------
    sec("3. SYSTEMIC STRESS - IF TAIL DEPENDENCE GETS WORSE (nu = 2)")
    stress_cfg = cred.config.model_copy(update={"copula_nu": 2.0})
    m_stress = compute_metrics(simulate(stress_cfg, n_years=cfg.default_years, dependence="dependent"))
    m_base = compute_metrics(simulate(cred.config, n_years=cfg.default_years, dependence="dependent"))
    print(f"{'metric':<10} {'central':>12} {'systemic':>12} {'change':>10}")
    for metric, label in (("es_99", "ES99"), ("p99_5", "P99.5"), ("p99_9", "P99.9")):
        base = getattr(m_base, metric)
        stress = getattr(m_stress, metric)
        pct = (stress / base - 1) * 100
        print(f"{label:<10} {fmt_usd(base):>12} {fmt_usd(stress):>12} {pct:>+9.1f}%")

    # --- 4. Chart ----------------------------------------------------------
    sec("4. UNCERTAINTY BAND CHART")
    metrics = ["EAL", "VaR99", "ES99", "P99.5", "P99.9"]
    keys = ["eal", "var_99", "es_99", "p99_5", "p99_9"]
    medians = [uncer.bands[k].median for k in keys]
    p5s = [uncer.bands[k].p5 for k in keys]
    p95s = [uncer.bands[k].p95 for k in keys]

    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(metrics))
    ax.errorbar(
        medians, y, xerr=[np.array(medians) - np.array(p5s), np.array(p95s) - np.array(medians)],
        fmt="o", color="#c0392b", ecolor="#7f8c8d", capsize=4, ms=7,
    )
    ax.set_yticks(y)
    ax.set_yticklabels(metrics)
    ax.set_xlabel("Annual loss (US$ millions)")
    ax.set_title("Headline cyber risk measures - central estimate & 90% band")
    ax.grid(True, axis="x", alpha=0.3)
    for yy, med in zip(y, medians):
        ax.annotate(fmt_usd(med), (med, yy), textcoords="offset points", xytext=(6, 0), va="center")
    fig.tight_layout()
    chart = OUT_DIR / "uncertainty_bands.png"
    fig.savefig(chart, dpi=150)
    plt.close(fig)
    print(f"   Chart written: {chart.name}")

    # --- 5. Plain-English summary ------------------------------------------
    sec("5. SUMMARY (WHAT A CONSULTANT WOULD SAY)")
    e = uncer.bands["eal"]
    es = uncer.bands["es_99"]
    print(f"   * Your expected annual cyber loss is around {fmt_usd(e.median)}, "
          f"but could plausibly be between {fmt_usd(e.p5)} and {fmt_usd(e.p95)}.")
    print(f"   * In a 1-in-100-year stress, we'd expect to lose about "
          f"{fmt_usd(es.median)} (range {fmt_usd(es.p5)} - {fmt_usd(es.p95)}).")
    print(f"   * If cyber events become more correlated across scenarios "
          f"(systemic stress), ES99 rises {100*(m_stress.es_99/m_base.es_99-1):+.0f}% "
          f"to {fmt_usd(m_stress.es_99)}.")
    print(f"   * A reasonable limit conversation starts from P99.5 "
          f"{fmt_usd(uncer.bands['p99_5'].median)} and stresses it.")


if __name__ == "__main__":
    main()
