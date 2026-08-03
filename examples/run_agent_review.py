"""Senior-broker review: does the agent gather enough info before advising?

Runs each missing-information scenario through the agent's elicitation
phase and shows:
  1. What the client provided
  2. Which dimensions the agent detected as missing
  3. The exact questions + why-it-matters the agent asks
  4. That the agent does NOT produce a premature recommendation

Usage:  python examples/run_agent_review.py
"""

from __future__ import annotations

from agent.consultant_agent import advise
from agent.elicitation import DIMENSIONS

SCENARIOS = [
    (
        "A. New business - no information given",
        {},
    ),
    (
        "B. Manufacturer - controls and appetite missing",
        {"industry": "Manufacturing", "revenue": 500_000_000},
    ),
    (
        "C. Bank - no risk appetite, no incident history",
        {
            "industry": "Financial Services",
            "revenue": 2_000_000_000,
            "customer_data_volume": 1_000_000,
            "technology_dependency": "Very high",
            "security_controls": "Strong",
            "existing_coverage": "$10M limit",
        },
    ),
    (
        "D. Hospital - no revenue, no coverage, no appetite",
        {
            "industry": "Healthcare",
            "customer_data_volume": 500_000,
            "technology_dependency": "High",
            "security_controls": "MFA, patching",
            "previous_incidents": 2,
        },
    ),
]


def main() -> None:
    print("=" * 76)
    print("SENIOR BROKER REVIEW - INFORMATION GATHERING")
    print("=" * 76)
    for name, provided in SCENARIOS:
        print(f"\n{name}")
        print("-" * 76)
        print("  PROVIDED:")
        if provided:
            for k, v in provided.items():
                print(f"    {k:<24} {v}")
        else:
            print("    (nothing)")
        result = advise(provided, score_and_run=lambda p: (_ for _ in ()).throw(
            AssertionError("advise() must not run the model on incomplete data")
        ))
        print(f"  -> agent detected missing: {', '.join(result.missing) if result.missing else 'none'}")
        if not result.complete:
            print("  -> agent did NOT give advice (correct: data incomplete)")
            print("  -> questions asked:")
            for q in result.questions:
                print(f"      * {q.question}")
                print(f"        Why: {q.why_it_matters}")
        else:
            print("  -> agent proceeded to recommendation (only if complete)")

    # The 8 dimensions the agent is equipped to ask about
    print("\n" + "=" * 76)
    print("DIMENSIONS THE AGENT ASKS ABOUT (and why)")
    print("=" * 76)
    for d, spec in DIMENSIONS.items():
        print(f"\n  [{d}]")
        print(f"    asks: {spec['question']}")
        print(f"    why : {spec['why']}")


if __name__ == "__main__":
    main()
