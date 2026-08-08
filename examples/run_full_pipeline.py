"""End-to-end CyberRiskAI pipeline (Phases 2-4).

Demonstrates the full stack on a worked example:
    firm profile -> scoring (Phase 2)
    -> score-driven loss simulation (Phase 1 + score link)
    -> policy transform -> retained/transferred (Phase 4)
    -> Excel report (Phase 4)
    -> consultant recommendation (Phase E, rule-based)

Usage:  python examples/run_full_pipeline.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics
from cyberrisk.policy_transform import PolicyStructure, transform_events_to_years
from cyberrisk.reporting.excel import write_report
from cyberrisk.scoring import CompanyProfile, compute_score
from cyberrisk.simulation import simulate

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "output"


def fmt_usd(x: float) -> str:
    if x >= 1e9:
        return f"${x/1e9:,.2f}B"
    if x >= 1e6:
        return f"${x/1e6:,.2f}M"
    if x >= 1e3:
        return f"${x/1e3:,.1f}K"
    return f"${x:,.0f}"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config(
        ROOT / "config" / "scenarios.yaml",
        ROOT / "config" / "simulation_config.yaml",
    )

    # --- 1. Score the firm -------------------------------------------------
    profile = CompanyProfile(
        firm_name="Acme Manufacturing",
        revenue_usd=1_500_000_000.0,
        employees=8_000,
        factor_scores={
            # threat & exposure
            "external_attack_surface": 70.0,
            "industry_targeting": 60.0,
            "data_sensitivity": 75.0,
            # vulnerability mgmt
            "patch_cadence": 65.0,
            "vuln_scanning": 40.0,
            "open_critical_vulns": 80.0,
            # access control
            "mfa_coverage": 60.0,
            "privileged_access": 85.0,
            "iam_governance": 70.0,
            # endpoint resilience
            "edr_coverage": 65.0,
            "backup_frequency": 60.0,
            "dr_testing": 45.0,
            # third party
            "vendor_assessment": 65.0,
            "contractual_security": 50.0,
            "supply_chain_visibility": 75.0,
            # governance
            "incident_response": 45.0,
            "risk_oversight": 50.0,
            "cyber_insurance": 45.0,
        },
    )
    scored = compute_score(profile)
    print("\n=== 1. SCORING (Phase 2) ===")
    print(f"Firm          : {scored.firm_name}")
    print(f"Risk score    : {scored.composite_score:.1f}/100")
    print(f"Risk category : {scored.risk_category}")
    print(f"Risk drivers  : {scored.risk_drivers}")
    print("Domain scores :")
    for k, v in sorted(scored.domain_scores.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<22} {v:6.1f}")

    # --- 2. Score-driven loss simulation ------------------------------------
    print("\n=== 2. LOSS SIMULATION (score-driven, Phase 1+2) ===")
    result = simulate(cfg, n_years=100_000, score=scored.composite_score, return_events=True)
    m = compute_metrics(result)
    print(f"EAL            : {fmt_usd(m.eal)}")
    print(f"VaR 99%        : {fmt_usd(m.var_99)}")
    print(f"ES 99%         : {fmt_usd(m.es_99)}")
    print(f"P(no loss)     : {m.prob_zero_loss*100:.1f}%")

    # --- 3. Policy transform ------------------------------------------------
    print("\n=== 3. POLICY TRANSFORM (Phase 4) ===")
    policy = PolicyStructure(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=5_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=20_000_000.0,
    )
    ev = result.events
    pm = transform_events_to_years(
        ev[:, 2], ev[:, 0], ev[:, 1],
        n_years=result.years,
        scenario_keys=result.scenario_keys,
        policy=policy,
    )
    retained, transferred = pm["retained"], pm["transferred"]
    print(f"Retained EAL   : {fmt_usd(float(retained.mean()))}")
    print(f"Transferred EAL: {fmt_usd(float(transferred.mean()))}")
    print(f"Retained ES99  : {fmt_usd(float(retained[retained >= np.quantile(retained, 0.99)].mean()))}")
    # policy adequacy: share of years fully within aggregate limit
    within = np.mean(transferred < policy.annual_aggregate_limit)
    print(f"P(within agg limit): {within*100:.1f}%")

    # --- 4. Excel report ----------------------------------------------------
    print("\n=== 4. REPORTING (Phase 4) ===")
    out = OUT_DIR / "Acme_Manufacturing_report.xlsx"
    path = write_report(result, policy_metrics=pm, out_path=out)
    print(f"Workbook written: {path}")

    # --- 5. Consultant recommendation ---------------------------------------
    print("\n=== 5. CONSULTANT RECOMMENDATION (Phase E, rule-based) ===")
    from agent.consultant_agent import generate_recommendations

    rec = generate_recommendations(scored, m)
    print(f"Summary: {rec.summary}")
    for r in rec.recommendations:
        print(f"  - {r}")


if __name__ == "__main__":
    main()
