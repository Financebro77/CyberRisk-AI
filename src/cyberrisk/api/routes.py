"""HTTP routes for the CyberRisk AI platform.

Every route is a thin wrapper over an existing, already-tested tool
function in ``cyberrisk.agent`` (tools.py / sensitivity_tools.py /
model_mechanics.py).  The tool functions:

    * accept pydantic DTOs (``CompanyBrief`` / ``PolicyInput``) and
    * return JSON-serialisable dicts, including the ``insufficient_info``
      completeness guard that the UI turns into a form prompt.

No engine or agent file is imported for mutation -- the engine is consumed
read-only exactly as the agent consumes it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cyberrisk import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
from cyberrisk.agent.model_mechanics import explain_model_mechanics
from cyberrisk.agent.sensitivity_tools import run_control_improvement_scenario
from cyberrisk.agent.scenario_contribution import analyze_scenario_contribution
from cyberrisk.agent.tools import (
    analyse_insurance_structure,
    assess_company_risk,
    generate_risk_report,
    run_loss_simulation,
)
from cyberrisk.agent.schemas import PolicyInput as PolicyInputDTO
from cyberrisk.agent.disclosure import DISCLOSURE_HEADING, LIMITATIONS

from cyberrisk.api.dependencies import (
    brief_from_request,
    n_years_from_request,
    policy_from_request,
)
from cyberrisk.calibration import load_config

router = APIRouter()


# ---------------------------------------------------------------------------
# Request bodies (thin envelopes so FastAPI validates + documents the shape)
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    """A client brief for scoring.  All fields optional -- scoring works on
    partial briefs and reports what was assumed."""

    firm_name: str | None = None
    industry: str | None = None
    revenue_usd: float | None = Field(default=None, gt=0.0)
    customer_records: int | None = Field(default=None, ge=0)
    technology_dependency: str | None = None
    security_controls: str | None = None
    previous_incidents: int = 0
    existing_coverage: str | None = None
    risk_appetite: str | None = None


class SimulateRequest(BaseModel):
    """A client brief plus an optional Monte Carlo years override."""

    firm_name: str | None = None
    industry: str | None = None
    revenue_usd: float | None = Field(default=None, gt=0.0)
    customer_records: int | None = Field(default=None, ge=0)
    technology_dependency: str | None = None
    security_controls: str | None = None
    previous_incidents: int = 0
    existing_coverage: str | None = None
    risk_appetite: str | None = None
    n_years: int | None = Field(default=None, ge=1_000, le=500_000)


class InsuranceRequest(SimulateRequest):
    """A client brief plus policy terms (defaults mirror ``PolicyInput``)."""

    per_occurrence_deductible: float | None = Field(default=None, ge=0.0)
    per_occurrence_limit: float | None = Field(default=None, ge=0.0)
    annual_aggregate_deductible: float | None = Field(default=None, ge=0.0)
    annual_aggregate_limit: float | None = Field(default=None, ge=0.0)
    coinsurance: float | None = Field(default=None, ge=0.0, lt=1.0)


class ControlImprovementRequest(SimulateRequest):
    """A client brief plus the control change to model."""

    control_change: str


class ReportRequest(BaseModel):
    """A client brief plus an optional firm name for the workbook."""

    firm_name: str | None = None
    industry: str | None = None
    revenue_usd: float | None = Field(default=None, gt=0.0)
    customer_records: int | None = Field(default=None, ge=0)
    technology_dependency: str | None = None
    security_controls: str | None = None
    previous_incidents: int = 0
    existing_coverage: str | None = None
    risk_appetite: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness check for the platform."""
    return {"status": "ok", "service": "CyberRisk AI", "version": __version__}


@router.post("/score")
def score(req: ScoreRequest) -> dict[str, Any]:
    """Score a client's cyber risk profile (0-100) and identify drivers.

    Deterministic: the same brief always yields the same score.  Works on
    partial briefs and reports which factors were assumed from neutral
    defaults.
    """
    brief = brief_from_request(req.model_dump(), firm_name=req.firm_name)
    return assess_company_risk(brief)


@router.post("/simulate")
def simulate_route(req: SimulateRequest) -> dict[str, Any]:
    """Run the Monte Carlo loss model and return EAL / VaR / ES / PML.

    Requires ``revenue_usd`` and ``security_controls`` -- otherwise returns
    the completeness guard ``{"status": "insufficient_info", ...}`` which the
    UI turns into a form prompt.
    """
    data = req.model_dump()
    brief = brief_from_request(data, firm_name=req.firm_name)
    return run_loss_simulation(brief, n_years=n_years_from_request(data))


