"""Streamlit chat interface for the CyberRisk consultant agent.

Launch with:

    python -m streamlit run src/cyberrisk/agent/app.py

The sidebar shows the DeepSeek configuration status and lets the user pick
the model.  Chat history lives in st.session_state; each message runs the
same CyberRiskAgent tool loop as the terminal CLI.

Every quantitative figure in the conversation comes from the CyberRisk
engine via the agent's tools -- the LLM never supplies numbers itself.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.agent.deepseek_client import ENV_API_KEY, ENV_BASE_URL, ENV_MODEL, DeepSeekClient
from cyberrisk.agent.schemas import AgentConfig

st.set_page_config(page_title="CyberRisk Consultant", page_icon="🛡️", layout="centered")

# Install the sanitised root logger so no log line can leak a secret or
# personal data (see cyberrisk.privacy).
try:
    from cyberrisk.privacy import configure_sanitised_logging

    configure_sanitised_logging()
except ImportError:  # pragma: no cover - privacy module always present
    pass

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

st.session_state.setdefault("agent", None)
st.session_state.setdefault("messages", [])


def get_agent() -> CyberRiskAgent | None:
    """Build (once) and return the configured agent."""
    if st.session_state.agent is None:
        key = os.getenv(ENV_API_KEY)
        if not key:
            return None
        config = AgentConfig(model=os.getenv(ENV_MODEL, "deepseek-chat"))
        st.session_state.agent = CyberRiskAgent(config=config)
    return st.session_state.agent


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🛡️ CyberRisk Consultant")
    st.caption("Marsh/Aon-style AI cyber risk adviser on top of the CyberRisk engine.")
    st.divider()

    st.subheader("DeepSeek configuration")
    if DeepSeekClient.is_configured():
        st.success("API key detected ✓")
        st.text_input(
            "Model",
            value=os.getenv(ENV_MODEL, "deepseek-chat"),
            key="model",
            help="deepseek-chat or deepseek-reasoner",
        )
        st.text_input("Base URL", value=os.getenv(ENV_BASE_URL, "https://api.deepseek.com"), key="base_url", disabled=True)
    else:
        st.error(f"`{ENV_API_KEY}` is not set. Create a `.env` file in the project root "
                 f"(see `.env.example`) with `{ENV_API_KEY}=sk-...`, then restart.")
        st.code("DEEPSEEK_API_KEY=sk-...", language="bash")

    st.divider()
    n_years = st.slider("Simulation years (Monte Carlo)", 10_000, 200_000, 100_000, step=10_000)
    st.caption("A 100k-year run takes a few seconds; lower is faster to test with.")

    if st.button("Clear conversation", use_container_width=True):
        st.session_state.agent = None
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

st.header("Cyber Risk Consultant")
st.caption(
    "Ask about your cyber exposure. The agent will ask clarifying questions, "
    "run the loss model, and translate the results into insurance advice."
)

agent = get_agent()
if agent is None:
    st.stop()

# Render history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------------------

if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown(
            "I'm your cyber risk consultant. Give me a company description and I'll "
            "assess your exposure and insurance structure.\n\n"
            "*Try: \"Assess a healthcare technology company with 10 million patient "
            "records, weak MFA and limited network segmentation.\"*"
        )

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

prompt = st.chat_input("Describe the company you want assessed…")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Consultant is working…"):
            try:
                welcome = len(st.session_state.messages) == 1
                answer = agent.chat(prompt, welcome=welcome)
            except RuntimeError as exc:
                answer = f"⚠️ {exc}"
        st.markdown(answer)
    if getattr(agent, "last_privacy_notice", ""):
        st.caption(f"🔒 {agent.last_privacy_notice}")
    st.session_state.messages.append({"role": "assistant", "content": answer})
