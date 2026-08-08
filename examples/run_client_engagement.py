"""Marsh-style client engagement: run CyberRiskAI on a multinational logistics firm.

This is the showcase deliverable.  It runs the FULL pipeline on a realistic
multinational client (a global logistics & supply-chain operator) and prints
everything a professional cyber advisory would contain:

   1. Client profile
   2. Client interview (information elicitation)
   3. Risk assessment (scoring)
   4. Loss modelling (score-driven simulation)
   5. VaR / Expected Shortfall interpretation
   6. Insurance response & client retained loss (policy transform vs current program)
   7. Risk mitigation recommendations
   8. Executive summary

Run:  python examples/run_client_engagement.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from agent.consultant_agent import generate_recommendations
from agent.elicitation import DIMENSIONS
from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics
from cyberrisk.policy_transform import PolicyStructure, transform_events_to_years
from cyberrisk.scoring import CompanyProfile, compute_score, load_scoring_weights
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
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> None:
    # ------------------------------------------------------------------ config
    cfg = load_config(
        ROOT / "config" / "scenarios.yaml",
        ROOT / "config" / "simulation_config.yaml",
    )
    weights = load_scoring_weights()

    # ------------------------------------------------------------------ 1. client
    sec("1. CLIENT PROFILE")
    print("   Atlas Global Logistics Group (AGL)")
    print("   Industry: Multinational logistics & supply-chain operator")
    print("   Revenue : $6.5bn; 32,000 employees; 45 countries")
    print("   Profile : one of the largest third-party logistics (3PL) firms in")
    print("             EMEA; runs a 24/7 global freight network on ~120 critical")
    print("             IT systems (TMS/WMS, customs clearance, port integrations),")
    print("             ~80% cloud-hosted; holds data on 4m+ shipper accounts and")
    print("             900k+ customs filings.")
    print("\n   Cyber concerns raised by the client:")
    print("   * 'A ransomware event would halt our freight network -- that's our")
    print("      entire revenue stream. How exposed are we?'")
    print("   * 'We hold a lot of client and customs data. What is the regulatory")
    print("      and class-action exposure?'")
    print("   * 'Our current program is $25M limit / $1M retention. Is that enough?'")
    print("   * 'Where should we focus our next security investment?'")

    # ------------------------------------------------------------------ 2. interview
    sec("2. CLIENT INTERVIEW (information elicitation)")
    print("   The agent's first meeting establishes the facts it needs before")
    print("   advising.  The eight dimensions it asks about:")
    for dim, spec in DIMENSIONS.items():
        print(f"   * [{dim}] {spec['question']}")
    print("\n   For this engagement, the client provided:")
    print("   - Industry: Logistics / supply chain")
    print("   - Revenue: $6.5bn, 32,000 staff, 45 countries")
    print("   - Data: 4m+ shipper accounts, 900k customs filings (sensitive)")
    print("   - Tech dependency: Very high (24/7 network, 80% cloud)")
    print("   - Controls: Strong (MFA, SIEM, patching) but OT/warehouse gaps")
    print("   - Incidents: 1 significant ransomware attempt in last 3 yrs (contained)")
    print("   - Coverage: $25M limit / $1M retention / no sub-limit")
    print("   - Appetite: retain up to $1M, sensitive to premium")

    # ------------------------------------------------------------------ 3. risk assessment
    sec("3. RISK ASSESSMENT (scoring)")
    # Map the client's profile onto factor ratings consistent with a logistics firm.
    factor_scores = {}
    rating_map = {
        "external_attack_surface": 75.0,   # large global footprint, 45 countries
        "industry_targeting": 80.0,        # logistics is a top-3 targeted sector
        "data_sensitivity": 75.0,          # shipper + 900k customs filings
        "patch_cadence": 65.0,             # monthly on IT, quarterly on OT/warehouse
        "vuln_scanning": 65.0,             # continuous on IT, weak on OT
        "open_critical_vulns": 70.0,       # OT lag creates an exposure
        "mfa_coverage": 35.0,              # strong on IT, absent on some OT
        "privileged_access": 40.0,         # segmented on IT, weak on OT
        "iam_governance": 45.0,            # defined but OT users not fully governed
        "edr_coverage": 40.0,              # strong on IT
        "backup_frequency": 35.0,          # daily, offline copies
        "dr_testing": 45.0,                # annual
        "vendor_assessment": 65.0,         # deep 3PL partner exposure, mixed controls
        "contractual_security": 50.0,      # standard, some partners weaker
        "supply_chain_visibility": 60.0,   # partial (depends on partners)
        "incident_response": 30.0,         # tested plan
        "risk_oversight": 20.0,            # dedicated CISO/board
        "cyber_insurance": 45.0,           # partial program
    }
    for k, v in rating_map.items():
        factor_scores[k] = v

    company = CompanyProfile(
        firm_name="Atlas Global Logistics Group",
        revenue_usd=6_500_000_000,
        employees=32_000,
        customer_records=4_000_000,
        factor_scores=factor_scores,
    )
    scored = compute_score(company, weights)
    print(f"   Composite risk score : {scored.composite_score:.1f}/100")
    print(f"   Risk category        : {scored.risk_category}")
    print("\n   Domain breakdown (higher = worse):")
    for dk, dv in sorted(scored.domain_scores.items(), key=lambda kv: -kv[1]):
        print(f"     {dk:<24} {dv:5.1f}")
    print(f"\n   Key risk drivers     : {', '.join(scored.risk_drivers[:6])}")

    # ------------------------------------------------------------------ 4. loss modelling
    sec("4. LOSS MODELLING (score-driven Monte Carlo)")
    result = simulate(
        cfg,
        n_years=100_000,
        score=scored.composite_score,
        return_events=True,
    )
    m = compute_metrics(result)
    print("   Simulation: 100,000 simulated years, score-driven frequencies,")
    print("   Student-t dependence, catastrophe years enabled.")
    print(f"\n   Expected Annual Loss (EAL)    : {fmt_usd(m.eal)}")
    print(f"   1-in-100 year loss (P99.0)    : {fmt_usd(m.p99_0)}")
    print(f"   1-in-200 year loss (P99.5)    : {fmt_usd(m.p99_5)}")
    print(f"   1-in-1000 year loss (P99.9)   : {fmt_usd(m.p99_9)}")
    print(f"   Expected Shortfall 99% (ES99) : {fmt_usd(m.es_99)}")
    print(f"   P(no loss year)               : {m.prob_zero_loss*100:.1f}%")
    print("\n   Scenario contribution to EAL:")
    contrib = m.scenario_contribution()
    for key in sorted(contrib, key=lambda k: -contrib[k]):
        print(f"     {key:<16} {m.aal_by_scenario[key]/1e6:6.2f}M  ({contrib[key]*100:4.1f}%)")

    # ------------------------------------------------------------------ 5. VaR / ES
    sec("5. VAR / EXPECTED SHORTFALL INTERPRETATION")
    # Actuarial-standard wording: every VaR names the confidence level, the
    # 1-year horizon, and the loss definition (ground-up, before insurance).
    print(f"   VaR 99% (1-year, ground-up before insurance) {fmt_usd(m.var_99)}:")
    print(f"     '99% annual aggregate VaR is {fmt_usd(m.var_99)}. Only 1% of")
    print("     simulated years exceed this amount.'")
    print(f"   ES 99% (1-year, ground-up before insurance)  {fmt_usd(m.es_99)}:")
    print(f"     'The 99% Expected Shortfall is {fmt_usd(m.es_99)}, the average annual")
    print("     loss in the worst 1% of simulated outcomes.'")
    print(f"   ES99 / EAL = {m.es_99/m.eal:.1f}x: the tail is {m.es_99/m.eal:.1f} times the")
    print("   average year.  This is the 'catastrophe multiplier' -- a single 1-in-100")
    print("   event can be worth over a decade of average losses.")

    # ------------------------------------------------------------------ 6. insurance response & client retained loss
    sec("6. INSURANCE RESPONSE & CLIENT RETAINED LOSS")
    # Current program: $25M limit / $1M retention
    current = PolicyStructure(
        per_occurrence_deductible=1_000_000,
        per_occurrence_limit=25_000_000,
        annual_aggregate_deductible=1_000_000,
        annual_aggregate_limit=25_000_000,
    )
    ev = result.events
    out = transform_events_to_years(
        ev[:, 2], ev[:, 0], ev[:, 1],
        n_years=result.years,
        scenario_keys=result.scenario_keys,
        policy=current,
    )
    retained, transferred = out["retained"], out["transferred"]
    print("   Current program: $25M limit / $1M retention / $25M aggregate")
    print("   SECTION 1 -- GROUND-UP CYBER LOSS (before insurance):")
    print(f"     EAL  : {fmt_usd(m.eal)}")
    print(f"     VaR99: {fmt_usd(m.var_99)}")
    print(f"     ES99 : {fmt_usd(m.es_99)}")
    print(f"     P99.9: {fmt_usd(m.p99_9)}")
    print("   SECTION 2 -- INSURANCE RESPONSE:")
    print(f"     Policy limit   : {fmt_usd(current.annual_aggregate_limit)}")
    print(f"     Retention      : {fmt_usd(current.per_occurrence_deductible)}")
    print(f"     Covered loss   : {fmt_usd(float(transferred.mean()))} (transferred EAL)")
    print(f"     Insurer payment: {fmt_usd(float(transferred.mean()))}")
    # years where transferred hits the limit (exhaustion)
    exhausted = np.mean(transferred >= current.annual_aggregate_limit - 1e-6)
    print(f"     P(annual limit exhausted) : {exhausted*100:.2f}%")
    print("   SECTION 3 -- CLIENT RETAINED LOSS:")
    print(f"     Retained EAL  : {fmt_usd(float(retained.mean()))}")
    retained_es99 = float(retained[retained >= np.quantile(retained, 0.99)].mean())
    print(f"     Retained ES99 : {fmt_usd(retained_es99)}")
    # Residual uncovered exposure for a 1-in-1000-year (P99.9) event:
    #   gross loss - retention - insurance recovery, floored at 0.
    gross_999 = m.p99_9
    retention = current.per_occurrence_deductible
    limit = current.annual_aggregate_limit
    insurer_payment = min(max(0.0, gross_999 - retention), limit)
    residual = max(0.0, gross_999 - retention - insurer_payment)
    print(f"     For a {fmt_usd(gross_999)} extreme loss event:")
    print(f"       Client retention        : {fmt_usd(retention)}")
    print(f"       Insurance recovery      : {fmt_usd(insurer_payment)} maximum")
    print(f"       Residual uncovered      : {fmt_usd(residual)}")
    if residual > 0:
        print(f"     -> The $25M limit covers {fmt_usd(m.es_99)} of the 1-in-100 tail, but a")
        print(f"        P99.9 event ({fmt_usd(m.p99_9)}) leaves {fmt_usd(residual)} the client retains after insurance.")

    # ------------------------------------------------------------------ 7. mitigation
    sec("7. RISK MITIGATION RECOMMENDATIONS")
    rec = generate_recommendations(scored, m)
    print(f"   Category: {rec.risk_category}")
    for r in rec.recommendations:
        print(f"   * {r}")

    # ------------------------------------------------------------------ 8. executive
    sec("8. EXECUTIVE SUMMARY")
    gross_999 = m.p99_9
    retention = current.per_occurrence_deductible
    limit = current.annual_aggregate_limit
    insurer_payment = min(max(0.0, gross_999 - retention), limit)
    residual = max(0.0, gross_999 - retention - insurer_payment)
    print("   ATLAS GLOBAL LOGISTICS GROUP -- CYBER RISK ASSESSMENT")
    print(f"   Risk score {scored.composite_score:.0f}/100 ({scored.risk_category})")
    print(f"   Expected annual loss: {fmt_usd(m.eal)}; 1-in-100 year: {fmt_usd(m.es_99)}")
    print(f"   Ground-up 1-in-1000 year loss: {fmt_usd(gross_999)} (before insurance)")
    print("   At the current $25M limit / $1M retention, a 1-in-1000 event leaves a")
    print(f"   residual uncovered exposure of {fmt_usd(residual)} after insurance.")
    print("   Recommend a higher limit and OT hardening.")

    # Mandatory model-limitations disclosure at the end of the advisory report.
    from cyberrisk.agent.disclosure import disclosure_block

    print(f"\n{disclosure_block()}")


if __name__ == "__main__":
    main()
