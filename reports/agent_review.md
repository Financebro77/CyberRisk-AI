# Senior Broker Review — CyberRiskAI Consultant Agent

**Reviewer role:** senior insurance broker (Marsh/Aon-style)
**Focus:** does the agent gather sufficient information *before* providing cyber risk advice?
**Standard applied:** *a broker who advises on incomplete data without asking is negligent.*
**Date:** 2026-08-02
**Evidence:** `examples/run_agent_review.py`, `tests/test_agent_elicitation.py` (20 tests)

---

## 1. Executive Finding

**Before this change, the agent failed the review on every count.** The prior `consultant_agent` was a "ready-to-advise" terminal: it took a pre-computed `ScoredFirm` + `RiskMetrics` and immediately produced recommendations. It had **zero** information-gathering capability — it never asked about industry, revenue, data volume, technology dependency, controls, incidents, coverage, or risk appetite. Hand it a blank profile and it would still advise.

**After the change, the agent passes.** A new **information-elicitation phase** (`src/agent/elicitation.py`) is now the mandatory first step. It:
- Knows the **8 dimensions** a broker needs, with a plain-English question and *why it matters* for each.
- Detects which are missing (including "unknown"/"n/a" placeholders).
- **Asks** for what's missing, **explains why it matters**, and **refuses** to give advice until complete.

---

## 2. What the Agent Now Asks For

| Dimension | The question the agent asks | Why it matters (what it changes) |
|---|---|---|
| **Industry** | What industry do you operate in? | Drives the baseline threat picture and regulatory duties |
| **Revenue** | What is your annual revenue? | Main driver of loss magnitude → shapes the limit |
| **Customer data volume** | How many records, how sensitive? | Drives notification/regulatory cost and class-action risk |
| **Technology dependency** | How dependent on IT / third parties? | Determines business-interruption cover need |
| **Security controls** | What controls (MFA, patching, EDR)? | Strongest predictor of event rate → risk score driver |
| **Previous incidents** | Any incidents in last 3-5 years? | Best evidence of real event rate (credibility) |
| **Existing coverage** | Current limits/retentions/sub-limits? | Identifies the coverage gap |
| **Risk appetite** | How much will you retain? | The objective the recommendation targets |

---

## 3. Missing-Information Scenarios Tested

| Scenario | Missing | Agent behaviour | Verdict |
|---|---|---|---|
| **A. New business — nothing provided** | all 8 | Asks all 8 questions; explains why each matters; refuses advice | **PASS** |
| **B. Manufacturer — no controls, no appetite** | 6 dimensions | Asks for controls, appetite + the rest; no premature advice | **PASS** |
| **C. Bank — no appetite, no incidents** | appetite + incidents | Asks both (and why) | **PASS** |
| **D. Hospital — no revenue, coverage, appetite** | 3 dimensions | Asks all three with reasons | **PASS** |

**Scenario A sample output** (new business, nothing given):
```
Before I can advise you on cyber risk, I need a little more information.
I have not drawn any conclusions yet -- the following would change the advice,
so I would rather ask than guess:

  * What industry does your company operate in?
      Why it matters: Sector drives the baseline threat picture: a bank is
      targeted far more often than a manufacturer...
  * What security controls are in place (MFA, patching, EDR, backups, IR)?
      Why it matters: Controls are the strongest predictor of how often you
      suffer an event and how contained it is...
  ...
```

---

## 4. The Three Required Behaviours — Verified

1. **Asks clarifying questions** — the agent flags exactly the missing dimensions (test asserts each of the 8 is detected when removed individually, and each missing triggers a question).
2. **Avoids premature conclusions** — `advise()` **never calls the model** while data is incomplete (test proves `score_and_run` is *not* invoked); the response explicitly says "I have not drawn any conclusions yet."
3. **Explains why information matters** — every question carries a non-trivial "why" tied to the advice outcome (test requires ≥ 5 words of reasoning; each is 1-2 sentences of real substance).

---

