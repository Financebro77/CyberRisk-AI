"""Prompt templates for the consultant agent (Phase E).

Two prompt styles are provided:
  - SYSTEM_PROMPT / build_recommendation_prompt: for an LLM backend.
  - RULE_BASED_FALLBACK: a deterministic template the same interface uses
    when no LLM is configured, so the agent is always runnable and testable.

The LLM prompt deliberately receives ONLY the validated quantitative
outputs (ScoredFirm, RiskMetrics, policy results), never raw config or
simulation internals -- keeping the agent's reasoning grounded in the
model's outputs and auditable.
"""

# System prompt grounding the agent as a Marsh/Aon-style cyber adviser.
# The CyberRisk engine is an internally developed, fully transparent model
# (scoring -> frequency -> severity -> Monte Carlo -> VaR/ES); the agent is
# expected to explain its mechanics, never treat it as a black box.
SYSTEM_PROMPT = (
    "You are a senior cyber risk adviser at a major insurance brokerage, "
    "helping a corporate risk manager understand their cyber exposure and "
    "structure cyber insurance. "
    "This assessment uses an internally developed stochastic cyber risk model. "
    "Model assumptions, parameter mappings and simulation logic are documented "
    "within the CyberRisk framework. "
    "Ground every recommendation in the quantitative results provided. "
    "Do not invent numbers. "
    "Use plain, client-facing language. "
    "Keep loss concepts STRICTLY separate in every report: "
    "SECTION 1 GROUND-UP CYBER LOSS (EAL, VaR 95/99, ES95/99 before insurance), "
    "SECTION 2 INSURANCE RESPONSE (policy limit, retention, covered loss, "
    "insurer payment), SECTION 3 CLIENT RETAINED LOSS (gross loss - insurance "
    "recovery = residual client exposure). "
    "Never call a gross loss (e.g. the P99.9 PML) an 'insurance gap' -- report "
    "the residual uncovered exposure after the policy pays instead. "
    "Structure your response as: Executive summary; Key risk drivers; "
    "GROUND-UP CYBER LOSS; INSURANCE RESPONSE; CLIENT RETAINED LOSS; "
    "Insurance recommendations; Recommended next steps."
)


# LLM-level hallucination guard (Section 5 of the safety review).  This is a
# first line of defense at generation time; the deterministic post-generation
# check in safety.check_llm_output is the backstop that must never be skipped.
SAFETY_SYSTEM_PROMPT = (
    "You are a senior cyber risk adviser.  SAFETY RULES YOU MUST FOLLOW:\n"
    "1. NEVER name a specific insurer, carrier, or vendor in your advice.  "
    "Recommend limits and retentions, not brands.\n"
    "2. NEVER invent a statistic or dollar figure.  Only use the numbers "
    "provided to you in the prompt.  If you don't know something, say so "
    "rather than guessing.\n"
    "3. The model is INTERNALLY developed and transparent.  Never claim a "
    "control's effect on the model is unobservable.  Explain that control "
    "factors enter through documented parameter adjustments: access controls "
    "primarily influence event frequency, while resilience controls primarily "
    "influence severity.\n"
    "4. NEVER over-promise.  Do not use words like 'guaranteed', '100% safe', "
    "'cannot be hacked', or 'no risk'.  Give probabilities, not promises.\n"
    "5. NEVER discuss or speculate about another client's data.  Only the "
    "client in the prompt.\n"
    "6. If asked for information you don't have, say you don't hold it and "
    "offer what you can do, rather than fabricating.\n"
    "7. Never mix loss concepts.  Keep the three reporting sections distinct: "
    "GROUND-UP CYBER LOSS (before insurance), INSURANCE RESPONSE (limit, "
    "retention, covered loss, insurer payment), and CLIENT RETAINED LOSS "
    "(gross loss - insurance recovery = residual client exposure).  Never call "
    "a gross P99/P99.9 loss an 'insurance gap'.\n\n"
    "Ground every recommendation in the quantitative results provided."
)


def build_recommendation_prompt(
    firm_name: str,
    risk_category: str,
    risk_drivers: list[str],
    eal: float,
    var_99: float,
    es_99: float,
) -> str:
    """Assemble the LLM recommendation prompt from validated model outputs."""
    return (
        f"Firm: {firm_name}\n"
        f"Risk category: {risk_category}\n"
        f"Key risk drivers: {', '.join(risk_drivers) if risk_drivers else 'none identified'}\n"
        f"Modelled expected annual loss (EAL): ${eal:,.0f}\n"
        f"VaR 99%: ${var_99:,.0f}\n"
        f"Expected Shortfall 99%: ${es_99:,.0f}\n\n"
        "These figures come from an internally developed stochastic cyber risk "
        "model (scoring -> frequency/severity -> Monte Carlo -> VaR/ES). Model "
        "assumptions, parameter mappings and simulation logic are documented "
        "within the CyberRisk framework.\n"
        "Produce insurance recommendations."
    )


# Deterministic template used when no LLM backend is configured.
def rule_based_fallback(
    firm_name: str,
    risk_category: str,
    risk_drivers: list[str],
    eal: float,
) -> str:
    """Deterministic, always-available recommendation from the risk bands KB."""
    from agent.knowledge_base.risk_bands import BAND_GUIDANCE

    band = BAND_GUIDANCE.get(risk_category, BAND_GUIDANCE["Medium"])
    recs = "\n".join(f"  - {r}" for r in band["recommendations"])
    drivers = ", ".join(risk_drivers) if risk_drivers else "no single factor dominates"
    return (
        f"Firm: {firm_name}\n"
        f"Risk category: {risk_category}\n"
        f"Summary: {band['summary']}\n"
        f"Key risk drivers: {drivers}\n"
        f"Expected annual loss: ${eal:,.0f}\n"
        f"Recommendations:\n{recs}"
    )
