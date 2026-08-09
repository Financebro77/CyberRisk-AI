#!/usr/bin/env bash
# =====================================================================
# CyberRisk AI — Docker deployment validation
#
# Verifies (from the repo root):
#   1. The Docker image builds successfully.
#   2. The container starts and stays healthy.
#   3. The API responds (GET /api/health).
#   4. The AI agent loads.
#   5. The risk engine executes.
#   6. RAG retrieval works.
#   7. Environment variables are injected at runtime (and no key is baked).
#
# Usage:
#   bash docker/validate/validate.sh [--no-build]
#
#   --no-build   reuse an existing cyberrisk:latest image instead of rebuilding
#
# Exit code 0 = all checks passed; nonzero otherwise.
#
# Windows PowerShell users: run docker/validate/validate.ps1 instead.
# =====================================================================

set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Docker on Windows (Docker Desktop via Git Bash) requires Windows paths for
# bind mounts, not MSYS /c/... paths.  Convert when present.
if command -v cygpath >/dev/null 2>&1; then
    REPO_ROOT="$(cygpath -w "$REPO_ROOT")"
fi

IMAGE="cyberrisk:latest"
CTN="cyberrisk-validate"
NET="cyberrisk-validate-net"
NO_BUILD="${1:-}"
CONTAINER_SMOKE="python docker/validate/smoke_test.py"

PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); printf '  \033[32m[PASS]\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '  \033[31m[FAIL]\033[0m %s\n' "$1"; }

cleanup() {
    docker rm -f "$CTN" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

# ----------------------------------------------------------------------
# 1. Image builds
# ----------------------------------------------------------------------
echo "== [1/7] Building image ${IMAGE} =="
if [ "$NO_BUILD" = "--no-build" ] && docker image inspect "$IMAGE" >/dev/null 2>&1; then
    pass "image already exists (--no-build)"
else
    if docker build -t "$IMAGE" . >/tmp/cyberrisk-build.log 2>&1; then
        pass "docker build -t ${IMAGE} ."
    else
        fail "docker build failed — see /tmp/cyberrisk-build.log"
        tail -30 /tmp/cyberrisk-build.log
        exit 1
    fi
fi

# ----------------------------------------------------------------------
# 2. Container starts (and stays up)
# ----------------------------------------------------------------------
echo
echo "== [2/7] Starting container =="
docker network create "$NET" >/dev/null 2>&1
if docker run -d --rm \
    --name "$CTN" \
    --network "$NET" \
    -p 18000:8000 \
    -v "${REPO_ROOT}/knowledge/corpus:/app/knowledge/corpus:ro" \
    -v "${REPO_ROOT}/knowledge/manifests:/app/knowledge/manifests:ro" \
    -v "${REPO_ROOT}/data/output:/app/data/output" \
    "$IMAGE" >/tmp/cyberrisk-run.log 2>&1; then
    pass "container started"
else
    fail "container failed to start — see /tmp/cyberrisk-run.log"
    cat /tmp/cyberrisk-run.log
    exit 1
fi

# Wait for the healthcheck to become healthy (up to 120s).
healthy=0
for _ in $(seq 1 60); do
    state="$(docker inspect -f '{{.State.Health.Status}}' "$CTN" 2>/dev/null || echo starting)"
    if [ "$state" = "healthy" ]; then healthy=1; break; fi
    if [ "$state" = "unhealthy" ]; then break; fi
    sleep 2
done
if [ "$healthy" = "1" ]; then
    pass "container healthy"
else
    fail "container not healthy (last state: ${state:-unknown})"
    docker logs "$CTN" 2>&1 | tail -30
    exit 1
fi

# ----------------------------------------------------------------------
# 3. API responds
# ----------------------------------------------------------------------
echo
echo "== [3/7] API health check =="
# Published host port for the container's 8000.  `docker port` may emit
# `0.0.0.0:18000`, `127.0.0.1:18000`, or `::1:18000`; normalise to a
# curl-usable host:port on the loopback.
API_HOST="$(docker port "$CTN" 18000 2>/dev/null | head -1 | sed -E 's/^.*:([0-9]+)$/127.0.0.1:\1/')"
[ -n "$API_HOST" ] || API_HOST="127.0.0.1:18000"
api_ok=0
for _ in $(seq 1 20); do
    body="$(curl -fsS "http://${API_HOST}/api/health" 2>/dev/null)" && { api_ok=1; break; }
    sleep 1
done
if [ "$api_ok" = "1" ]; then
    pass "GET /api/health → ${body}"
else
    fail "API did not respond at http://${API_HOST}/api/health"
    docker logs "$CTN" 2>&1 | tail -20
    exit 1
fi

# ----------------------------------------------------------------------
# 4–7. Agent / engine / RAG / env — in-container smoke test
# ----------------------------------------------------------------------
echo
echo "== [4–7] In-container smoke test (agent, engine, RAG, env) =="
SMOKE_DIR="${REPO_ROOT}/docker/validate"
if docker run --rm \
    --name "${CTN}-smoke" \
    --network "$NET" \
    -v "${REPO_ROOT}/config:/app/config:ro" \
    -v "${REPO_ROOT}/knowledge/corpus:/app/knowledge/corpus:ro" \
    -v "${REPO_ROOT}/knowledge/manifests:/app/knowledge/manifests:ro" \
    -v "${REPO_ROOT}/data/output:/app/data/output" \
    -v "${SMOKE_DIR}/smoke_test.py:/app/smoke_test.py:ro" \
    -e "LLM_PROVIDER=deepseek" \
    "$IMAGE" \
    python /app/smoke_test.py; then
    pass "in-container smoke test passed"
else
    fail "in-container smoke test failed"
    exit 1
fi

# ----------------------------------------------------------------------
# Env vars load from .env (runtime injection), if present.
# ----------------------------------------------------------------------
if [ -f "${REPO_ROOT}/.env" ]; then
    echo
    echo "== [env] .env present — verifying runtime injection =="
    if docker run --rm \
        --name "${CTN}-env" \
        -v "${SMOKE_DIR}/smoke_test.py:/app/smoke_test.py:ro" \
        --env-file "${REPO_ROOT}/.env" \
        "$IMAGE" \
        python /app/smoke_test.py >/tmp/cyberrisk-env.log 2>&1; then
        pass "env vars injected via --env-file (see /tmp/cyberrisk-env.log)"
    else
        fail "env-file run failed — see /tmp/cyberrisk-env.log"
        tail -20 /tmp/cyberrisk-env.log
        exit 1
    fi
else
    echo
    echo "== [env] .env absent — skipping .env injection check (engine still offline) =="
fi

# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------
echo
echo "=========================================="
echo "Docker validation: ${PASS} passed, ${FAIL} failed"
echo "=========================================="
[ "$FAIL" -eq 0 ]
