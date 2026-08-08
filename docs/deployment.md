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

The repo ships a multi-stage `Dockerfile` and a `docker-compose.yml` that
containerise the FastAPI app and serve the pre-built frontend from a single
image.

### 2.1 The shipped `Dockerfile`

Three stages:

- **backend** — `python:3.12-slim` with the system deps for knowledge
  parsing (`poppler-utils`), installs the package with
  `.[web,reporting,knowledge]`.
- **frontend** — `node:20-alpine` builds the React SPA (`app/frontend`).
- **runtime** — the backend image plus the built SPA; runs as an
  unprivileged user and health-checks `/api/health`.

```dockerfile
# ---- backend: build the Python package ----
FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential poppler-utils && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir -e ".[web,reporting,knowledge]"

# ---- frontend: build the React app ----
FROM node:20-alpine AS frontend
WORKDIR /build
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend ./
RUN npm run build

# ---- runtime: single image serving API + built UI ----
FROM backend AS runtime
COPY --from=frontend /build/dist /app/app/frontend/dist
EXPOSE 8000
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
    ports:
      - "8000:8000"
    env_file:
      - .env                      # LLM_PROVIDER + OPENAI_API_KEY / DEEPSEEK_API_KEY
    volumes:
      # Knowledge corpus + manifests (read-only) so ingested content persists.
      - ./knowledge/corpus:/app/knowledge/corpus:ro
      - ./knowledge/manifests:/app/knowledge/manifests:ro
      # Generated reports (write).
      - ./data/output:/app/data/output
    restart: unless-stopped
```

### 2.3 Run

```bash
docker compose up --build
# → http://localhost:8000
```

### 2.4 Image build checklist

- **Secrets:** never bake keys into the image — always inject via
  `env_file` / environment.
- **Volumes:** mount `knowledge/corpus` (read) and `data/output` (write) so
  knowledge persists and reports are retained.
- **Non-root:** run as an unprivileged user in the runtime stage
  (`USER 10001`).
- **Healthcheck:** hit `GET /api/health` for liveness.

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

- [ ] **AuthN/AuthZ** — add SSO / API-key auth in front of the API (the
  engine itself is stateless and safe to expose, but client briefs are
  confidential).
- [ ] **CI/CD** — run `pytest` + the security scanner + frontend build in CI;
  push tagged images to a registry on release.
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
