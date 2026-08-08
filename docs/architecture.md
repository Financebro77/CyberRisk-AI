# Architecture

This document describes how CyberRisk AI is put together. It is written for
engineers and architects who want to understand the system end-to-end before
contributing, deploying, or integrating.

> The quantitative engine is a **read-only, deterministic core**. The AI agent
> and web layer consume it through a tool layer and never modify it. This
> separation is deliberate: the model's numbers are reproducible and auditable,
> independent of which LLM (or no LLM at all) is driving the interface.

---

## 1. System overview

CyberRisk AI is a layered platform:

```
                    ┌────────────────────────────────────────────┐
                    │             Interfaces                      │
                    │   CLI · Streamlit · Web (React) · Python    │
                    └───────────────────────┬────────────────────┘
                                            │
                    ┌───────────────────────▼────────────────────┐
                    │            AI consultant layer              │
                    │   agent_controller.py (tool-calling loop)   │
                    │   tools.py (engine-backed tool registry)    │
                    │   llm/ (provider abstraction)               │
                    │   knowledge/ (RAG retrieval)                │
                    └───────────────────────┬────────────────────┘
                                            │ read-only, via tools
                    ┌───────────────────────▼────────────────────┐
                    │          Quantitative risk engine            │
                    │   scoring → frequency → severity →           │
                    │   Monte Carlo → metrics → policy transform   │
                    └─────────────────────────────────────────────┘
```

The stack in one table:

| Layer | Technology | Path |
|---|---|---|
| Interfaces | CLI, Streamlit, React + Vite, FastAPI, Python API | `src/cyberrisk/cli.py`, `src/cyberrisk/agent/app.py`, `src/cyberrisk/api/`, `app/frontend/` |
| AI consultant | Tool-calling agent, bounded loop, hallucination backstop | `src/cyberrisk/agent/` |
| LLM abstraction | `LLMClient` interface + OpenAI/DeepSeek providers + factory | `src/cyberrisk/llm/` |
| Knowledge / RAG | Ingest → chunk → embed → SQLite vector store → retrieve | `src/cyberrisk/knowledge/` |
| Quantitative engine | NumPy/SciPy/Pandas, deterministic when seeded | `src/cyberrisk/*.py` |

---

## 2. The AI agent architecture

The agent is a **Marsh/Aon-style cyber risk consultant**: it talks to a client,
decides when quantitative modelling is needed, runs the loss engine as tools,
and translates the results into board-ready insurance advice.

### 2.1 Components

```
User
  → Chat interface (Streamlit app.py · terminal run_chat.py · CLI cli.py)
    → LLM client (llm/ — OpenAI or DeepSeek via the factory)
      → Agent controller (agent_controller.py) — bounded tool-calling loop
        → CyberRisk tools (tools.py)
          → Existing engine (scoring → simulate → compute_metrics
                             → policy transform → write_report)
            → Consultant-style response back up
```

| Module | Responsibility |
|---|---|
| `schemas.py` | `CompanyBrief` (the running client picture), `AgentConfig`, tool input/output DTOs (Pydantic v2) |
| `memory.py` | Conversation memory + accumulated client facts across turns |
| `prompts.py` | The senior-consultant persona, grounding rules ("NEVER invent a number"), RAG citation rules |
| `tools.py` | The engine-backed tool registry — **the only place that touches the engine** |
| `agent_controller.py` | The bounded tool-calling loop and tool execution |
| `llm/` | Provider-agnostic LLM client (OpenAI / DeepSeek) |
| `app.py` / `run_chat.py` | Streamlit and terminal chat interfaces |

### 2.2 The tool-calling loop

`agent_controller.py` runs a bounded loop:

1. Append the user's latest message to conversation memory.
2. Send the full history **plus the tool schemas** to the LLM.
3. If the model requests tools, validate the JSON arguments, execute each tool
   against the real engine, inject the results as `role: tool` messages, and
   loop back to step 2.
4. If the model produces text, run the existing **hallucination backstop**
   against the metrics the tools actually returned, then return it.

The loop is bounded by `max_tool_rounds` (default 6) so a misbehaving model
cannot loop forever.

### 2.3 The tool registry

