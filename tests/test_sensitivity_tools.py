"""Tests for the control-improvement sensitivity tool.

The agent can offer to model improvements ("implement MFA") but must NEVER
claim a sensitivity result unless the scenario tool actually ran.  These tests
lock in:

    - supported control changes map to the right factor / target rating,
    - before/after metrics (EAL, VaR99, ES99) and impact are reported,
    - the result is deterministic (same brief -> same output),
    - the tool refuses an incomplete brief and an unsupported control change,
    - a change that would not improve an already-strong control is an honest
      no-op,
    - the agent's prompts only let it claim sensitivity after success.
"""

from __future__ import annotations

import pytest

from cyberrisk.agent.schemas import CompanyBrief
from cyberrisk.agent.sensitivity_tools import (
    _CONTROL_CHANGE_FACTORS,
    ControlImprovementResult,
    normalize_control_change,
    run_control_improvement_scenario,
)

BRIEF = CompanyBrief(
    firm_name="MedTech Health",
    industry="Healthcare",
    revenue_usd=500_000_000,
    customer_records=10_000_000,
    technology_dependency="High",
    security_controls="weak MFA and limited network segmentation",
)

N = 20_000  # small, deterministic Monte Carlo years for fast tests


def _run(change: str, brief: CompanyBrief = BRIEF) -> dict:
    out = run_control_improvement_scenario(brief, change, n_years=N)
    assert out["status"] == "ok", out
    return out


# ---------------------------------------------------------------------------
# Control-change mapping
# ---------------------------------------------------------------------------


def test_supported_control_changes_map_to_factors():
    """Each supported change targets the expected factor + improved rating."""
    assert _CONTROL_CHANGE_FACTORS["implement mfa"] == ("mfa_coverage", "comprehensive")
    assert _CONTROL_CHANGE_FACTORS["improve segmentation"] == ("privileged_access", "segmented")
    assert _CONTROL_CHANGE_FACTORS["reduce privileged access"] == ("privileged_access", "least_privilege")
    assert _CONTROL_CHANGE_FACTORS["add immutable backups"] == ("backup_frequency", "continuous")
    assert _CONTROL_CHANGE_FACTORS["add backups"] == ("backup_frequency", "daily")


def test_normalize_control_change_aliases():
    assert normalize_control_change("implement MFA") == "implement mfa"
    assert normalize_control_change("2fa") == "implement mfa"
    assert normalize_control_change("immutable backups") == "add immutable backups"
    assert normalize_control_change("least privilege") == "reduce privileged access"
    assert normalize_control_change("improve network segmentation") == "improve segmentation"
    assert normalize_control_change("reduce the risk") is None


# ---------------------------------------------------------------------------
# Before / after + impact structure
# ---------------------------------------------------------------------------


def test_control_change_reports_before_after_and_impact():
    out = _run("implement MFA")
    assert out["label"] == "Implement MFA"
    assert out["factor_key"] == "mfa_coverage"
    assert out["target_rating"] == "comprehensive"
    # Before block has the three headline metrics.
    for key in ("eal", "var_99", "es_99"):
        assert key in out["before"] and key in out["after"]
    assert 0 < out["before"]["eal"] < out["before"]["var_99"] < out["before"]["es_99"]
    # Impact has both measures.
    assert "loss_reduction" in out["impact"]
    assert "percentage_improvement" in out["impact"]


def test_control_improvement_does_not_increase_eal():
    """Improving a control must not raise the expected loss."""
    for change in ("implement MFA", "improve segmentation", "reduce privileged access",
                   "add immutable backups", "add backups"):
        out = _run(change)
        assert out["after"]["eal"] <= out["before"]["eal"], change
        assert out["impact"]["loss_reduction"] >= 0.0, change


def test_percentage_improvement_consistency():
    """percentage_improvement == loss_reduction / before_eal (floored at 0).

    Compared against the ROUNDED figures the report actually shows (the tool
    rounds each metric to 2 dp in the payload), so the impact is consistent
    with what the client sees.
    """
    out = _run("implement MFA")
    b, a, imp = out["before"], out["after"], out["impact"]
    # The tool rounds percentage_improvement to 4 dp and loss_reduction to 2 dp,
    # both from the rounded before/after figures the report displays.
    expected_reduction = round(max(0.0, b["eal"] - a["eal"]), 2)
    assert imp["loss_reduction"] == expected_reduction
    expected_pct = round(expected_reduction / b["eal"], 4) if b["eal"] else 0.0
    assert imp["percentage_improvement"] == expected_pct


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_result_is_deterministic():
    """Same brief + same change + same seed -> identical output."""
    a = run_control_improvement_scenario(BRIEF, "implement MFA", n_years=N)
    b = run_control_improvement_scenario(BRIEF, "implement MFA", n_years=N)
    assert a == b


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_refuses_incomplete_brief():
    """Without revenue + controls the tool must ask, not model an assumption."""
    partial = CompanyBrief(firm_name="MedTech", industry="Healthcare")
    out = run_control_improvement_scenario(partial, "implement MFA", n_years=N)
    assert out["status"] == "insufficient_info"
    assert "revenue_usd" in out["needed"]
    assert "security_controls" in out["needed"]


