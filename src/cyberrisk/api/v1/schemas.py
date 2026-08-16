"""Typed request / result / error schemas for the versioned mobile API.

Request bodies inherit the shared brief / knob / policy-term fields from
``cyberrisk.api.models`` (mirroring ``CompanyBrief`` / ``PolicyInput`` in
``cyberrisk.agent.schemas``).  No new business rules live here -- these are
envelopes that let FastAPI validate and document the wire shape, exactly like
the unversioned ``api/routes.py`` requests.
"""

from __future__ import annotations

from cyberrisk.api.models import CompanyBriefRequest, PolicyTerms, SimulationKnobs


class AssessmentStartRequest(CompanyBriefRequest):
    """Optional body for ``POST /assessment/start``.

    CompanyBrief-shaped (all fields optional).  Used only to report whether the
    brief already satisfies the loss model's completeness guard; no simulation
    runs.
    """


class AssessmentSubmitRequest(CompanyBriefRequest, SimulationKnobs, PolicyTerms):
    """Body for ``POST /assessment/submit``.

    A CompanyBrief plus the optional Monte Carlo years knob and optional policy
    terms.  Field constraints mirror ``CompanyBrief`` / ``PolicyInput`` (the
    knob bounds live in ``cyberrisk.api.models``) so the v1 layer applies
    identical validation to the web layer.
    """