The agent can call six tools (`tools.py`, `TOOL_SCHEMAS`):

| Tool | What it does |
|---|---|
| `assess_company_risk` | Scores the profile (0–100), risk category, and top risk drivers |
| `run_loss_simulation` | Monte Carlo EAL, VaR 95/99, ES 95/99, PML, loss-distribution quantiles, per-scenario AAL |
| `analyse_insurance_structure` | Tests a policy (limit, retention, sub-limits) — insurer payment vs client retained exposure |
| `generate_risk_report` | Writes the Excel assessment workbook |
| `run_control_improvement_scenario` | Models the effect of a control change (e.g. "implement MFA") — before/after EAL, VaR, ES |
| `search_incidents` | Searches the curated incident index, returning citable structured facts |

### 2.4 Why the numbers are trustworthy

- The system prompt forbids inventing figures.
- **The tools are the only source of numbers** — the LLM never computes them.
- A **completeness guard** blocks the loss tools until the client provides
  revenue and a security-controls description; the agent asks instead of
  assuming a profile.
- The **deterministic factor mapping** (`build_factor_scores`) turns free-text
  controls (e.g. *"weak MFA and limited network segmentation"*) into the
  engine's 18 factor scores via configured evidence scales — the same brief
  always yields the same score.
- An existing **hallucination check** (`src/agent/safety.py`) validates
  claim-framed dollar figures against the tool results as a final backstop.

---

## 3. The risk engine

The quantitative engine is the deterministic core. It is composed of
independent, unit-tested modules under `src/cyberrisk/`:

| Module | Purpose |
|---|---|
| `calibration.py` | Scenario definitions (frequency + severity specs) and config loading from `config/*.yaml` |
| `scoring.py` | 18-factor risk scoring → 0–100 score + Low/Medium/High/Critical category |
| `frequency.py` | Per-scenario frequency models (Poisson / negative-binomial counts) |
| `severity.py` | Per-scenario severity distributions (heavy-tailed) |
| `copulas.py` | Dependency modelling between scenarios (one-factor, Student-t) |
| `simulation.py` | Monte Carlo: draw years of scenario losses, aggregate |
| `metrics.py` | EAL, VaR, Expected Shortfall, PML, bootstrap standard errors |
| `policy_transform.py` | Insurance structure: retained vs transferred loss |
| `credibility.py` | Blend industry baseline with a client's own experience |
| `uncertainty.py` | Parameter-uncertainty bands around the point estimates |

The pipeline the agent drives:

```
compute_score → simulate → compute_metrics → transform_events_to_years → write_report
```

Everything is **deterministic when seeded**: the same profile + seed always
produces the same score, distribution, and metrics.

---

## 4. Monte Carlo simulation

The simulation is the heart of the platform.

### 4.1 How it works

For each simulated year and each scenario:

1. **Draw a frequency** from the scenario's calibrated count distribution
   (e.g. Poisson with scenario-specific annual rate λ).
2. **Draw a severity** for each event from the scenario's severity
   distribution (heavy-tailed, e.g. lognormal / Pareto-style).
3. **Apply dependence** across scenarios via a copula, so correlated scenarios
   (e.g. a cloud outage that also triggers business interruption) do not
   silently double-count or cancel out.
4. **Aggregate** per-year losses to build the full annual loss distribution.

A typical run uses **100,000–200,000 simulated years** — a few seconds on a
laptop (the engine is CPU-bound NumPy).

### 4.2 What it produces

From the simulated distribution, `metrics.py` derives:

- **EAL** — the mean annual loss.
- **VaR 95 / VaR 99** — loss thresholds exceeded with 5% / 1% probability.
- **ES 95 / ES 99** — the average loss in the worst 5% / 1% of years.
- **PML** — 1-in-100, 1-in-200, and 1-in-1000-year probable maximum losses.
- **P(no loss)** — the share of simulated years with zero loss.
- **Per-scenario AAL** — each scenario's contribution to expected annual loss.
- **Loss exceedance curve** — P(loss ≥ x) across loss levels.

---

## 5. RAG pipeline

The consultant's recommendations are grounded in a curated corpus via a
retrieval-augmented generation (RAG) pipeline in `src/cyberrisk/knowledge/`.