@router.post("/insurance")
def insurance(req: InsuranceRequest) -> dict[str, Any]:
    """Test an insurance structure and report the insurer's response and
    the client's residual retained exposure."""
    data = req.model_dump()
    brief = brief_from_request(data, firm_name=req.firm_name)
    policy = policy_from_request(data)
    return analyse_insurance_structure(brief, policy=policy, n_years=n_years_from_request(data))


@router.post("/insurance/optimise")
def insurance_optimise(req: InsuranceRequest) -> dict[str, Any]:
    """Evaluate the current structure and recommend an improved one.

    Runs the requested policy through ``analyse_insurance_structure`` (the
    "current" view), then sweeps a grid of limit / retention combinations
    over the SAME cached Monte Carlo simulation and picks the structure that
    best closes the residual-exposure gap per dollar of additional limit.

    Everything returned comes from the engine -- no hardcoded numbers.  The
    grid is modest (6 limits x 4 retentions) because each evaluation reuses
    the cached simulation and only re-runs the policy transform (~ms each).
    """
    data = req.model_dump()
    brief = brief_from_request(data, firm_name=req.firm_name)
    policy = policy_from_request(data) or PolicyInputDTO()

    current = analyse_insurance_structure(brief, policy=policy, n_years=n_years_from_request(data))

    # If the brief can't be modelled, return the completeness guard.
    if current.get("status") == "insufficient_info":
        return current

    ground = current["ground_up_loss"]
    pml_1in1000 = ground["pml_1in1000"]

    # Sweep limits as a share of the 1-in-1000 PML, retentions in $ steps.
    limit_grid = [
        max(1_000_000.0, pml_1in1000 * f)
        for f in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5)
    ]
    retention_grid = [250_000.0, 500_000.0, 1_000_000.0, 2_000_000.0]

    best: dict[str, Any] | None = None
    best_score = float("-inf")
    for limit in limit_grid:
        for retention in retention_grid:
            trial = PolicyInputDTO(
                per_occurrence_deductible=retention,
                per_occurrence_limit=None,
                annual_aggregate_deductible=policy.annual_aggregate_deductible,
                annual_aggregate_limit=limit,
                coinsurance=policy.coinsurance,
            )
            res = analyse_insurance_structure(brief, policy=trial, n_years=n_years_from_request(data))
            if res.get("status") != "ok":
                continue
            residual = res["client_retained_loss"]["residual_exposure_at_p99_9"]
            recovery = res["insurance_response"]["insurer_payment"]
            # Objective: maximise recovery per dollar of limit, penalising
            # residual tail exposure.  Higher limit may not buy proportionate
            # recovery (heavy tail), so the score rewards closing the gap.
            score = recovery - 0.5 * residual - 0.1 * retention
            if score > best_score:
                best_score = score
                best = {
                    "policy_limit": limit,
                    "retention": retention,
                    "residual_exposure": residual,
                    "insurer_payment": recovery,
                    "p_annual_limit_exhausted": res["insurance_response"]["p_annual_limit_exhausted"],
                    "evaluation": res["evaluation"],
                }

    if best is None:
        best = {
            "policy_limit": policy.per_occurrence_limit or 0.0,
            "retention": policy.per_occurrence_deductible or 0.0,
            "residual_exposure": current["client_retained_loss"]["residual_exposure_at_p99_9"],
            "insurer_payment": current["insurance_response"]["insurer_payment"],
            "p_annual_limit_exhausted": current["insurance_response"]["p_annual_limit_exhausted"],
            "evaluation": current["evaluation"],
        }

    return {
        "status": "ok",
        "firm_name": current["firm_name"],
        "current": current,
        "recommended": best,
        "ground_up_loss": ground,
    }


@router.post("/controls-improvement")
def controls_improvement(req: ControlImprovementRequest) -> dict[str, Any]:
    """Model the effect of a control improvement (e.g. 'implement MFA')."""
    data = req.model_dump()
    brief = brief_from_request(data, firm_name=req.firm_name)
    return run_control_improvement_scenario(
        brief,
        control_change=req.control_change,
        n_years=n_years_from_request(data),
    )


@router.post("/report")
def report(req: ReportRequest) -> dict[str, Any]:
    """Generate the Excel risk-report workbook and return its path."""
    brief = brief_from_request(req.model_dump(), firm_name=req.firm_name)
    return generate_risk_report(brief, firm_name=req.firm_name)


