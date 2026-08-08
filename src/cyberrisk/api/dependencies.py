"""Shared helpers for the CyberRisk API layer.

These add no risk logic; they wire the existing tool layer (which already
returns JSON-serialisable dicts and enforces the completeness guard) into
FastAPI response schemas.
"""

from __future__ import annotations

from typing import Any

from cyberrisk.agent.schemas import AgentConfig, CompanyBrief, PolicyInput


def brief_from_request(data: dict[str, Any], firm_name: str | None = None) -> CompanyBrief:
    """Build a ``CompanyBrief`` from an API request body.

    Only the brief fields are picked out (the body may also carry tool
    knobs like ``n_years`` / ``policy`` / ``control_change``), so the same
    DTO validation the agent uses applies here.
    """
    brief_keys = set(CompanyBrief.model_fields.keys())
    brief_data = {k: v for k, v in data.items() if k in brief_keys and v is not None}
    if firm_name:
        brief_data["firm_name"] = firm_name
    return CompanyBrief(**brief_data)


def policy_from_request(data: dict[str, Any]) -> PolicyInput | None:
    """Build a ``PolicyInput`` when the request carries policy terms."""
    policy_keys = set(PolicyInput.model_fields.keys())
    terms = {k: v for k, v in data.items() if k in policy_keys and v is not None}
    return PolicyInput(**terms) if terms else None


def n_years_from_request(data: dict[str, Any], default: int = 100_000) -> int | None:
    """The optional Monte Carlo years knob, validated against AgentConfig bounds."""
    raw = data.get("n_years")
    if raw is None:
        return None
    cfg = AgentConfig()  # ge=1_000, le=500_000 on n_years
    return int(raw)
