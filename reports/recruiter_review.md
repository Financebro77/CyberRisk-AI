# Recruiter Review — CyberRiskAI Project

**Reviewer role:** senior recruiter, Risk Analytics (Marsh/Aon-style)
**Project:** CyberRiskAI — AI-enabled commercial cyber risk assessment platform
**Date:** 2026-08-02
**Scope:** technical sophistication, insurance relevance, quant modelling quality, AI implementation, business value, CV positioning.

---

## 1. What This Project Is (honest framing)

CyberRiskAI is a **cyber insurance risk modelling platform**: it scores a firm's cyber profile, calibrates scenario-based frequency/severity loss models, runs Monte Carlo simulation, computes VaR / Expected Shortfall / return-period PML, applies insurance policy terms (retained vs transferred loss), adds credibility & parameter-uncertainty, and wraps it all in a consultant agent that gathers information, guards against hallucination, and produces client-facing recommendations.

**Scale:** ~3,800 lines of source across 27 modules, ~4,000 lines across 31 test files, **289 tests passing**, 6 written reports (validation, improvement roadmap, benchmark, agent review, hallucination, client engagement).

---

## 2. Evaluation by Criterion

### 2.1 Technical Sophistication — **7.5/10**

**Strengths**
- Clean `src/` package layout with a real distinction between core engine (`cyberrisk/`) and agent (`agent/`).
- **Configuration-driven modelling**: scenarios, scoring weights, uncertainty specs, and simulation knobs all live in YAML/CSV — no hard-coded parameters. This is a professional, audit-friendly pattern.
- **Reproducibility baked in**: chunk-stable, seed-driven Monte Carlo; results are bit-identical across runs and machines.
- **Deep test culture**: 289 tests split into unit tests *and* an insurance-principle validation suite (`tests/validate/`) that checks *why* numbers behave, not just *that* they run.
- Good docstrings that read like a practitioner's explanation, not boilerplate.

**Weaknesses**
- No packaging metadata beyond a minimal `pyproject.toml` (no `README.md`, no `LICENSE`, no CI/CD).
- No performance optimisation or profiling; the simulation is vectorised but there's no benchmark of runtime at scale.
- No type-checking/linting configuration (no `mypy`/`ruff` config), no pre-commit hooks.

### 2.2 Insurance Industry Relevance — **8.5/10**

**Strengths**
- **The core is genuinely industry-shaped**: occurrence-level simulation (policy terms applied per event before aggregation — the *correct* actuarial approach), Poisson/NegBin frequency, lognormal/GPD severity, Gaussian/Student-t copula dependence, credibility weighting (limited-fluctuation), parameter uncertainty bands, return-period PML. These are the actual building blocks of cyber CAT models.
- **Explainability for a broker**: every concept has a plain-English framing ("burstiness", "catastrophe years", "engineer's tolerance"). This is exactly what a Marsh practice needs.
- **Benchmark profile framework** tests the model across a realistic risk spectrum (manufacturing → bank → hospital → micro-firm).

**Weaknesses**
- **Calibration data is mock/illustrative.** The λ, severity, and dependence parameters are anchored to public benchmarks + documented assumptions, not a licensed loss dataset (Advisen/Cyence). An industry practitioner would probe this immediately.
- No actual **premium/pricing** output (rate-on-line, premium basis) — the model stops at "limit/retention gap", not "price".

### 2.3 Quantitative Modelling Quality — **8/10**

**Strengths**
- **Analytically validated**: simulated EAL matches closed-form λ·E[S] to 0.2%; ES99/P99.9 convergence and bootstrap SEs reported; Hill tail index confirms heavy-but-finite-variance tail.
- **Correct risk-measure discipline**: ES99 is reported *alongside* VaR because it's the decision-relevant tail measure; PML is reported as return-period percentiles (not the unstable sample max).
- **Dependence handled properly**: Student-t copula for genuine tail dependence, with the copula-level χ(0.99) measured (2.4× the Gaussian) — not just asserted.
- **Uncertainty is quantified** (credibility + parameter bands), which is rare in student work.

**Weaknesses**
- **Severity drivers are thin**: loss scales only with revenue via a single exponent; no sector-specific calibration, no sensitivity to data volume or downtime.
- **No tail extrapolation**: the model estimates tail percentiles from simulation; it doesn't fit a parametric tail (e.g. Peaks-over-Threshold) to stabilise the deepest quantiles, which real cyber models do.
- **No parameter-uncertainty propagated into the LLM agent's confidence** (the agent speaks in points, not bands).

### 2.4 AI Implementation Quality — **7.5/10**

**Strengths**
- **The agent is grounded**: it only reasons over validated model outputs, never raw internals.
- **Information elicitation**: refuses to advise until the 8 dimensions a broker needs are gathered — a genuine domain-aware behavior.
- **Hallucination guardrails**: deterministic classification of 5 adversarial classes + a post-generation check on LLM output with a rule-based fallback. This is genuinely safety-conscious and rare.
- **Testable without an LLM**: rule-based fallback means the whole agent is deterministic and unit-testable.

