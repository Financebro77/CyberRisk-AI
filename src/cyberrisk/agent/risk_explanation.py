"""Actuarial-standard risk measure explanations (VaR and Expected Shortfall).

The consultant agent reports VaR and Expected Shortfall to clients who are
corporate risk managers / boards, not actuaries -- but the wording must be
*actuarially defensible*.  Every reported risk measure is a triple:

    (confidence level, time horizon, loss definition)

and a client-facing sentence must make all three explicit, so a figure like
"99% VaR = $30M" is never mistaken for "the amount you lose 1% of the time"
(which is false -- it is the loss only 1% of simulated years EXCEED).

The classic mis-statement the module forbids:

    "There is a 1% chance you lose exactly this amount."

VaR is a threshold the loss is *at or below* with the confidence level; it is
not a point mass.  ES is the average of the tail *beyond* that threshold.

Every function here returns a structured dataclass (confidence, horizon,
loss definition) PLUS a ready-to-say client sentence, so the agent can quote
either the components or the full sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# The risk measure triple every VaR / ES explanation must state.
HORIZON = "1-year"  # the simulation aggregates 100,000 independent annual loss scenarios


@dataclass(frozen=True)
class VarExplanation:
    """A full VaR explanation: the measure triple + a client-facing sentence.

    Attributes
        confidence     the confidence level, e.g. 0.99 ("99%")
        var            the VaR amount in US dollars
        horizon        the time horizon the VaR is over ("1-year")
        loss_definition what is being measured ("total economic loss before
                       insurance recovery" for ground-up, or the client's
                       retained loss after insurance)
        sentence       a complete client-facing sentence
    """

    confidence: float
    var: float
    horizon: str
    loss_definition: str
    sentence: str


@dataclass(frozen=True)
class ESExplanation:
    """A full Expected Shortfall explanation: the triple + a client sentence."""

    confidence: float
    es: float
    horizon: str
    loss_definition: str
    sentence: str


def _fmt_usd(x: float) -> str:
    """Compact US$ formatting for client-facing sentences."""
    if x >= 1e9:
        return f"${x/1e9:,.1f}B"
    if x >= 1e6:
        return f"${x/1e6:,.1f}M"
    if x >= 1e3:
        return f"${x/1e3:,.1f}K"
    return f"${x:,.0f}"


def _confidence_pct(confidence: float) -> str:
    """Format a confidence level as a whole-number percent string, e.g. 0.99 -> '99%'."""
    return f"{confidence*100:.0f}%"


def _exceed_probability(confidence: float) -> str:
    """The exceedance tail probability as a percent string, e.g. 0.99 -> '1%'."""
    return f"{(1 - confidence)*100:.0f}%"


def explain_var(
    var: float,
    confidence: float = 0.99,
    loss_definition: str = "total economic loss before insurance recovery",
) -> VarExplanation:
    """Explain a VaR figure with the full (confidence, horizon, definition) triple.

    Parameters
        var               the VaR amount in US dollars
        confidence        the confidence level (default 0.99)
        loss_definition   what the loss measure represents (default ground-up)

    Returns
        VarExplanation with `.confidence`, `.horizon`, `.loss_definition` and
        `.sentence` -- the sentence always names all three and describes VaR as
        a *threshold the loss stays at or below* with the confidence level.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if var < 0:
        raise ValueError("VaR cannot be negative")
    pct = _confidence_pct(confidence)
    tail = _exceed_probability(confidence)
    sentence = (
        f"{pct} annual aggregate {loss_definition} VaR is {_fmt_usd(var)}. "
        f"This means that based on the simulated annual loss distribution, "
        f"only {tail} of simulated years exceed this amount."
    )
    return VarExplanation(
        confidence=confidence,
        var=var,
        horizon=HORIZON,
        loss_definition=loss_definition,
        sentence=sentence,
    )


def explain_expected_shortfall(
    es: float,
    confidence: float = 0.99,
    loss_definition: str = "total economic loss before insurance recovery",
) -> ESExplanation:
    """Explain an Expected Shortfall figure with the full triple.

    Parameters
        es                the ES amount in US dollars
        confidence        the confidence level (default 0.99)
        loss_definition   what the loss measure represents

    Returns
        ESExplanation.  The sentence describes ES as the *average annual loss
        in the worst (1-confidence) tail of simulated outcomes*.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if es < 0:
        raise ValueError("ES cannot be negative")
    pct = _confidence_pct(confidence)
    tail = _exceed_probability(confidence)
    sentence = (
        f"The {pct} Expected Shortfall is {_fmt_usd(es)}, representing the "
        f"average annual loss in the worst {tail} of simulated outcomes "
        f"({loss_definition})."
    )
    return ESExplanation(
        confidence=confidence,
        es=es,
        horizon=HORIZON,
        loss_definition=loss_definition,
        sentence=sentence,
    )


# The mis-statement the agent must never make: VaR is a threshold, not a point
# mass -- there is no "exactly this amount" tail probability.
FORBIDDEN_VAR_PHRASES: tuple[str, ...] = (
    "chance you lose exactly this amount",
    "chance you lose exactly",
    "probability you lose exactly this amount",
    "exactly this amount",
    "chance of losing exactly",
)


def contains_forbidden_var_wording(text: str) -> bool:
    """Return True if a client-facing sentence uses a forbidden VaR phrasing.

    Guards against the classic mis-statement: "There is a 1% chance you lose
    exactly this amount."  VaR is a threshold the loss stays at or below with
    the confidence level, not a point mass.
    """
    if not text:
        return False
    low = text.lower()
    return any(phrase in low for phrase in FORBIDDEN_VAR_PHRASES)


def explain_risk_measures(
    var_99: float,
    es_99: float,
    var_95: float | None = None,
    es_95: float | None = None,
    loss_definition: str = "total economic loss before insurance recovery",
) -> dict[str, str]:
    """Return a dict of ready-to-say risk-measure sentences for a report.

    Produces a compact set of explanations the agent can drop into the
    GROUND-UP CYBER LOSS section of a client report.  Keys are
    var_99 / es_99 (and var_95 / es_95 when supplied).  Each value is the
    full actuarial sentence (confidence + horizon + loss definition).
    """
    out: dict[str, str] = {}
    out["var_99"] = explain_var(var_99, 0.99, loss_definition).sentence
    out["es_99"] = explain_expected_shortfall(es_99, 0.99, loss_definition).sentence
    if var_95 is not None:
        out["var_95"] = explain_var(var_95, 0.95, loss_definition).sentence
    if es_95 is not None:
        out["es_95"] = explain_expected_shortfall(es_95, 0.95, loss_definition).sentence
    return out
