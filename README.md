<p align="center">
  <img src="docs/images/landing.png" alt="CyberRisk AI — commercial cyber risk quantification" width="840" />
</p>

<h1 align="center">🛡️ CyberRisk AI</h1>

<p align="center">
  <b>Cyber risk, quantified.</b><br/>
  Size your cyber exposure the way actuaries price catastrophe risk —<br/>
  Monte Carlo loss simulation, Value-at-Risk, Expected Shortfall, then insurance that actually fits.
</p>

<p align="center">
  <a href="https://www.python.org/"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue.svg" /></a>
  <a href="https://fastapi.tiangolo.com/"><img alt="FastAPI" src="https://img.shields.io/badge/API-FastAPI-009688.svg" /></a>
  <a href="https://react.dev/"><img alt="React 19" src="https://img.shields.io/badge/UI-React%2019-61DAFB.svg" /></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green.svg" /></a>
  <a href="#testing"><img alt="tests" src="https://img.shields.io/badge/tests-680%20backend%20%2B%2042%20frontend-brightgreen.svg" /></a>
</p>

---

**CyberRisk AI turns a handful of facts about a company — industry, revenue,
records held, security controls — into a board-ready, dollar-denominated cyber
loss model.** The engine simulates your tail the way catastrophe models price
hurricanes: thousands of scenario-driven Monte Carlo years, ranked into the
metrics a CFO, CRO, or underwriter actually signs off on.

> **The short version:** a healthcare firm with 10M patient records and weak
> controls models at **EAL ≈ $3.6M/year**, a **1-in-100-year loss of $27M**
> (VaR 99) and a **tail average of $43M** (ES 99). CyberRisk AI produces
> exactly these numbers — then tells you what to fix and how to insure it.

No LLM invents the figures. Every dollar is an engine output, and the AI
consultant that walks you through the analysis is grounded in a curated,
GDPR/HIPAA/NIST-aware knowledge base — **with no personal data ever stored.**

---

## Why CyberRisk AI

| Problem | How CyberRisk AI answers it |
|---|---|
| "How much cyber risk do we actually carry?" | An **18-factor scoring model** (industry targeting, data sensitivity, MFA, patching, EDR, supply chain…) maps your controls to a 0–100 score. |
| "What would a bad year cost us?" | **Monte Carlo loss simulation** — scenario frequency & severity calibrated to Verizon DBIR, IBM Cost of a Data Breach, ENISA and CISA KEV — produces EAL, **VaR 95/99** and **Expected Shortfall 95/99**. |
| "Is our insurance actually covering the tail?" | A **policy-transfer engine** projects every simulated loss year through your limit/retention/aggregate and tells you what's retained vs. transferred. |
| "We don't have a risk model team." | An **AI consultant** elicits the right questions, runs the tools, and explains the result in plain language — with citations. |
| "What should we fix first?" | Every assessment ranks the **top risk drivers** and quantifies the score/curve impact of remediating each one. |
| "Is my data safe?" | **Privacy-first by design.** No PII stored, no secrets committed, no client data on disk. Self-hostable, fully offline engine. |

---

## What it produces — a real run

Here is a **live engine run** on a representative healthcare-technology client
(200,000 simulated years):

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
| Third-party exposure | High — onboarding-only vendor assessment, minimal contractual security |
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

**What those numbers mean:**

| Metric | Value | Interpretation |
|---|---|---|
| **Risk score** | 73.4 / 100 | **High** risk band. Healthcare is heavily targeted, data sensitivity is critical (10M records), and patching/privileged-access/EDR are weak. |
| **EAL** | $3.62M | Expected **annual** loss from cyber events — the headline number for budgeting and pricing. |
| **VaR 99** | $27.42M | The loss exceeded with 1% probability in any year — the 1-in-100-year event. |
| **ES 99** | $42.71M | Average loss **in the worst 1% of years** — the figure that matters for capital and reinsurance. |
| **P(no loss)** | 10.2% | The firm loses money in ~90% of modelled years — consistent with a High risk category. |
| **Retained vs transferred** | $1.75M / $1.87M | With the tested structure the client retains roughly half the expected annual loss; the insurer pays half. |
| **P(within aggregate)** | 99.7% | The $25M aggregate would absorb the policy's transfers in 99.7% of years — broadly adequate, but the $1M aggregate deductible still leaves meaningful retained risk. |

