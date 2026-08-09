# Deployment

This document covers three deployment paths:

1. **Local installation** — run the engine, CLI, Streamlit, and web app on a
   single machine (the supported, tested path today).
2. **Docker deployment** — a recommended containerised setup. *The repo does
   not ship a `Dockerfile` yet*; this section specifies one so it can be
   added as a tracked deliverable.
3. **Cloud deployment roadmap** — the production hardening steps to run the
   platform at scale behind a real API.

---

## 1. Local installation

### 1.1 Prerequisites

| Requirement | Minimum |
|---|---|
| **Python** | **3.10 or newer** (3.11/3.12 recommended) |
| **OS** | Windows 10/11, macOS, or Linux |
| **Node.js** | Only for frontend development; the pre-built `app/frontend/dist` is served by FastAPI, so this is skippable |
| **Internet** | Only for the AI consultant layer (OpenAI / DeepSeek); the engine runs fully offline |

### 1.2 Install

```bash
git clone <your-repo-url> cyberrisk
cd cyberrisk

python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Core engine + agent extras:
pip install -e ".[agent]"

# Optional extras — they compose:
#   .[web]          FastAPI + Uvicorn web layer
#   .[reporting]    Excel report generation
#   .[knowledge]    PDF/DOCX parsing
#   .[test]         pytest
pip install -e ".[agent,web,reporting,knowledge,test]"
```

### 1.3 Configure the LLM provider

```bash
Copy-Item .env.example .env        # Windows
cp .env.example .env               # macOS / Linux
```

Set your provider in `.env`:

