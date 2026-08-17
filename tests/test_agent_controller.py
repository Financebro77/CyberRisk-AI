"""Agent controller tests using a scripted fake DeepSeek client.

No network.  The fake client plays back a planned script of responses: first
a round of tool calls, then a final text answer.  The controller must
execute the tools against the real engine, inject the results, and return
the final text -- proving the loop works without a live API.
"""

from __future__ import annotations

import pytest

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.agent.deepseek_client import ChatResponse
from cyberrisk.agent.disclosure import disclosure_block
from cyberrisk.agent.memory import ConversationMemory
from cyberrisk.agent.schemas import AgentConfig


class ScriptedClient:
    """Plays back a script of ChatResponses, recording each request."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.request_count = 0

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        self.requests.append(messages)
        self.request_count += 1
        if not self.script:
            return ChatResponse(content="done")
        return self.script.pop(0)


def _tool_call(name: str, arguments: dict, call_id: str = "call_x") -> dict:
    return {"id": call_id, "name": name, "arguments": arguments}


def _make_agent(script) -> CyberRiskAgent:
    client = ScriptedClient(script)
    config = AgentConfig(max_tool_rounds=8)
    return CyberRiskAgent(client=client, config=config, memory=ConversationMemory())


def test_agent_executes_tools_then_answers():
    script = [
        ChatResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "run_loss_simulation",
                    {
                        "industry": "Healthcare",
                        "revenue_usd": 500_000_000,
                        "customer_records": 10_000_000,
                        "security_controls": "weak MFA and limited network segmentation",
                    },
                    call_id="call_1",
                )
            ],
        ),
        ChatResponse(content="The client's EAL is $X and VaR 99 is $Y."),
    ]
    agent = _make_agent(script)

    answer = agent.chat("Assess a healthcare company with weak MFA.")
    assert "EAL" in answer

    # The tool result must have been injected into memory as a tool message.
    roles = [m["role"] for m in agent.memory.get()]
    assert "tool" in roles
    # The assistant tool_calls message carries the function call.
    tool_msgs = [m for m in agent.memory.get() if m.get("role") == "assistant" and "tool_calls" in m]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_calls"][0]["function"]["name"] == "run_loss_simulation"

    # Client facts were accumulated.
    assert agent.brief.revenue_usd == 500_000_000
    assert "mfa" in agent.brief.security_controls.lower()


def test_agent_returns_insufficient_info_and_asks():
    """When the brief lacks revenue/controls, the tool says so and the agent asks."""
    script = [
        ChatResponse(
            content="",
            tool_calls=[
                _tool_call("run_loss_simulation", {"industry": "Retail"}, call_id="call_1")
            ],
        ),
        ChatResponse(content="I need your revenue and a description of your security controls."),
    ]
    agent = _make_agent(script)
    answer = agent.chat("Assess our retail business")
    assert "revenue" in answer.lower() or "controls" in answer.lower()
    # The insufficient_info result was passed back as a tool message.
    tool_messages = [m for m in agent.memory.get() if m.get("role") == "tool"]
    assert tool_messages
    assert '"status": "insufficient_info"' in tool_messages[0]["content"]


def test_agent_rounds_are_bounded():
    """A model that never produces text must not loop forever."""
    script = [
        ChatResponse(
            content="",
            tool_calls=[_tool_call("assess_company_risk", {"industry": "Retail"}, call_id=f"c{i}")],
        )
        for i in range(10)
    ]
    agent = _make_agent(script)
    with pytest.raises(RuntimeError, match="did not produce a final answer"):
        agent.chat("assess us")


def test_final_answer_is_grounded_in_tool_results():
    """The model's final answer must be generated with the tool results in
    context -- the numbers the LLM quotes are the engine's, not its own."""
    script = [
        ChatResponse(
            content="",
            tool_calls=[
                _tool_call(
                    "run_loss_simulation",
                    {
                        "industry": "Healthcare",
                        "revenue_usd": 500_000_000,
                        "customer_records": 10_000_000,
                        "security_controls": "weak MFA and limited network segmentation",
                    },
                    call_id="call_1",
                )
            ],
        ),
        ChatResponse(content="Your EAL is based on the simulation I ran."),
    ]
    agent = _make_agent(script)
    answer = agent.chat("Assess our healthcare business")
    assert "simulation" in answer.lower()
    # The tool result (with real engine EAL) is in memory before the answer.
    tool_msgs = [m for m in agent.memory.get() if m.get("role") == "tool"]
    assert tool_msgs, "tool result should be present before the final answer"
    assert '"eal"' in tool_msgs[0]["content"]
    # Protocol ordering: system, user, assistant(tool_calls), tool, assistant(answer).
    # The final answer comes after the tool result.
    roles = [m["role"] for m in agent.memory.get()]
    assert roles.index("tool") < len(roles) - 1
    assert roles[-1] == "assistant"


def test_final_text_is_returned_without_tools():
    script = [ChatResponse(content="A thoughtful consultant reply.")]
    agent = _make_agent(script)
    answer = agent.chat("Explain VaR in plain English")
    # The final answer must carry the mandatory model-limitations disclosure.
    assert answer.startswith("A thoughtful consultant reply.")
    assert answer.endswith(disclosure_block())


def test_agent_runs_demo_assessment_and_isolates_client_facts():
    """A demo request fabricates a company and runs the real engine on it —
    tagged DEMO, with standard metrics — and the demo NEVER mutates the
    running client facts (session isolation)."""
    script = [
        ChatResponse(
            content="",
            tool_calls=[_tool_call("generate_demo_assessment", {}, call_id="call_demo")],
        ),
        ChatResponse(content="Here is your DEMO assessment. The company is fictional."),
    ]
    agent = _make_agent(script)

    answer = agent.chat("Show me a demo of the platform")

    # The demo tool ran with real engine data.
    assert agent.tool_trace
    trace = agent.tool_trace[0]
    assert trace["name"] == "generate_demo_assessment"
    assert trace["ok"] is True
    data = trace["data"]
    assert data["demo"] is True
    assert "disclaimer" in data and "DEMO" in data["disclaimer"]
    # Standard metric keys the post-guard validates against.
    for key in ("eal", "var_99", "es_99", "aal_by_scenario"):
        assert key in data, key
    assert "client_retained_loss" in data
    # Chat-only: no report workbook path.
    assert "report_path" not in data
    # Session isolation: the demo call carried only non-brief args (empty
    # brief merges nothing), so the running client facts are untouched.
    assert agent.brief.revenue_usd is None
    assert agent.brief.security_controls is None
    # The hallucination backstop ran cleanly (no unverifiable-figures caveat).
    assert "could not be fully verified" not in answer


def test_agent_demo_excluded_sector_returns_error_to_model():
    """Asking for a critical-infrastructure demo returns an error the model
    can read, instead of fabricating a dangerous profile."""
    script = [
        ChatResponse(
            content="",
            tool_calls=[
                _tool_call("generate_demo_assessment", {"sector": "Power"}, call_id="call_demo")
            ],
        ),
        ChatResponse(content="That sector is not available for demos."),
    ]
    agent = _make_agent(script)
    agent.chat("Show me a demo for a power company")
    data = agent.tool_trace[0]["data"]
    assert data["status"] == "error"
    assert "excluded" in data["error"].lower()