**What the consultant would tell the board:** the tail exposure (ES99
$42.7M vs. a $10M per-occurrence limit) is largely **uninsured**. The move is
(a) raise the occurrence limit toward the P99.9 tail, (b) remediate the top
drivers — patch cadence, privileged access, vendor security — which move the
score and the entire loss distribution, and (c) revisit retention given a
~90% annual probability of at least one loss event.

> These figures are a live engine run on the profile above — illustrative of a
> worked example, not a quote or guarantee. Reproduce them yourself:
> `python examples/run_full_pipeline.py`.

---

## Key features

1. **Actuarial-grade scoring** — an 18-factor model that turns qualitative
   security posture into a calibrated 0–100 score with named risk drivers.
2. **Monte Carlo tail analysis** — scenario-based frequency/severity
   simulation producing **EAL, VaR 95/99, Expected Shortfall 95/99 and PML**,
   calibrated to industry-standard benchmark data.
3. **AI risk consultant** — a tool-calling LLM agent (DeepSeek or OpenAI) that
   elicits missing facts, runs the engine, and writes board-ready advice with
   citations. **It asks before it models — it never guesses.**
4. **Insurance structuring** — project simulated losses through any
   limit/retention/aggregate structure and read out retained vs. transferred
   EAL and probability of exhausting the policy.
5. **RAG-grounded knowledge base** — recommendations cite a curated corpus
   (NIST CSF 2.0, ISO 27001, GDPR, DORA, NIS2, DBIR…) that you extend with
   **zero code changes** — content is data, never code.
6. **Privacy-first by design** — no personal data stored, an input-privacy
   guard redacts PII before it reaches the model, and no client data is
   written to disk. The repo ships source + synthetic examples only.
7. **Model-validation suite** — a dedicated sub-suite (`tests/validate/`)
   proves the engine's properties (non-negative losses, calibrated
   percentiles) hold, not just that functions run.
8. **One process, two surfaces** — a FastAPI backend serving both the `/api`
   routes and the React SPA, so the web UI, the AI consultant and the mobile
   voice client all share the same engine.
9. **Versioned mobile API** — a mobile client runs a full assessment in **one
   round-trip** via `/api/v1` (score, EAL/VaR/ES, insurance, citations).
10. **Deploy anywhere** — Docker, Render, or Vercel, from a single
    multi-stage Dockerfile that builds the RAG index at build time
    (on Vercel the consultant serves incident evidence and gracefully
    omits vector-store citations).

---

## How it works

```
┌─────────────────────────────────────────────────────────────────────────┐
│  The CyberRisk AI pipeline                                             │
│                                                                         │
│  Client brief ──► 1. Score     18-factor risk score (0–100)            │
│                     │            + named risk drivers                   │
│                     ▼                                                  │
│                 2. Simulate   Monte Carlo frequency × severity          │
│                     │            over N years (seeded, reproducible)    │
│                     ▼                                                  │
│                 3. Metrics    EAL · VaR 95/99 · ES 95/99 · PML          │
│                     │            P(no loss)                             │
│                     ▼                                                  │
│                 4. Insure     project losses through the policy         │
│                                structure → retained vs transferred      │
│                                                                         │
│   The AI consultant wraps 1–4 as tools, grounded in the RAG knowledge   │
│   base, and writes the analysis in plain language with citations.       │
└─────────────────────────────────────────────────────────────────────────┘
```

The engine is deliberately deterministic and auditable: scenario
probabilities are seeded, every figure traces to a calibration table, and the
hallucination guard verifies that any claim the consultant makes traces to
either a tool metric or a retrieved chunk. See [Model Methodology](docs/model-methodology.md)
and [Architecture](docs/architecture.md).

---

## Try it in five minutes

**Requirements:** Python 3.10+ (or Docker).

### Option A — Python (no container)

```bash
# 1. Create a virtualenv and install
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[web,agent,knowledge]"

# 2. (Optional) configure an LLM for the AI consultant
cp .env.example .env                  # set LLM_PROVIDER + DEEPSEEK_API_KEY / OPENAI_API_KEY

# 3. Run the quantitative engine end-to-end — no API key needed
python examples/run_full_pipeline.py

# 4. Or start the web app
python -m uvicorn cyberrisk.api.main:app --port 8000
open http://localhost:8000            # web UI · /docs = interactive API docs
```

