"""Terminal chat interface for the CyberRisk consultant agent.

Runs the same CyberRiskAgent the Streamlit app uses, without a browser.
Useful for quick testing of the DeepSeek integration and the tool loop.

    python -m cyberrisk.agent.run_chat

Requires DEEPSEEK_API_KEY (via .env or the environment).
"""

from __future__ import annotations

import sys

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.agent.deepseek_client import DeepSeekClient


def _render_metrics(answer: str) -> None:
    """Print the answer verbatim (the model already formats the sections)."""
    print(answer)
    print()


def main() -> None:
    try:
        client = DeepSeekClient()
    except RuntimeError as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        sys.exit(1)

    agent = CyberRiskAgent(client=client)
    print("=" * 72)
    print("CYBERRISK CONSULTANT AGENT  (DeepSeek)")
    print(f"Model: {client.model_name}   Type 'exit' or Ctrl-C to quit")
    print("=" * 72)
    print()
    print("Try:  Assess a healthcare company with weak MFA and limited segmentation.")

    welcome = True
    while True:
        try:
            prompt = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit", "q"):
            break
        print("\nConsultant>")
        try:
            answer = agent.chat(prompt, welcome=welcome)
            _render_metrics(answer)
        except RuntimeError as exc:
            print(f"[error] {exc}")
        welcome = False


if __name__ == "__main__":
    main()
