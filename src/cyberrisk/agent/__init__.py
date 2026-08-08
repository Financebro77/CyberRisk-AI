"""AI-powered cyber risk consultant agent (provider-agnostic LLM layer).

Sits ON TOP of the quantitative risk engine (src/cyberrisk).  It adds a
tool-calling LLM agent that:

    * asks clarifying questions when the client brief is incomplete,
    * invokes the existing engine as tools (scoring, Monte Carlo loss
      simulation, insurance structuring, report generation),
    * and translates the quantitative results into Marsh/Aon-style
      consultant advice.

The quantitative engine (scoring, calibration, frequency, severity,
simulation, metrics, policy_transform, reporting) is UNCHANGED -- the agent
consumes it read-only through the tool layer in tools.py.

Architecture:

    User -> chat interface (app.py / run_chat.py / cli.py)
         -> LLM client (cyberrisk/llm: OpenAI or DeepSeek via the factory)
         -> CyberRiskAgent (agent_controller.py)
         -> tools (tools.py)
         -> existing engine (compute_score -> simulate -> compute_metrics
                             -> transform_events_to_years -> write_report)

The concrete provider is chosen by the LLM_PROVIDER env var in
cyberrisk/llm/factory.py.  ``deepseek_client`` remains as a backward-
compatibility alias for the DeepSeek provider.
"""

from __future__ import annotations

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.agent.deepseek_client import DeepSeekClient
from cyberrisk.agent.disclosure import (
    DISCLOSURE_HEADING,
    LIMITATIONS,
    append_disclosure,
    disclosure_block,
)
from cyberrisk.agent.model_mechanics import (
    ModelMechanics,
    explain_model_mechanics,
)
from cyberrisk.agent.risk_explanation import (
    ESExplanation,
    VarExplanation,
    contains_forbidden_var_wording,
    explain_expected_shortfall,
    explain_risk_measures,
    explain_var,
)
from cyberrisk.agent.scenario_contribution import (
    ScenarioContribution,
    analyze_scenario_contribution,
    scenario_contribution_summary,
)
from cyberrisk.agent.schemas import AgentConfig, CompanyBrief
from cyberrisk.agent.sensitivity_tools import (
    ControlImprovementResult,
    run_control_improvement_scenario,
)
from cyberrisk.agent.tools import (
    analyse_insurance_structure,
    assess_company_risk,
    build_factor_scores,
    generate_risk_report,
    run_loss_simulation,
)

__all__ = [
    "AgentConfig",
    "CompanyBrief",
    "CyberRiskAgent",
    "DISCLOSURE_HEADING",
    "DeepSeekClient",
    "ESExplanation",
    "LIMITATIONS",
    "ModelMechanics",
    "ScenarioContribution",
    "VarExplanation",
    "analyse_insurance_structure",
    "analyze_scenario_contribution",
    "append_disclosure",
    "assess_company_risk",
    "build_factor_scores",
    "contains_forbidden_var_wording",
    "ControlImprovementResult",
    "disclosure_block",
    "explain_expected_shortfall",
    "explain_model_mechanics",
    "explain_risk_measures",
    "explain_var",
    "generate_risk_report",
    "run_control_improvement_scenario",
    "run_loss_simulation",
    "scenario_contribution_summary",
]
