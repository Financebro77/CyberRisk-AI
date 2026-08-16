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
from typing import TYPE_CHECKING, Any

from cyberrisk.agent.schemas import CompanyBrief, PolicyInput
from cyberrisk.agent.tools import search_incidents
from cyberrisk.api.assessment import (
    compose_assessment,
    mitigation_scenarios,
    model_limitations,
)

logger = logging.getLogger("cyberrisk.api.v1")

# The retriever reads a read-only vector store; build it once per process and
# reuse it across requests (re-opening SQLite + re-reading every vector per
# submit is wasted work).
if TYPE_CHECKING:
    from cyberrisk.knowledge.rag import Retriever

_retriever: Retriever | None = None


def run_assessment_pipeline(
    brief: CompanyBrief,
    *,
    policy: PolicyInput | None = None,
    n_years: int | None = None,
    request_id: str = "",
) -> dict[str, Any]:
    """Run a complete assessment via the shared ``compose_assessment`` and map
    the tool dicts into the versioned result schema.

    Returns either the engine's ``insufficient_info`` guard (HTTP-200 business
    response, no simulation run) or the full result payload under
    ``{"status": "ok", "result": {...}}``.
    """
    out = compose_assessment(brief, policy=policy, n_years=n_years)
    if out["status"] != "ok":
        return out
    result = build_result_payload(
        score_res=out["score"],
        sim_res=out["sim"],
        ins_res=out["ins"],
        contrib=out["contrib"],
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
    mitigation_recommendations = mitigation_scenarios(contrib)

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
        "model_limitations": model_limitations(),
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
    query = " ".join(part for part in (industry, "cyber risk") if part)
    # The top driver (if any) sharpens the search.
    if drivers:
        query = f"{query} {drivers[0]}"

    # 1. RAG semantic search over the knowledge corpus.  The retriever wraps a
    #    read-only vector store — build it once and reuse it across requests.
    try:
        global _retriever
        if _retriever is None:
            from cyberrisk.knowledge.rag import Retriever

            _retriever = Retriever.from_derived(top_k=4)
        chunks = _retriever.retrieve(query) if query else []
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
