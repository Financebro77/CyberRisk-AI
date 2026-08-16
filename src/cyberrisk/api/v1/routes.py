"""Versioned mobile API routes (``/api/v1``).

Thin HTTP envelope over the existing tool layer -- no risk logic lives here.
The assessment lifecycle:

    POST /assessment/start     -> id + required fields (no compute)
    POST /assessment/submit    -> full result (or insufficient_info guard)
    GET  /assessment/{id}      -> status view
    GET  /assessment/{id}/results -> full result payload

Auth + rate limiting are inherited from the existing ``APIGatewayMiddleware``
(it guards every ``/api/*`` path).  ``/api/v1/health`` is exempt so load
balancers / probes can reach it without a key.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from cyberrisk import __version__

from cyberrisk.api.dependencies import (
    brief_from_request,
    n_years_from_request,
    policy_from_request,
)
from cyberrisk.api.v1.middleware import get_request_id
from cyberrisk.api.v1.schemas import AssessmentStartRequest, AssessmentSubmitRequest
from cyberrisk.api.v1.service import run_assessment_pipeline
from cyberrisk.api.v1.store import AssessmentStore, get_store

router = APIRouter(tags=["v1"])


@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe for the versioned API (auth-exempt)."""
    return {
        "status": "ok",
        "service": "CyberRisk AI",
        "version": __version__,
        "api_version": "v1",
    }


@router.post(
    "/assessment/start",
    status_code=201,
    response_model=None,
)
def assessment_start(
    req: AssessmentStartRequest | None = None,
    store: AssessmentStore = Depends(get_store),
) -> dict[str, Any]:
    """Begin an assessment: return an id + the fields the loss model requires.

    Accepts an optional CompanyBrief-shaped body; if it already satisfies the
    completeness guard the status is ``"ready"`` with empty ``required_fields``,
    otherwise ``"pending"`` with the missing fields listed.  No simulation runs.
    """
    data = req.model_dump() if req is not None else {}
    brief = brief_from_request(data)
    missing = brief.missing_for_simulation()

    assessment_id = uuid.uuid4().hex
    status = "ready" if not missing else "pending"
    entry = store.create(assessment_id, status=status, required_fields=missing)
    return {
        "assessment_id": entry.assessment_id,
        "status": entry.status,
        "required_fields": entry.required_fields,
    }


@router.post(
    "/assessment/submit",
    status_code=201,
    response_model=None,
)
def assessment_submit(
    request: Request,
    req: AssessmentSubmitRequest,
    store: AssessmentStore = Depends(get_store),
) -> dict[str, Any]:
    """Run a full assessment for the submitted brief and store the result.

    Returns the full ``result`` payload in the response (one round-trip) so a
    mobile client does not need a second request.  When the brief cannot be
    modelled, returns the completeness guard with ``status:
    "insufficient_info"`` and the ``needed`` fields -- no simulation runs.
    """
    request_id = get_request_id(request.scope)
    data = req.model_dump()
    brief = brief_from_request(data)
    policy = policy_from_request(data)
    n_years = n_years_from_request(data)

    assessment_id = uuid.uuid4().hex
    # The pipeline runs the completeness guard itself (via run_loss_simulation);
    # no pre-check here so the required-fields list + message live in one place.
    outcome = run_assessment_pipeline(
        brief,
        policy=policy,
        n_years=n_years,
        request_id=request_id,
    )
    status = outcome.get("status", "error")
    if status != "ok":
        # Persist the guard / error outcome so a status poll sees it, then
        # return the same shape the client needs to ask for missing fields.
        needed = outcome.get("needed", [])
        message = outcome.get("message", "Assessment could not be completed.")
        store.store_result(assessment_id, status, needed=needed, message=message)
        return {
            "assessment_id": assessment_id,
            "status": status,
            "needed": needed,
            "message": message,
        }
    store.store_result(assessment_id, "ok", result=outcome["result"])
    return {
        "assessment_id": assessment_id,
        "status": "ok",
        "result": outcome["result"],
    }


@router.get(
    "/assessment/{assessment_id}",
    response_model=None,
)
def assessment_status(
    assessment_id: str,
    store: AssessmentStore = Depends(get_store),
) -> dict[str, Any]:
    """Status view for an assessment (never the full result)."""
    entry = store.get(assessment_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Assessment not found or expired.")
    out: dict[str, Any] = {
        "assessment_id": entry.assessment_id,
        "status": entry.status,
        "created_at": _iso(entry.created_at),
    }
    if entry.status == "insufficient_info":
        out["needed"] = entry.needed
        out["message"] = entry.message
    elif entry.status == "pending":
        out["required_fields"] = entry.required_fields
    return out


@router.get(
    "/assessment/{assessment_id}/results",
    response_model=None,
)
def assessment_results(
    assessment_id: str,
    store: AssessmentStore = Depends(get_store),
) -> dict[str, Any]:
    """The full result payload for a finished assessment."""
    entry = store.get_result(assessment_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Assessment not found, expired, or not yet completed.")
    return {
        "assessment_id": entry.assessment_id,
        "status": entry.status,
        "result": entry.result,
    }


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