@router.get("/report/download")
def report_download() -> Any:
    """Download the most recently generated Excel workbook as a file.

    The workbook is written to disk by ``generate_risk_report``; this route
    streams it back with a download filename so a browser can save it.
    """
    from fastapi.responses import FileResponse

    data_dir = REPO_ROOT / "data" / "output"
    # Most recent workbook in the output dir.
    xlsx = sorted(data_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not xlsx:
        raise HTTPException(status_code=404, detail="No report generated yet. Run /api/report first.")
    return FileResponse(
        xlsx[0],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=xlsx[0].name,
    )


@router.post("/report/executive")
def report_executive(req: ReportRequest) -> dict[str, Any]:
    """Aggregate the full executive-report data in one response.

    Calls the existing tools read-only (score + simulate + insurance + scenario
    contribution) and packages the results the Executive Report page renders.
    No numbers are computed here -- every figure comes from the engine.
    """
    data = req.model_dump()
    brief = brief_from_request(data, firm_name=req.firm_name)
    n_years = n_years_from_request(data)

    # 1. Risk score + drivers.
    score_res = assess_company_risk(brief)
    # 2. Monte Carlo simulation metrics + scenario contributions + mitigation
    #    roadmap (recommended controls are model-linked in the engine).
    sim_res = run_loss_simulation(brief, n_years=n_years)
    if sim_res.get("status") == "insufficient_info":
        return sim_res
    # 3. Insurance analysis with default policy terms (current program).
    ins_res = analyse_insurance_structure(brief, policy=None, n_years=n_years)
    # 4. Scenario contribution detail (per-scenario AAL + recommended controls).
    contrib = analyze_scenario_contribution(brief, n_years=n_years)

    return {
        "status": "ok",
        "firm_name": score_res.get("firm_name", brief.firm_name or "Client"),
        "executive_summary": {
            "risk_score": score_res.get("risk_score"),
            "risk_category": score_res.get("risk_category"),
            "sentence": (
                f"{brief.firm_name or 'The client'} carries a {score_res.get('risk_category', '')} "
                f"cyber risk profile (score {score_res.get('risk_score', 0):.1f}/100). "
                f"Modelled expected annual loss is ${sim_res.get('eal', 0) / 1e6:.1f}M, with a "
                f"1-in-100-year loss of ${sim_res.get('var_99', 0) / 1e6:.1f}M."
            ),
        },
        "risk_rating": {
            "score": score_res.get("risk_score"),
            "category": score_res.get("risk_category"),
            "domain_scores": score_res.get("domain_scores", {}),
            "risk_drivers": score_res.get("risk_drivers", []),
        },
        "financial_exposure": {
            "eal": sim_res.get("eal"),
            "var_95": sim_res.get("var_95"),
            "var_99": sim_res.get("var_99"),
            "es_99": sim_res.get("es_99"),
            "pml_1in200": sim_res.get("pml_1in200"),
            "pml_1in1000": sim_res.get("pml_1in1000"),
            "loss_distribution": sim_res.get("loss_distribution"),
            "prob_zero_loss": sim_res.get("prob_zero_loss"),
        },
        "insurance_analysis": {
            "ground_up_loss": ins_res.get("ground_up_loss"),
            "insurance_response": ins_res.get("insurance_response"),
            "client_retained_loss": ins_res.get("client_retained_loss"),
            "evaluation": ins_res.get("evaluation"),
        },
        "mitigation_roadmap": contrib.get("scenarios", []) if contrib.get("status") == "ok" else [],
        "scenario_contributions": sim_res.get("scenario_contribution", {}),
        "model_limitations": {
            "heading": DISCLOSURE_HEADING,
            "limitations": list(LIMITATIONS),
        },
    }


@router.get("/model/methodology")
def methodology() -> dict[str, Any]:
    """White-box methodology sections the UI shows on the Methodology page."""
    return {"sections": explain_model_mechanics().sections()}


@router.get("/scenarios")
def scenarios() -> dict[str, Any]:
    """The calibrated scenario catalog (name, key, params) for the UI."""
    cfg = load_config()
    out: dict[str, Any] = {
        "scenarios": [],
        "simulation": {
            "default_years": cfg.default_years,
            "copula_model": cfg.copula_model,
        },
    }
    for scenario in cfg.scenarios:
        out["scenarios"].append(
            {
                "key": scenario.key,
                "name": scenario.name,
                "frequency_model": scenario.frequency.model,
                "lambda_annual": scenario.frequency.lambda_annual,
                "severity_model": scenario.severity.model,
            }
        )
    return out