### 5.1 Pipeline stages

```
corpus/ documents
   → extract (PDF / DOCX / HTML / MD / TXT / YAML)
   → clean (normalise, strip noise)
   → chunk (section-aware or plain, per config)
   → embed (HashEmbedder by default; pluggable via EmbedderRegistry)
   → store (SQLite vector store, content-hash deduplicated)
   → retrieve (semantic search + structured incident index)
   → inject into the system prompt with citation markers
```

The pipeline is driven by **manifests** (`knowledge/manifests/*.yaml`) — the
single source of truth for which documents and datasets are registered.

### 5.2 Retrieval at query time

When the user asks a question, the agent controller (`_rag_context`) pulls
context from two sources:

1. **Semantic retrieval** — vector search over the embedded corpus chunks.
2. **Structured incident retrieval** — the incident index, matched by
   industry / attack-type keywords in the query.

Retrieved context is injected into the per-turn system prompt with strict
citation rules (`RAG_RULES`), so the consultant can reference
`[citation: chunk_id]`. Retrieval is **additive and never required** — the
agent still works without a populated knowledge base.

---

## 6. The LLM layer

`src/cyberrisk/llm/` is a provider-agnostic abstraction so the same agent runs
on **OpenAI** or **DeepSeek** (or any provider that implements the interface).

### 6.1 Interface

| Component | Responsibility |
|---|---|
| `base.py` | `LLMClient` abstract interface + shared `ChatResponse` type and response-normalisation helpers |
| `openai_provider.py` | `OpenAIProvider` — native OpenAI chat-completions API (`OPENAI_API_KEY`, `OPENAI_MODEL`) |
| `deepseek_provider.py` | `DeepSeekProvider` — OpenAI-compatible DeepSeek endpoint (`DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`) |
| `factory.py` | Picks the provider from `LLM_PROVIDER=openai` / `=deepseek` |

### 6.2 The interface surface

The `LLMClient` interface provides:

- `chat(messages, tools, temperature, max_tokens)` — the tool-calling surface
  the agent loop uses; returns `ChatResponse` with `content` and/or
  `tool_calls`.
- `generate_response(messages, ...)` — plain-text reply (no tools).
- `generate_structured_output(messages, ...)` — JSON-object reply, parsed to a
  dict (`response_format={"type": "json_object"}`).
- `check_connection()` — a cheap probe (model list or 1-token chat).
- `is_configured()` — whether the provider's key is present in the environment.

### 6.3 Switching providers

Set `LLM_PROVIDER` in `.env` (or the environment) and restart:

```ini
LLM_PROVIDER=deepseek    # DEEPSEEK_API_KEY=sk-...
LLM_PROVIDER=openai      # OPENAI_API_KEY=sk-...
```

If unset, the factory infers the provider from whichever key is present.
Adding a third provider means implementing `LLMClient` and registering it in
the factory — no agent, engine, or UI code changes.

### 6.4 Security model

- **API keys are never hard-coded** — always from env / `.env` (gitignored).
- Keys are read at construction; a missing key raises a clear, actionable
  `RuntimeError`.
- `generate_structured_output` and all responses are **normalised and parsed**
  defensively — bad JSON returns an empty result, never a crash.
- The `openai` package is imported **lazily** (it is an optional dependency).

---

## 7. How the layers connect (end-to-end)

A representative request — *"Assess a healthcare company with 10M patient
records and weak MFA"*:

1. The chat interface hands the message to `CyberRiskAgent.chat()`.
2. The privacy input guard scans the message (redacts/block PII).
3. The controller retrieves RAG context for the query.
4. The LLM returns a tool call for `run_loss_simulation`.
5. The controller executes the tool → the engine computes score + simulation
   + metrics, returns EAL/VaR/ES.
6. The result is injected into memory; the LLM may call more tools (e.g.
   `analyse_insurance_structure`).
7. The LLM produces the final answer; the hallucination backstop validates the
   quoted figures against the tool results.
8. The final answer (with the mandatory model-limitations disclosure) is
   returned and stored in memory.

---

*Next: [model-methodology.md](model-methodology.md) for the statistical detail,
or [deployment.md](deployment.md) to run it.*
