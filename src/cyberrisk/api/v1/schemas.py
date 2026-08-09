"""Typed request / result / error schemas for the versioned mobile API.

Every model mirrors the existing validation semantics of the tool layer
(``CompanyBrief`` / ``PolicyInput`` in ``cyberrisk.agent.schemas``).  No new
business rules live here -- these are envelopes that let FastAPI validate and
document the wire shape, exactly like the unversioned ``api/routes.py``
requests.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AssessmentStartRequest(BaseModel):
    """Optional body for ``POST /assessment/start``.

    CompanyBrief-shaped (all fields optional).  Used only to report whether the
    brief already satisfies the loss model's completeness guard; no simulation
    runs.
    """

    firm_name: str | None = None
    industry: str | None = None
    revenue_usd: float | None = Field(default=None, gt=0.0)
    customer_records: int | None = Field(default=None, ge=0)
    technology_dependency: str | None = None
    security_controls: str | None = None
    previous_incidents: int = 0
    existing_coverage: str | None = None
    risk_appetite: str | None = None


class AssessmentSubmitRequest(BaseModel):
    """Body for ``POST /assessment/submit``.

    A CompanyBrief plus the optional Monte Carlo years knob and optional policy
    terms.  Field constraints mirror ``CompanyBrief`` / ``PolicyInput`` /
    ``AgentConfig`` so the v1 layer applies identical validation to the web
    layer.
    """

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

    per_occurrence_deductible: float | None = Field(default=None, ge=0.0)
    per_occurrence_limit: float | None = Field(default=None, ge=0.0)
    annual_aggregate_deductible: float | None = Field(default=None, ge=0.0)
    annual_aggregate_limit: float | None = Field(default=None, ge=0.0)
    coinsurance: float | None = Field(default=None, ge=0.0, lt=1.0)


class ErrorDetail(BaseModel):
    """One field-validation problem (safe: loc + message only)."""

    loc: list[str | int]
    msg: str


class ErrorEnvelope(BaseModel):
    """Consistent error body returned for every non-2xx v1 response."""

    error: dict[str, Any]


class AssessmentResult(BaseModel):
    """The full assessment result payload.

    Documented as a response model so the OpenAPI spec is explicit.  Every
    field maps 1:1 to an existing tool / engine output -- nothing here is
    computed by the API.
    """

    risk_score: float
    risk_category: str
    domain_scores: dict[str, float]
    top_risk_drivers: list[str]
    expected_annual_loss: float
    var_95: float
    var_99: float
    es_95: float
    es_99: float
    pml_1000: float
    insurance_analysis: dict[str, Any]
    mitigation_recommendations: list[dict[str, Any]]
    model_limitations: dict[str, Any]
    evidence: dict[str, Any]
