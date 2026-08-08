"""CyberRisk AI Consultant — global command-line launcher.

Typing ``cyberrisk`` in a terminal starts the interactive consultant.

This module is an INTERFACE LAYER ONLY.  It:
    * checks that the core services are available (lightweight capability
      probes, not computations),
    * prints the startup screen,
    * constructs the CyberRiskAgent (which connects to the LLM, seeds the
      system prompt, and initialises retrieval + the quantitative engine
      through its tools),
    * runs an interactive conversation loop.

It does NOT contain Monte Carlo, scoring, insurance, or RAG logic — those live
in the existing engine / knowledge / agent modules and are reached through
``CyberRiskAgent``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.llm.factory import is_configured

# Repo root: src/cyberrisk/cli.py -> src/cyberrisk -> src -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

HEADER = "=" * 50
TITLE = "CyberRisk AI Consultant"
SUBTITLE = "Commercial Cyber Risk Advisory Platform"

HELP_TEXT = """Commands:
  exit / quit   leave the consultant
  help          show this help
  clear         clear the screen

Ask anything, e.g.:
  > Assess ransomware exposure for a healthcare provider
  > What cyber insurance limit and retention should a $500M manufacturer consider?
  > How does the model treat business email compromise?
"""


def _risk_engine_ok() -> bool:
    """Risk engine availability: the simulation/scoring modules import."""
    try:
        import cyberrisk.simulation  # noqa: F401
        import cyberrisk.scoring  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _knowledge_base_ok() -> bool:
    """Knowledge base availability: the corpus + manifests exist."""
    try:
        return (REPO_ROOT / "knowledge" / "corpus").is_dir() and (
            REPO_ROOT / "knowledge" / "manifests"
        ).is_dir()
    except Exception:  # noqa: BLE001
        return False


def _retrieval_ok() -> bool:
    """Retrieval availability: the vector store exists or can be initialised."""
    try:
        from cyberrisk.knowledge.config import load_ingest_config

        return (load_ingest_config().derived_path / "vector.db").exists()
    except Exception:  # noqa: BLE001
        return False


def _llm_ok() -> bool:
    """LLM availability: the active provider's API key is configured."""
    return is_configured()


def _tick(ok: bool) -> str:
    """A check/cross marker that survives the console's encoding.

    The Unicode ✓/✗ render on UTF-8 terminals but crash on GBK/other legacy
    codepages (common on Windows).  We probe whether the console can encode
    them and fall back to [OK] / [--] when it cannot.
    """
    try:
        "✓".encode(sys.stdout.encoding or "utf-8")
        return "✓" if ok else "✗"
    except (UnicodeEncodeError, LookupError):
        return "[OK]" if ok else "[--]"


def _print_startup() -> None:
    print(HEADER)
    print(TITLE)
    print(SUBTITLE)
    print(HEADER)
    print()
    print("System Status:")
    print()
    print(f"  {_tick(_risk_engine_ok())} Risk Engine")
    print(f"  {_tick(_knowledge_base_ok())} Knowledge Base")
    print(f"  {_tick(_retrieval_ok())} Retrieval System")
    print(f"  {_tick(_llm_ok())} LLM Connection")
    print()
    if not _llm_ok():
        print(
            "  Note: set LLM_PROVIDER=openai|deepseek and the matching key "
            "(OPENAI_API_KEY or DEEPSEEK_API_KEY, in .env or the environment) "
            "to enable the LLM."
        )
    print("Ready.")
    print()


def _clear_screen() -> None:
    """Clear the terminal (ANSI escape on POSIX, cls on Windows)."""
    if sys.platform.startswith("win"):
        subprocess.run(["cls"], shell=True, check=False)
    else:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()


def main() -> int:
    """Launch the CyberRisk AI Consultant."""
    # Install the sanitised root logger so no log line can leak a secret or
    # personal data (see cyberrisk.privacy).
    try:
        from cyberrisk.privacy import configure_sanitised_logging

        configure_sanitised_logging()
    except ImportError:  # pragma: no cover - privacy module always present
        pass
    _print_startup()

    # Construct the agent: this connects to the LLM (reads .env), seeds the
    # system prompt, and provides the tools that reach the quantitative engine
    # and the knowledge retrieval system.  If the LLM key is missing, the agent
    # raises a clear error which we surface and exit on.
    try:
        agent = CyberRiskAgent()
    except RuntimeError as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        return 1

    print("Type 'exit', 'quit', or 'help'. Ctrl-C to leave.")
    welcome = True
    while True:
        try:
            prompt = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        low = prompt.lower()
        if low in ("exit", "quit"):
            break
        if low == "help":
            print(HELP_TEXT)
            continue
        if low == "clear":
            _clear_screen()
            continue

        try:
            answer = agent.chat(prompt, welcome=welcome)
            print(f"\n{answer}\n")
        except RuntimeError as exc:
            print(f"[error] {exc}")
        welcome = False

    print("\nGoodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
