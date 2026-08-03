"""Benchmark scenario runner: validate CyberRiskAI across 5 client profiles.

Runs the full pipeline (score -> simulation -> metrics) on the 5 synthetic
clients in config/benchmark_profiles.yaml, checks each against the
consultant's expected outcome, and prints a summary table.

Usage:  python examples/run_benchmarks.py
"""

from __future__ import annotations

from pathlib import Path

from cyberrisk.benchmark import (
    load_benchmark_profiles,
    run_benchmarks,
    evaluate_results,
)

ROOT = Path(__file__).resolve().parent.parent


def fmt_usd(x: float) -> str:
    if x >= 1e9:
        return f"${x/1e9:,.2f}B"
    if x >= 1e6:
        return f"${x/1e6:,.2f}M"
    if x >= 1e3:
        return f"${x/1e3:,.1f}K"
    return f"${x:,.0f}"


def main() -> None:
    profiles = load_benchmark_profiles(ROOT / "config" / "benchmark_profiles.yaml")
    print("=" * 76)
    print("CyberRiskAI BENCHMARK SCENARIOS - 5 CLIENT PROFILES")
    print("=" * 76)
    for p in profiles:
        print(
            f"\n{p.name}  [{p.industry}]  revenue {fmt_usd(p.revenue_usd)}  "
            f"data exposure: {p.data_exposure}"
        )
        print(f"  Expected: {p.expected_category} (score "
              f"{p.expected_score_min:.0f}-{p.expected_score_max:.0f})")
        if p.expected_loss_note:
            print(f"  Loss note: {p.expected_loss_note}")

    print("\n" + "=" * 76)
    print("MODEL OUTPUT")
    print("=" * 76)
    results = run_benchmarks(profiles, n_years=200_000, seed=42)
    for r in results:
        print(
            f"{r.profile.name:<34} score={r.risk_score:6.1f}  cat={r.risk_category:<8}  "
            f"EAL={fmt_usd(r.eal)}  ES99={fmt_usd(r.es_99)}  P99.9={fmt_usd(r.p99_9)}"
        )

    print("\n" + "=" * 76)
    print("QA CHECKS (vs consultant expectations)")
    print("=" * 76)
    for line in evaluate_results(results):
        print(line)

    n_pass = sum(1 for r in results if r.checks_passed())
    print(f"\n{n_pass}/{len(results)} benchmark profiles PASS")


if __name__ == "__main__":
    main()
