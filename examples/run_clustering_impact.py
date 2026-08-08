"""Phase 3 CFO impact report: burstiness + catastrophe years.

Shows how the Phase-3 features move the numbers, in plain English:

  1. BURSTINESS (negative binomial): incidents aren't perfectly regular.
     The dispersion (Var/Mean) per scenario and how much the tail lifts.
  2. CATASTROPHE YEARS (event clustering): ~1 year in 20, everything costs
     ~2x.  Compare the model with clustering ON vs OFF.
  3. Full Phase-3 model: the numbers a CFO would see.

Usage:  python examples/run_clustering_impact.py
"""

from __future__ import annotations

from pathlib import Path


from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics
from cyberrisk.simulation import simulate

ROOT = Path(__file__).resolve().parent.parent


def fmt_usd(x: float) -> str:
    if x >= 1e9:
        return f"${x/1e9:,.2f}B"
    if x >= 1e6:
        return f"${x/1e6:,.2f}M"
    if x >= 1e3:
        return f"${x/1e3:,.1f}K"
    return f"${x:,.0f}"


def sec(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main() -> None:
    cfg = load_config(
        ROOT / "config" / "scenarios.yaml",
        ROOT / "config" / "simulation_config.yaml",
    )

    # --- 1. Burstiness table ------------------------------------------------
    sec("1. BURSTINESS - HOW MUCH MORE VARIABLE THAN 'REGULAR' IS YOUR INCIDENT COUNT?")
    print("   A perfectly regular Poisson pattern has variance = mean (dispersion 1.0).")
    print("   Dispersion 1.5-2.0 means the annual count varies 50-100% MORE than regular.")
    print(f"{'scenario':<14} {'model':<8} {'lambda':>7} {'dispersion':>10}")
    for s in cfg.scenarios:
        disp = s.frequency.freq_dispersion or 1.0
        print(f"{s.key:<14} {s.frequency.model:<8} {s.frequency.lambda_annual:>7.2f} {disp:>10.1f}")

    # --- 2. Clustering ON vs OFF --------------------------------------------
    sec("2. CATASTROPHE YEARS - ~1 YEAR IN 20, EVERYTHING COSTS ~2X")
    cfg_off = cfg.model_copy(update={"event_clustering_enabled": False})
    cfg_on = cfg  # clustering already enabled in config

    m_off = compute_metrics(simulate(cfg_off, n_years=200_000, dependence="dependent"))
    m_on = compute_metrics(simulate(cfg_on, n_years=200_000, dependence="dependent"))

    print(f"{'metric':<10} {'no clustering':>13} {'clustering on':>13} {'change':>10}")
    for metric, label in (("eal", "EAL"), ("es_99", "ES99"), ("p99_5", "P99.5"), ("p99_9", "P99.9")):
        off = getattr(m_off, metric)
        on = getattr(m_on, metric)
        pct = (on / off - 1) * 100
        print(f"{label:<10} {fmt_usd(off):>13} {fmt_usd(on):>13} {pct:>+9.1f}%")

    # --- 3. The full Phase-3 model ------------------------------------------
    sec("3. FULL PHASE-3 MODEL - THE NUMBERS A CFO WOULD SEE")
    m = compute_metrics(simulate(cfg, n_years=200_000, dependence="dependent"))
    print(f"   Expected annual loss (EAL)      : {fmt_usd(m.eal)}")
    print(f"   1-in-100 year loss (P99.0)      : {fmt_usd(m.p99_0)}")
    print(f"   1-in-200 year loss (P99.5)      : {fmt_usd(m.p99_5)}")
    print(f"   1-in-1000 year loss (P99.9)     : {fmt_usd(m.p99_9)}")
    print(f"   Expected Shortfall 99% (ES99)   : {fmt_usd(m.es_99)}")
    print(f"   P(no loss year)                 : {m.prob_zero_loss*100:.1f}%")

    # --- 4. Plain-English summary -------------------------------------------
    sec("4. SUMMARY (WHAT A CONSULTANT WOULD SAY)")
    print("   * Your incident counts are bursty, not regular: the annual count")
    print(f"     varies up to {max((s.frequency.freq_dispersion or 1) for s in cfg.scenarios):.0f}x"
          f" as much as a perfectly regular pattern.")
    print(f"   * Roughly one year in {int(1/cfg.catastrophe_probability)}, several things go wrong at once and")
    print(f"     everything costs ~{cfg.catastrophe_multiplier_mean:.0f}x more.  That is where the")
    print("     tail risk lives.")
    print(f"   * Adding catastrophe years raises ES99 by "
          f"{100*(m_on.es_99/m_off.es_99-1):.0f}% and the 1-in-1000 PML by "
          f"{100*(m_on.p99_9/m_off.p99_9-1):.0f}%.")
    print("   * A limit sized off the no-clustering model would be too low in the")
    print("     catastrophe years that actually drive claims.")


if __name__ == "__main__":
    main()
