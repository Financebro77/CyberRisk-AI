"""Safety guardrails for the consultant agent (AI-safety review, hallucination).

The safety evaluator's standard: an advisory agent must NEVER invent facts,
must ADMIT uncertainty, must REQUEST missing information, must not leak
confidential client data, and must cite the assumptions behind any claim.

This module classifies a client's request/question into one of five
adversarial classes and returns a SAFE response for each:

    1. nonexistent_stat    asks for a statistic/benchmark the model does not
                           hold ("average ransom in Kazakhstan", "the 2027
                           breach-cost figure") -> admit we don't have it;
                           offer what we DO hold (calibrated benchmarks).
    2. confidential_data   asks about another client's exposure/limits/policy
                           ("what limit did Acme buy?") -> refuse, do not
                           speculate.
    3. unsupported_recommendation  asks to recommend a specific product,
                           vendor, or a conclusion the model cannot support
                           ("which insurer should I buy from?") -> decline to
                           endorse a named product; offer the modelling.
    4. ambiguous_info      the client's answer is too vague to score
                           ("we're in finance") -> ask to disambiguate.
    5. contradictory_info  two answers conflict ("revenue $500M" + "we are a
                           startup with 5 staff") -> flag the contradiction,
                           ask which is right, never guess.

For any request that IS within the model's remit, the agent proceeds to the
normal elicit/advise flow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SafetyVerdict:
    """Outcome of guarding a client request."""

    class_name: str  # one of the five classes, or "ok"
    flagged: bool  # True if the request was intercepted
    response: str  # safe client-facing text (empty when flagged=False)
    assumptions_cited: list[str] = None  # assumptions we disclosed (if any)


@dataclass
class OutputCheck:
    """Result of checking a generated (LLM) response for hallucination."""

    ok: bool  # True if the response is safe to show the client
    reason: str  # plain-English explanation of what was found (empty if ok)
    offending: list[str] = None  # the specific tokens/phrases flagged (if any)


# Names/terms the agent must never endorse or quote as fact.
_NAMED_INSURERS = re.compile(
    r"\b(aig|allianz|axa|chubb|travellers?|beazley|hiscox|cna|society general|"
    r"tokio marine|munich re|swiss re|covea|msig|qbe|great american|travelers)\b",
    re.I,
)
_NAMED_VENDORS = re.compile(
    r"\b(crowdstrike|sentinelone|palo alto|check point|fortinet|sophos|carbon black|"
    r"crowd?strike|trellix|zscaler|okta|duo|crowdstrike)\b",
    re.I,
)
_OVERCERTAIN_PHRASES = re.compile(
    r"\b(guaranteed?|100%\s*(safe|covered|protected)|will definitely|absolutely no risk|"
    r"cannot be hacked|impossible to breach|never a breach)\b",
    re.I,
)
# Known insurance carriers / vendors the calibrated model does NOT track.
_KNOWN_CARRIER_NAMES = {"aig", "allianz", "axa", "chubb", "travelers", "beazley", "hiscox"}


def check_llm_output(
    text: str,
    validated_metrics: dict[str, float] | None = None,
) -> OutputCheck:
    """Check a generated (LLM) response for hallucination before showing it.

    Three checks:
      1. NAMED PARTIES -- any specific insurer/vendor named is an unsupported
         endorsement the agent must not make.
      2. OVER-CERTAINTY -- "guaranteed", "100% safe", "cannot be hacked" etc.
         overpromise and must be refused.
      3. UNSUPPORTED FIGURES -- any US$ figure that does not match a validated
         model output (EAL / VaR / ES / PML).  We accept figures that round
         to a validated metric; anything else is an invented number.

    Parameters
        text               the LLM's generated response
        validated_metrics  dict of validated model figures, e.g.
                           {"EAL": 5_000_000, "ES99": 50_000_000}.  When
                           provided, any $ figure not within tolerance of one
                           of these is flagged as invented.

    Returns
        OutputCheck.  `ok=True` only if NONE of the three checks fire.
    """
    if not text:
        return OutputCheck(ok=True, reason="")

    offending: list[str] = []
    reason_parts: list[str] = []

    # 1. Named parties
    for m in _NAMED_INSURERS.finditer(text):
        token = m.group(0)
        offending.append(f"named insurer: {token}")
    for m in _NAMED_VENDORS.finditer(text):
        token = m.group(0)
        offending.append(f"named vendor: {token}")
    if any("named insurer" in o or "named vendor" in o for o in offending):
        reason_parts.append("the response names a specific insurer/vendor, which the agent must not endorse")

    # 2. Over-certainty
    for m in _OVERCERTAIN_PHRASES.finditer(text):
        offending.append(f"over-certain claim: {m.group(0)}")
    if any("over-certain" in o for o in offending):
        reason_parts.append("the response makes a guarantee the model cannot support")

    # 3. Unsupported figures presented as FACT about the model.
    #    We only flag a figure that the LLM presents as a model output claim
    #    ("your EAL will be $42M", "the modelled loss is X") and that does NOT
    #    match a validated metric.  A figure offered as a RECOMMENDATION
    #    ("consider a retention around $5M") is legitimate and not flagged --
    #    recommendations are the agent's job, invented model claims are not.
    if validated_metrics:
        # claims that frame a number as a model fact
        claim_patterns = [
            re.compile(r"(your\s+)?(eal|expected annual loss|modelled (loss|cost|exposure)|"
                       r"the (model|model's) (says|shows|implies)|forecast|predicted)\b", re.I),
            re.compile(r"(will be|is exactly|amounts? to|comes to|equals?)\s*\$", re.I),
        ]
        for m in re.finditer(r"[$]\s?([\d][\d,]*(?:\.\d+)?)\s?(k|m|b|million|billion|thousand)?", text, re.IGNORECASE):
            raw = m.group(1).replace(",", "")
            try:
                number = float(raw)
            except ValueError:
                continue
            unit = m.group(2)
            mult = {"k": 1e3, "m": 1e6, "b": 1e9, "thousand": 1e3, "million": 1e6, "billion": 1e9}.get(
                (unit or "").lower(), 1.0
            )
            value = number * mult
            # only consider it a claim if a claim-framing phrase is nearby
            window = text[max(0, m.start() - 60): m.end() + 20]
            is_claim = any(p.search(window) for p in claim_patterns)
            if not is_claim:
                continue
            # Accept if it matches any validated metric within 5% (rounding)
            if not any(abs(value - v) / max(v, 1e-9) < 0.05 for v in validated_metrics.values()):
                offending.append(f"unsupported figure: ${raw}{unit or ''}")
        if any("unsupported figure" in o for o in offending):
            reason_parts.append("the response states a dollar figure as a model fact that does not match the validated output")

    if offending:
        return OutputCheck(ok=False, reason="; ".join(reason_parts) or "response failed safety checks", offending=offending)
    return OutputCheck(ok=True, reason="")


# ---------------------------------------------------------------------------
# RAG output check — extend the base hallucination guard with retrieval-aware
# verification, so the "never fabricate facts without supporting documents"
# guarantee is enforced post-generation, not just by prompt.
# ---------------------------------------------------------------------------

# A citation marker in an answer: [citation: <chunk_id>]
_CITATION_RE = re.compile(r"\[citation:\s*([^\]]+)\]", re.IGNORECASE)


def _extract_figures(text: str) -> list[float]:
    """Extract all numeric figures (with k/m/b multipliers) from text."""
    out: list[float] = []
    for m in re.finditer(
        r"[$]?\s?([\d][\d,]*(?:\.\d+)?)\s?(k|m|b|million|billion|thousand)?",
        text,
        re.IGNORECASE,
    ):
        try:
            raw = m.group(1).replace(",", "")
            number = float(raw)
        except ValueError:
            continue
        unit = m.group(2)
        mult = {
            "k": 1e3, "m": 1e6, "b": 1e9,
            "thousand": 1e3, "million": 1e6, "billion": 1e9,
        }.get((unit or "").lower(), 1.0)
        out.append(number * mult)
    return out


def _figure_in_texts(value: float, texts: list[str], tolerance: float = 0.05) -> bool:
    """True if ``value`` matches a number in any ``texts`` within ``tolerance``."""
    for t in texts:
        for fig in _extract_figures(t):
            if fig > 0 and abs(value - fig) / fig < tolerance:
                return True
    return False


def check_rag_output(
    text: str,
    validated_metrics: dict[str, float] | None = None,
    retrieved_chunks: list | None = None,
) -> OutputCheck:
    """Check an LLM response that may cite retrieved knowledge.

    Runs the base ``check_llm_output`` (named parties, over-certainty,
    unsupported figures vs engine metrics), then adds three RAG-specific
    checks:

      1. CITATION RESOLUTION -- every [citation: chunk_id] in the answer must
         resolve to a retrieved chunk.  A citation to nothing is a fabrication.
      2. DOCUMENT-FIGURE CLAIMS -- a claim-framed figure that does NOT match a
         validated engine metric must match a retrieved document's content.
         If it matches neither, it is invented.
      3. DOCUMENT FACT GROUNDING -- if the answer cites a retrieved chunk, the
         chunk must be one of the retrieved chunks (already guaranteed by #1);
         this is the "never assert a document fact without supporting evidence".

    Parameters
        text               the LLM's generated response
        validated_metrics  validated engine figures (EAL/VaR/ES/PML) — engine
                           numbers stay authoritative
        retrieved_chunks   list of RetrievedChunk (or objects with .chunk_id,
                           .content) the retriever found

    Returns
        OutputCheck.  ok=False if any check fires — the caller should fall back
        to the deterministic rule-based answer.
    """
    # Base checks (named parties, over-certainty, engine-figure claims).
    # NOTE: base failures are MERGED with the RAG checks below, not returned
    # early — a [MODEL OUTPUT]-tagged figure may be flagged by both the base
    # unsupported-figure check AND the MODEL-OUTPUT check, and the caller needs
    # the specific reason.  If nothing is retrieved, the base verdict stands.
    base = check_llm_output(text, validated_metrics)

    if not retrieved_chunks:
        # No retrieval happened: nothing extra to verify.  (The agent's prompt
        # still forbids inventing facts, and base checks catch unsupported
        # engine figures.)
        return base

    by_id = {c.chunk_id: c for c in retrieved_chunks}
    contents = [c.content for c in retrieved_chunks]
    offending: list[str] = list(base.offending or [])
    reason_parts: list[str] = []

    # 1. Citation resolution.
    cited_ids = set(_CITATION_RE.findall(text))
    for cid in cited_ids:
        if cid not in by_id:
            offending.append(f"citation does not resolve: {cid}")
    if any("citation does not resolve" in o for o in offending):
        reason_parts.append("the response cites a document that was not retrieved")

    # 2. Document-figure claims: a claim-framed figure that isn't an engine
    #    metric must match a retrieved document.
    if validated_metrics:
        for m in re.finditer(
            r"[$]\s?([\d][\d,]*(?:\.\d+)?)\s?(k|m|b|million|billion|thousand)?",
            text,
            re.IGNORECASE,
        ):
            raw = m.group(1).replace(",", "")
            try:
                value = float(raw) * {
                    "k": 1e3, "m": 1e6, "b": 1e9,
                    "thousand": 1e3, "million": 1e6, "billion": 1e9,
                }.get((m.group(2) or "").lower(), 1.0)
            except ValueError:
                continue
            # Claim-framed?
            claim_patterns = [
                re.compile(r"(document|the (source|report|regulation) (says|states|notes|requires)|"
                           r"according to the retrieved|the retrieved (doc|document) states)\b", re.I),
            ]
            window = text[max(0, m.start() - 60): m.end() + 20]
            is_doc_claim = any(p.search(window) for p in claim_patterns)
            if not is_doc_claim:
                continue
            # It must be an engine metric (already allowed by base) OR a
            # retrieved document figure.
            is_engine = any(
                abs(value - v) / max(v, 1e-9) < 0.05 for v in validated_metrics.values()
            )
            if not is_engine and not _figure_in_texts(value, contents):
                offending.append(f"unsupported document figure: ${raw}")

    # 3. Document-fact grounding: every cited chunk must be retrieved (already
    #    covered by #1), and any document-framed assertion must carry a citation.
    #    A document-framed claim with NO citation is unverifiable -> flag.
    doc_claim_phrases = re.compile(
        r"(the (regulation|directive|report|document|source) (says|states|notes|requires|establishes)|"
        r"according to (the|a) (regulation|directive|report|document|source))\b",
        re.I,
    )
    for m in doc_claim_phrases.finditer(text):
        window = text[m.start(): m.end() + 200]
        if not _CITATION_RE.search(window):
            offending.append("document fact without citation")
            break

    # 4. MODEL-OUTPUT tag verification — every [MODEL OUTPUT]-tagged figure must
    #    match a validated engine metric.  A fabricated model figure is flagged.
    for m in re.finditer(
        r"\[MODEL OUTPUT\][^\n]*?\$([\d][\d,]*(?:\.\d+)?)\s?(k|m|b|million|billion|thousand)?",
        text,
        re.IGNORECASE,
    ):
        try:
            value = float(m.group(1).replace(",", "")) * {
                "k": 1e3, "m": 1e6, "b": 1e9,
                "thousand": 1e3, "million": 1e6, "billion": 1e9,
            }.get((m.group(2) or "").lower(), 1.0)
        except ValueError:
            continue
        if not any(
            abs(value - v) / max(v, 1e-9) < 0.05 for v in validated_metrics.values()
        ):
            offending.append(f"MODEL OUTPUT figure not in tool results: ${m.group(1)}")

    # 5. INDUSTRY-EVIDENCE tag grounding — every [INDUSTRY EVIDENCE]-tagged
    #    claim must carry a citation that resolves, OR its figure must match a
    #    retrieved document.  Otherwise it's ungrounded "evidence".
    for m in re.finditer(r"\[INDUSTRY EVIDENCE\]", text, re.IGNORECASE):
        window = text[m.start(): m.end() + 300]
        has_citation = _CITATION_RE.search(window) or re.search(r"\[incident: ([^\]]+)\]", window)
        has_grounding = False
        for fm in re.finditer(
            r"\$([\d][\d,]*(?:\.\d+)?)\s?(k|m|b|million|billion|thousand)?",
            window,
            re.IGNORECASE,
        ):
            try:
                value = float(fm.group(1).replace(",", "")) * {
                    "k": 1e3, "m": 1e6, "b": 1e9,
                    "thousand": 1e3, "million": 1e6, "billion": 1e9,
                }.get((fm.group(2) or "").lower(), 1.0)
            except ValueError:
                continue
            if _figure_in_texts(value, contents):
                has_grounding = True
                break
        if not has_citation and not has_grounding:
            offending.append("INDUSTRY EVIDENCE claim without a resolvable citation or matching document")

    # 6. Assumption-presented-as-fact — a claim-framed $ figure that matches
    #    NEITHER a tool metric NOR a retrieved document is an unsourced
    #    assumption stated as a fact.
    if validated_metrics:
        for m in re.finditer(
            r"\$([\d][\d,]*(?:\.\d+)?)\s?(k|m|b|million|billion|thousand)?",
            text,
            re.IGNORECASE,
        ):
            try:
                value = float(m.group(1).replace(",", "")) * {
                    "k": 1e3, "m": 1e6, "b": 1e9,
                    "thousand": 1e3, "million": 1e6, "billion": 1e9,
                }.get((m.group(2) or "").lower(), 1.0)
            except ValueError:
                continue
            is_engine = any(
                abs(value - v) / max(v, 1e-9) < 0.05 for v in validated_metrics.values()
            )
            if not is_engine and not _figure_in_texts(value, contents):
                # Skip figures already flagged by check #2 (unsupported doc fig).
                offending.append(f"assumption presented as fact: ${m.group(1)}")

    # Include the base (non-RAG) reason if it fired, so a merged verdict
    # explains both the base and the RAG-specific failures.
    if base.reason:
        reason_parts.insert(0, base.reason)
    if any("unsupported document figure" in o for o in offending):
        reason_parts.append("the response states a document figure that neither the engine nor the retrieved documents support")
    if any("document fact without citation" in o for o in offending):
        reason_parts.append("the response asserts a document fact without citing a retrieved chunk")
    if any("MODEL OUTPUT figure not in tool results" in o for o in offending):
        reason_parts.append("the response labels a figure [MODEL OUTPUT] that does not match any tool result")
    if any("INDUSTRY EVIDENCE claim without" in o for o in offending):
        reason_parts.append("the response labels a claim [INDUSTRY EVIDENCE] with no resolvable citation or matching document")
    if any("assumption presented as fact" in o for o in offending):
        reason_parts.append("the response presents an unsourced figure as a fact (an assumption, not verified)")

    if offending:
        return OutputCheck(
            ok=False,
            reason="; ".join(reason_parts) or "response failed RAG checks",
            offending=offending,
        )
    return OutputCheck(ok=True, reason="")


# ---------------------------------------------------------------------------
# 1. Nonexistent / out-of-scope statistics
# ---------------------------------------------------------------------------
# Phrases that ask for a figure the calibrated model does not hold:
# a specific country/region stat, a future year, a specific insurer's data,
# or a benchmark with no source in our calibration.
# NOTE: the statistic must be a real statistic (cost/loss/rate/payment +
# a place/time/scope) -- NOT a generic "buy a product" or "what limit".
_NONEXISTENT_PATTERNS = [
    re.compile(r"(average|median|typical|standard).*(ransom|breach|loss|cost|payment|rate)", re.I),
    re.compile(r"(ransom|breach|loss|cost|payment|rate).*\bin\s+\b(canada|france|germany|india|china|japan|australia|brazil|kazakhstan|uk|ireland|scandinavia|nordic)\b", re.I),
    re.compile(r"(2026|2027|2028|2029|2030)\s+(breach|ransom|loss|cost|payment)", re.I),
    re.compile(r"(average|typical|median|standard)\b.*\b(ransom|breach|downtime|outage)\b", re.I),
]

# Words that show the user is asking about THEIR OWN firm (a legitimate
# modelling request) rather than a generic industry/regional statistic.
_CLIENT_CONTEXT = re.compile(
    r"\b(assess|model|our|my|we are|we're|our company|our firm|my company|"
    r"company|firm|business|organisation|revenue|records|portfolio|"
    r"retention|policy|premium)\b",
    re.I,
)


def _looks_like_generic_stat(text: str) -> bool:
    """True when the request asks for a generic statistic AND gives no context
    about a specific client the agent could model instead.

    Pattern #4 (the `(what|how much)...loss/cost/premium/rate` catch-all) is
    meant for "what is the average ransom in Canada" -- a figure the model
    does not hold.  It must NOT swallow "assess MY company and what is the
    expected annual loss", which is the agent's core job.
    """
    generic_ask = re.search(
        r"(what|how much|how many|quote|figure|number|stat)\b.*\b(paid?|cost|loss|premium|rate)\b",
        text,
        re.I,
    )
    if not generic_ask:
        return False
    return not _CLIENT_CONTEXT.search(text)


def guard_statistics_request(text: str) -> SafetyVerdict | None:
    """Intercept requests for statistics we don't have."""
    if any(p.search(text) for p in _NONEXISTENT_PATTERNS) or _looks_like_generic_stat(text):
        return SafetyVerdict(
            class_name="nonexistent_stat",
            flagged=True,
            response=(
                "I don't hold a figure for that specific statistic, and I won't "
                "invent one.  I do have sector-level benchmarks (from Verizon DBIR, "
                "IBM Cost of a Data Breach, and similar) that I can use to model "
                "YOUR exposure -- tell me your industry and revenue and I'll show you "
                "what the calibrated model implies for your firm."
            ),
            assumptions_cited=["calibrated benchmarks: Verizon DBIR, IBM CODB, Hiscox"],
        )
    return None


# ---------------------------------------------------------------------------
# 2. Confidential data about another client
# ---------------------------------------------------------------------------
_CONFIDENTIAL_PATTERNS = [
    re.compile(r"\b(acme|competitor|another|other)\s+(client|firm|company|broker|insurer)\b", re.I),
    re.compile(r"\b(their|his|her)\s+(limit|retention|premium|policy|coverage|exposure)\b", re.I),
    re.compile(r"\b(what limit|how much).*(competitor|their|their's)\b", re.I),
    re.compile(r"\b(competitor|their)\b.*\b(pay|paid|premium|coverage|limit)\b", re.I),
    # any named company + a coverage/limit/buy term -> another client's confidential data
    re.compile(r"\b(acme corp|acme|globo corp|megacorp|bigcorp|northwind|contoso)\b.*\b(limit|coverage|premium|policy|retention|buy|bought|paid)\b", re.I),
]


def guard_confidential(text: str) -> SafetyVerdict | None:
    """Refuse to disclose or speculate about another party's data."""
    if any(p.search(text) for p in _CONFIDENTIAL_PATTERNS):
        return SafetyVerdict(
            class_name="confidential_data",
            flagged=True,
            response=(
                "I can't discuss another client's limits, premiums, or exposure -- "
                "that's confidential, and I won't speculate.  What I CAN do is model "
                "your own exposure and suggest a sensible limit range for a firm of "
                "your size and sector."
            ),
            assumptions_cited=[],
        )
    return None


# ---------------------------------------------------------------------------
# 3. Unsupported recommendations (specific vendor / product / unbacked claim)
# ---------------------------------------------------------------------------
_UNSUPPORTED_PATTERNS = [
    # asking to pick a SPECIFIC named product/vendor (not a generic "what limit")
    re.compile(r"\b(which|recommend|should i (use|buy|pick))\b.*\b(insurer|carrier|vendor|provider|product|tool|solution)\b", re.I),
    re.compile(r"\b(insurer|carrier|vendor|provider|tool)\b.*\b(name|recommend|pick|choose|which)\b", re.I),
    re.compile(r"\b(buy|purchase|switch to|go with)\s+(a|an|the)?\s*(named\s+)?(insurer|carrier|vendor|provider|product|tool|solution)\b", re.I),
    re.compile(r"\b(best|top|greatest|most recommended)\s+(tool|product|vendor|insurer|carrier|provider|solution)\b", re.I),
    re.compile(r"\b(name|tell me|suggest)\s+(a|the)?\s*(best|good|top)?\s*(tool|product|vendor|insurer|carrier|provider|solution)\b", re.I),
    re.compile(r"\b(guarantee|promise|will definitely|100% safe|no risk)\b", re.I),
]


def guard_unsupported_recommendation(text: str) -> SafetyVerdict | None:
    """Decline to endorse a named vendor / give an unbacked guarantee."""
    if any(p.search(text) for p in _UNSUPPORTED_PATTERNS):
        return SafetyVerdict(
            class_name="unsupported_recommendation",
            flagged=True,
            response=(
                "I won't name a specific insurer, vendor, or product -- I'm not "
                "licensed to sell and I don't have their current terms.  What I CAN "
                "give you is a defensible LIMIT and RETENTION range from the modelled "
                "loss distribution, and the questions to ask any carrier.  I also "
                "won't promise a specific outcome; I'll give you the probabilities "
                "the model implies."
            ),
            assumptions_cited=["modelled loss distribution", "no endorsement of any carrier"],
        )
    return None


# ---------------------------------------------------------------------------
# 4. Ambiguous information
# ---------------------------------------------------------------------------
# Answers too vague to score: sector/business descriptors with no shape,
# or a value that could mean several things.
_AMBIGUOUS_WORDS = {
    "finance", "fintech", "tech", "services", "it", "digital", "retail-ish",
    "like a bank", "big company", "a startup", "startup", "a small firm",
}
_AMBIGUOUS_PATTERNS = [
    # bare vague descriptors: "finance", "we're in finance", "in IT services"
    re.compile(r"(?:we'?re|we are|in the|in|it's|it is|a)\s+(finance|fintech|tech|services|it|digital|it services)", re.I),
    re.compile(r"^\s*(finance|fintech|tech|services|it|digital|it services)\s*$", re.I),
    # "startup" / "small firm" with no industry shape (a bare startup gives
    # no sector to pick a baseline from; a specific sector is not ambiguous)
    re.compile(r"\b(startup|a startup|small firm)\b", re.I),
]


def guard_ambiguity(text: str) -> SafetyVerdict | None:
    """Flag an answer that is too vague to score and ask to disambiguate."""
    stripped = text.strip().lower()
    if stripped in {w.lower() for w in _AMBIGUOUS_WORDS} or any(
        p.search(text) for p in _AMBIGUOUS_PATTERNS
    ):
        return SafetyVerdict(
            class_name="ambiguous_info",
            flagged=True,
            response=(
                "That's a little too broad for me to score accurately.  For example, "
                "'finance' could mean a small fintech, a mid-market insurer, or a "
                "global bank -- and those carry very different cyber risk.  Could you "
                "tell me more precisely what your company does, and roughly how many "
                "employees you have?"
            ),
            assumptions_cited=["precise sector is needed to pick the right baseline"],
        )
    return None


# ---------------------------------------------------------------------------
# 5. Contradictory information
# ---------------------------------------------------------------------------
# Two client answers conflict.  We detect the common cases and ask which is
# right rather than guessing.
_REVENUE_RE = re.compile(r"revenue", re.I)
_STAFF_RE = re.compile(r"(employ|staff|headcount|people|size)", re.I)
_INCIDENTS_RE = re.compile(r"incident", re.I)


def detect_contradictions(answers: dict[str, object]) -> list[str]:
    """Check a set of client answers for internal contradictions.

    Returns a list of human-readable contradiction descriptions.  The rule is
    always: flag, then ask which is right -- never guess.

    Checks:
      - revenue vs headcount (a $100M+ firm with <20 staff is implausible)
      - a large firm claiming zero incidents AND no coverage (contradicts the
        risk picture -- a firm that large with no incidents at all is unusual)
      - negative incident count
      - zero incidents but a fully-tested incident response plan (if a firm
        claims a tested plan AND zero incidents, that's plausible -- but a
        claim of 'tested' with no incidents to have learned from is worth a
        light check only if the firm is large)
    """
    contradictions: list[str] = []

    revenue = answers.get("revenue")
    staff = answers.get("employees") or answers.get("staff") or answers.get("headcount")
    incidents = answers.get("previous_incidents")

    # revenue vs staff: a tiny company with huge revenue (or vice versa) is
    # implausible enough to question.
    if isinstance(revenue, (int, float)) and isinstance(staff, (int, float)):
        if staff <= 20 and revenue >= 100_000_000:
            contradictions.append(
                f"you report revenue of ${revenue:,.0f} but only {staff:.0f} employees "
                f"-- that combination is implausible for most sectors."
            )
        if staff >= 10_000 and revenue <= 1_000_000:
            contradictions.append(
                f"you report {staff:.0f} employees but only ${revenue:,.0f} in revenue "
                f"-- that combination is implausible for most sectors."
            )

    if isinstance(incidents, (int, float)) and incidents < 0:
        contradictions.append("the incident count can't be negative.")

    # a large firm with zero incidents AND no insurance AND weak controls is
    # suspicious enough to ask about (the answers fight the size).
    if (
        isinstance(revenue, (int, float))
        and revenue >= 250_000_000
        and isinstance(incidents, (int, float))
        and incidents == 0
    ):
        controls = str(answers.get("security_controls") or "").lower()
        if not controls or any(w in controls for w in ("none", "no", "minimal", "weak")):
            contradictions.append(
                "you report a large firm (over $250M) with no recorded incidents "
                "and weak or no security controls -- that combination is very "
                "unusual and worth confirming before I model your risk."
            )

    return contradictions


def guard_contradiction(answers: dict[str, object]) -> SafetyVerdict | None:
    """Flag contradictions in the provided answers; never guess which is right."""
    issues = detect_contradictions(answers)
    if issues:
        detail = "\n".join(f"  - {i}" for i in issues)
        return SafetyVerdict(
            class_name="contradictory_info",
            flagged=True,
            response=(
                f"I noticed something that doesn't quite add up before I model your "
                f"risk:\n{detail}\n\nI'd rather resolve this than guess.  Could you "
                f"confirm which is correct?  Getting the size and revenue right "
                f"matters -- it drives how large a loss the model expects."
            ),
            assumptions_cited=["size vs revenue consistency", "non-negative incident count"],
        )
    return None


# ---------------------------------------------------------------------------
# Top-level guard
# ---------------------------------------------------------------------------

def guard_request(text: str | None, answers: dict[str, object] | None = None) -> SafetyVerdict:
    """Run all guards; return the first interception, else an 'ok' verdict.

    Parameters
        text      the client's request / question (may be None)
        answers   any client-provided dimension answers (for contradiction check)

    Returns
        SafetyVerdict.  If `flagged` is False the request is safe to proceed
        through the normal elicit/advise flow.
    """
    if text:
        # Confidentiality is the highest-priority concern: another party's
        # data must be refused regardless of how it's phrased, so check it
        # FIRST before the other guards can mislabel it.
        for guard in (guard_confidential, guard_statistics_request, guard_unsupported_recommendation, guard_ambiguity):
            verdict = guard(text)
            if verdict is not None:
                return verdict
    if answers:
        verdict = guard_contradiction(answers)
        if verdict is not None:
            return verdict
    return SafetyVerdict(class_name="ok", flagged=False, response="", assumptions_cited=[])
