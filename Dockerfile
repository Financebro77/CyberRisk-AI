# =====================================================================
# CyberRisk AI — multi-stage build
#
# Stage 1 (backend): build the Python package.
# Stage 2 (frontend): build the React SPA.
# Stage 3 (runtime): single image serving API + built UI on :8000.
#
#   docker build -t cyberrisk:latest .
#   docker compose up --build
# =====================================================================

# ---- Stage 1: backend ----
FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# System deps for PDF/DOCX knowledge parsing (poppler-utils) and wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir -e ".[web,reporting,knowledge]"

# ---- Stage 2: frontend ----
FROM node:20-alpine AS frontend
WORKDIR /build
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend ./
RUN npm run build

# ---- Stage 3: runtime ----
FROM backend AS runtime
WORKDIR /app

# Built SPA from the frontend stage.
COPY --from=frontend /build/dist /app/app/frontend/dist

# Knowledge corpus + manifests are mounted as volumes (read-only), reports
# land in data/output (write) — see docker-compose.yml.

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 cyberrisk
USER cyberrisk

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["python", "-m", "uvicorn", "cyberrisk.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
