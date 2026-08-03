"""Risk-appetite validation for the consultant agent.

The senior-broker check this implements:

    "Your stated retention must be a sane target given your modelled
    exposure.  Wanting to retain $50k is fine if your expected loss is
    $100k; it is a red flag if your expected loss is $5M -- you would be
    self-insuring a catastrophe without realising it."

The agent:
  1. Parses the client's stated retention from free text ("$1M retention",
     "we retain 500k", "no appetite to retain much", "we want to keep our
     premium low") into a dollar figure where possible.
  2. Compares it against the modelled EAL and ES99 (the tail).
  3. Returns a plain-English verdict the consultant can read to the client.

Rules of thumb (deliberately simple, defensible):
  - retention <= 2x EAL        -> sensible: you're retaining ordinary losses.
  - 2x EAL < retention <= ES99 -> high but not reckless: you're self-insuring
                                   a chunk of the tail.
  - retention > ES99           -> "self-insuring the catastrophe": you'd be
                                   funding the worst-case yourself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class AppetiteVerdict:
    """Result of checking a stated retention against modelled exposure."""

    retention: float | None  # parsed US$ figure; None if not parseable
    eal: float
    es_99: float
    rating: str  # "sensible" | "high" | "self-insuring" | "unparseable"
    message: str  # plain-English explanation

    @property
    def is_sane(self) -> bool:
        return self.rating == "sensible"


def parse_retention(text: str) -> float | None:
    """Extract a US$ retention figure from free text, or None if unparseable.

    Handles: "$1M", "1,500,000", "500k", "a $250,000 retention", "retain up
    to $2m".  Returns None for qualitative statements ("we keep our premium
    low", "as little as possible") -- the agent then asks for a figure
    rather than guessing.
    """
    if not text:
        return None
    t = text.strip().lower()
    # explicit "none"/"zero" appetite -> retention ~ 0 (buy full cover)
    if re.fullmatch(r"(none|zero|as little as possible|minimal|nothing)", t):
        return 0.0
    # find a currency figure: $ or number followed by k/m/b, or bare comma number
    m = re.search(r"\$?\s*([\d][\d,]*(?:\.\d+)?)\s*([kmb]?)", t)
    if not m:
        return None
    number = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    multiplier = {"k": 1e3, "m": 1e6, "b": 1e9}.get(unit, 1.0)
    return number * multiplier


def validate_appetite(retention: float | None, eal: float, es_99: float) -> AppetiteVerdict:
    """Check a stated retention against the modelled exposure.

    Parameters
        retention  parsed retention figure (None if the client was vague)
        eal        modelled expected annual loss
        es_99      modelled 99% expected shortfall (the tail)

    Returns
        AppetiteVerdict with a rating and a client-facing message.
    """
    if retention is None:
        return AppetiteVerdict(
            retention=None,
            eal=eal,
            es_99=es_99,
            rating="unparseable",
            message=(
                "I need a dollar figure for how much you are willing to retain "
                "before insurance responds.  If you prefer, I can talk through "
                "what typical retentions look like for a firm of your size."
            ),
        )

    if retention <= 2.0 * eal:
        rating = "sensible"
        message = (
            f"Retaining {_fmt(retention)} is sensible for your exposure: your "
            f"expected annual loss is {_fmt(eal)}, so this retention keeps "
            f"ordinary-year losses inside your own book while insurance covers "
            f"the tail."
        )
    elif retention <= es_99:
        rating = "high"
        message = (
            f"Retaining {_fmt(retention)} is on the high side.  It is below your "
            f"modelled 1-in-100 tail ({_fmt(es_99)}), so insurance still responds "
            f"to the worst years -- but you would be self-funding a meaningful "
            f"chunk of the tail.  Let's check the premium saving against that risk."
        )
    else:
        rating = "self-insuring"
        message = (
            f"A retention of {_fmt(retention)} is effectively self-insuring the "
            f"catastrophe: it exceeds your modelled 99% tail loss of {_fmt(es_99)}. "
            f"In the worst year, insurance would barely respond.  I would strongly "
            f"recommend a lower retention -- let's discuss."
        )
    return AppetiteVerdict(retention=retention, eal=eal, es_99=es_99, rating=rating, message=message)


def _fmt(x: float) -> str:
    """Compact US$ formatting."""
    if x >= 1e9:
        return f"${x/1e9:,.2f}B"
    if x >= 1e6:
        return f"${x/1e6:,.2f}M"
    if x >= 1e3:
        return f"${x/1e3:,.1f}K"
    return f"${x:,.0f}"