def test_refuses_unsupported_control_change():
    out = run_control_improvement_scenario(BRIEF, "harden the network", n_years=N)
    assert out["status"] == "unknown_control_change"
    assert "not supported" in out["message"]


def test_no_op_when_control_already_strong():
    """A change that would not improve an already-strong control is a no-op."""
    strong = CompanyBrief(
        firm_name="Clean Co",
        industry="Manufacturing",
        revenue_usd=500_000_000,
        security_controls="strong MFA, comprehensive backups, full segmentation",
    )
    out = run_control_improvement_scenario(strong, "implement MFA", n_years=N)
    # Already comprehensive MFA -> the tool must not downgrade or claim an impact.
    assert out["status"] == "ok"
    assert out["impact"]["percentage_improvement"] == 0.0
    assert out["after"] == out["before"]


# ---------------------------------------------------------------------------
# Result dataclass invariants
# ---------------------------------------------------------------------------


def test_result_object_math():
    r = ControlImprovementResult(
        control_change="implement mfa", label="Implement MFA",
        factor_key="mfa_coverage", target_rating="comprehensive",
        before_eal=100.0, before_var_99=200.0, before_es_99=300.0,
        after_eal=80.0, after_var_99=180.0, after_es_99=280.0,
    )
    assert r.loss_reduction == 20.0
    assert r.percentage_improvement == pytest.approx(0.2)
    d = r.to_dict()
    assert d["impact"]["loss_reduction"] == 20.0
    assert d["impact"]["percentage_improvement"] == pytest.approx(0.2)


def test_result_object_no_negative_reduction():
    """If the 'improvement' raised EAL (shouldn't happen), reduction is floored at 0."""
    r = ControlImprovementResult(
        control_change="x", label="X", factor_key="k", target_rating="t",
        before_eal=80.0, before_var_99=100.0, before_es_99=120.0,
        after_eal=100.0, after_var_99=130.0, after_es_99=150.0,
    )
    assert r.loss_reduction == 0.0
    assert r.percentage_improvement == 0.0


# ---------------------------------------------------------------------------
# Prompt / controller integration
# ---------------------------------------------------------------------------


def test_system_prompt_only_claims_sensitivity_after_success():
    from cyberrisk.agent.prompts import GROUNDING_REMINDER, SYSTEM_PROMPT

    assert "run_control_improvement_scenario" in SYSTEM_PROMPT
    assert "seven tools" in SYSTEM_PROMPT
    # The hard rule: no sensitivity claim until the tool returned ok.
    assert "may only report a control-change impact" in SYSTEM_PROMPT
    assert "never invent the improvement's effect" in SYSTEM_PROMPT.lower()
    assert "run_control_improvement_scenario actually ran" in GROUNDING_REMINDER


def test_tool_is_in_controller_schema():
    from cyberrisk.agent.tools import TOOL_SCHEMAS

    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert "run_control_improvement_scenario" in names
    schema = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "run_control_improvement_scenario")
    props = schema["function"]["parameters"]["properties"]
    assert "control_change" in props
    assert "n_years" in props


def test_controller_executes_scenario_tool():
    """The bounded tool loop runs the scenario tool and returns its result."""
    from cyberrisk.agent.agent_controller import CyberRiskAgent
    from cyberrisk.agent.deepseek_client import ChatResponse
    from cyberrisk.agent.memory import ConversationMemory
    from cyberrisk.agent.schemas import AgentConfig

    class ScriptedClient:
        def __init__(self):
            self.script = [
                ChatResponse(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_1",
                            "name": "run_control_improvement_scenario",
                            "arguments": {
                                "industry": "Healthcare",
                                "revenue_usd": 500_000_000,
                                "customer_records": 10_000_000,
                                "technology_dependency": "High",
                                "security_controls": "weak MFA and limited network segmentation",
                                "control_change": "implement MFA",
                            },
                        }
                    ],
                ),
                ChatResponse(content="Implementing MFA reduces the modelled EAL."),
            ]

        def chat(self, messages, tools=None, temperature=None, max_tokens=None):
            self.last_tools = tools
            return self.script.pop(0)

    client = ScriptedClient()
    agent = CyberRiskAgent(
        client=client, config=AgentConfig(max_tool_rounds=8), memory=ConversationMemory()
    )
    agent.chat("Model the impact of implementing MFA")

    tool_msgs = [m for m in agent.memory.get() if m.get("role") == "tool"]
    assert tool_msgs, "scenario tool result missing from memory"
    payload = tool_msgs[-1]["content"]
    assert '"before"' in payload and '"after"' in payload and '"impact"' in payload
    names = [t["function"]["name"] for t in client.last_tools]
    assert "run_control_improvement_scenario" in names
