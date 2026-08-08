# CyberRisk AI

> **An AI-powered cyber risk advisory platform combining cyber threat intelligence, Monte Carlo loss modelling, and insurance analytics.**

CyberRisk AI is a quantitative cyber risk assessment and advisory platform built for insurance underwriters, brokers, risk analysts, and the AI engineers who support them. It turns a company's security posture and financial profile into defensible numbers — expected annual loss, tail risk, and insurance-structure outcomes — and then explains them in plain language through an AI consultant grounded in a curated cyber knowledge base.

---

## 1. Project Overview

Traditional cyber assessments are qualitative. They ask "is your security good or bad?" and deliver a score, a stoplight, and a vague recommendation — but they cannot answer the questions a board or an underwriter actually asks:

- **How much should we expect to lose per year?**
- **What is our 1-in-200 or 1-in-1000-year loss?**
- **Given our loss distribution, what insurance limit and retention make sense?**

CyberRisk AI answers these by combining three layers:

1. **A quantitative risk engine** — scenario-based frequency–severity modelling, Monte Carlo simulation, and coherent risk measures (VaR, Expected Shortfall, PML).
2. **A curated knowledge layer** — a vector-searchable corpus of regulatory texts, standards, industry reports, and incident data that grounds the AI's reasoning in citable sources.
3. **An AI consultant** — a Marsh/Aon-style advisory agent that elicits client facts, runs the engine as tools, and translates results into actionable insurance and control recommendations — without inventing numbers.

The platform ships as an interactive console consultant, a Streamlit chat app, a FastAPI web layer, and a Python library with a full benchmark and validation harness.

---

## 2. Problem Statement

### Why traditional cyber assessments are insufficient

Most cyber risk assessments rely on **expert judgment scored on a checklist**. This approach has structural limitations:

| Limitation | Consequence |
|---|---|
| **Qualitative, not quantitative** | "High risk" cannot be priced, reserved, or compared across a portfolio. |
| **Point estimates, no tails** | A single "most likely" loss hides the fat-tailed reality of cyber events — the 1-in-200-year loss that actually threatens solvency. |
| **No portfolio view** | Assessments are done in isolation, so underwriters cannot aggregate correlated exposure. |
| **Static and stale** | A point-in-time score decays quickly as the threat landscape and the company change. |
| **Unverifiable** | Scores rarely cite evidence, making them hard to audit, challenge, or improve. |

**Cyber risk is fundamentally a statistical problem.** Frequency of breach follows a rare-event process; severity is heavy-tailed; events are correlated across industries, geographies, and shared infrastructure. Yet most assessments treat it as a compliance exercise rather than a modelling problem.

CyberRisk AI treats it as one: it maps qualitative signals to quantitative parameters, simulates the full loss distribution, and reports coherent risk measures that insurance professionals can actually use to structure coverage.

---

## 3. Architecture

```
User Input
   │
   ▼
Risk Scoring ──────────────► factor scores (0–100) + risk category
   │
   ▼
Frequency–Severity Model ──► per-scenario frequency (Poisson) × severity (loss distributions)
   │
   ▼
Monte Carlo Simulation ────► thousands of simulated years of loss
   │
   ▼
VaR / Expected Shortfall ──► EAL, VaR 95/99, ES 95/99, P99.9 tail metrics
   │
   ▼
Insurance Analysis ────────► policy limits, retentions, retained vs transferred loss
   │
   ▼
AI Consultant ─────────────► board-ready advice grounded in the knowledge base
```

The pipeline is fully deterministic when seeded: the same client profile always produces the same score, distribution, and metrics.

---

## 4. Key Capabilities

