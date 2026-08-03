"""Mandatory model limitations disclosure for client advisory reports.

Every client-facing advisory report must end with this disclosure.  It is a
single source of truth shared by every surface that renders a final report:

    - the DeepSeek consultant agent's final answer (agent_controller.chat),
    - the rule-based / LLM consultant (agent.consultant_agent),
    - the Excel workbook (cyberrisk.reporting.excel),
    - the system prompt / grounding reminder (so the LLM keeps it verbatim).

The disclosure is deliberately deterministic and unchanged across reports: it
is a risk-management disclaimer, not a data-dependent paragraph.  Only append
it to FINAL advisory reports -- not to clarifying-question turns or mid-dialogue
responses.
"""

from __future__ import annotations

# The heading every report must carry before the limitation bullets.
DISCLOSURE_HEADING = "Model Limitations"

# The five mandated limitation statements, in order.
LIMITATIONS: tuple[str, ...] = (
    "Cyber losses are probabilistic estimates, not predictions.",
    "Results depend on benchmark datasets and modelling assumptions.",
    "Catastrophic systemic cyber events may not be fully captured.",
    "Parameter uncertainty exists.",
    "Insurance terms and policy wording may affect actual recovery.",
)


def disclosure_block() -> str:
    """The full disclosure paragraph: heading + bulleted limitations.

    Returns the block exactly as it must appear at the end of a final report.
    """
    lines = [DISCLOSURE_HEADING, ""]
    lines.extend(f"- {item}" for item in LIMITATIONS)
    return "\n".join(lines)


def disclosure_lines() -> list[str]:
    """The disclosure as a list of lines (heading, then one per limitation)."""
    return [DISCLOSURE_HEADING, *LIMITATIONS]


def append_disclosure(report: str) -> str:
    """Return `report` with the mandatory disclosure appended.

    Idempotent: if the disclosure block is already at the end of the report,
    it is not appended twice.
    """
    block = disclosure_block()
    if block in report:
        return report
    if not report or not report.strip():
        return block
    separator = "\n\n" if not report.endswith("\n\n") else "\n"
    return f"{report.rstrip()}{separator}{block}"


def ensure_disclosure(report: str) -> str:
    """Alias for ``append_disclosure`` -- guarantees the disclosure is present."""
    return append_disclosure(report)
