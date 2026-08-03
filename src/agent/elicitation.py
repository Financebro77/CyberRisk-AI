"""Information elicitation for the consultant agent.

The senior-broker principle this implements:

    "A broker who advises on incomplete data without asking is negligent."

Before the agent can give any cyber risk advice it needs eight pieces of
information.  When one is missing, the agent must:

    1. ASK a clarifying question (never assume a default silently);
    2. EXPLAIN why the piece matters to the advice;
    3. NOT draw a premature conclusion from incomplete data.

This module is the "first meeting" phase of the agent: it takes whatever
the client has provided so far, works out what is still missing, and asks
the right questions.  Only when `is_information_complete` is True should
`generate_recommendations` be called.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The eight dimensions a cyber risk adviser needs, with the plain-English
# reason each one matters (what it changes about the advice).
DIMENSIONS: dict[str, dict] = {
    "industry": {
        "question": "What industry does your company operate in?",
        "why": "Sector drives the baseline threat picture: a bank is targeted far more often than a manufacturer, and some sectors face specific regulatory duties (e.g. healthcare data, financial conduct).",
    },
    "revenue": {
        "question": "What is your annual revenue?",
        "why": "Revenue is the main driver of how large a loss can be: business-interruption and response costs scale with the size of the operation, so it directly shapes the limit you need.",
    },
    "customer_data_volume": {
        "question": "How many customer / personal records do you hold, and how sensitive are they?",
        "why": "Record volume and sensitivity drive both the notification/regulatory cost and the risk of class-action exposure -- the two biggest breach-cost components after response.",
    },
    "technology_dependency": {
        "question": "How dependent is your business on IT and third-party systems (cloud, SaaS, critical software)?",
        "why": "High technology dependency means a system outage or a supplier breach can interrupt revenue at scale -- it determines how much business-interruption cover you need.",
    },
    "security_controls": {
        "question": "What security controls are in place (MFA, patching, EDR, backups, incident response)?",
        "why": "Controls are the strongest predictor of how often you suffer an event and how contained it is.  This is the single biggest driver of your risk score.",
    },
    "previous_incidents": {
        "question": "Have you had any cyber incidents in the last 3-5 years, and what was the impact?",
        "why": "Past incidents are the best evidence of your real event rate -- they pull your modelled frequency toward your own history (credibility) rather than the industry average.",
    },
    "existing_coverage": {
        "question": "What cyber insurance do you currently hold (limits, retentions, sub-limits)?",
        "why": "We need to know what is already covered so we can identify the gap -- the difference between your exposure and your current tower is where the advice adds value.",
    },
    "risk_appetite": {
        "question": "How much loss are you willing to retain before insurance responds (your risk appetite)?",
        "why": "Risk appetite is the target: it tells us whether to recommend a higher retention and lower premium, or lower retention and higher premium.  Without it, a 'recommendation' has no objective.",
    },
}


@dataclass
class ElicitationQuestion:
    """One clarifying question the agent needs to ask."""

    dimension: str
    question: str
    why_it_matters: str


@dataclass
class ElicitationResult:
    """Outcome of the information check."""

    complete: bool
    missing: list[str] = field(default_factory=list)
    questions: list[ElicitationQuestion] = field(default_factory=list)

    def formatted_response(self) -> str:
        """The client-facing 'first meeting' message when info is missing."""
        if self.complete:
            return (
                "Thank you -- I have enough to work with. "
                "I can now score your profile and model your exposure."
            )
        lines = [
            "Before I can advise you on cyber risk, I need a little more information. "
            "I have not drawn any conclusions yet -- the following would change the advice, "
            "so I would rather ask than guess:"
        ]
        for q in self.questions:
            lines.append(f"\n  * {q.question}")
            lines.append(f"      Why it matters: {q.why_it_matters}")
        lines.append(
            "\nOnce you give me these, I will assess your profile and come back "
            "with a proper recommendation."
        )
        return "\n".join(lines)


# The full set of dimensions the agent will ultimately need.
REQUIRED_DIMENSIONS = list(DIMENSIONS)


def determine_missing(
    provided: dict[str, object],
    required: list[str] | None = None,
) -> ElicitationResult:
    """Work out which of the 8 dimensions are missing from what the client gave.

    Parameters
        provided   dict of the client's answers so far, keyed by dimension.
                   A value counts as 'provided' if it is non-empty and not a
                   placeholder for 'unknown' (None, '', or 0 sentinel).
        required   optional subset of dimensions to check (default all 8).

    Returns
        ElicitationResult: complete=True only if nothing is missing; otherwise
        the missing dimensions and the questions to ask (with why-it-matters).
    """
    required = required or REQUIRED_DIMENSIONS
    missing = [d for d in required if not _is_provided(provided.get(d))]
    questions = [
        ElicitationQuestion(
            dimension=d,
            question=DIMENSIONS[d]["question"],
            why_it_matters=DIMENSIONS[d]["why"],
        )
        for d in missing
    ]
    return ElicitationResult(complete=len(missing) == 0, missing=missing, questions=questions)


def _is_provided(value: object) -> bool:
    """A value counts as provided if it is non-empty and not an 'unknown' sentinel."""
    if value is None:
        return False
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("", "unknown", "n/a", "not sure", "?", "tbd", "to be determined", "unspecified"):
            return False
        return True
    if isinstance(value, (int, float)):
        # 0 revenue / 0 records / 0 incidents may be a legitimate zero.
        # Only treat explicit None / empty as missing; numeric 0 is provided.
        return True
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


# ---------------------------------------------------------------------------
# Multi-turn consultation session (follow-up dialogue loop)
# ---------------------------------------------------------------------------

MAX_DIALOGUE_TURNS = 6  # a real conversation can't run forever


@dataclass
class ConsultationSession:
    """A multi-turn information-gathering conversation.

    The client answers questions over several turns; the agent merges each
    answer into what it already knows, re-asks ONLY the dimensions still
    missing, and pushes back politely when the client says "unknown" rather
    than answering.

    This is the follow-up loop the broker-review flagged as missing: the
    single-shot `elicit()` asks once, but a real first meeting is a dialogue.
    """

    answers: dict[str, object] = field(default_factory=dict)
    max_turns: int = MAX_DIALOGUE_TURNS
    turn: int = 0
    _finished: bool = False

    @property
    def complete(self) -> bool:
        return self._finished or self.missing == []

    @property
    def missing(self) -> list[str]:
        missing = determine_missing(self.answers).missing
        # A vague risk appetite ("we want to keep our premium low") is not a
        # usable figure -- push back for a dollar amount, like a broker would.
        appetite = self.answers.get("risk_appetite")
        if appetite is not None and "risk_appetite" not in missing:
            from agent.risk_appetite import parse_retention

            if parse_retention(str(appetite)) is None:
                missing = missing + ["risk_appetite"]
        return missing

    @property
    def blocked(self) -> bool:
        """The conversation stalled: too many turns with no progress."""
        return self.turn >= self.max_turns and not self.complete

    def reply(self, answers: dict[str, object]) -> ElicitationResult:
        """Register the client's latest answers and ask for what's still missing.

        Returns an ElicitationResult.  `complete=True` means all dimensions are
        now known (no more questions).  If `blocked`, the session is over
        without enough information -- the caller must decide how to proceed.
        """
        self.turn += 1
        # Merge only genuinely informative answers; keep existing ones on blank/unknown.
        for key, value in answers.items():
            if _is_provided(value):
                self.answers[key] = value

        if self.complete:
            self._finished = True
            return ElicitationResult(complete=True, missing=[], questions=[])

        missing = self.missing
        questions = [
            ElicitationQuestion(
                dimension=d,
                question=DIMENSIONS[d]["question"],
                why_it_matters=DIMENSIONS[d]["why"],
            )
            for d in missing
        ]
        return ElicitationResult(complete=False, missing=missing, questions=questions)

    def formatted_response(self) -> str:
        """Client-facing message for the current state of the conversation."""
        if self.complete:
            return (
                "Thank you -- I now have what I need. "
                "I can assess your profile and model your exposure."
            )
        if self.blocked:
            return (
                "I'm sorry, but I still don't have enough to give you sound advice, "
                "and I would rather not guess.  Please come back with at least your "
                f"industry, revenue and the following: {', '.join(self.missing[:3])}... "
                "and I will take it from there."
            )
        missing = self.missing
        lines = [
            f"Thank you -- noted.  I still need {len(missing)} more piece"
            f"{'s' if len(missing) != 1 else ''} of information before I can advise. "
            "I have not drawn any conclusions yet:"
        ]
        for q in self._questions_for(missing):
            lines.append(f"\n  * {q.question}")
            lines.append(f"      Why it matters: {q.why_it_matters}")
        return "\n".join(lines)

    def _questions_for(self, missing: list[str]) -> list[ElicitationQuestion]:
        return [
            ElicitationQuestion(
                dimension=d,
                question=DIMENSIONS[d]["question"],
                why_it_matters=DIMENSIONS[d]["why"],
            )
            for d in missing
        ]