## 5. Defensive Checks a Broker Would Care About

- **"unknown" / "n/a" / "not sure" are treated as gaps, not answers.** A client who says "not sure" on revenue is flagged, not silently defaulted.
- **Legitimate zeros are accepted.** "0 records" or "0 incidents" is real information, not a gap — the agent proceeds (tested).
- **The guard is structural, not cosmetic.** `advise()` returns an `ElicitationResult` (questions) — a different type from `ConsultantRecommendation`. The caller cannot accidentally treat "please give me more info" as advice.
- **Reproducible / testable.** All 20 elicitation tests are deterministic; no LLM needed for the elicitation phase (works in rule-based mode).

---

## 6. Residual Findings & Recommendations

1. **The elicitation asks all missing dimensions at once.** A real broker often prioritises (ask for revenue and incidents first; data volume can wait). Consider adding a `priority` to dimensions so the first message asks only the top 3-4. **Medium — not yet done.**
2. **No follow-up dialogue yet.** ✅ **DONE — implemented.** `ConsultationSession` in `elicitation.py` is a multi-turn loop: it merges answers turn-by-turn, re-asks only what's still missing, pushes back on "unknown", blocks after `max_turns`, and treats a vague risk appetite ("keep our premium low") as not-yet-provided. See `examples/run_consultation_demo.py`.
3. **The 'why it matters' is static text.** Fine for now, but it could be personalised (e.g. "as a bank, revenue is especially important because..."). Low priority.
4. **No risk-appetite validation.** ✅ **DONE — implemented.** `agent/risk_appetite.py` parses a retention from free text ("$1M", "retain 500k", "as little as possible") and validates it against the modelled EAL/ES99 with three ratings: **sensible** (≤ 2×EAL), **high** (2×EAL → ES99), **self-insuring** (> ES99). Wired into `advise(risk_appetite_text=...)`. A client wanting to retain $60M against a $50M ES99 is told they're self-insuring the catastrophe.

---

## 6.5 What Changed (follow-up implementation)

**Dialogue loop** (`src/agent/elicitation.py` — `ConsultationSession`):
- Multi-turn: the client answers in pieces; the agent merges each turn and re-asks ONLY the still-missing dimensions.
- "unknown"/"n/a" answers are pushed back, not accepted.
- A vague risk appetite ("we want to keep our premium low") is treated as not-yet-provided — the agent asks for a figure, exactly as a broker would.
- Bounded: blocks after `max_turns` (default 6) if no progress, with a graceful "I'd rather not guess" close.

**Risk-appetite validation** (`src/agent/risk_appetite.py`):
- Parses a retention from free text ("$1M", "retain 500k", "as little as possible" → 0).
- Validates against modelled EAL / ES99 with three verdicts:
  - **sensible** — retention ≤ 2×EAL (you're retaining ordinary losses);
  - **high** — 2×EAL < retention ≤ ES99 (you're self-funding a chunk of the tail);
  - **self-insuring** — retention > ES99 (you'd fund the worst case yourself).
- Wired into `advise(risk_appetite_text=...)`; a vague figure returns an "unparseable" verdict asking for a dollar amount.

**Demo:** `examples/run_consultation_demo.py` runs a full first meeting — industry/revenue → data/tech → "unknown" controls (re-asked) → incidents/coverage/vague appetite (re-asked) → real figure → appetite verdict + advice.

---

## 7. Overall Verdict

**PASS — both §6 follow-ups now implemented.**

The agent behaves like a competent first-meeting broker: it establishes the eight facts it needs (over a dialogue, not one shot), tells the client why each matters, refuses premature advice on incomplete data, pushes back on "unknown"/vague answers, and reality-checks the client's stated retention against the modelled loss. The three required behaviours — **ask, avoid premature conclusions, explain why** — plus the §6 dialogue and appetite checks are all implemented and enforced by tests.

**Remaining (optional):** prioritising which questions to ask first (§6.1) and personalised "why it matters" text (§6.3) — both low priority.
