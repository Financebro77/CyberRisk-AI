# CyberRisk AI (Not an expert at this, open to any feedback!)

> **An AI-powered cyber risk advisory platform combining cyber threat intelligence, Monte Carlo loss modelling, and insurance analytics.**

CyberRisk AI is a quantitative cyber risk assessment and advisory platform built for insurance underwriters, brokers, risk analysts, and the AI engineers who support them. It turns a company's security posture and financial profile into defensible numbers — expected annual loss, tail risk, and insurance-structure outcomes — and then explains them in plain language through an AI consultant grounded in a curated cyber knowledge base.

---

## Quick Start (5-minute setup)

```bash
# 1. Clone and enter the repo
git clone <your-repo-url> cyberrisk
cd cyberrisk

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# 3. Install with the agent extras (OpenAI / DeepSeek + Streamlit)
pip install -e ".[agent]"

# 4. Configure your API key
cp .env.example .env        # then edit .env and set LLM_PROVIDER + your key

# 5. Launch the interactive consultant
cyberrisk
```

That's it — you should be in the interactive consultant within five minutes. If `cyberrisk` isn't on your PATH, run `python -m cyberrisk.cli` instead.

> **No API key yet?** The quantitative engine (scoring, Monte Carlo simulation, VaR/ES, insurance structuring) runs entirely offline with **no key required** — only the AI consultant layer needs an LLM key (OpenAI or DeepSeek). See [Python API usage](#c-python-api-usage) to run the engine without an LLM.

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
| LLM integration | **OpenAI or DeepSeek**, selected via `LLM_PROVIDER` — pluggable `src/cyberrisk/llm/` layer (both use the `openai` SDK; DeepSeek via its OpenAI-compatible endpoint) |
| Embeddings | Lightweight `HashEmbedder` with content-hash dedup, plus a pluggable `EmbedderRegistry` for swapping in dense models |
| Web / UI | **Streamlit** chat app, **FastAPI** + Uvicorn API layer, **React/Vite** frontend |
| Reporting | Excel workbooks (openpyxl / xlsxwriter), matplotlib figures |
| Validation | pytest (41 tests), benchmark harness, convergence and calibration checks |

> **Note on the vector database.** The current store is a deliberately minimal SQLite implementation — zero external dependencies, thread-safe, and content-hash-deduplicated. The architecture isolates it behind a `VectorStore` interface so it can be swapped for a production vector DB (e.g. Chroma, Qdrant, or pgvector) without touching the retrieval logic.

---

## 6. Installation & Usage

### 6.1 System requirements

| Requirement | Minimum |
|---|---|
| **Python** | **3.10 or newer** (3.11/3.12 recommended; developed on 3.12/3.13) |
| **Operating system** | Windows 10/11, macOS, or Linux (POSIX shell examples assume Unix; PowerShell variants are noted inline) |
| **Hardware** | Any modern machine; the Monte Carlo engine is CPU-bound and runs comfortably on a laptop (200,000 simulated years in a few seconds) |
| **Internet** | Required only for the AI consultant layer (OpenAI / DeepSeek API). The engine and web UI run fully offline. |
| **Node.js** | Optional — only needed to build/run the React frontend in development. The pre-built `web/frontend/dist` is served by FastAPI, so this is skippable. |

**Core dependencies** (installed automatically from `pyproject.toml`):

| Package | Version | Purpose |
|---|---|---|
| `numpy` | ≥ 1.23 | Numerical core of the simulation engine |
| `pandas` | ≥ 1.5 | Data handling, event tables |
| `scipy` | ≥ 1.9 | Statistical distributions, optimisation |
| `pyyaml` | ≥ 6.0 | Config loading (`config/*.yaml`) |
| `pydantic` | ≥ 2.0 | Schema validation at every boundary |
| `matplotlib` | ≥ 3.6 | Loss-distribution figures |

**Optional extras** (each installs on top of the core):

| Extra | `pip install -e ".[...]"` | Adds |
|---|---|---|
| `agent` | `.[agent]` | AI consultant: OpenAI / DeepSeek (`openai` SDK), `python-dotenv`, **Streamlit** |
| `web` | `.[web]` | FastAPI + Uvicorn web layer |
| `reporting` | `.[reporting]` | Excel report generation (`openpyxl`, `xlsxwriter`) |
| `knowledge` | `.[knowledge]` | Document parsing for the knowledge base (`pypdf`, `python-docx`) |
| `test` | `.[test]` | Test suite (`pytest`) |

### 6.2 Installation

```bash
# 1. Clone and enter the repo
git clone <your-repo-url> cyberrisk
cd cyberrisk

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# 3. Install the package (editable) with the extras you need.
#    `.[agent]` gets you the full AI consultant experience:
pip install -e ".[agent]"
```

If you plan to use the other surfaces, install their extras too — they compose, so you can combine them in one command:

```bash
pip install -e ".[agent,web,reporting,knowledge]"
# or, to include the test suite:
pip install -e ".[agent,web,reporting,knowledge,test]"
```

Verify the install:

```bash
python -c "import cyberrisk; print(cyberrisk.__version__)"   # → 0.1.0
```

### 6.3 Environment configuration

1. **Copy the example environment file** to `.env`:

   ```bash
   # Windows (PowerShell):
   Copy-Item .env.example .env
   # macOS / Linux:
   cp .env.example .env
   ```

2. **Open `.env`** and set the provider plus your API key:

   ```ini
   # LLM provider: "openai" or "deepseek" (defaults to whichever key is set)
   LLM_PROVIDER=deepseek

   # --- DeepSeek (https://platform.deepseek.com) ---
   DEEPSEEK_API_KEY=sk-your-deepseek-key-here

   # --- OpenAI (https://platform.openai.com) — only if LLM_PROVIDER=openai ---
   # OPENAI_API_KEY=sk-your-openai-key-here
   ```

**Which keys are required vs optional:**

| Variable | Required? | Notes |
|---|---|---|
| `LLM_PROVIDER` | **Required** to switch providers | `openai` or `deepseek`. If unset, the provider is inferred from whichever key is present |
| `DEEPSEEK_API_KEY` | **Required** for the DeepSeek provider | The AI consultant (CLI/chat/web) needs one of the two keys set |
| `DEEPSEEK_BASE_URL` | Optional | Defaults to `https://api.deepseek.com`; override for a proxy |
| `DEEPSEEK_MODEL` | Optional | Defaults to `deepseek-chat`; use `deepseek-reasoner` for reasoning |
| `OPENAI_API_KEY` | **Required** for the OpenAI provider | The AI consultant (CLI/chat/web) needs one of the two keys set |
| `OPENAI_MODEL` | Optional | Defaults to `gpt-4o-mini`; any GPT model id |
| `OPENAI_BASE_URL` | Optional | Override for a compatible gateway / proxy |

#### Switching LLM providers

The consultant runs on whichever provider `LLM_PROVIDER` names. Set it in `.env`
(or export it) and restart the app — the client is built once per agent.

```ini
# DeepSeek (default)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...

# or OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

If `LLM_PROVIDER` is left blank, the provider is inferred from whichever key
is set — set only `DEEPSEEK_API_KEY` and you get DeepSeek, set only
`OPENAI_API_KEY` and you get OpenAI. The abstraction lives in
[`src/cyberrisk/llm/`](#project-layout): a common `LLMClient` interface, one
provider per file (`openai_provider.py`, `deepseek_provider.py`), and a
factory (`factory.py`) that picks the provider. Adding a third provider means
implementing the interface and registering it in the factory — the agent
controller, CLI, Streamlit app, and web API are unchanged.

**Security rules for secrets:**

- Your `.env` is **gitignored** (`.gitignore` line 14–16) — never commit real keys.
- If you ever `git add` a modified `.env` accidentally, remove it from the index immediately with `git rm --cached .env` and rotate the key — it is compromised.
- Do not paste keys into chat messages, issues, or screenshots.
- On shared machines, keep `.env` outside the repo or restrict its file permissions.
- The code loads the key via `python-dotenv`; you can also export it as a real environment variable, which takes precedence.

### 6.4 Running the CyberRisk AI agent

There are three ways to start the system. All three talk to the same engine; they differ in interface.

#### A) CLI mode (interactive consultant)

```bash
cyberrisk
```

(If the launcher isn't on your PATH: `python -m cyberrisk.cli`)

On launch you'll see a system-status screen, then an interactive prompt:

```
==================================================
CyberRisk AI Consultant
Commercial Cyber Risk Advisory Platform
==================================================

System Status:
  ✓ Risk Engine
  ✓ Knowledge Base
  ✓ Retrieval System
  ✓ LLM Connection
Ready.

Type 'exit', 'quit', or 'help'. Ctrl-C to leave.

>
```

- Each check reports whether the engine, knowledge base, retrieval system, and LLM connection are operational. If the LLM check fails, set `DEEPSEEK_API_KEY` (in `.env` or the environment).
- The agent then **elicits the facts it needs** — industry, revenue, data volume, security controls, incidents, existing coverage — asking follow-up questions until it can model. It refuses to model on insufficient information rather than guessing.
- Once it has the facts, it runs the quantitative engine as tools and reports **score, risk category, EAL, VaR, Expected Shortfall, and insurance structuring**, grounded in the knowledge base.

Example prompts to try:

| Prompt | What the platform does |
|---|---|
| "Assess a healthcare technology company with 10M patient records, weak MFA, limited network segmentation." | Asks for revenue, scores the profile, simulates the loss distribution, and reports EAL/VaR/ES with the top risk drivers. |
| "We're a $500M manufacturer. What cyber limit and retention should we buy?" | Models the exposure and tests an insurance structure — limit, retention, covered vs retained loss. |
| "How exposed are we to ransomware? What's our 1-in-1000-year loss?" | Runs the simulation and quotes EAL, scenario AAL, and the P99.9 tail loss. |
| "Explain VaR 95 vs Expected Shortfall for our board." | A conversational explanation grounded in the modelled numbers. |

Type `exit`, `quit`, or `help` for the command list; `Ctrl-C` leaves the session.

#### B) Web application

The web app has a **React frontend** and a **FastAPI backend** (which also serves the built frontend).

**Production / single-process mode** (serves the pre-built frontend and API on one port):

```bash
# Install the web extra first
pip install -e ".[web]"

# Start the API + built frontend on http://localhost:8000
python -m uvicorn cyberrisk.api.main:app --port 8000
```

Open <http://localhost:8000> — the UI is served from `web/frontend/dist`, and interactive API docs live at <http://localhost:8000/docs>.

**Development mode** (live-reloading React + proxied API):

```bash
# Terminal 1 — FastAPI backend on :8000
python -m uvicorn cyberrisk.api.main:app --port 8000 --reload

# Terminal 2 — Vite dev server on :5173 (proxies /api → :8000)
cd web/frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` calls to the backend (`web/frontend/vite.config.ts`), so both must be running.

**Alternative: Streamlit chat app** (a single-command chat UI):

```bash
pip install -e ".[agent]"
python -m streamlit run src/cyberrisk/agent/app.py
```

#### C) Python API usage

The engine and agent are plain Python modules, so you can drive them programmatically — in notebooks, scripts, or your own service.

**Engine-only (no API key, fully offline):**

```python
# assess_offline.py
from pathlib import Path
from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics
from cyberrisk.scoring import CompanyProfile, compute_score
from cyberrisk.simulation import simulate

cfg = load_config(
    Path("config/scenarios.yaml"),
    Path("config/simulation_config.yaml"),
)

profile = CompanyProfile(
    firm_name="Acme Manufacturing",
    revenue_usd=500_000_000,
    factor_scores={
        # ... 18 factors, each 0-100 (see examples/run_full_pipeline.py)
        "external_attack_surface": 70.0,
        "mfa_coverage": 60.0,
        # ...
    },
)

scored = compute_score(profile)
metrics = compute_metrics(
    simulate(cfg, n_years=100_000, score=scored.composite_score)
)

print(f"{scored.firm_name}: {scored.composite_score:.1f}/100 ({scored.risk_category})")
print(f"EAL:  ${metrics.eal/1e6:,.2f}M")
print(f"VaR99: ${metrics.var_99/1e6:,.2f}M")
print(f"ES99:  ${metrics.es_99/1e6:,.2f}M")
```

**AI consultant (requires the active provider's API key — see [Switching LLM providers](#switching-llm-providers)):**

```python
# consultant_offline_check.py
from cyberrisk.agent.agent_controller import CyberRiskAgent

agent = CyberRiskAgent()                      # provider from LLM_PROVIDER env
answer = agent.chat(
    "Assess a $400M healthcare technology firm holding 10M patient records "
    "with partial MFA and weekly backups."
)
print(answer)
```

**Web-layer tools (the same functions the FastAPI routes wrap):**

```python
from cyberrisk.agent.tools import assess_company_risk
from cyberrisk.agent.schemas import CompanyBrief

result = assess_company_risk(CompanyBrief(
    firm_name="MedData Health Technologies",
    industry="Healthcare",
    revenue_usd=400_000_000,
    customer_records=10_000_000,
    security_controls="partial MFA, weekly backups, onboarding-only vendor assessment",
))
# result contains score, risk category, EAL/VaR/ES, and the top risk drivers
```

> The full end-to-end pipeline example (score → simulate → insurance → Excel report → rule-based recommendation) is `python examples/run_full_pipeline.py`.

---

## 7. Example Assessment (worked example)

To see the engine behave on a realistic profile, the benchmark ships with a healthcare-technology profile close to the one below. Here is a **live run** of the engine on a representative healthcare technology company:

**Client profile — "MedData Health Technologies"**

| Attribute | Value |
|---|---|
| Industry | Healthcare technology |
| Revenue | $400M |
| Records held | ~10,000,000 patient records (critical sensitivity) |
| Industry targeting | Very high |
| MFA coverage | Partial (~50–70% of users) |
| Backups | Weekly, DR tested annually |
| Third-party exposure | High — onboarding-only vendor assessment, minimal contractual security, limited supply-chain visibility |
| Patching | Ad hoc, high number of open critical vulnerabilities |
| Prior incidents | None disclosed |

**Output (engine, 200,000 simulated years):**

```
Risk score: 73.4/100
Risk category: High
Risk drivers: industry_targeting, data_sensitivity, patch_cadence,
              privileged_access, edr_coverage, contractual_security,
              supply_chain_visibility, incident_response
EAL: $3.62M
VaR 95: $13.37M
VaR 99: $27.42M
ES 95: $23.05M
ES 99: $42.71M
P(no loss): 10.2%

Insurance structure tested: $250k per-occurrence deductible, $10M limit,
                            $1M annual aggregate deductible, $25M aggregate limit
Retained EAL: $1.75M
Transferred EAL: $1.87M
P(within aggregate limit): 99.7%
```

**What these numbers mean:**

| Metric | Value | Interpretation |
|---|---|---|
| **Risk score** | 73.4 / 100 | **High** risk band. Worst drivers: healthcare is heavily targeted, data sensitivity is critical (10M records), and patching/privileged-access/EDR controls are weak. |
| **EAL** | $3.62M | Expected **annual** loss from cyber events. The headline number for pricing. |
| **VaR 99** | $27.42M | The loss exceeded with 1% probability in any year — the 1-in-100-year event. |
| **ES 99** | $42.71M | Average loss **in the worst 1% of years** (Expected Shortfall, conditional tail expectation). The number that matters for capital and reinsurance. |
| **P(no loss)** | 10.2% | The firm loses money in ~90% of modelled years — consistent with a High risk category. |
| **Retained vs transferred EAL** | $1.75M / $1.87M | With the tested structure, the client retains roughly half the expected annual loss and the insurer pays half. |
| **P(within aggregate limit)** | 99.7% | The $25M aggregate limit would absorb the policy's annual transfers in 99.7% of years — a broadly adequate structure, though the $1M aggregate deductible still leaves meaningful retained risk. |

**Insurance recommendation (as the consultant would frame it):** the firm's tail exposure (ES99 $42.7M, far above the $10M per-occurrence limit) makes the current structure leave the tail largely uninsured. A board-facing recommendation would be to (a) raise the occurrence limit toward the P99.9 tail, (b) remediate the top risk drivers — particularly patch cadence, privileged-access controls, and vendor security — which move the score and the whole loss distribution, and (c) reassess retention given the 90%-annual probability of at least one loss event.

> These figures are a live engine run on the profile above; they are illustrative of a worked example, not a quote or a guarantee. Run the example yourself for your own profile.

---

## 8. Improving Model Accuracy: Required Information

CyberRisk AI's estimates are only as good as the information it is given. Like any actuarial model, the platform quantifies risk from the facts supplied to it — and the quality and completeness of those facts directly bound the precision of its outputs. This section describes what information most improves the accuracy of the risk score, the loss distribution, and the insurance-structure analysis, and why each category matters.

The agent is designed to elicit and work with partial information — it asks before it models rather than guessing. But the more of the following you can provide, the more defensible and decision-ready the result. Each category below maps directly to an input the quantitative engine consumes.

### 8.1 Company Profile Information

Accurate modelling starts with the facts that anchor the baseline: who the company is, and what its business looks like.

- **Industry sector**
- **Company size**
- **Annual revenue**
- **Geographic footprint**
- **Number of employees**
- **Number of customers**
- **Business criticality**
- **Digital dependency**

**Why it matters:** Industry and business characteristics influence baseline cyber threat frequency. A financial institution is targeted more often than a regional manufacturer; a company that runs its business on cloud infrastructure has a different exposure profile from one that operates on-premises. Industry and targeting feed the scenario frequency calibration, while revenue scales the severity distribution — so getting these facts right anchors the entire loss model to the correct baseline.

### 8.2 Data Asset Information

Loss severity is driven by what is actually at risk inside the company.

- **Number of records held**
- **Types of sensitive data:**
  - Personal data
  - Healthcare data
  - Financial data
  - Intellectual property
- **Data classification**
- **Data storage locations**
- **Cloud usage**

**Why it matters:** Data sensitivity drives breach severity and regulatory exposure. The model maps record volume to a data-sensitivity rating that feeds both the risk score and the severity distributions — 10 million healthcare records produces a materially different loss profile from 10,000 marketing contacts. Sensitive categories such as healthcare or financial data carry higher regulatory and notification costs (HIPAA, GDPR, state privacy laws), and storage location and cloud usage shape both the attack surface and the business-interruption exposure.

### 8.3 Cybersecurity Control Information

The model becomes materially more accurate when security controls are described in detail rather than as a single word such as "good" or "weak". Quantified answers are best.

**Identity and Access Management**
- MFA coverage percentage
- Privileged Access Management
- Single sign-on
- Identity governance

**Network Security**
- Network segmentation
- Firewall maturity
- Zero Trust implementation

**Endpoint Security**
- EDR deployment
- Patch management
- Vulnerability scanning

**Resilience**
- Backup frequency
- Immutable backups
- Disaster recovery testing
- Recovery Time Objectives (RTO)

**Why it matters:** Security controls influence both the probability and the severity of cyber incidents. They feed the 18-factor scoring model, and through the score, the simulated frequency and severity of each scenario. Weak privileged-access and patching controls raise breach frequency; poor resilience raises the severity of ransomware and business-interruption outcomes. Precise inputs (e.g. "65% MFA coverage", "immutable backups, RTO 4 hours") tighten the score — and therefore the whole loss distribution — far more than qualitative descriptions.

### 8.4 Third-Party and Supply Chain Risk

Modern cyber losses frequently originate outside the company's own perimeter.

- **Number of suppliers**
- **Critical vendors**
- **Cloud providers**
- **Software dependencies**
- **Third-party security assessments**
- **Contractual cyber requirements**

**Why it matters:** Supply chain compromise is a major driver of modern cyber losses. Vendors with access to the company's data or infrastructure extend the attack surface beyond what internal controls can protect, and cloud dependency concentrates business-interruption risk. The model treats third-party exposure as a distinct scenario and incorporates vendor-assessment practices and contractual security obligations directly into the risk score.

### 8.5 Historical Incident Data

Accuracy improves when users share the firm's own loss experience.

- **Previous cyber incidents**
- **Breach history**
- **Ransomware events**
- **Downtime events**
- **Previous insurance claims**
- **Loss amounts**

**Why it matters:** Historical experience allows better calibration. CyberRisk AI applies a credibility-weighted calibration: it starts from the industry baseline for a company like yours, then shifts frequency and severity toward your own observed experience the more of it you provide — while never discarding the sector prior entirely, because a few years of history is too little to trust on its own. A firm with a clean record therefore receives a better-than-average modelled rate, and a firm with a troubled record a worse one, each fully auditable.

### 8.6 Insurance Information

The insurance-structure analysis is only as precise as the policy terms it is given.

- **Current cyber insurance limit**
- **Retention / deductible**
- **Policy structure**
- **Coverage sections**
- **Sublimits**
- **Exclusions**
- **Claims history**

**Why it matters:** The insurance module requires accurate policy terms to estimate retained and transferred risk. It projects each simulated year of loss through the policy structure — deductible, per-occurrence and aggregate limits, sublimits, exclusions — to calculate what the client retains versus what the insurer pays. Given imprecise terms, the platform can still estimate total exposure, but the retained/transferred split, the number a board actually acts on, requires the real policy wordings.

### 8.7 Quantitative Benchmark Data

Advanced users can improve the calibration itself by adding benchmark datasets to the knowledge base.

- **Industry breach frequency data**
- **Loss severity datasets**
- **Sector benchmarks**
- **Regional cyber statistics**
- **Insurance claims datasets**

Public sources commonly used in the field:

- **Verizon DBIR** (Data Breach Investigations Report)
- **IBM Cost of a Data Breach Report**
- **ENISA Threat Landscape reports**
- **NIST publications**
- **CISA vulnerability data**

These sources feed the frequency–severity calibration tables and the curated corpus that grounds the AI consultant's reasoning. See §9, Knowledge Base Updates, for how to ingest new datasets into `knowledge/datasets/` and the corpus.

### 8.8 Data Quality Guidance

| Information | Impact on Accuracy |
|---|---|
| High-quality security control data | Improves frequency modelling |
| Historical loss data | Improves severity calibration |
| Industry benchmarks | Improves baseline assumptions |
| Insurance policy details | Improves coverage analysis |
| Incomplete information | Increases uncertainty |

### 8.9 A Note on Model Output

> CyberRisk AI produces probabilistic risk estimates, not guaranteed predictions. Better-quality input data reduces uncertainty and improves the reliability of risk quantification.

---

## 9. Knowledge Base Updates

The AI consultant's recommendations are grounded in a curated corpus. You extend it by dropping documents into the knowledge folder — no code changes required.

### Layout

```
knowledge/
├── corpus/                  # source documents you curate (the "what the AI knows")
│   ├── incidents/           #   breach/incident case data
│   ├── industry-reports/    #   DBIR, IBM CODB, ENISA, Hiscox, NetDiligence...
│   ├── insurance/           #   wordings, claims guides, market terms
│   ├── regulatory/          #   GDPR, HIPAA, NIS2, DORA, AI Act, SEC...
│   ├── standards/           #   NIST CSF 2.0, NIST 800-53, ISO 27001, CIS...
│   ├── threat-intel/        #   threat landscape reports
│   └── vulnerability-data/  #   CISA KEV, CVE data
├── datasets/                # structured calibration data (CSV/JSON)
│   ├── benchmarks/          #   DBIR frequency, IBM CODB severity tables
│   ├── history/             #   historical incident series
│   └── market/              #   market-level pricing data
├── manifests/               # corpus_manifest.yaml (registered documents)
├── mappings/                # taxonomy + source mappings
├── pipelines/               # ingest/embed/refresh pipeline config
├── schemas/                 # JSON schemas for documents and the manifest
└── derived/                 # generated chunks, embeddings, vector.db (gitignored)
```

### Supported formats

PDF, Markdown, DOCX, HTML, plain text, and YAML — see `src/cyberrisk/knowledge/config.py`.

### The ingestion / update workflow

Add a document, then run the auto-update pipeline:

```bash
# 1. Drop your document into the relevant corpus folder, e.g.
#    knowledge/corpus/standards/nist-csf-2.0/my_note.pdf

# 2. Run the automatic update pipeline — it detects, parses, chunks,
#    embeds, and updates the vector DB in one pass
python -m cyberrisk.knowledge.update

# Useful flags:
python -m cyberrisk.knowledge.update --force    # re-index everything (ignore cache)
python -m cyberrisk.knowledge.update --report   # print the last update report
```

What the pipeline does, automatically:

1. **Scans** `knowledge/corpus/**` for supported files not already in the manifest.
2. **Registers** each new file with metadata inferred from its path (domain, title, license, content hash).
3. **Extracts** text, **cleans** it, and **chunks** it (section-aware or plain, per config).
4. **Embeds** the chunks (content-hash deduplication avoids re-embedding).
5. **Updates** the SQLite vector store (`knowledge/derived/vector.db`).
6. **Logs** every action to `knowledge/derived/update/` and writes a report.

An update report is written to `knowledge/derived/update/` and, after a quality-gated run, `reports/knowledge_population_report.md`.

**Quality gate.** The authoritative population path (`python -m cyberrisk.knowledge.populate`) only ingests documents whose source is registered as **approved** in the source registry (`authoritative_sources.yaml`) — unapproved sources are skipped and logged. The auto-update path is the permissive one for your own documents.

**Duplicates.** Content-hash dedup means re-running the update is safe: unchanged files are skipped, changed files are re-ingested, and the vector store is updated incrementally.

> **Licensing.** The repo is source code + curated example data only. If you add proprietary licensed corpora (e.g. paid DBIR/CODB content), keep them out of version control and store the files locally under `knowledge/corpus/` — it's gitignored for derived artifacts, and licensed source text should be held behind your own access controls.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **`[config error] ... OPENAI_API_KEY / DEEPSEEK_API_KEY` / "LLM Connection ✗"** on launch | No provider key configured (or `LLM_PROVIDER` names a provider whose key is missing) | Copy `.env.example` → `.env`, set `LLM_PROVIDER=openai` or `=deepseek`, and set the matching `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`. Alternatively `export` the key. |
| **`ModuleNotFoundError: No module named 'cyberrisk'`** | Package not installed | `pip install -e ".[agent]"` from the repo root. Check you're in the venv (`.venv\Scripts\Activate.ps1` / `source .venv/bin/activate`). |
| **`ModuleNotFoundError: ... openai / streamlit / fastapi / uvicorn / openpyxl`** | An optional extra is missing | Install the matching extra: `pip install -e ".[agent]"` (LLM/Streamlit), `".[web]"` (FastAPI), `".[reporting]"` (Excel), `".[knowledge]"` (PDF/DOCX parsing). |
| **Port already in use** | Uvicorn on :8000 or Vite on :5173 is already running | Find and stop the process, or change the port: `python -m uvicorn cyberrisk.api.main:app --port 8001` and update the Vite proxy target in `web/frontend/vite.config.ts`. |
| **`RuntimeError` when calling `CyberRiskAgent()`** | LLM not configured or API unreachable | Check `LLM_PROVIDER` and the matching key (`DEEPSEEK_API_KEY` / `OPENAI_API_KEY`), network access to the provider endpoint, and that your key is valid/active. |
| **Model not loading / "Retrieval System ✗"** | Vector DB missing or stale | The store regenerates on demand; run `python -m cyberrisk.knowledge.update` to rebuild `knowledge/derived/vector.db`. |
| **Windows: `UnicodeEncodeError` / missing `✓` `✗` glyphs** | Legacy console codepage (GBK etc.) | The CLI already falls back to `[OK]`/`[--]` on legacy codepages. Use Windows Terminal for full glyph support. |
| **Agent says "insufficient information" instead of modelling** | The completeness guard is working as designed | Provide the missing facts (industry, revenue, controls, etc.) — the agent refuses to model on guesses. |
| **Numerical mismatch between runs** | You changed the seed or a config | The pipeline is deterministic when seeded; different seeds/config produce different draws. Compare like-for-like. |
| **Excel report not written** | `reporting` extra missing | `pip install -e ".[reporting]"` (openpyxl / xlsxwriter). |

---

## 11. Future Roadmap

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

## Project Layout

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
├── agent/              # AI consultant: LLM client (via llm/), tools, controller, UI
├── llm/                # LLM provider abstraction: base interface, OpenAI/DeepSeek providers, factory
└── api/                # FastAPI web layer

web/
└── frontend/           # React + Vite SPA (dist/ is served by FastAPI)

examples/               # runnable worked examples (full pipeline, benchmarks, demos)
config/                 # scoring weights, scenarios, simulation, benchmark profiles
knowledge/              # corpus, datasets, manifests, derived artifacts (see §9)
```

---

## Privacy and Security

CyberRisk AI is designed so that **no personal information is stored** and
the repository is safe to publish publicly.

**What the platform does not store:**

- **No personal information.** CyberRisk AI does not store personal data
  (names, emails, phone numbers, addresses). The input-privacy guard
  detects and redacts personal data before it reaches the model
  ([`src/cyberrisk/privacy.py`](src/cyberrisk/privacy.py)).
- **No client-identifiable data on disk.** Client conversations and firm
  facts live in memory for the duration of a session; they are not written
  to persistent storage by default. Persisting a conversation scrubs
  personal data first (see `config/privacy.yaml`).
- **No private datasets.** The repository ships source code, documentation,
  and **synthetic example data only**. Public benchmark datasets (Verizon
  DBIR, IBM Cost of a Data Breach) are referenced by calibration table, not
  bundled. Licensed or client-confidential corpora must be sourced and held
  outside version control by the operator.

**Your responsibilities:**

- **Do not upload confidential client information.** Users should not upload
  confidential client information into the repository, issues, or
  discussions.
- **API credentials are yours, stored locally.** All secrets are read from
  environment variables or a local `.env` file (gitignored). Never commit a
  key. See [§6.3 Environment configuration](#63-environment-configuration)
  and [`SECURITY.md`](SECURITY.md).
- **All examples are synthetic.** The example companies and datasets
  (`examples/`, `data/examples/`, `config/benchmark_profiles.yaml`) are
  fictional. No real company is represented.

**The repository contains no private datasets and no secrets.** The
`.gitignore` blocks `.env`, private keys, raw/private/client data
directories, generated reports, and local databases. A security scanner
(`scripts/security_scan.py`) and pre-commit hooks
([`.pre-commit-config.yaml`](.pre-commit-config.yaml)) enforce this before
anything is committed.

See [`SECURITY.md`](SECURITY.md) for the full security policy, vulnerability
reporting, and data-protection statement.

---

## License & Data Policy

This repository is **source code and documentation only**. Confidential client materials, licensed cyber datasets, and generated reports are **not committed** — see `.gitignore`. Curated example benchmark data is included by design; licensed corpora must be sourced independently.

---

*CyberRisk AI is a research and modelling platform, not licensed financial advice. Outputs are model estimates for analytical use, not guarantees of loss or recovery.*