- **Cyber risk scoring** — a transparent, deterministic 18-factor scoring model that maps a company's security posture (controls, attack surface, data sensitivity) to a 0–100 score and a Low/Medium/High/Critical category. Every factor is weighted in `config/scoring_weights.yaml` and auditable.
- **Loss simulation** — scenario-based Monte Carlo over cyber events (data breach, ransomware, BEC, cloud outage, business interruption, supply chain, OT/physical), each with calibrated frequency and severity.
- **EAL calculation** — Expected Annual Loss, the average annual cost of cyber exposure across the simulated distribution.
- **VaR / ES** — coherent tail measures: Value-at-Risk at the 95/99 percentiles and Expected Shortfall (conditional tail expectation), plus 1-in-100 and 1-in-1000-year PMLs.
- **Insurance optimisation** — model a policy structure (limit, retention, sub-limits) and see what is covered, what the insurer pays, and what the client retains — the residual gap, quantified.
- **RAG knowledge retrieval** — a semantic search over a curated corpus (regulatory frameworks, standards, industry reports, incident data) that retrieves citable, source-tagged chunks to ground every AI recommendation.
- **AI consultant** — a bounded tool-calling agent that elicits the facts it needs, refuses to model without them, and explains the numbers in board language.

---

## 5. Technical Stack

| Layer | Technology |
|---|---|
| Language | **Python** (≥ 3.10) |
| Numerical core | **NumPy**, **SciPy**, **Pandas** |
| Statistical modelling | Scenario frequency–severity distributions, copula dependency modelling |
| ML / deep learning | **PyTorch** *(planned — for dense embedding models via `EmbedderRegistry`; engine currently runs on NumPy/SciPy)* |
| Vector database | SQLite-backed vector store (`knowledge/derived/vector.db`) — zero-dependency, SQL-queryable, regenerable |
| LLM integration | **DeepSeek** via the OpenAI-compatible SDK (`openai` client) |
| Embeddings | Lightweight `HashEmbedder` with content-hash dedup, plus a pluggable `EmbedderRegistry` for swapping in dense models |
| Web / UI | **Streamlit** chat app, **FastAPI** + Uvicorn API layer |
| Reporting | Excel workbooks (openpyxl / xlsxwriter), matplotlib figures |
| Validation | pytest (41 tests), benchmark harness, convergence and calibration checks |

> **Note on the vector database.** The current store is a deliberately minimal SQLite implementation — zero external dependencies, thread-safe, and content-hash-deduplicated. The architecture isolates it behind a `VectorStore` interface so it can be swapped for a production vector DB (e.g. Chroma, Qdrant, or pgvector) without touching the retrieval logic.

---

## 6. Example Output

The engine's behaviour is validated against a benchmark of five representative client profiles. A preview of the model output:

```
============================================================================
CyberRiskAI BENCHMARK SCENARIOS - 5 CLIENT PROFILES
============================================================================

Precision Manufacturing Co         score=  16.1  cat=Low       EAL=$3.73M  ES99=$61.22M  P99.9=$91.57M
Metro Retail Group                 score=  44.5  cat=Medium    EAL=$4.96M  ES99=$69.01M  P99.9=$99.74M
St Helier Health System            score=  73.4  cat=High      EAL=$6.59M  ES99=$77.83M  P99.9=$116.14M
Meridian Capital Bank              score=  40.9  cat=Medium    EAL=$4.78M  ES99=$66.54M  P99.9=$98.64M
Brightline Consulting LLP          score=  86.6  cat=Critical  EAL=$7.52M  ES99=$84.34M  P99.9=$124.07M
```

What these numbers mean:

- **EAL** — the average annual cost of cyber exposure. The critical-profile firm (Brightline) has the highest EAL despite the smallest revenue, because its controls are the worst in the set.
- **ES99** — Expected Shortfall at the 99th percentile: the average loss *in the worst 1% of years*. This is the tail number that matters for capital and reinsurance decisions.
- **P99.9** — the 1-in-1000-year loss, the far tail.

The full benchmark, validation suite, and convergence analysis live in `data/output/validation/` and the `tests/` directory.

---

## 7. Installation

### Prerequisites

- Python **3.10+**
- A DeepSeek API key (for the AI consultant layer) — sign up at <https://platform.deepseek.com>

### Setup

