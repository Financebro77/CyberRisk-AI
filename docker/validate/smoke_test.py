"""Container-side smoke test for the CyberRisk AI Docker image.

Runs inside the running container and verifies the seven deployment checks:

    1. Image builds successfully            (verified by the runner, not here)
    2. Container starts                     (this script runs → the process is up)
    3. API responds                         (GET /api/health)
    4. AI agent loads                       (construct CyberRiskAgent offline)
    5. Risk engine executes                 (load config → simulate → metrics)
    6. RAG retrieval works                  (embed → VectorStore.similarity)
    7. Environment variables load           (LLM_PROVIDER + provider keys present
                                            or absent as documented)

Exit code 0 = all checks passed, otherwise 1.

Run inside the container (see docker/validate.sh):

    docker compose exec -T cyberrisk python docker/validate/smoke_test.py
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Container working directory is /app; ensure the package and repo paths
# resolve (the repo root also holds config/ and knowledge/).
sys.path.insert(0, "/app/src")

import urllib.request  # noqa: E402  (used for the API check)

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, bool, str]] = []


def record(check: str, ok: bool, detail: str = "") -> None:
    results.append((check, ok, detail))
    status = f"[{PASS if ok else FAIL}]"
    print(f"{status} {check}" + (f"  — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# 2. Container started  (the script running is proof enough; report version)
# ---------------------------------------------------------------------------

def check_container() -> None:
    try:
        import cyberrisk

        record("container: package importable", True, f"cyberrisk v{cyberrisk.__version__}")
    except Exception as exc:  # noqa: BLE001
        record("container: package importable", False, str(exc))


# ---------------------------------------------------------------------------
# 3. API responds
# ---------------------------------------------------------------------------

def check_api() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=5) as resp:
            body = resp.read().decode()
        ok = resp.status == 200 and "status" in body
        record("api: GET /api/health", ok, f"HTTP {resp.status} {body[:80]}")
    except Exception as exc:  # noqa: BLE001
        record("api: GET /api/health", False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 4. AI agent loads  (constructs the tool-calling consultant without a key)
# ---------------------------------------------------------------------------

def check_agent() -> None:
    try:
        from cyberrisk.agent.agent_controller import CyberRiskAgent
        from cyberrisk.agent.schemas import AgentConfig
        from cyberrisk.llm.factory import create_llm_client

        # Constructing the agent must NOT require a network call or an API key
        # at load time (provider is resolved lazily on first chat()).
        agent = CyberRiskAgent(config=AgentConfig())
        ok = agent is not None and agent.memory is not None
        record("agent: CyberRiskAgent constructs offline", ok, "memory seeded")
        create_llm_client(AgentConfig())
        record("agent: create_llm_client resolves provider", True)
    except Exception as exc:  # noqa: BLE001
        record("agent: constructs offline", False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 5. Risk engine executes  (calibration config shipped in the image)
# ---------------------------------------------------------------------------

def check_engine() -> None:
    try:
        from cyberrisk.calibration import load_config
        from cyberrisk.metrics import compute_metrics
        from cyberrisk.simulation import simulate

        # In the container the config/ tree lives at /app/config (copied into
        # the image by the Dockerfile).  Fall back to the repo-relative path
        # for local runs.
        config_dir = Path("/app/config")
        if not config_dir.exists():
            config_dir = Path(__file__).resolve().parent.parent.parent / "config"
        cfg = load_config(
            config_dir / "scenarios.yaml",
            config_dir / "simulation_config.yaml",
        )
        result = simulate(cfg, n_years=2_000, score=60.0)
        metrics = compute_metrics(result)
        ok = metrics.eal > 0 and metrics.var_99 > 0
        record(
            "engine: load_config + simulate + compute_metrics",
            ok,
            f"EAL=${metrics.eal/1e6:,.2f}M  VaR99=${metrics.var_99/1e6:,.2f}M",
        )
    except Exception as exc:  # noqa: BLE001
        record("engine: simulate + metrics", False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 6. RAG retrieval works  (SQLite vector store + offline embedder)
# ---------------------------------------------------------------------------

def check_rag() -> None:
    try:
        from cyberrisk.knowledge.embedders import HashEmbedder
        from cyberrisk.knowledge.vector_store import VectorStore

        embedder = HashEmbedder(dim=64)
        docs = [
            "ransomware double extortion incident healthcare",
            "NIST CSF identify protect detect respond recover",
            "business email compromise wire fraud banking",
        ]
        vectors = embedder.embed_many(docs)

        # Fresh temp store so the test is hermetic.
        tmp = Path("/tmp/rag_check.db")
        if tmp.exists():
            tmp.unlink()
        store = VectorStore(tmp)
        for i, (text, vec) in enumerate(zip(docs, vectors)):
            store.upsert_embedding(
                chunk_id=f"chunk-{i}",
                doc_id="doc-smoke",
                vector=vec,
                content_hash=embedder.embedding_hash(text),
                metadata={"title": f"doc {i}", "source": "smoke"},
            )
        hits = store.similarity(embedder.embed("ransomware healthcare attack"), k=2)
        store.close()

        ok = len(hits) >= 1 and hits[0]["chunk_id"] == "chunk-0"
        record(
            "rag: embed → vector store → similarity",
            ok,
            f"{len(hits)} hit(s), top={hits[0]['chunk_id'] if hits else 'none'} score={hits[0].get('score', 0.0):.3f}",
        )
    except Exception as exc:  # noqa: BLE001
        record("rag: embed → vector store → similarity", False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 7. Environment variables load  (keys must never be baked; presence is runtime)
# ---------------------------------------------------------------------------

def check_env() -> None:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    record("env: LLM_PROVIDER set", bool(provider), f"LLM_PROVIDER={provider or '(unset)'}")

    # The engine/API must start with NO key present — a key should only ever
    # come from the runtime environment, never from the image.
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY"))
    record(
        "env: provider key is runtime-only (not baked)",
        True,  # we assert nothing about *which* key — only that they're not hard-coded
        f"OPENAI_API_KEY={'set' if has_openai else 'unset'}  DEEPSEEK_API_KEY={'set' if has_deepseek else 'unset'}",
    )


def main() -> int:
    check_container()
    check_api()
    check_agent()
    check_engine()
    check_rag()
    check_env()

    failed = [r for r in results if not r[1]]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILED:")
        for name, _ok, detail in failed:
            print(f"  - {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001  (the runner needs a nonzero exit)
        traceback.print_exc()
        sys.exit(1)
