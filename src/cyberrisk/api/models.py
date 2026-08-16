"""Shared request models for the web and versioned APIs.

The two API surfaces -- the web ``/api/*`` routes and the mobile ``/api/v1/*``
assessment routes -- accept the same company-brief-shaped bodies, so the brief
fields are defined ONCE here and inherited by both families of request models.
Field constraints mirror ``cyberrisk.agent.schemas.CompanyBrief`` /
``PolicyInput`` exactly (revenue > 0, non-negative records/incidents, bounded
``n_years``, ``coinsurance < 1``), so the FastAPI boundary applies identical
validation everywhere without re-declaring the fields per endpoint.

These are wire models, not DTOs: ``firm_name`` stays optional (``None``) where
the agent-side ``CompanyBrief`` defaults to ``""``, and nothing here runs the
completeness guard -- that lives in the tool layer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# The Monte Carlo years knob bounds, shared by the request schemas and the
# unvalidated-dict guard (dependencies.n_years_from_request) so they cannot
# drift apart.
MIN_N_YEARS = 1_000
MAX_N_YEARS = 500_000


class CompanyBriefRequest(BaseModel):
    """A client brief for any scoring / modelling endpoint.

    All fields optional -- scoring works on partial briefs and reports what
    was assumed.  Mirrors ``CompanyBrief``'s field constraints.
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


class SimulationKnobs(BaseModel):
    """The optional Monte Carlo years override shared by simulate-family bodies."""

    n_years: int | None = Field(default=None, ge=MIN_N_YEARS, le=MAX_N_YEARS)


class PolicyTerms(BaseModel):
    """Optional policy terms shared by insurance-family bodies."""

    per_occurrence_deductible: float | None = Field(default=None, ge=0.0)
    per_occurrence_limit: float | None = Field(default=None, ge=0.0)
    annual_aggregate_deductible: float | None = Field(default=None, ge=0.0)
    annual_aggregate_limit: float | None = Field(default=None, ge=0.0)
    coinsurance: float | None = Field(default=None, ge=0.0, lt=1.0)
