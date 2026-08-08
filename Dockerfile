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
# Secrets: injected at runtime via env_file / environment (see
# docker-compose.yml).  NEVER baked into the image.
# =====================================================================

# ---- Stage 1: backend -------------------------------------------------
FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for PDF/DOCX knowledge parsing and native wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install the package first (caches dependencies across rebuilds).
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[web,reporting,knowledge]"

# ---- Stage 2: frontend (React SPA) ------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /build

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
