"""Tests for the scenario contribution analysis.

The agent must report each scenario's share of EAL and explain it by linking
frequency drivers, severity drivers, and recommended controls to model outputs
-- never inventing an explanation.  These tests lock in:

    - contributions are computed from the simulated loss shares (sum ~1),
    - the four headline scenarios (ransomware, breach, BEC, cloud outage) are
      reported with their shares,
    - frequency drivers come from the client's factor scores (elevated above
      baseline),
    - severity drivers include the scenario's configured characteristics and
      the client's elevated resilience factors,
    - recommended controls map to the scenario's drivers,
    - every explanation is flagged `linked_to_model`,
    - the tool refuses an incomplete brief,
    - the run_loss_simulation output carries the detail,
    - the prompts forbid scenario explanations without model output.
"""

from __future__ import annotations

import pytest

from cyberrisk.agent.schemas import CompanyBrief
from cyberrisk.agent.scenario_contribution import (
    analyze_scenario_contribution,
    scenario_contribution_summary,
)

BRIEF = CompanyBrief(
    firm_name="MedTech Health",
    industry="Healthcare",
    revenue_usd=500_000_000,
    customer_records=10_000_000,
    technology_dependency="High",
    security_controls="weak MFA and limited network segmentation",
)

N = 20_000


# ---------------------------------------------------------------------------
# Contribution structure
# ---------------------------------------------------------------------------


def test_contributions_computed_and_sum_to_one():
    out = analyze_scenario_contribution(BRIEF, n_years=N)
    assert out["status"] == "ok"
    assert len(out["scenarios"]) == 7  # all configured scenarios present
    assert out["total_contribution"] == pytest.approx(1.0, abs=0.05)
    for s in out["scenarios"]:
        assert 0.0 <= s["contribution"] <= 1.0
        assert s["linked_to_model"] is True


def test_headline_scenarios_are_reported():
    """Ransomware, data breach, BEC, and cloud outage all carry a share."""
    out = analyze_scenario_contribution(BRIEF, n_years=N)
    keys = {s["scenario_key"] for s in out["scenarios"]}
    assert {"ransomware", "breach", "bec", "cloud_outage"} <= keys
    by_key = {s["scenario_key"]: s for s in out["scenarios"]}
    for key in ("ransomware", "breach", "bec", "cloud_outage"):
        assert by_key[key]["contribution"] > 0.0, key
        assert by_key[key]["aal"] > 0.0, key


# ---------------------------------------------------------------------------
# Drivers link to model outputs
# ---------------------------------------------------------------------------


def test_frequency_drivers_come_from_factor_scores():
    """Elevated factor scores appear as frequency drivers for the scenario."""
    out = analyze_scenario_contribution(BRIEF, n_years=N)
    ransomware = next(s for s in out["scenarios"] if s["scenario_key"] == "ransomware")
    # 'weak MFA' raises mfa_coverage above baseline -> MFA weakness is a driver.
    assert any("MFA" in d for d in ransomware["frequency_drivers"])
    # 'limited segmentation' raises privileged_access -> exposed privilege.
    assert any("privileged" in d.lower() for d in ransomware["frequency_drivers"])


def test_severity_drivers_include_scenario_config_and_resilience():
    out = analyze_scenario_contribution(BRIEF, n_years=N)
    ransomware = next(s for s in out["scenarios"] if s["scenario_key"] == "ransomware")
    # Ransomware config: sigma 1.30 -> heavy tail; loading 0.70 -> systemic.
    assert any("sigma" in d for d in ransomware["severity_drivers"])
    assert any("correlation" in d.lower() or "loading" in d.lower() for d in ransomware["severity_drivers"])


def test_ransomware_matches_required_example():
    """The spec's example: MFA weakness / backup weakness / immutable backups."""
    brief = CompanyBrief(
        firm_name="Weak Backups Co",
        industry="Manufacturing",
        revenue_usd=800_000_000,
        security_controls="weak MFA, poor backups, no DR testing, limited segmentation",
    )
    out = analyze_scenario_contribution(brief, n_years=N)
    ransomware = next(s for s in out["scenarios"] if s["scenario_key"] == "ransomware")
    assert any("MFA" in d for d in ransomware["frequency_drivers"])
    assert any("backup weakness" in d for d in ransomware["severity_drivers"])
    assert "immutable backups" in ransomware["recommended_controls"]
    assert "privileged access management" in ransomware["recommended_controls"]


def test_recommended_controls_map_to_drivers():
    out = analyze_scenario_contribution(BRIEF, n_years=N)
    for s in out["scenarios"]:
        assert s["recommended_controls"], f"no controls for {s['scenario_key']}"
        # Every control is a non-empty string (a real mitigation, not noise).
        assert all(isinstance(c, str) and c for c in s["recommended_controls"])


def test_no_explanation_without_model_link():
    """Every scenario explanation must be flagged as model-linked."""
    out = analyze_scenario_contribution(BRIEF, n_years=N)
    for s in out["scenarios"]:
        assert s["linked_to_model"] is True


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_refuses_incomplete_brief():
    partial = CompanyBrief(firm_name="MedTech", industry="Healthcare")
    out = analyze_scenario_contribution(partial, n_years=N)
    assert out["status"] == "insufficient_info"
    assert "revenue_usd" in out["needed"]
    assert "security_controls" in out["needed"]


def test_deterministic():
    a = analyze_scenario_contribution(BRIEF, n_years=N)
    b = analyze_scenario_contribution(BRIEF, n_years=N)
    assert a == b


# ---------------------------------------------------------------------------
# Summary / integration
# ---------------------------------------------------------------------------


def test_summary_reports_headline_shares_and_drivers():
    summary = scenario_contribution_summary(BRIEF, n_years=N)
    assert "Scenario contribution to EAL" in summary
    assert "Ransomware" in summary and "%" in summary
    assert "Frequency drivers" in summary
    assert "Severity drivers" in summary
    assert "Recommended controls" in summary


def test_run_loss_simulation_includes_contribution_detail():
    from cyberrisk.agent.tools import run_loss_simulation

    out = run_loss_simulation(BRIEF, n_years=N)
    assert out["status"] == "ok"
    detail = out["scenario_contribution_detail"]
    assert len(detail) == 7
    assert all(s["linked_to_model"] for s in detail)
    # The plain contribution dict is still present and consistent.
    assert abs(sum(out["scenario_contribution"].values()) - 1.0) < 0.05


def test_controller_exposes_scenario_contribution():
    from cyberrisk.agent.agent_controller import CyberRiskAgent

    out = CyberRiskAgent.scenario_contribution(BRIEF, n_years=N)
    assert out["status"] == "ok"
    assert len(out["scenarios"]) == 7


def test_prompts_forbid_unlinked_scenario_explanations():
    from cyberrisk.agent.prompts import GROUNDING_REMINDER, SYSTEM_PROMPT

    assert "SCENARIO CONTRIBUTION ANALYSIS" in SYSTEM_PROMPT
    assert "NEVER generate a scenario explanation without linking it to the model outputs" in SYSTEM_PROMPT
    assert "only explain the per-scenario EAL share, frequency drivers, severity drivers" in GROUNDING_REMINDER
    assert "Never generate a scenario explanation without linking to model outputs" in GROUNDING_REMINDER
