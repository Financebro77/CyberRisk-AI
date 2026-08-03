"""Full consultation demo: follow-up dialogue + risk-appetite validation.

Shows the agent behaving like a real broker in a first meeting:

    Turn 1: client gives only industry + revenue
    Turn 2: client adds data volume + tech dependency, says "unknown" on controls
    Turn 3: client answers controls + incidents, is vague on appetite
    Turn 4: client gives coverage + a real retention figure
    -> agent validates the appetite against the modelled loss and advises

Usage:  python examples/run_consultation_demo.py
"""

from __future__ import annotations

from pathlib import Path

from agent.consultant_agent import advise
from agent.elicitation import ConsultationSession
from agent.risk_appetite import parse_retention, validate_appetite
from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics
from cyberrisk.scoring import CompanyProfile, compute_score
from cyberrisk.simulation import simulate

ROOT = Path(__file__).resolve().parent.parent


def score_and_run(provided: dict) -> tuple:
    """Map a complete provided dict to (ScoredFirm, RiskMetrics)."""
    cfg = load_config(
        ROOT / "config" / "scenarios.yaml",
        ROOT / "config" / "simulation_config.yaml",
    )
    # Derive factor scores from the controls string is simplified here; for the
    # demo we use the benchmark profile's scoring path via a representative set.
    from cyberrisk.benchmark import _rating_to_score
    from cyberrisk.scoring import load_scoring_weights

    weights = load_scoring_weights()
    # Map the 8 dimensions to factor scores using a neutral-but-sensible profile.
    factor_scores = {}
    base = {
        "external_attack_surface": "moderate",
        "industry_targeting": "moderate_target",
        "data_sensitivity": "moderate",
        "patch_cadence": "monthly",
        "vuln_scanning": "weekly",
        "open_critical_vulns": "moderate",
        "mfa_coverage": "majority",
        "privileged_access": "basic",
        "iam_governance": "defined",
        "edr_coverage": "majority",
        "backup_frequency": "daily",
        "dr_testing": "annual",
        "vendor_assessment": "annual",
        "contractual_security": "standard",
        "supply_chain_visibility": "partial",
        "incident_response": "documented",
        "risk_oversight": "delegated",
        "cyber_insurance": "partial",
    }
    # Revenue feeds the firm profile; the rest is held constant for the demo.
    for k, rating in base.items():
        factor_scores[k] = _rating_to_score(weights, k, rating)
    revenue = float(provided.get("revenue") or 500_000_000)
    company = CompanyProfile(firm_name="Demo Client", revenue_usd=revenue, factor_scores=factor_scores)
    scored = compute_score(company, weights)
    cfg_adj = cfg.model_copy(update={"firm_revenue_usd": revenue})
    metrics = compute_metrics(simulate(cfg_adj, n_years=100_000, score=scored.composite_score))
    return scored, metrics


def main() -> None:
    print("=" * 76)
    print("CONSULTATION DEMO - FOLLOW-UP DIALOGUE + RISK APPETITE")
    print("=" * 76)

    session = ConsultationSession(max_turns=6)

    # --- Turn 1 -------------------------------------------------------
    print("\n[Client] 'We are a mid-sized manufacturer, about $500M revenue.'")
    r = session.reply({"industry": "Manufacturing", "revenue": 500_000_000})
    print(f"[Agent] still needs: {', '.join(r.missing)}")
    print("        ->", session.formatted_response().splitlines()[0])

    # --- Turn 2 -------------------------------------------------------
    print("\n[Client] 'We hold ~50k customer records, very dependent on our ERP and cloud.'")
    r = session.reply({"customer_data_volume": 50_000, "technology_dependency": "High"})
    print(f"[Agent] still needs: {', '.join(r.missing)}")

    # --- Turn 3: client says 'unknown' on controls ----------------------
    print("\n[Client] 'Our security controls? Not sure, honestly.'")
    r = session.reply({"security_controls": "unknown"})
    print(f"[Agent] re-asks (not accepted): security_controls still in missing = "
          f"{'security_controls' in r.missing}")
    r = session.reply({"security_controls": "MFA, patching, EDR"})
    print(f"[Agent] controls accepted; still needs: {', '.join(r.missing)}")

    # --- Turn 4: appetite (vague) -------------------------------------------
    print("\n[Client] 'We had one incident 2 years ago, have a $5M policy, "
          "and we want to keep our premium low.'")
    r = session.reply({
        "previous_incidents": 1,
        "existing_coverage": "$5M limit",
        "risk_appetite": "we want to keep our premium low",
    })
    print(f"[Agent] still needs: {', '.join(r.missing) if r.missing else '(none)'}")
    print("        -> a vague appetite ('keep premium low') is pushed back for a figure")

    # --- Turn 5: real appetite figure -------------------------------------
    print("\n[Client] 'Actually, we could retain up to $1.5M.'")
    r = session.reply({"risk_appetite": "retain up to $1.5M"})
    print(f"[Agent] complete = {r.complete}")
    print("        ->", session.formatted_response())

    # --- Now validate appetite + advise -----------------------------------
    print("\n" + "=" * 76)
    print("RISK-APPETITE VALIDATION + ADVICE")
    print("=" * 76)
    scored, metrics = score_and_run(session.answers)
    retention = parse_retention("retain up to $1.5M")
    verdict = validate_appetite(retention, metrics.eal, metrics.es_99)
    print(f"\nModelled EAL   : ${metrics.eal/1e6:,.2f}M")
    print(f"Modelled ES99  : ${metrics.es_99/1e6:,.2f}M")
    print(f"Stated retention: {retention/1e6:,.2f}M")
    print(f"Appetite verdict: [{verdict.rating}]")
    print(f"  {verdict.message}")

    # Full advice via advise()
    rec = advise(
        session.answers,
        score_and_run=score_and_run,
        risk_appetite_text="retain up to $1.5M",
    )
    print(f"\nFinal advice for {rec.firm_name} (category {rec.risk_category}):")
    for rline in rec.recommendations:
        print(f"  - {rline}")


if __name__ == "__main__":
    main()