**Weaknesses**
- **No real LLM integration demonstrated** — the agent has an `llm_backend` seam but no working example with an actual model. A reviewer can't see it "think."
- **The elicitation is rule-based**, not conversational AI — a real LLM would make the interview feel more natural.
- **No multi-turn memory beyond the session** — no persistence, no RAG over a knowledge base.

### 2.5 Business Value — **8/10**

**Strengths**
- The end-to-end demo (`client_engagement.md`) produces a **professional advisory deliverable** — interview → score → loss model → VaR/ES → gap analysis → recommendations → executive summary. That's a compelling story for a hiring panel.
- The "broker-to-CFO translation" is consistent throughout — the single most valuable skill in risk analytics.

**Weaknesses**
- **No pricing / premium recommendation** (the business pays for a premium number).
- **No portfolio view** (single-firm only; no book-level aggregation, which is where real brokers make money).

### 2.6 CV Positioning — **7/10**

**Strengths**
- The project has a clear narrative: "I built a cyber insurance risk model with Monte Carlo VaR/ES, an explainable scoring engine, and a grounded AI consultant."
- Six written reports show the ability to **communicate** — rare and valuable.

**Weaknesses**
- **No public proof** (no GitHub link, no deployed demo, no screenshot/demo video).
- The project name and docs are functional but not polished for external readers.
- **No quantification of "impact"** on the CV (e.g. "built a model that sizes cyber limits for a $6.5bn logistics firm").

---

## 3. Weaknesses & Missing Features (ranked by hiring impact)

| Priority | Gap | Why it matters to a recruiter |
|---|---|---|
| **High** | No real LLM integration | The AI part is the headline; a reviewer can't see it actually reason. A live demo with a real model (e.g. Claude/OpenAI) would prove the seam works. |
| **High** | Calibration is mock data | An insurance interviewer will ask "where's the data?" within 5 minutes. A documented, realistic calibration (even from public DBIR/Hiscox/IBM tables, cleaned) would disarm this. |
| **High** | No pricing/premium output | The business payoff is the price; limit/retention gap alone is half the story. |
| **Med** | No portfolio aggregation | Real Marsh/Aon value is book-level; a single-firm demo is a toy by comparison. |
| **Med** | No GitHub / README / public presence | A top-tier student project is *visible*. |
| **Med** | No tail extrapolation / severity driver depth | The quant depth is good; these two would make it excellent. |
| **Low** | No CI, linting, typing, docs build | Polish; recruiter won't reject for it but reviewers will notice. |

---

## 4. Improvements That Would Make This Top-Tier

1. **Wire a real LLM** (the seam exists) and record a 3-minute demo: "ask the agent about a client, watch it elicit, score, model, and recommend — with the hallucination guard visible." This single change converts the AI from a claim to a proof.
2. **Replace mock calibration with a documented public-data calibration** (a `calibration_notes.md` showing DBIR/Hiscox/IBM → parameters). It doesn't need licensed data — a defensible, sourced calibration is enough for an interview.
3. **Add a premium/pricing layer**: rate-on-line, load on ES99, and a recommended premium range. This completes the business loop ("how much should this cost").
4. **Add a simple portfolio view**: aggregate 5-10 firms into a book, show book-level VaR/ES and diversification. One notebook, high payoff.
5. **Publish**: GitHub repo + README with architecture diagram + the client engagement demo. A screenshot of the LEC and the gap-analysis table goes a long way.
6. **Deepen the tail**: a Peaks-over-Threshold fit on the simulated tail to report stable 1-in-250/1-in-1000 PML with confidence bounds.
7. **Add severity-driver sensitivity** (data volume, downtime, sector) to the gap analysis, not just revenue.

---

## 5. Recommendation on CV Positioning

**Lead with the business story, not the tech.**

> *"I built an AI-enabled cyber insurance risk platform that scores a company's controls, models loss distributions with Monte Carlo VaR/Expected Shortfall, applies insurance policy terms, and generates client-ready recommendations — demonstrated on a $6.5bn logistics firm where the model identified that a $25M limit is exhausted ~2% of the time, self-funding up to $47M in the tail."*

Then back it with: 289 tests, analytic validation to 0.2%, an AI agent with hallucination guardrails, and six written reports.

**What to fix before sending it out:**
- The 3 "High" gaps (§3) — real LLM demo, documented calibration, pricing output.
- A GitHub presence with the README + architecture diagram.
- Keep the reports as evidence of communication — they're a differentiator most candidates lack.

---

## 6. Verdict

**This is a strong, near-top-tier project.** The quant engine is professionally shaped (occurrence-level simulation, heavy tails, Student-t dependence, credibility, uncertainty bands), the AI agent is genuinely grounded and safety-conscious, and the end-to-end deliverable reads like real advisory work. What separates it from top-tier is **proof and polish**: a real LLM demo, a sourced calibration, a pricing output, and public visibility. With those three, this is a compelling flagship project for a Risk Analytics interview.
