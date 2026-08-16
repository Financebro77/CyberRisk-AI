"""Shared assessment composition for the web and versioned APIs.

Both API surfaces run the same four-step assessment against the same
already-tested tool functions -- score, simulate, insurance, scenario
contribution.  This module owns that composition ONCE, so the web
``report_executive`` and the v1 ``/assessment/submit`` pipeline cannot drift
apart or re-run the Monte Carlo an extra time for the mitigation roadmap.

No risk logic lives here; every figure comes from the tools below.
"""

from __future__ import annotations

from typing import Any

from cyberrisk.agent.disclosure import DISCLOSURE_HEADING, LIMITATIONS
from cyberrisk.agent.schemas import CompanyBrief, PolicyInput
from cyberrisk.agent.tools import (
    analyse_insurance_structure,
    assess_company_risk,
    run_loss_simulation,
)


def compose_assessment(
    brief: CompanyBrief,
    *,
    policy: PolicyInput | None = None,
    n_years: int | None = None,
) -> dict[str, Any]:
    """Run score -> simulate -> insurance -> contribution for a brief.

    Returns either the engine's ``insufficient_info`` guard (HTTP-200 business
    response, no simulation run) or ``{"status": "ok", "score", "sim", "ins",
    "contrib"}`` with the four tool dicts.  The mitigation roadmap
    (``contrib["scenarios"]``) is the model-linked detail ``run_loss_simulation``
    already computed -- reusing it avoids a second Monte Carlo pass.
    """
    score_res = assess_company_risk(brief)
    sim_res = run_loss_simulation(brief, n_years=n_years)
    if sim_res.get("status") == "insufficient_info":
        return {
            "status": "insufficient_info",
            "needed": sim_res.get("needed", []),
            "message": sim_res.get("message", "Insufficient information to model the loss."),
        }
    ins_res = analyse_insurance_structure(brief, policy=policy, n_years=n_years)
    return {
        "status": "ok",
        "score": score_res,
        "sim": sim_res,
        "ins": ins_res,
        "contrib": {
            "status": "ok",
            "scenarios": sim_res.get("scenario_contribution_detail", []),
        },
    }


def mitigation_scenarios(contrib: dict[str, Any]) -> list[Any]:
    """The model-linked mitigation roadmap from a ``contrib`` dict."""
    return contrib.get("scenarios", []) if contrib.get("status") == "ok" else []


def model_limitations() -> dict[str, Any]:
    """The disclosure + limitations block shared by both API surfaces."""
    return {"heading": DISCLOSURE_HEADING, "limitations": list(LIMITATIONS)}