> The **risk engine is fully offline** — only the AI consultant layer needs an
> LLM API key. Try the engine first; add the consultant when you want it.

### Option B — Docker (everything included)

```bash
cp .env.example .env                  # set your LLM keys
docker compose up --build
open http://localhost:8000
```

The container runs as a non-root user with a health check, and the
multi-stage build produces the RAG vector index from the committed corpus at
build time. Validate the full deployment in CI with
`docker/validate/validate.sh` (macOS/Linux) or `docker/validate/validate.ps1`
(Windows).

---

## The AI consultant

The consultant is a tool-calling LLM agent that acts like a senior cyber risk
advisor:

1. **Elicits** the facts it needs — it asks targeted follow-ups rather than
   modelling on guesses (partial data → `insufficient_info` with a list of
   what's missing).
2. **Runs the engine** — scoring, Monte Carlo, insurance structuring — through
   the same tools the API exposes.
3. **Writes the answer** — Marsh/Aon-style advice in plain language, with the
   quantitative outputs, citations, and model limitations disclosed.

**Provider-agnostic.** Switch between DeepSeek and OpenAI via one env var:

| Variable | Purpose | Example |
|---|---|---|
| `LLM_PROVIDER` | Provider to use (`deepseek` / `openai`) | `deepseek` |
| `DEEPSEEK_API_KEY` | Key for the DeepSeek provider | `sk-...` |
| `DEEPSEEK_MODEL` | Model name (default `deepseek-chat`) | `deepseek-chat` |
| `OPENAI_API_KEY` | Key for the OpenAI provider | `sk-...` |
| `OPENAI_MODEL` | Model name (default `gpt-4o-mini`) | `gpt-4o-mini` |
| `CYBERRISK_API_KEY` | *Optional* bearer key for API/CLI consumers gating every `/api/*` route — leave **unset** on web deploys (the SPA sends no bearer header) | `openssl rand -hex 32` |
| `CYBERRISK_RATE_LIMIT` | *Optional* requests/minute per client (0 = off) | `60` |

Use it programmatically in one line:

```python
from cyberrisk.agent.agent_controller import CyberRiskAgent

agent = CyberRiskAgent()                    # provider from LLM_PROVIDER env
answer = agent.chat(
    "Assess a $400M healthcare technology firm holding 10M patient records "
    "with partial MFA and weekly backups."
)
print(answer)
```

---

## Python API

The engine and agent are plain Python modules — drive them from notebooks,
scripts, or your own service.

**Engine-only (no API key, fully offline):**

```python
from pathlib import Path
from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics
from cyberrisk.scoring import CompanyProfile, compute_score
from cyberrisk.simulation import simulate

cfg = load_config(Path("config/scenarios.yaml"), Path("config/simulation_config.yaml"))

profile = CompanyProfile(
    firm_name="Acme Manufacturing",
    revenue_usd=500_000_000,
    factor_scores={"external_attack_surface": 70.0, "mfa_coverage": 60.0},
)

scored = compute_score(profile)
metrics = compute_metrics(simulate(cfg, n_years=100_000, score=scored.composite_score))

print(f"{scored.firm_name}: {scored.composite_score:.1f}/100 ({scored.risk_category})")
print(f"EAL:   ${metrics.eal/1e6:,.2f}M")
print(f"VaR99: ${metrics.var_99/1e6:,.2f}M")
print(f"ES99:  ${metrics.es_99/1e6:,.2f}M")
```

**Web-layer tools (the same functions the API routes wrap):**

```python
from cyberrisk.agent.tools import assess_company_risk
from cyberrisk.agent.schemas import CompanyBrief

result = assess_company_risk(CompanyBrief(
    firm_name="MedData Health Technologies",
    industry="Healthcare",
    revenue_usd=400_000_000,
    customer_records=10_000_000,
    security_controls="partial MFA, weekly backups",
))
# score, risk category, EAL/VaR/ES, and the top risk drivers
```

---

## The web app

A single FastAPI process serves both the API and the React SPA.

**Development mode (live-reload):**

```bash
# Terminal 1 — FastAPI backend on :8000
python -m uvicorn cyberrisk.api.main:app --port 8000 --reload

# Terminal 2 — Vite dev server on :5173 (proxies /api → :8000)
cd app/frontend && npm ci && npm run dev
```

Open <http://localhost:5173>. In production, `npm run build` emits the SPA
into `app/frontend/dist`, which FastAPI serves with an SPA fallback — one
origin for everything.

**Versioned mobile API** — a mobile client (including the iOS voice PWA at
`/voice.html`) runs a full assessment in one round-trip:

```bash
curl -X POST http://localhost:8000/api/v1/assessment/submit \
  -H "Content-Type: application/json" \
  -d '{"firm_name":"Acme","industry":"Healthcare","revenue_usd":400000000,
       "customer_records":10000000,"technology_dependency":"High",
       "security_controls":"MFA partial, weekly backups, weak segmentation"}'
```

The response carries `assessment_id`, `status`, and the full `result` —
risk score, EAL, VaR/ES, PML, insurance analysis, mitigation recommendations,
model limitations, and evidence/citations. Full route reference:
[docs/api.md](docs/api.md).

---

## The knowledge base

The consultant's recommendations are grounded in a curated corpus that you
extend with **no code changes** — content is data, never code:

```
knowledge/
├── corpus/                  # source documents you curate
│   ├── incidents/           #   breach/incident case data
│   ├── industry-reports/    #   DBIR, IBM CODB, ENISA, Hiscox, NetDiligence…
│   ├── insurance/           #   wordings, claims guides, market terms
│   ├── regulatory/          #   GDPR, HIPAA, NIS2, DORA, AI Act, SEC…
│   ├── standards/           #   NIST CSF 2.0, NIST 800-53, ISO 27001, CIS…
│   ├── threat-intel/        #   threat landscape reports
│   └── vulnerability-data/  #   CISA KEV, CVE data
├── datasets/                # structured calibration data (CSV/JSON)
├── manifests/               # corpus_manifest.yaml (registered documents)
└── derived/                 # chunks, embeddings, vector.db (gitignored)
```

**Add a document and it just works:**

```bash
# 1. Drop a PDF/Markdown/DOCX/HTML/YAML into a corpus folder
# 2. Run the pipeline — it scans, parses, chunks, embeds, and updates the index
python -m cyberrisk.knowledge.update
python -m cyberrisk.knowledge.update --force   # re-index everything
```

Content-hash deduplication makes re-runs safe; a quality gate
(`knowledge.populate`) only ingests documents registered as **approved** in
the source registry. See [Knowledge Base](docs/knowledge-base.md).

---

## Deploy

Three supported paths, all from the same codebase:

### Docker (any host)
```bash
docker compose up --build
```
The image bakes the RAG vector index from the committed corpus, runs as a
non-root user, and health-checks `/api/health`.

### Render (free tier, no laptop needed)
The repo ships a [Render Blueprint](render.yaml) — import the repo, set
`DEEPSEEK_API_KEY` (optionally `CYBERRISK_API_KEY` for API consumers; leave it
unset for the web UI, which sends no bearer header), deploy. The iOS voice PWA
is reachable at `https://<app>.onrender.com/voice.html` from any WiFi.
Details in [docs/deployment.md](docs/deployment.md).

### Vercel (serverless)
The repo ships a zero-config FastAPI deployment (`vercel.json`, `api/vc_app.py`):

```bash
npm i -g vercel && vercel deploy --prod
```

Set `LLM_PROVIDER=deepseek` and `DEEPSEEK_API_KEY` (leave `CYBERRISK_API_KEY`
unset — the SPA sends no bearer header) in the project's **Environment
Variables**. The build command compiles the React SPA, Vercel promotes the
FastAPI static mount to the CDN, and `/api/*` + unknown client-side routes fall
through to the serverless function. Vercel serves the SPA, API, Excel reports
and incident evidence; vector-store RAG citations are baked at build time on
Docker/Render and gracefully omitted here.

---

## Privacy & security

CyberRisk AI is designed so that **no personal information is stored** and the
repository is safe to publish publicly.

- **No personal information.** The input-privacy guard detects and redacts
  personal data (names, emails, phones, addresses) before it reaches the model.
- **No client-identifiable data on disk.** Conversations and firm facts live
  in memory for the session; persisting scrubs personal data first
  (`config/privacy.yaml`).
- **No private datasets.** The repo ships source code, docs, and **synthetic
  example data only**. Secrets are read from environment / a gitignored
  `.env`, never committed. A security scanner
  ([`scripts/security_scan.py`](scripts/security_scan.py)) and pre-commit hooks
  enforce this.
- **All examples are synthetic.** No real company is represented.

See [`SECURITY.md`](SECURITY.md) for the full security policy and
vulnerability reporting.

---

## Testing

```bash
# Backend — 680 tests (engine + agent + knowledge + model validation)
python -m pytest -q

# Frontend — 42 tests (chat shell, transcript, components)
cd app/frontend && npm test
```

The full suite includes a dedicated model-validation sub-suite
(`tests/validate/`) that asserts the engine's mathematical properties hold —
calibrated percentiles, non-negative losses, policy-transfer accounting — not
just that the functions run. The deterministic agent tests need no API key.

---

## Roadmap

**Near term**
- [ ] Production vector database (Chroma / Qdrant / pgvector) behind `VectorStore`
- [ ] Dense embedding models swapped in via `EmbedderRegistry`
- [ ] Portfolio aggregation — correlated exposure across a book of clients
- [ ] Multi-year loss chains and reinsurance-pricing outputs (quota share, excess-of-loss)

**Medium term**
- [ ] Reinsurance pricing and Solvency II capital-modelling (SCR) outputs
- [ ] Automated benchmark refresh against the latest DBIR / IBM CODB / ENISA
- [ ] Scenario-dependency copula calibration from real correlated breach data

**Long term**
- [ ] Live threat-intelligence feed continuously updating scenario frequencies
- [ ] Credibility-weighted calibration to a client's actual claims experience
- [ ] Underwriting workbench UI for portfolio triage, quoting, and monitoring

---

## Contributing

Contributions are welcome — this is a research and modelling platform. Please:

- **Open an issue** first for feature requests or bug reports.
- Keep the **quantitative engine deterministic** — changes must not break
  seeded reproducibility.
- Add tests for any engine or agent change; the suite is the gate.
- **Never commit** real client data, licensed datasets, or API keys.

See [`SECURITY.md`](SECURITY.md) for vulnerability reporting.

---

## Project layout

```
src/
├── cyberrisk/          # Installed Python package (engine, agent, llm, api, cli)
│   ├── scoring.py      #   18-factor risk scoring
│   ├── simulation.py   #   Monte Carlo loss simulation
│   ├── metrics.py      #   EAL, VaR, Expected Shortfall, PML
│   ├── knowledge/      #   ingestion, chunking, embedding, vector store, RAG
│   ├── agent/          #   AI consultant: LLM client, tools, controller
│   └── api/            #   FastAPI web layer (+ /api/v1 mobile API)
├── agent/              # Rule-based consultant agent (safety, elicitation, …)
└── engine/             # Logical engine namespace (re-exports)

app/
├── frontend/           # React 19 + Vite SPA (dist/ is served by FastAPI)
└── backend/            # FastAPI re-export (uvicorn app.backend:app)

api/vc_app.py           # Vercel serverless entrypoint
config/                 # scoring weights, scenarios, simulation config
docs/                   # architecture, methodology, deployment, API, knowledge
examples/               # runnable worked examples
knowledge/              # corpus, datasets, manifests, derived artifacts
tests/                  # 680 tests incl. tests/validate/ model validation
Dockerfile              # multi-stage image (backend + frontend + runtime)
vercel.json             # Vercel serverless config
render.yaml             # Render Blueprint
```

---

## License & data policy

Licensed under the **[MIT License](LICENSE)** — permissive, so it can be
embedded, extended, and used commercially with attribution.

- **Source code and documentation only.** Confidential client materials,
  licensed datasets, and generated reports are never committed (see
  `.gitignore`). Curated example benchmark data is included by design;
  licensed corpora must be sourced independently.
- **No warranty.** The Software is provided "as is", without warranty of any
  kind.

*CyberRisk AI is a research and modelling platform, not licensed financial
advice. Outputs are model estimates for analytical use, not guarantees of loss
or recovery.*
