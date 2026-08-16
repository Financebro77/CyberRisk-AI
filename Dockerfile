# =====================================================================
# CyberRisk AI — multi-stage production image
#
#   Stage 1  backend   : build the Python package (engine + agent + API)
#   Stage 2  frontend  : build the React SPA
#   Stage 3  runtime   : single image serving BOTH the API and the built UI
#
# Build & run:
#   docker build -t cyberrisk:latest .
#   docker compose up --build
#   → http://localhost:8000        (UI + API)
#   → http://localhost:8000/docs   (API docs)
#
# What runs in this container:
#   1. AI agent backend  — the tool-calling consultant (cyberrisk.agent)
#   2. Risk engine       — Monte Carlo simulation + scoring (cyberrisk.*)
#   3. RAG retrieval     — SQLite vector store (knowledge/derived) + HashEmbedder
#   4. Web app           — React SPA served statically by the same process
#   5. Env configuration — read at runtime from the environment / .env
#
# Secrets (API keys) are injected at runtime via env_file / environment
# (see docker-compose.yml).  NEVER baked into the image.
# =====================================================================

# ---- Stage 1: backend -------------------------------------------------
FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # `src/` must be on the path: the runtime imports `agent.safety` from
    # the legacy top-level `src/agent/` package (src/ is also the wheel
    # location for the `cyberrisk` package).
    PYTHONPATH=/app/src

WORKDIR /app

# System deps for PDF/DOCX knowledge parsing and native wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install the package first (caches dependencies across rebuilds).
# `agent` extra carries the OpenAI SDK + python-dotenv used by the API's
# chat routes; `knowledge` the PDF/DOCX parsers; `reporting` the Excel
# writers.  A plain (non-editable) wheel install keeps the image decoupled
# from the source tree.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[web,reporting,knowledge,agent]"

# Runtime configuration: the engine resolves its calibration at
# <repo>/config/ (scenarios.yaml, simulation_config.yaml, scoring_weights.yaml,
# ...).  This is shipped into the image so the engine runs offline and the
# container is self-contained.
COPY config ./config

# RAG vector index: build it from the committed corpus at image build time so
# the runtime image is self-contained (no host volumes, as on a PaaS like
# Render).  Ingest -> embed are the existing offline pipelines; they are
# deterministic and need no API keys.  Derived artifacts (knowledge/derived/*)
# are regenerable and stay excluded from the build context via .dockerignore.
COPY knowledge ./knowledge
RUN python -m cyberrisk.knowledge.pipeline && \
    python -m cyberrisk.knowledge.embed_pipeline

# ---- Stage 2: frontend (React SPA) ------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /build

# package-lock.json is the single source of truth (npm ci is strict); the
# pnpm-lock.yaml in the tree is NOT used — kept out via .dockerignore.
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci

COPY app/frontend ./
RUN npm run build

# ---- Stage 3: runtime (API + built UI) --------------------------------
FROM backend AS runtime

# Built SPA from the frontend stage.
COPY --from=frontend /build/dist /app/app/frontend/dist

# Knowledge corpus + manifests are mounted as volumes (read-only) by
# docker-compose.yml; generated reports land in data/output (write).
# The vector index (knowledge/derived) is baked at build time and may be
# overridden by a read-only volume for live refreshes.

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 cyberrisk \
    && mkdir -p /app/data/output \
    && chown -R cyberrisk:cyberrisk /app/data /app/app/frontend/dist
USER cyberrisk

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

# Serve the API and the built frontend from a single uvicorn process.
CMD ["python", "-m", "uvicorn", "cyberrisk.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
