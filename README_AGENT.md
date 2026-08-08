# CyberRisk AI Consultant Agent

A Marsh/Aon-style cyber risk consultant built on top of the CyberRisk
quantitative risk engine, powered by **DeepSeek**.

The agent talks to a client, decides when quantitative modelling is needed,
runs the existing loss engine as tools, and translates the results into
insurance advice a board can act on. **The quantitative engine is untouched**
— this layer is purely additive.

```
User
  → Chat interface (Streamlit `app.py` or terminal `run_chat.py`)
    → DeepSeek LLM reasoning layer (`deepseek_client.py`)
      → Agent controller (`agent_controller.py`)  — bounded tool-calling loop
        → CyberRisk tools (`tools.py`)
          → Existing engine (`compute_score` → `simulate` → `compute_metrics`
                             → `transform_events_to_years` → `write_report`)
            → Consultant-style response back up
```

---

## 1. Installation

```powershell
cd /path/to/project
.venv\Scripts\python -m pip install -e ".[agent]"
```

This installs the package plus the agent extras: `openai` (DeepSeek's
OpenAI-compatible SDK), `python-dotenv`, and `streamlit`.

> If you plan to use the Excel report tool, also install
> `.venv\Scripts\python -m pip install -e ".[reporting]"` (openpyxl).

## 2. Environment setup

```powershell
Copy-Item .env.example .env
```

Then open `.env` and set your key:

```ini
DEEPSEEK_API_KEY=sk-your-key-here
```

Optional settings (defaults shown):

```ini
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat        # or deepseek-reasoner
```

The agent reads these via `python-dotenv` at startup. The API key is never
hard-coded and never committed — keep `.env` out of version control.

## 3. DeepSeek API configuration

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | ✅ | — | Get it at https://platform.deepseek.com |
| `DEEPSEEK_BASE_URL` | | `https://api.deepseek.com` | OpenAI-compatible endpoint |
| `DEEPSEEK_MODEL` | | `deepseek-chat` | `deepseek-reasoner` for R1-style reasoning |

DeepSeek exposes an OpenAI-compatible API, so the agent uses the official
`openai` SDK with a custom `base_url`. If the key is missing, both interfaces
print a clear message instead of failing mid-conversation.

## 4. Launch the chatbot

### Streamlit (recommended)

```powershell
cd /path/to/project
.venv\Scripts\python -m streamlit run src\cyberrisk\agent\app.py
```

Open the printed URL (default http://localhost:8501). The sidebar shows
DeepSeek config status; you can adjust simulation years and clear the
conversation.

### Terminal (quick testing)

```powershell
cd /path/to/project
.venv\Scripts\python -m cyberrisk.agent.run_chat
```

Type questions directly; `exit` or Ctrl-C to quit.

## 5. How it works

1. **Tools** (`tools.py`) wrap the engine read-only:
   - `assess_company_risk` — scores the profile (0–100), risk category, drivers.
   - `run_loss_simulation` — Monte Carlo EAL, VaR 95/99, Expected Shortfall
     95/99, 1-in-200 and 1-in-1000 PMLs, loss-distribution quantiles,
     per-scenario AAL.
   - `analyse_insurance_structure` — ground-up loss, insurance response
     (covered loss, insurer payment), and client retained loss (gross loss −
     insurance recovery = residual uncovered exposure), with residual >= 0
     and insurer payment <= policy limit. Never calls a gross loss a "gap".
   - `generate_risk_report` — writes an Excel workbook.
2. **Controller** (`agent_controller.py`) runs a bounded tool-calling loop:
   send history + tool schemas to DeepSeek → execute requested tools with
   validated JSON args → inject results → repeat until the model answers.
3. **Deterministic profile mapping** (`build_factor_scores`) turns the
   client's free-text brief (e.g. *"weak MFA and limited network
   segmentation"*) into the engine's 18 factor scores via the configured
   evidence scales. The same brief always yields the same score.
4. **Completeness guard** — the loss tools refuse to run until the client has
   given **revenue** and a **security-controls description**, returning
   `{"status": "insufficient_info", "needed": [...]}` so the agent asks
   instead of inventing a profile.
5. **No invented numbers** — the system prompt forbids it, the tools are the
   only source of figures, and the completeness guard blocks assumed
   profiles. The existing hallucination check in `src/agent/safety.py` is
   available as a backstop.

## 6. Example questions to try

| Question | What the agent does |
|---|---|
| "Assess a healthcare technology company with 10 million patient records, weak MFA and limited network segmentation." | Asks for revenue if missing, then scores and runs the model. Expect High/Critical rating, ransomware + business-interruption as top drivers, a fat tail, and an insurance-gap warning. |
| "We're a $500M manufacturer. What cyber insurance limit and retention should we buy?" | Models the exposure, tests a structure via `analyse_insurance_structure`, and recommends a limit/retention with the gap quantified. |
| "How exposed are we to ransomware? What's our worst-case 1-in-1000-year loss?" | Runs the simulation and quotes EAL, scenario AAL, and the 1-in-1000 PML. |
| "Explain VaR 95 versus Expected Shortfall in plain English for our board." | A conversational explanation grounded in the modelled numbers. |
| "We have no security controls and store a lot of customer data." | The agent asks for revenue and specifics before modelling — it will not guess a profile. |

## 7. Tests

```powershell
# Deterministic agent tests (no API key needed)
.venv\Scripts\python -m pytest tests\test_agent_tools.py tests\test_agent_controller.py tests\test_agent_scenario.py tests\test_agent_deepseek_client.py -v

# Full suite (engine regression check)
.venv\Scripts\python -m pytest -q
```

The live API round-trip test (`test_live_chat_round_trip`) runs only when
`DEEPSEEK_API_KEY` is set.

## 8. Project layout (agent layer)

```
src/cyberrisk/agent/
├── __init__.py            # public exports
├── schemas.py             # CompanyBrief, AgentConfig, tool DTOs
├── deepseek_client.py     # OpenAI-compatible DeepSeek wrapper (env-only keys)
├── prompts.py             # Marsh/Aon persona + grounding rules
├── tools.py               # engine-backed tools + deterministic factor mapping
├── memory.py              # conversation memory + client facts
├── agent_controller.py    # bounded tool-calling loop
├── app.py                 # Streamlit chat UI
└── run_chat.py            # terminal chat UI
```
