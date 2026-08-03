"""Tests for the white-box model-mechanics explanation.

The agent must be able to explain the internally developed CyberRisk model
(not hedge it as a third-party black box).  These tests lock in that
``explain_model_mechanics()`` returns the four methodology sections, that
they match the configured engine, and that the controller seeds the system
prompt with the white-box statement.
"""

from __future__ import annotations

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.agent.memory import ConversationMemory
from cyberrisk.agent.model_mechanics import ModelMechanics, explain_model_mechanics

# The mandated disclosure that must appear wherever the model is described.
WHITEBOX_STATEMENT = (
    "This assessment uses an internally developed stochastic cyber risk model. "
    "Model assumptions, parameter mappings and simulation logic are documented "
    "within the CyberRisk framework."
)


def test_mechanics_has_four_sections():
    m = explain_model_mechanics()
    assert isinstance(m, ModelMechanics)
    assert set(m.sections()) == {
        "scoring_methodology",
        "frequency_adjustments",
        "severity_adjustments",
        "simulation_methodology",
    }


def test_mechanics_describes_the_real_engine():
    """Each section must reflect the actual configured model, not generic text."""
    m = explain_model_mechanics()
    # Scoring: 18 factors / 6 domains is what scoring_weights.yaml defines.
    assert "18 factor" in m.scoring_methodology
    assert "6 weighted domains" in m.scoring_methodology
    # Frequency: the score -> lambda log-linear link and the 50 reference.
    assert "lambda" in m.frequency_adjustments.lower()
    assert "50" in m.frequency_adjustments
    # Severity: lognormal, revenue-scaled, per-scenario.
    assert "lognormal" in m.severity_adjustments.lower()
    assert "revenue" in m.severity_adjustments.lower()
    # Simulation: Monte Carlo over the configured 100k default years.
    assert "monte carlo" in m.simulation_methodology.lower()
    assert "100,000" in m.simulation_methodology


def test_full_text_contains_whitebox_statement():
    text = explain_model_mechanics().full_text()
    assert WHITEBOX_STATEMENT in text


def test_mechanics_is_reproducible():
    """The explanation must be deterministic across calls (cached)."""
    assert explain_model_mechanics() is explain_model_mechanics()
    assert explain_model_mechanics().sections() == explain_model_mechanics().sections()


def test_controller_seeds_whitebox_system_prompt():
    """The agent's system message must carry the white-box disclosure + pipeline."""
    from cyberrisk.agent.deepseek_client import ChatResponse
    from cyberrisk.agent.schemas import AgentConfig

    class ScriptedClient:
        def __init__(self):
            self.script = [ChatResponse(content="A white-box reply.")]

        def chat(self, messages, tools=None, temperature=None, max_tokens=None):
            return self.script.pop(0)

    agent = CyberRiskAgent(
        client=ScriptedClient(), config=AgentConfig(), memory=ConversationMemory()
    )
    agent.chat("Explain how the model works")

    system = agent.memory.get()[0]
    assert system["role"] == "system"
    content = system["content"]
    assert WHITEBOX_STATEMENT in content
    # The pipeline and the frequency/severity channel guidance are in scope.
    assert "Risk Score" in content and "VaR / ES" in content
    assert "Scenario Frequency" in content and "Severity Distribution" in content
    assert "Access controls primarily influence event frequency" in content
    assert "resilience controls primarily influence severity" in content


def test_controller_exposes_mechanics():
    secs = CyberRiskAgent.explain_model_mechanics()
    assert set(secs) == {
        "scoring_methodology",
        "frequency_adjustments",
        "severity_adjustments",
        "simulation_methodology",
    }
    assert all(isinstance(v, str) and v for v in secs.values())