```ini
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
# or
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

> **No key?** The quantitative engine runs fully offline without any LLM key.
> Only the AI consultant layer needs one.

### 1.4 Launch options

| Interface | Command |
|---|---|
| **CLI consultant** | `cyberrisk` (or `python -m cyberrisk.cli`) |
| **Terminal chat** | `python -m cyberrisk.agent.run_chat` |
| **Streamlit chat** | `python -m streamlit run src/cyberrisk/agent/app.py` |
| **Web (API + UI)** | `pip install -e ".[web]"` then `python -m uvicorn cyberrisk.api.main:app --port 8000` |

Open the web app at <http://localhost:8000> (API docs at `/docs`).

### 1.5 Populate the knowledge base (optional but recommended)

The agent works without it, but grounding improves with a populated corpus:

```bash
python -m cyberrisk.knowledge.update        # scan + ingest + embed + index
python -m cyberrisk.knowledge.populate      # quality-gated authoritative path
```

See [knowledge-base.md](knowledge-base.md) for details.

### 1.6 Verify

```bash
python -m pytest -q                         # 600 tests
python -c "import cyberrisk; print(cyberrisk.__version__)"
```

---

## 2. Docker deployment

The repo ships a multi-stage `Dockerfile`, a `.dockerignore`, and a
`docker-compose.yml` that containerise the app and serve **both** the
FastAPI backend and the pre-built React frontend from a single image.

Deployment is designed around five requirements:

1. **AI agent backend** — uvicorn serves `/api/*` (the consultant agent and
   its tools) and `/docs`.
2. **Risk calculation engine** — the engine (`cyberrisk.*`) runs in-process
   inside the same container.
3. **RAG knowledge retrieval** — the SQLite vector store
   (`knowledge/derived/vector.db`) and offline `HashEmbedder` need **no
   external vector database**; the corpus and index are provided via volumes.
4. **Web application** — the built React SPA is served by the same process on
   :8000.
5. **Environment variable configuration** — read from `.env` via `env_file`,
   never baked into the image.

### 2.1 Docker architecture

The deployment is a **single image, single process**: one uvicorn worker
serves both the FastAPI backend and the statically-served React SPA. This is
the simplest topology that satisfies all five requirements; a multi-service
split (separate API, worker, vector-store containers) is unnecessary because
the engine and the SQLite vector store are embedded — see §3.2 for when to
split.

```
                ┌────────────────────────────────────────────────────┐
                │          cyberrisk:latest  (python:3.12-slim)      │
                │                                                    │
                │   uvicorn cyberrisk.api.main:app        :8000      │
                │     ├── /api/*      FastAPI routers + agent tools  │
                │     ├── /           React SPA (static, built)      │
                │     ├── /assets     SPA assets (static)            │
                │     └── /docs       Swagger UI                     │
                │                                                    │
                │   embedded: cyberrisk engine · RAG (SQLite + Hash) │
                └────────────────────────────────────────────────────┘
                        ▲ volumes                    ▲ .env (runtime)
        ┌───────────────┴────────────────┐   ┌───────┴────────┐
        │ knowledge/corpus   (ro)        │   │ LLM_PROVIDER   │
        │ knowledge/manifests(ro)        │   │ *_API_KEY      │
        │ knowledge/derived  (ro)        │   │ CYBERRISK_*    │
        │ data/output        (rw)        │   └────────────────┘
        └────────────────────────────────┘
```

Three build stages (`Dockerfile`):

- **backend** — `python:3.12-slim`; system deps for knowledge parsing
  (`poppler-utils`); installs the package as a **wheel** with
  `.[web,reporting,knowledge,agent]` (the `agent` extra brings the OpenAI SDK
  and `python-dotenv` used by the chat routes; a plain install — not
  `pip install -e` — keeps the image decoupled from the source tree).
  `PYTHONPATH=/app/src` is set because the runtime imports the legacy
  top-level `agent.safety` package from `src/`.
- **frontend** — `node:20-alpine`; `npm ci` against `package-lock.json`
  (single source of truth) then `npm run build` → `app/frontend/dist`.
- **runtime** — the backend image plus the built SPA; runs as an unprivileged
  user (`USER cyberrisk`, uid 10001), health-checks `/api/health`.

```dockerfile
# docker build -t cyberrisk:latest .   (or: docker compose up --build)
FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential poppler-utils && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[web,reporting,knowledge,agent]"

FROM node:20-alpine AS frontend
WORKDIR /build
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend ./
RUN npm run build

FROM backend AS runtime
COPY --from=frontend /build/dist /app/app/frontend/dist
RUN useradd --create-home --uid 10001 cyberrisk \
    && mkdir -p /app/data/output \
    && chown -R cyberrisk:cyberrisk /app/data /app/app/frontend/dist
USER cyberrisk
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "cyberrisk.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.2 The shipped `docker-compose.yml`

```yaml
services:
  cyberrisk:
    build:
      context: .
      dockerfile: Dockerfile
    image: cyberrisk:latest
    container_name: cyberrisk
    ports:
      - "8000:8000"
    environment:
      - LLM_PROVIDER=${LLM_PROVIDER:-deepseek}
    env_file:
      - .env                       # OPENAI_API_KEY / DEEPSEEK_API_KEY + overrides
    volumes:
      - ./knowledge/corpus:/app/knowledge/corpus:ro
      - ./knowledge/manifests:/app/knowledge/manifests:ro
      - ./knowledge/derived:/app/knowledge/derived:ro
      - ./data/output:/app/data/output
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      start_period: 15s
      retries: 3
```

### 2.3 Run

```bash
# 1. Configure your LLM provider
cp .env.example .env        # set LLM_PROVIDER + OPENAI_API_KEY / DEEPSEEK_API_KEY

# 2. Build and start
docker compose up --build

# 3. Open
#    http://localhost:8000        (UI + API)
#    http://localhost:8000/docs   (API docs)
```

Stop with `docker compose down` (add `-v` to also remove the named
volumes). Rebuild after source changes with `docker compose up --build`.

### 2.4 Validating the deployment

The repo ships a self-contained validation suite that exercises the seven
deployment checks from inside a real container run. It is **not** part of the
pytest suite (it requires Docker) and is safe to run with or without an LLM
API key — the engine, agent construction, and RAG checks are fully offline.

| Check | What it verifies |
|---|---|
| 1. Image builds | `docker build -t cyberrisk:latest .` succeeds |
| 2. Container starts | the container boots and the `/api/health` healthcheck turns `healthy` |
| 3. API responds | `GET /api/health` returns HTTP 200 |
| 4. AI agent loads | `CyberRiskAgent` constructs offline (provider resolved lazily) |
| 5. Risk engine executes | `load_config` → `simulate` → `compute_metrics` returns sane EAL/VaR |
| 6. RAG retrieval works | `HashEmbedder` → `VectorStore.similarity` returns the top hit |
| 7. Env vars load | `LLM_PROVIDER` is read at runtime; keys are runtime-only, never baked |

**Run on Windows (PowerShell):**

```powershell
.\docker\validate\validate.ps1          # build + full validation
.\docker\validate\validate.ps1 -NoBuild # reuse the existing image
```

**Run on macOS / Linux (bash):**

```bash
bash docker/validate/validate.sh
bash docker/validate/validate.sh --no-build
```

What the runner does:

1. Builds the image (or reuses it with `-NoBuild` / `--no-build`).
2. Starts a throwaway container (`cyberrisk-validate`, auto-removed) with the
   corpus, manifests, and output volumes mounted, then waits for `healthy`.
3. Hits `GET /api/health` on the published port `18000`.
4. Runs `docker/validate/smoke_test.py` inside the container — a Python
   script that imports the package, constructs the agent, runs a 2,000-year
   simulation, exercises the SQLite vector store, and reports env vars.
5. If a `.env` file is present, re-runs the smoke test with `--env-file` to
   confirm secrets are injected at runtime — and prints the env summary so
   you can confirm a key is set **without** it being baked into the image.

Each check prints `[PASS]` or `[FAIL]`; the runner exits nonzero on the first
failure, so it drops straight into CI. Example output:

```
== [1/7] Building image cyberrisk:latest ==
  [PASS] docker build -t cyberrisk:latest .
== [2/7] Starting container ==
  [PASS] container started
  [PASS] container healthy
== [3/7] API health check ==
  [PASS] GET /api/health -> {"status":"ok"}
== [4-7] In-container smoke test (agent, engine, RAG, env) ==
  [PASS] container: package importable  — cyberrisk v0.1.0
  [PASS] api: GET /api/health
  [PASS] agent: CyberRiskAgent constructs offline
  [PASS] engine: load_config + simulate + compute_metrics  — EAL=$1.23M  VaR99=$8.45M
  [PASS] rag: embed -> vector store -> similarity  — 2 hit(s), top=chunk-0 score=0.81
  [PASS] env: LLM_PROVIDER set  — LLM_PROVIDER=deepseek
==========================================
Docker validation: 8 passed, 0 failed
==========================================
```

> **CI note:** the bash runner is designed to drop into GitHub Actions — it
> only needs Docker and the repo. Example job: run on `ubuntu-latest`, then
> `bash docker/validate/validate.sh --no-build` after the image is built in
> the same job.

### 2.5 Volumes & the vector index

- **Corpus & manifests** (`knowledge/corpus`, `knowledge/manifests`, read-only)
  — the RAG source content. Bind-mounted so host-side edits are visible
  without an image rebuild.
- **Vector index** (`knowledge/derived`, read-only) — the SQLite
  `vector.db`. Two valid strategies:
  1. **Baked-in (default)** — populate the index before building; the image
     ships a self-contained retrieval store. Requires a rebuild to refresh.
  2. **Host-mounted** — re-run `python -m cyberrisk.knowledge.update` on the
     host and restart the container to pick up new chunks without a rebuild.
  The two compose volume mappings shown above mount it read-only; do **not**
  mount it writable in production.
- **Output** (`data/output`, read-write) — generated Excel reports and charts,
  persisted across restarts.

### 2.6 Secure secret handling

- **`.env` is the single source of secrets.** Compose injects it via
  `env_file`; the app reads it with `python-dotenv` at startup.
- **`.dockerignore`** excludes `.env`, `.env.*`, `.venv/`, `node_modules/`,
  `*.key`, `*.pem`, `knowledge/derived/`, `data/raw|private|client_data/`,
  `reports/`, `web/`, and other artifacts from the build context — so secrets
  and regenerable files never enter an image or an image layer.
- **Never** commit `.env` (gitignored), and never pass keys on the
  `docker build` command line (they would be baked into a layer).
- For production, prefer a secrets manager (see §3.1) that injects the same
  variables at runtime.

### 2.7 Image build checklist

- **Secrets:** never bake keys into the image — always inject via
  `env_file` / environment.
- **Extras:** install `.[web,reporting,knowledge,agent]` so the agent chat
  routes (OpenAI SDK, `python-dotenv`) are present at runtime — not just the
  API extras.
- **Editable installs:** use a plain `pip install .` (wheel), not
  `pip install -e .`, in the image.
- **Volumes:** mount `knowledge/corpus` + `knowledge/derived` (read) and
  `data/output` (write) so knowledge persists and reports are retained.
- **Non-root:** run as an unprivileged user in the runtime stage
  (`USER cyberrisk`).
- **Healthcheck:** `GET /api/health` for liveness (used by orchestration).

---

## 3. Cloud deployment roadmap

The platform is ready to run behind an API today; the following steps harden
it for production at scale. They are ordered by priority.

### 3.1 Minimal production (start here)

- [ ] **Reverse proxy + TLS** — put Nginx / Caddy in front of uvicorn; enable
  HTTPS. Uvicorn itself should not terminate TLS.
- [ ] **Run multiple uvicorn workers** — `--workers 4` (or run under Gunicorn)
  for concurrency.
- [ ] **Session store** — the chat sessions currently live in-process
  (`api/chat.py` `_SESSIONS`). Move to **Redis** so sessions survive restarts
  and scale across workers.
- [ ] **Secret management** — inject `LLM_PROVIDER` + `OPENAI_API_KEY` /
  `DEEPSEEK_API_KEY` via the platform's secret manager (AWS Secrets Manager,
  Vault), never via a committed file.
- [ ] **Structured logging** — the app already sanitises logs
  (`cyberrisk.privacy`); ship them to a central sink (CloudWatch / Loki).

### 3.2 Scale & reliability

- [ ] **Production vector store** — replace the SQLite vector store with
  **pgvector / Qdrant / Chroma** behind the existing `VectorStore` interface
  (already abstracted — see roadmap in the README).
- [ ] **Object storage for reports** — write generated Excel reports to S3 /
  GCS instead of local disk (`data/output`).
- [ ] **Caching** — cache expensive Monte Carlo simulations keyed by the
  profile + seed (identical briefs shouldn't re-run 100k years).
- [ ] **Rate limiting** — add per-key / per-IP limits on `/api/*` (the LLM
  calls are billed).
- [ ] **Autoscaling** — containerised workload with a horizontal-pod
  autoscaler on CPU; Monte Carlo is CPU-bound.

### 3.3 Platform integration

- [x] **API-key auth + rate limiting** — shipped (`CYBERRISK_API_KEY`,
  `CYBERRISK_RATE_LIMIT`); see [api.md §4](api.md).
- [ ] **SSO / multi-key auth** — per-tenant keys or SSO in front of the API
  (client briefs are confidential).
- [ ] **CI/CD** — run `pytest` + the security scanner + the Docker build in
  CI; push tagged images to a registry on release.
- [ ] **DB migration tooling** — once sessions/settings move to Postgres, add
  Alembic migrations.

### 3.4 Reference deployment topologies

**Single box (dev / small team):**

```
Browser → [Nginx :443 → uvicorn :8000]
                      ├── SQLite vector store (knowledge/derived)
                      ├── local data/output (reports)
                      └── in-process sessions
```

**Production (horizontal scale):**

```
Browser → [CDN] → [Nginx LB] → [uvicorn × N]
                                  ├── Redis (sessions, cache)
                                  ├── Postgres + pgvector (knowledge)
                                  └── S3 (reports)
```

---

*Next: [api.md](api.md) for the API surface, or
[knowledge-base.md](knowledge-base.md) for the knowledge layer.*
