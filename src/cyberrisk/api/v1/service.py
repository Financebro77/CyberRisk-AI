"""Assessment pipeline composition for the versioned mobile API.

This module is a THIN composition layer.  It calls the existing, already-tested
tool functions read-only (the same seam the unversioned web API uses) and maps
their dict outputs into the versioned result schema.  No risk logic, no Monte
Carlo, no scoring, no RAG pipeline is re-implemented here.

The completeness guard (``{"status": "insufficient_info", ...}``) is passed
through unchanged so a client knows exactly which fields to ask for.
"""

from __future__ import annotations

import logging
from typing import Any

from cyberrisk.agent.disclosure import DISCLOSURE_HEADING, LIMITATIONS
from cyberrisk.agent.scenario_contribution import analyze_scenario_contribution
from cyberrisk.agent.schemas import CompanyBrief, PolicyInput
from cyberrisk.agent.tools import (
    analyse_insurance_structure,
    assess_company_risk,
    run_loss_simulation,
    search_incidents,
)

logger = logging.getLogger("cyberrisk.api.v1")

# The loss model cannot run without these (CompanyBrief.missing_for_simulation).
# The engine's completeness guard is the single source of truth; this is only a
# fallback for evidence gathering when the guard was not hit.
_REQUIRED_BRIEF_FIELDS = ("revenue_usd", "security_controls")


def run_assessment_pipeline(
    brief: CompanyBrief,
    *,
    policy: PolicyInput | None = None,
    n_years: int | None = None,
    request_id: str = "",
) -> dict[str, Any]:
    """Run a complete assessment: score -> simulate -> insurance -> contribution.

    Returns either the engine's ``insufficient_info`` guard (HTTP-200 business
    response, no simulation run) or the full result payload under
    ``{"status": "ok", "result": {...}}``.
    """
    # 1. Risk score + drivers (deterministic, works on partial briefs).
    score_res = assess_company_risk(brief)
    # 2. Monte Carlo loss simulation (guarded).
    sim_res = run_loss_simulation(brief, n_years=n_years)
    if sim_res.get("status") == "insufficient_info":
        return {
            "status": "insufficient_info",
            "needed": sim_res.get("needed", []),
            "message": sim_res.get("message", "Insufficient information to model the loss."),
        }
    # 3. Insurance adequacy with the requested policy terms (or defaults).
    ins_res = analyse_insurance_structure(brief, policy=policy, n_years=n_years)
    # 4. Scenario contribution -> model-linked mitigation roadmap.
    contrib = analyze_scenario_contribution(brief, n_years=n_years)

    result = build_result_payload(
        score_res=score_res,
        sim_res=sim_res,
        ins_res=ins_res,
        contrib=contrib,
        brief=brief,
        request_id=request_id,
    )
    return {"status": "ok", "result": result}


def build_result_payload(
    *,
    score_res: dict[str, Any],
    sim_res: dict[str, Any],
    ins_res: dict[str, Any],
    contrib: dict[str, Any],
    brief: CompanyBrief,
    request_id: str = "",
) -> dict[str, Any]:
    """Map the tool dicts into the versioned result schema.

    Pure mapping -- every value comes from an existing tool output.  The only
    rename is ``pml_1in1000`` (the engine key for the 1-in-1000-year PML) to the
    API name ``pml_1000``.
    """
    mitigation_recommendations = contrib.get("scenarios", []) if contrib.get("status") == "ok" else []

    return {
        "risk_score": score_res.get("risk_score"),
        "risk_category": score_res.get("risk_category"),
        "domain_scores": score_res.get("domain_scores", {}),
        "top_risk_drivers": score_res.get("risk_drivers", []),
        "expected_annual_loss": sim_res.get("eal"),
        "var_95": sim_res.get("var_95"),
        "var_99": sim_res.get("var_99"),
        "es_95": sim_res.get("es_95"),
        "es_99": sim_res.get("es_99"),
        "pml_1000": sim_res.get("pml_1in1000"),
        "insurance_analysis": {
            "ground_up_loss": ins_res.get("ground_up_loss"),
            "policy": ins_res.get("policy"),
            "insurance_response": ins_res.get("insurance_response"),
            "client_retained_loss": ins_res.get("client_retained_loss"),
            "evaluation": ins_res.get("evaluation"),
        },
        "mitigation_recommendations": mitigation_recommendations,
        "model_limitations": {
            "heading": DISCLOSURE_HEADING,
            "limitations": list(LIMITATIONS),
        },
        "evidence": gather_evidence(brief, score_res, request_id=request_id),
    }


def gather_evidence(
    brief: CompanyBrief,
    score_res: dict[str, Any],
    *,
    request_id: str = "",
) -> dict[str, Any]:
    """Gather supporting evidence: RAG knowledge chunks + historical incidents.

    Both sources are wrapped so the API degrades gracefully when the knowledge
    store is absent (e.g. CI without ``knowledge/derived/vector.db``) -- it
    returns an empty ``citations`` list with a note, never an exception.

    Returns
        {"citations": [...], "incidents": [...], "note": str}
    """
    citations: list[dict[str, Any]] = []
    incidents: list[dict[str, Any]] = []
    note = ""

    # Topic-aware retrieval queries built from the brief + top risk drivers.
    industry = brief.industry or ""
    drivers = score_res.get("risk_drivers", []) or []
    query = " ".join(
        part
        for part in (industry, "cyber risk")
        if part
    )
    # The top driver (if any) sharpens the search.
    if drivers:
        query = f"{query} {drivers[0]}".strip()

    # 1. RAG semantic search over the knowledge corpus.
    try:
        from cyberrisk.knowledge.rag import Retriever

        retriever = Retriever.from_derived(top_k=4)
        chunks = retriever.retrieve(query) if query else []
        seen: set[str] = set()
        for chunk in chunks:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            citations.append(
                {
                    "doc_id": chunk.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "title": chunk.title,
                    "source": chunk.source,
                    "score": round(float(chunk.score), 4),
                    "content": chunk.content[:400],  # trim to keep responses lean
                }
            )
    except FileNotFoundError:
        note = "Knowledge base not available; evidence omitted."
        logger.warning("evidence skipped (no vector store): request_id=%s", request_id)
    except Exception:  # noqa: BLE001 - evidence must never break the assessment
        note = "Knowledge base temporarily unavailable; evidence omitted."
        logger.exception("evidence RAG lookup failed: request_id=%s", request_id)

    # 2. Historical incidents (filesystem-independent, always available).
    try:
        incident_res = search_incidents(industry=industry or None, limit=3)
        if incident_res.get("status") == "ok":
            incidents = incident_res.get("incidents", [])
    except Exception:  # noqa: BLE001
        logger.exception("incident lookup failed: request_id=%s", request_id)

    return {
        "citations": citations,
        "incidents": incidents,
        "note": note,
    }