```bash
# 1. Clone and enter the repo
git clone <your-repo-url> cyberrisk
cd cyberrisk

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

# 3. Install the package (editable) with the optional extras you need
pip install -e ".[agent]"          # AI consultant (DeepSeek + Streamlit)
pip install -e ".[reporting]"      # Excel report generation
pip install -e ".[web]"            # FastAPI web layer
pip install -e ".[knowledge]"      # document parsing (pypdf, python-docx)
```

### Configure API keys

```bash
# Copy the example env file and fill in your DeepSeek key
cp .env.example .env
```

```ini
DEEPSEEK_API_KEY=sk-your-key-here
# Optional:
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# DEEPSEEK_MODEL=deepseek-chat      # or deepseek-reasoner
```

Your `.env` is gitignored — never commit real keys.

### Run the AI consultant

The fastest way to see the platform in action:

```bash
# Interactive terminal consultant
cyberrisk

# Or the Streamlit chat app
python -m streamlit run src/cyberrisk/agent/app.py
```

Example prompts to try:

| Prompt | What the platform does |
|---|---|
| "Assess a healthcare technology company with 10M patient records, weak MFA, limited network segmentation." | Asks for revenue, scores the profile, simulates the loss distribution, and reports EAL/VaR/ES with the top risk drivers. |
| "We're a $500M manufacturer. What cyber limit and retention should we buy?" | Models the exposure and tests an insurance structure — limit, retention, covered vs retained loss. |
| "How exposed are we to ransomware? What's our 1-in-1000-year loss?" | Runs the simulation and quotes EAL, scenario AAL, and the P99.9 tail loss. |
| "Explain VaR 95 vs Expected Shortfall for our board." | A conversational explanation grounded in the modelled numbers. |

### Run the quantitative engine directly (no LLM needed)

```bash
# Full pipeline on a worked example (firm profile → score → simulation → insurance → Excel report)
python examples/run_full_pipeline.py

# Run the test suite (engine regression + agent determinism)
python -m pytest -q
```

### Project layout

```
src/cyberrisk/
├── scoring.py          # 18-factor risk scoring
├── frequency.py        # scenario frequency calibration
├── severity.py         # severity distributions
├── simulation.py       # Monte Carlo loss simulation
├── metrics.py          # EAL, VaR, Expected Shortfall, PML
├── copulas.py          # dependency modelling between scenarios
├── policy_transform.py # insurance structure: retained vs transferred
├── knowledge/          # ingestion, chunking, embedding, vector store, RAG
├── agent/              # AI consultant: DeepSeek client, tools, controller, UI
└── api/                # FastAPI web layer
```

---

## 8. Future Roadmap

**Near term**
- [ ] Production vector database (Chroma / Qdrant / pgvector) behind the existing `VectorStore` interface.
- [ ] Dense embedding models (PyTorch-based) swapped in via `EmbedderRegistry`, replacing the current lightweight `HashEmbedder` for higher-quality retrieval.
- [ ] Portfolio aggregation — model correlated exposure across a book of clients, not just a single firm.
- [ ] Multi-year loss chains and reinsurance-pricing outputs (quota share, excess-of-loss layers).

**Medium term**
- [ ] Reinsurance pricing integration and capital-modelling (SCR) outputs aligned with Solvency II.
- [ ] Automated benchmark refresh against the latest DBIR, IBM CODB, and ENISA threat landscapes.
- [ ] Scenario-dependency copula calibration from real correlated breach data.

**Long term**
- [ ] Live threat-intelligence feed that continuously updates scenario frequencies.
- [ ] Calibration to a client's actual claims experience (credibility weighting).
- [ ] Underwriting-workbench UI for portfolio triage, quoting, and ongoing monitoring.

---

## License & Data Policy

This repository is **source code and documentation only**. Confidential client materials, licensed cyber datasets, and generated reports are **not committed** — see `.gitignore`. Curated example benchmark data is included by design; licensed corpora must be sourced independently.

---

*CyberRisk AI is a research and modelling platform, not licensed financial advice. Outputs are model estimates for analytical use, not guarantees of loss or recovery.*
