<div align="center">

# CyberRisk AI

**A quantitative cyber risk assessment and advisory platform — Monte Carlo loss modelling, insurance analytics, and an AI consultant, all grounded in a curated knowledge base.**

[Python ≥ 3.10](https://www.python.org) · [MIT License](#license--data-policy) · [Security](SECURITY.md)

<!-- Landing page screenshot placeholder — see docs/images/README.md -->
![CyberRisk AI landing page](docs/images/landing.png)

</div>

---

## Project Overview

CyberRisk AI turns a company's security posture and financial profile into **defensible numbers**: expected annual loss (EAL), tail risk (VaR / Expected Shortfall), and insurance-structure outcomes. An AI consultant then explains the results in plain language a board — or an underwriter — can act on, without inventing a single figure.

It is built for:

- **Insurance underwriters & brokers** who need a transparent, auditable model instead of a qualitative score.
- **Risk analysts & AI engineers** who want a reference implementation of a scenario-based cyber loss engine with full tests.
- **Recruiters & contributors** who want to see production-grade Python: a validated numerical core, a privacy layer, a pluggable LLM layer, and 600 passing tests.

> CyberRisk AI is a research and modelling platform, **not licensed financial advice**. Outputs are model estimates for analytical use, not guarantees of loss or recovery.

---

## Key Features

- **Cyber risk scoring** — a deterministic 18-factor model that maps a company's security posture to a 0–100 score and a Low/Medium/High/Critical category. Every factor is weighted in `config/scoring_weights.yaml` and auditable.
- **Loss simulation** — scenario-based Monte Carlo over real cyber scenarios (data breach, ransomware, BEC, cloud outage, business interruption, supply chain, OT/physical), each with calibrated frequency and severity.
- **Coherent risk measures** — Expected Annual Loss, VaR at the 95/99 percentiles, Expected Shortfall (conditional tail expectation), and 1-in-100 / 1-in-1000-year PMLs.
- **Insurance optimisation** — model a policy structure (limit, retention, sub-limits, exclusions) and see what is covered, what the insurer pays, and what the client retains — the residual gap, quantified.
- **AI consultant** — a bounded, tool-calling agent that elicits the facts it needs, refuses to model without them, and explains the numbers in board language. The LLM **never supplies numbers**; every figure comes from the engine via tools.
- **RAG knowledge retrieval** — a semantic search over a curated corpus (regulatory frameworks, standards, industry reports, incident data) that grounds every recommendation in citable, source-tagged chunks.
- **Provider-agnostic LLM layer** — run the same agent on **OpenAI** or **DeepSeek** by setting `LLM_PROVIDER`; a pluggable `src/cyberrisk/llm/` interface.
- **Privacy by design** — an input guard detects and redacts personal data before it reaches the model, and sanitised logging ensures no secret or PII is written to logs.

---

## Documentation

- **[Architecture](docs/architecture.md)** — AI agent architecture, risk engine, Monte Carlo simulation, RAG pipeline, and the LLM layer.
- **[Model Methodology](docs/model-methodology.md)** — how the numbers are produced: risk scoring, EAL, VaR, Expected Shortfall, insurance analysis, and the model's explicit assumptions.
- **[Deployment](docs/deployment.md)** — local installation, Docker deployment, and the cloud deployment roadmap.
- **[API](docs/api.md)** — the FastAPI surface: endpoints, request/response shapes, and the planned future API.
- **[Knowledge Base](docs/knowledge-base.md)** — data sources, the RAG process, and how to add new knowledge.

---

## Architecture

<!-- Architecture diagram placeholder — see docs/images/README.md -->
![CyberRisk AI architecture](docs/images/architecture.png)

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

The pipeline is **fully deterministic when seeded** — the same client profile always produces the same score, distribution, and metrics.

### The AI consultant layer

```
User
  → Chat interface (Streamlit `app.py` or terminal `run_chat.py` / `cli.py`)
    → LLM client (`cyberrisk/llm` — OpenAI or DeepSeek via the factory)
      → Agent controller (`agent_controller.py`) — bounded tool-calling loop
        → CyberRisk tools (`tools.py`)
          → Existing engine (scoring → simulate → compute_metrics
                             → policy transform → write_report)
            → Consultant-style response back up
```

The agent is **purely additive** — the quantitative engine is consumed read-only through the tool layer and is never modified.

---

## Installation

### Requirements

| Requirement | Minimum |
|---|---|
| **Python** | **3.10 or newer** (3.11/3.12 recommended) |
| **OS** | Windows 10/11, macOS, or Linux |
| **Internet** | Required only for the AI consultant layer (OpenAI / DeepSeek API); the engine runs fully offline |

### 1. Clone and create a virtual environment

```bash
git clone <your-repo-url> cyberrisk
cd cyberrisk

python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate
```

### 2. Install the package

```bash
# Core engine + agent extras (OpenAI/DeepSeek SDK, Streamlit, dotenv):
pip install -e ".[agent]"

# Optionally add more extras — they compose:
#   .[web]          FastAPI + Uvicorn web layer
#   .[reporting]    Excel report generation (openpyxl, xlsxwriter)
#   .[knowledge]    PDF/DOCX parsing for the knowledge base
#   .[test]         Test suite (pytest)
pip install -e ".[agent,web,reporting,knowledge,test]"
```

Verify the install:

```bash
python -c "import cyberrisk; print(cyberrisk.__version__)"   # → 0.1.0
```

### 3. Configure your LLM provider

```bash
# Windows (PowerShell):
Copy-Item .env.example .env
# macOS / Linux:
cp .env.example .env
```

Open `.env` and set the provider plus your API key:

```ini
# LLM provider: "openai" or "deepseek" (defaults to whichever key is set)
LLM_PROVIDER=deepseek

# --- DeepSeek (https://platform.deepseek.com) ---
DEEPSEEK_API_KEY=sk-your-deepseek-key-here

# --- OpenAI (https://platform.openai.com) — only if LLM_PROVIDER=openai ---
# OPENAI_API_KEY=sk-your-openai-key-here
```

The key is read at runtime via `python-dotenv` and is **never hard-coded and never committed** — `.env` is gitignored.

### Switching LLM providers

The consultant runs on whichever provider `LLM_PROVIDER` names. Set it in `.env` (or export it) and **restart the app** — the client is built once per agent.

```ini
# DeepSeek
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...

# or OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

If `LLM_PROVIDER` is left blank, the provider is inferred from whichever key is present — set only `DEEPSEEK_API_KEY` and you get DeepSeek; set only `OPENAI_API_KEY` and you get OpenAI.

**Provider environment variables:**

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LLM_PROVIDER` | To switch | — | `openai` or `deepseek`; inferred if unset |
| `DEEPSEEK_API_KEY` | For DeepSeek | — | Get at https://platform.deepseek.com |
| `DEEPSEEK_BASE_URL` | | `https://api.deepseek.com` | OpenAI-compatible endpoint |
| `DEEPSEEK_MODEL` | | `deepseek-chat` | `deepseek-reasoner` for R1-style reasoning |
| `OPENAI_API_KEY` | For OpenAI | — | Get at https://platform.openai.com |
| `OPENAI_MODEL` | | `gpt-4o-mini` | Any GPT model id |
| `OPENAI_BASE_URL` | | OpenAI default | Override for a compatible gateway |

---

## How to Run the AI Agent

There are three ways to start the system. All three talk to the same engine; they differ in interface.

### Streamlit chat app (recommended)

```bash
python -m streamlit run src/cyberrisk/agent/app.py
```

Open the printed URL (default `http://localhost:8501`). The sidebar shows the LLM configuration status, lets you adjust Monte Carlo simulation years, and clear the conversation.

### Terminal chat (`run_chat`)

```bash
python -m cyberrisk.agent.run_chat
```

Type questions directly; `exit` or Ctrl-C to quit.

### How the agent behaves

The agent **elicits the facts it needs** — industry, revenue, data volume, security controls, incidents, existing coverage — asking follow-up questions until it can model. It **refuses to model on insufficient information** rather than guessing. Once it has the facts, it runs the quantitative engine as tools and reports score, risk category, EAL, VaR, Expected Shortfall, and insurance structuring, grounded in the knowledge base.

**Example questions to try:**

| Question | What the agent does |
|---|---|
| "Assess a healthcare technology company with 10 million patient records, weak MFA and limited network segmentation." | Asks for revenue if missing, then scores and runs the model. Expect High/Critical rating, ransomware + business-interruption as top drivers, a fat tail, and an insurance-gap warning. |
| "We're a $500M manufacturer. What cyber insurance limit and retention should we buy?" | Models the exposure, tests a structure via `analyse_insurance_structure`, and recommends a limit/retention with the gap quantified. |
| "How exposed are we to ransomware? What's our worst-case 1-in-1000-year loss?" | Runs the simulation and quotes EAL, scenario AAL, and the 1-in-1000 PML. |
| "Explain VaR 95 versus Expected Shortfall in plain English for our board." | A conversational explanation grounded in the modelled numbers. |
| "We have no security controls and store a lot of customer data." | The agent asks for revenue and specifics before modelling — it will not guess a profile. |

**Why the numbers are trustworthy:** the system prompt forbids inventing figures, the tools are the **only** source of numbers, and a completeness guard blocks assumed profiles. An existing hallucination check (`src/agent/safety.py`) acts as a backstop on the final answer.

---

## CLI Usage

The global `cyberrisk` launcher gives you a system-status screen and an interactive consultant prompt:

```bash
cyberrisk                       # or: python -m cyberrisk.cli
```

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

Each check reports whether the engine, knowledge base, retrieval system, and LLM connection are operational. Inside the prompt you can use `exit` / `quit` / `help` / `clear`.

---

## Web Application Usage

The web app has a **React frontend** and a **FastAPI backend** (which also serves the built frontend).

### Production / single-process mode

```bash
pip install -e ".[web]"

# Start the API + built frontend on http://localhost:8000
python -m uvicorn cyberrisk.api.main:app --port 8000
```

Open <http://localhost:8000> — the UI is served from `app/frontend/dist`, and interactive API docs live at <http://localhost:8000/docs>.

### Docker deployment

The repo ships a `Dockerfile` and `docker-compose.yml` for a single-container
deployment that serves **both** the API and the built frontend.

```bash
# 1. Configure your LLM provider
cp .env.example .env        # set LLM_PROVIDER + OPENAI_API_KEY / DEEPSEEK_API_KEY

# 2. Build and start
docker compose up --build
```

Open <http://localhost:8000> (UI + API) and <http://localhost:8000/docs>
(API docs).

**How it works:**

- The **backend** stage installs the Python package (`.[web,reporting,knowledge]`).
- The **frontend** stage builds the React SPA with `npm run build`.
- The **runtime** stage serves both from a single uvicorn process, as a
  non-root user, with a healthcheck on `/api/health`.
- **Secrets** are injected only from `.env` via `env_file` (gitignored,
  never baked into the image). `.dockerignore` excludes `.env`, `.venv`,
  `node_modules`, and other artifacts from the build context.

See [Deployment](docs/deployment.md) for full details, the cloud roadmap,
and troubleshooting.

### Development mode (live-reloading)

```bash
# Terminal 1 — FastAPI backend on :8000
python -m uvicorn cyberrisk.api.main:app --port 8000 --reload

# Terminal 2 — Vite dev server on :5173 (proxies /api → :8000)
cd app/frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` calls to the backend (`app/frontend/vite.config.ts`), so both must be running.

### Python API usage

The engine and agent are plain Python modules, so you can drive them programmatically — in notebooks, scripts, or your own service.

**Engine-only (no API key, fully offline):**

```python
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
        "external_attack_surface": 70.0,
        "mfa_coverage": 60.0,
        # ... 18 factors, each 0-100 (see examples/run_full_pipeline.py)
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

**AI consultant (requires the active provider's API key):**

```python
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

## Example Cyber Risk Assessment

Here is a **live engine run** on a representative healthcare technology company (200,000 simulated years):

<!-- Risk assessment output screenshot placeholder — see docs/images/README.md -->
![CyberRisk AI risk assessment output](docs/images/risk-assessment-output.png)

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

**Output (engine):**

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

## Knowledge Base

The AI consultant's recommendations are grounded in a curated corpus that you can extend with **no code changes** — content is data, never code.

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

**Supported formats:** PDF, Markdown, DOCX, HTML, plain text, and YAML — see `src/cyberrisk/knowledge/config.py`.

### Adding knowledge

Drop a document into the relevant corpus folder, then run the auto-update pipeline — it detects, parses, chunks, embeds, and updates the vector store in one pass:

```bash
# 1. Drop your document into a corpus folder, e.g.
#    knowledge/corpus/standards/nist-csf-2.0/my_note.pdf

# 2. Run the automatic update pipeline
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

**Quality gate.** The authoritative population path (`python -m cyberrisk.knowledge.populate`) only ingests documents whose source is registered as **approved** in the source registry (`authoritative_sources.yaml`). The auto-update path is the permissive one for your own documents.

**Duplicates.** Content-hash dedup means re-running the update is safe: unchanged files are skipped, changed files are re-ingested, and the vector store is updated incrementally.

> **Licensing.** The repo is source code + curated example data only. If you add proprietary licensed corpora (e.g. paid DBIR/CODB content), keep them out of version control and store the files locally under `knowledge/corpus/` — licensed source text should be held behind your own access controls.

---

## Supported Data Sources

The frequency–severity calibration and the curated corpus are built from public, industry-standard sources:

- **Verizon DBIR** (Data Breach Investigations Report) — sector breach frequency
- **IBM Cost of a Data Breach Report** — loss severity tables
- **ENISA Threat Landscape** — threat landscape reports
- **NIST publications** — frameworks and standards
- **CISA KEV** — known exploited vulnerabilities
- **Hiscox / NetDiligence** — cyber insurance market data

These feed the calibration tables in `knowledge/datasets/benchmarks/` and the curated corpus that grounds the AI consultant's reasoning. Public benchmark datasets are referenced **by calibration table, not bundled** — see the licensing note above.

---

## Data Required to Improve Model Accuracy

CyberRisk AI's estimates are only as good as the information it is given. Like any actuarial model, the platform quantifies risk from the facts supplied to it — and the quality and completeness of those facts directly bound the precision of its outputs. The agent is designed to elicit and work with partial information — it **asks before it models** rather than guessing.

### 1. Company profile information

- Industry sector, company size, annual revenue
- Geographic footprint, number of employees, number of customers
- Business criticality, digital dependency

**Why it matters:** Industry and business characteristics influence baseline cyber threat frequency. A financial institution is targeted more often than a regional manufacturer; a company that runs its business on cloud infrastructure has a different exposure profile from one that operates on-premises. Industry and targeting feed the scenario frequency calibration, while revenue scales the severity distribution.

### 2. Data asset information

- Number of records held
- Types of sensitive data (personal, healthcare, financial, IP)
- Data classification, storage locations, cloud usage

**Why it matters:** Data sensitivity drives breach severity and regulatory exposure. 10 million healthcare records produces a materially different loss profile from 10,000 marketing contacts. Sensitive categories carry higher regulatory and notification costs (HIPAA, GDPR, state privacy laws).

### 3. Cybersecurity control information

Precise, quantified answers are best — *"65% MFA coverage"*, *"immutable backups, RTO 4 hours"* — rather than a single word such as "good" or "weak".

- **Identity & access:** MFA coverage %, privileged access management, SSO, identity governance
- **Network:** segmentation, firewall maturity, Zero Trust implementation
- **Endpoint:** EDR deployment, patch management, vulnerability scanning
- **Resilience:** backup frequency, immutable backups, DR testing, RTO

**Why it matters:** Controls influence both the probability and severity of cyber incidents. They feed the 18-factor scoring model, and through the score, the simulated frequency and severity of each scenario.

### 4. Third-party and supply chain risk

- Number of suppliers, critical vendors, cloud providers, software dependencies
- Third-party security assessments, contractual cyber requirements

**Why it matters:** Supply chain compromise is a major driver of modern cyber losses. The model treats third-party exposure as a distinct scenario and incorporates vendor-assessment practices and contractual security obligations directly into the risk score.

### 5. Historical incident data

- Previous cyber incidents, breach history, ransomware and downtime events
- Previous insurance claims and loss amounts

**Why it matters:** CyberRisk AI applies a **credibility-weighted calibration**: it starts from the industry baseline, then shifts frequency and severity toward your own observed experience the more of it you provide — while never discarding the sector prior entirely. A firm with a clean record receives a better-than-average modelled rate, and a firm with a troubled record a worse one, each fully auditable.

### 6. Insurance information

- Current limit, retention/deductible, policy structure, coverage sections
- Sublimits, exclusions, claims history

**Why it matters:** The insurance module requires accurate policy terms to estimate retained and transferred risk. It projects each simulated year of loss through the policy structure to calculate what the client retains versus what the insurer pays.

### Data quality guidance

| Information | Impact on Accuracy |
|---|---|
| High-quality security control data | Improves frequency modelling |
| Historical loss data | Improves severity calibration |
| Industry benchmarks | Improves baseline assumptions |
| Insurance policy details | Improves coverage analysis |
| Incomplete information | Increases uncertainty |

> **A note on model output.** CyberRisk AI produces probabilistic risk estimates, not guaranteed predictions. Better-quality input data reduces uncertainty and improves the reliability of risk quantification.

---

## Privacy and Security

CyberRisk AI is designed so that **no personal information is stored** and the repository is safe to publish publicly.

**What the platform does not store:**

- **No personal information.** The input-privacy guard detects and redacts personal data (names, emails, phone numbers, addresses) before it reaches the model ([`src/cyberrisk/privacy.py`](src/cyberrisk/privacy.py)).
- **No client-identifiable data on disk.** Client conversations and firm facts live in memory for the duration of a session; they are not written to persistent storage by default. Persisting a conversation scrubs personal data first (see `config/privacy.yaml`).
- **No private datasets.** The repository ships source code, documentation, and **synthetic example data only**. Licensed or client-confidential corpora must be sourced and held outside version control by the operator.

**Your responsibilities:**

- **Do not upload confidential client information** into the repository, issues, or discussions.
- **API credentials are yours, stored locally.** All secrets are read from environment variables or a local `.env` file (gitignored). Never commit a key. See [`SECURITY.md`](SECURITY.md).
- **All examples are synthetic.** The example companies and datasets (`examples/`, `data/examples/`, `config/benchmark_profiles.yaml`) are fictional. No real company is represented.

**The repository contains no private datasets and no secrets.** The `.gitignore` blocks `.env`, private keys, raw/private/client data directories, generated reports, and local databases. A security scanner ([`scripts/security_scan.py`](scripts/security_scan.py)) and pre-commit hooks ([`.pre-commit-config.yaml`](.pre-commit-config.yaml)) enforce this before anything is committed.

See [`SECURITY.md`](SECURITY.md) for the full security policy, vulnerability reporting, and data-protection statement.

---

## Testing

```bash
# Deterministic agent tests (no API key needed)
python -m pytest tests/test_agent_tools.py tests/test_agent_controller.py tests/test_agent_scenario.py tests/test_agent_deepseek_client.py -v

# Full suite (engine + agent + knowledge + validation)
python -m pytest -q
```

The full suite is **600 tests**, including a model-validation sub-suite (`tests/validate/`). A live API round-trip test runs only when a provider key is set.

---

## Future Roadmap

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

## Contributing

Contributions are welcome. This is a research and modelling platform, so please:

- **Open an issue** first for feature requests or bug reports.
- Keep the **quantitative engine deterministic** — changes must not break seeded reproducibility.
- Add tests for any engine or agent change; the suite is the gate.
- **Never commit** real client data, licensed datasets, or API keys.

See [`SECURITY.md`](SECURITY.md) for vulnerability reporting.

---

## Project Layout

```
src/
├── cyberrisk/          # Installed Python package (engine, agent, llm, knowledge, api, cli)
│   ├── scoring.py      #   18-factor risk scoring
│   ├── simulation.py   #   Monte Carlo loss simulation
│   ├── metrics.py      #   EAL, VaR, Expected Shortfall, PML
│   ├── knowledge/      #   ingestion, chunking, embedding, vector store, RAG
│   ├── agent/          #   AI consultant: LLM client (via llm/), tools, controller, UI
│   ├── llm/            #   LLM provider abstraction: OpenAI/DeepSeek providers, factory
│   └── api/            #   FastAPI web layer
├── agent/              # Rule-based consultant agent (re-exports agent.safety, elicitation, ...)
├── engine/             # Logical engine namespace (re-exports cyberrisk engine modules)
└── rag/                # Logical RAG namespace (re-exports cyberrisk.knowledge)

app/
├── frontend/           # React + Vite SPA (dist/ is served by FastAPI)
└── backend/            # FastAPI re-export (uvicorn app.backend:app)

docs/                   # architecture, model methodology, deployment, API, knowledge base
examples/               # runnable worked examples (full pipeline, benchmarks, demos)
config/                 # scoring weights, scenarios, simulation, benchmark profiles
knowledge/              # corpus, datasets, manifests, derived artifacts
tests/                  # 600 tests, including tests/validate/ model-validation suite
scripts/                # security scanner
Dockerfile              # multi-stage image (backend + frontend + runtime)
docker-compose.yml      # containerised deployment
```

---

## License & Data Policy

This repository is licensed under the **[MIT License](LICENSE)** — permissive, so it can be embedded, extended, and used commercially with attribution. It is a good fit for a cyber risk / AI platform where the code is integrated into larger insurance and risk workflows.

- **Source code and documentation only.** Confidential client materials, licensed cyber datasets, and generated reports are **not committed** — see `.gitignore`. Curated example benchmark data is included by design; licensed corpora must be sourced independently.
- **No warranty.** The Software is provided "as is", without warranty of any kind (see the LICENSE file).

*CyberRisk AI is a research and modelling platform, not licensed financial advice. Outputs are model estimates for analytical use, not guarantees of loss or recovery.*
