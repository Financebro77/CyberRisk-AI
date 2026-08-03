"""Data models for the AI consultant agent.

Two families of models live here:

1. **Client-facing conversation models** -- `CompanyBrief` is the agent's
   running picture of the client, accumulated from the conversation.  Its
   fields deliberately mirror the eight elicitation dimensions already used
   by the rule-based consultant in ``src/agent/elicitation.py`` (industry,
   revenue, customer records, technology dependency, security controls,
   previous incidents, existing coverage, risk appetite), so the two
   consultant implementations speak the same client language.

2. **Tool input / output DTOs** -- structured envelopes for the engine calls
   the agent can make.  Tool outputs are always JSON-serialisable (floats /
   lists / strings), so they can be embedded directly in an LLM tool-call
   response.

Models are Pydantic v2, matching the engine's config-model convention
(validation lives on the input boundary).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------


class AgentConfig(BaseModel):
    """Runtime knobs for the DeepSeek consultant agent."""

    model: str = Field(default="deepseek-chat", description="DeepSeek model id")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)
    max_tool_rounds: int = Field(default=6, ge=1, le=12)
    n_years: int = Field(default=100_000, ge=1_000, description="Monte Carlo years")


# ---------------------------------------------------------------------------
# Client brief (conversational company profile)
# ---------------------------------------------------------------------------


class CompanyBrief(BaseModel):
    """The agent's running picture of a client, built from conversation.

    Fields map to the eight elicitation dimensions of the rule-based
    consultant.  All are optional -- a missing field means the agent should
    ASK before modelling (see tools.run_loss_simulation's completeness
    guard).
    """

    firm_name: str = ""
    industry: str | None = Field(
        default=None, description="e.g. 'Healthcare', 'Manufacturing', 'Financial services'"
    )
    revenue_usd: float | None = Field(
        default=None, gt=0.0, description="Annual revenue in USD"
    )
    customer_records: int | None = Field(
        default=None, ge=0, description="Number of customer / personal records held"
    )
    technology_dependency: str | None = Field(
        default=None, description="e.g. 'High', 'Moderate', 'Low'"
    )
    security_controls: str | None = Field(
        default=None,
        description="Free-text description of security posture, e.g. 'weak MFA and limited network segmentation'",
    )
    previous_incidents: int = Field(default=0, ge=0)
    existing_coverage: str | None = Field(
        default=None, description="Current cyber insurance, e.g. '$5M limit, $500k retention'"
    )
    risk_appetite: str | None = Field(
        default=None, description="Stated retention willingness, e.g. 'retain up to $1.5M'"
    )

    @model_validator(mode="after")
    def _require_name(self) -> CompanyBrief:
        return self

    def merge(self, other: "CompanyBrief") -> "CompanyBrief":
        """Return a new brief with `other`'s provided fields layered on top.

        Used to accumulate facts across conversation turns.  A field in
        `other` only overrides when it is genuinely provided (not None /
        empty / unknown), so a later vague answer never erases a solid one.
        """
        data = self.model_dump()
        for key, value in other.model_dump().items():
            if _is_provided(value):
                data[key] = value
        return CompanyBrief(**data)

    def missing_for_simulation(self) -> list[str]:
        """The fields the loss engine needs but the client has not given.

        Revenue and security controls are the two inputs that materially
        change the simulated loss; without them the agent must ask rather
        than invent a profile.
        """
        missing = []
        if self.revenue_usd is None:
            missing.append("revenue_usd")
        if not _is_provided(self.security_controls):
            missing.append("security_controls")
        return missing

    def to_tool_input(self) -> dict[str, Any]:
        """JSON view for tool arguments (only genuinely provided fields)."""
        return {
            k: v
            for k, v in self.model_dump().items()
            if _is_provided(v) and k != "firm_name"
        }


def _is_provided(value: object) -> bool:
    """A field counts as provided if it is non-empty and not an 'unknown' sentinel.

    Mirrors the semantics of agent.elicitation._is_provided so both
    consultants agree on what counts as a real answer.
    """
    if value is None:
        return False
    if isinstance(value, str):
        s = value.strip().lower()
        return s not in ("", "unknown", "n/a", "not sure", "?", "tbd", "to be determined", "unspecified")
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


# ---------------------------------------------------------------------------
# Tool DTOs
# ---------------------------------------------------------------------------


class AssessInput(BaseModel):
    """Arguments for assess_company_risk (subset of the brief that drives scoring)."""

    industry: str | None = None
    security_controls: str | None = Field(
        default=None, description="Free-text security posture, e.g. 'weak MFA'"
    )
    customer_records: int | None = None
    technology_dependency: str | None = None
    previous_incidents: int = 0
    existing_coverage: str | None = None
    risk_appetite: str | None = None


class SimulateInput(BaseModel):
    """Arguments for run_loss_simulation."""

    industry: str | None = None
    revenue_usd: float | None = None
    customer_records: int | None = None
    technology_dependency: str | None = None
    security_controls: str | None = Field(
        default=None, description="Free-text security posture; required to run"
    )
    previous_incidents: int = 0
    existing_coverage: str | None = None
    risk_appetite: str | None = None
    n_years: int | None = Field(default=None, ge=1_000, le=500_000)


class PolicyInput(BaseModel):
    """Arguments for analyse_insurance_structure."""

    per_occurrence_deductible: float = Field(default=250_000.0, ge=0.0)
    per_occurrence_limit: float | None = Field(default=5_000_000.0, ge=0.0)
    annual_aggregate_deductible: float = Field(default=1_000_000.0, ge=0.0)
    annual_aggregate_limit: float | None = Field(default=20_000_000.0, ge=0.0)
    coinsurance: float = Field(default=0.0, ge=0.0, lt=1.0)


class ReportInput(BaseModel):
    """Arguments for generate_risk_report."""

    firm_name: str = Field(default="Client")
    out_dir: str | None = Field(default=None, description="Output directory (default data/output)")


# ---------------------------------------------------------------------------
# Tool result envelope
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """A single tool invocation outcome passed back to the LLM."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    def as_tool_message(self, tool_call_id: str) -> dict[str, Any]:
        """OpenAI/DeepSeek `role: tool` message for this result."""
        payload: dict[str, Any] = {"status": "ok", **self.data} if self.ok else {
            "status": "error", "error": self.error or "unknown tool error"
        }
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": __import__("json").dumps(payload, ensure_ascii=False),
        }
