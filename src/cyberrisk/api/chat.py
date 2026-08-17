"""Stateful chat-session routes for the Armageddon consultant agent.

The frontend holds a session id; the backend owns the ``CyberRiskAgent``
(and its ``ConversationMemory`` / ``ClientFacts``) so the client does not
need to resend history every turn.

Every quantitative figure the model reports comes from a tool call the agent
actually executed -- the controller records a ``tool_trace`` per turn and the
UI renders charts ONLY from those tool results.  Nothing here invents numbers.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.agent.memory import ClientFacts, ConversationMemory
from cyberrisk.agent.schemas import CompanyBrief
from cyberrisk.api.chat_store import ChatStore
from cyberrisk.api.store import BoundedStore

logger = logging.getLogger("cyberrisk.api.chat")

router = APIRouter(prefix="/chat", tags=["chat"])

# ---------------------------------------------------------------------------
# In-process session store (single-process uvicorn dev server).
# A production deployment would back this with Redis / Postgres.
# ---------------------------------------------------------------------------

# One lock per session: a session's agent is stateful (memory, tool_trace,
# facts) and chat_turn is a sync route, so concurrent turns on the same
# session must be serialized or the tool loop interleaves (the base system
# message and per-turn RAG message are insert(0)/pop(0) in the same list).
# The lock travels WITH the agent inside the bounded-store value, so eviction
# and deletion always drop both together.
_MAX_SESSIONS = 32

_sessions: BoundedStore[str, tuple[CyberRiskAgent, threading.Lock]] = BoundedStore(
    max_entries=_MAX_SESSIONS,
)

# ---------------------------------------------------------------------------
# SQLite persistence (data/chat.db) — the durable half of the chat store.
# See chat_store.py for schema + rationale.  Vercel's filesystem is ephemeral,
# so on that deploy persistence is local-session only.
# ---------------------------------------------------------------------------


def _chat_db_path() -> Path:
    """Where the chat DB lives (CYBERRISK_CHAT_DB overrides for tests)."""
    override = os.getenv("CYBERRISK_CHAT_DB")
    if override:
        return Path(override)
    # src/cyberrisk/api/chat.py -> src/cyberrisk -> src -> repo root.
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "chat.db"


_chat_store: ChatStore | None = None
_chat_store_unavailable = False


def get_chat_store() -> ChatStore:
    """The process-wide chat store (created lazily on first use).

    Raises RuntimeError when the store cannot be constructed (e.g. Vercel's
    read-only filesystem).  The failure is cached so a broken deploy does not
    retry-and-log on every request; callers treat persistence as best-effort.
    """
    global _chat_store, _chat_store_unavailable
    if _chat_store_unavailable:
        raise RuntimeError("chat store unavailable (read-only filesystem)")
    if _chat_store is None:
        try:
            _chat_store = ChatStore(_chat_db_path())
        except Exception:  # noqa: BLE001 - a broken deploy must not 500 writes
            _chat_store_unavailable = True
            logger.exception("chat store unavailable (read-only filesystem?)")
            raise
    return _chat_store


def _chat_store_or_none() -> ChatStore | None:
    """Best-effort handle to the durable store, or None when unavailable.

    Read routes use this so a read-only deploy degrades to empty/not-found
    instead of 500ing (the durable store is best-effort by design).
    """
    try:
        return get_chat_store()
    except Exception:  # noqa: BLE001 - persistence is best-effort
        return None


def _get_session(session_id: str) -> tuple[CyberRiskAgent, threading.Lock]:
    """The agent and its per-session lock (raises 404 when absent).

    Falls back to the durable store: after a server restart (or an eviction
    past the in-memory cap) the agent is rebuilt from SQLite so an open
    conversation just keeps going.
    """
    session = _sessions.get(session_id)
    if session is None:
        session = _restore_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    return session


def _build_agent(
    *,
    memory: ConversationMemory | None = None,
    facts: ClientFacts | None = None,
) -> CyberRiskAgent:
    """Build an agent, mapping a misconfigured engine to a 503 (the LLM
    provider is lazy, so configuration errors surface at construction time)."""
    try:
        return CyberRiskAgent(memory=memory, facts=facts)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"The consultant engine is not configured: {exc}",
        ) from exc


def _create_agent() -> CyberRiskAgent:
    return _build_agent()


def _restore_session(session_id: str) -> tuple[CyberRiskAgent, threading.Lock] | None:
    """Rebuild an in-memory session from SQLite (None when unknown).

    The persisted memory excludes the system message (the agent re-seeds it
    idempotently in ``_init_system``) but keeps every ``tool`` / tool-call
    row — including ``tool_calls`` / ``tool_call_id`` — so the LLM can
    continue the tool loop coherently.  ``tool_trace`` is per-turn UI data,
    refreshed on the next turn — not needed for the loop.
    """
    try:
        row = get_chat_store().get_session(session_id)
    except Exception:  # noqa: BLE001 - persistence must never break a consult
        logger.exception("chat store read failed for session %s", session_id)
        return None
    if row is None:
        return None
    messages = [
        {
            "role": m["role"],
            "content": m["content"],
            **({"tool_calls": m["tool_calls"]} if m.get("tool_calls") else {}),
            **({"tool_call_id": m["tool_call_id"]} if m.get("tool_call_id") else {}),
        }
        for m in row["history"]
    ]
    try:
        brief = (
            CompanyBrief.model_validate_json(row["brief_json"])
            if row.get("brief_json")
            else CompanyBrief()
        )
    except Exception:  # noqa: BLE001 - a corrupt brief should not kill resume
        brief = CompanyBrief()
    agent = _build_agent(
        memory=ConversationMemory(messages=messages),
        facts=ClientFacts(brief=brief),
    )
    lock = threading.Lock()
    _sessions.put(session_id, (agent, lock))
    return agent, lock


def _persist_turn(
    agent: CyberRiskAgent,
    session_id: str,
    *,
    turn_trace: list[dict[str, Any]],
) -> None:
    """Write the turn to SQLite — best-effort, never fatal to a consult.

    The client brief is persisted only when the privacy policy allows
    client-data storage (config/privacy.yaml; the default disallows it), so
    the durable rows hold conversation text but not the assembled brief.
    """
    try:
        from cyberrisk.privacy import load_privacy_config

        brief = (
            agent.facts.brief.model_dump(mode="json")
            if load_privacy_config().allow_client_data_storage
            else None
        )
        get_chat_store().save_turn(
            session_id,
            agent.memory.get(),
            brief,
            turn_trace=turn_trace,
        )
    except Exception:  # noqa: BLE001 - persistence is additive, not required
        logger.exception("chat persistence failed for session %s", session_id)


def _session_payload(row: dict[str, Any]) -> dict[str, Any]:
    """A persisted session in the API shape: UI-safe history + per-message
    tool traces (so the frontend can re-render charts on resume)."""
    return {
        "session_id": row["session_id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "history": [
            {"role": m["role"], "content": m["content"], "tool_trace": m["tool_trace"]}
            for m in row["history"]
            if m["role"] != "tool" and m.get("content")
        ],
    }


# ---------------------------------------------------------------------------
# Request / response bodies
# ---------------------------------------------------------------------------


class ChatTurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)
    welcome: bool = False


class ChatTurnResponse(BaseModel):
    session_id: str
    role: str = "assistant"
    content: str
    # The tool-call trace for THIS turn: charts render from these results.
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    safety: dict[str, Any] | None = None
    model: str = ""
    # Privacy notice from the input guard, surfaced to the UI when the
    # user's message was redacted or blocked (e.g. contained personal data).
    privacy_notice: str = ""


def _history(agent: CyberRiskAgent) -> list[dict[str, Any]]:
    """Public, UI-safe history: system + user + assistant (tool msgs excluded)."""
    out: list[dict[str, Any]] = []
    for m in agent.memory.get():
        role = m.get("role")
        if role == "tool":
            continue
        content = m.get("content")
        if role == "system" or not content:
            continue
        out.append({"role": role, "content": content})
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/sessions")
def create_session() -> dict[str, str]:
    """Create a new consultant session and return its id."""
    session_id = uuid.uuid4().hex
    agent = _create_agent()
    # The bounded store evicts the oldest session when at the cap; the lock
    # rides in the same value so a session and its lock are always together.
    _sessions.put(session_id, (agent, threading.Lock()))
    # Write-through so the session exists server-side before the first turn.
    try:
        get_chat_store().create_session(session_id)
    except Exception:  # noqa: BLE001 - persistence is additive, not required
        logger.exception("chat session write-through failed for %s", session_id)
    return {"session_id": session_id}


@router.post("/{session_id}/turns")
def chat_turn(session_id: str, req: ChatTurnRequest) -> ChatTurnResponse:
    """Send a user message; run the agent's tool loop; return the answer.

    Serialized per session (the lock returned by ``_get_session``): the
    agent's memory and tool_trace are shared state, so overlapping turns would
    interleave.
    """
    agent, session_lock = _get_session(session_id)
    with session_lock:
        safety: dict[str, Any] | None = None

        # Run the mandatory pre-guards (confidentiality first, then
        # statistics, unsupported recommendations, ambiguity).  Intercepted
        # requests never reach the model -- they get a safe, deterministic
        # response.
        try:
            from agent.safety import guard_request
        except ImportError:  # pragma: no cover - src/agent is installed
            guard_request = None

        if guard_request is not None:
            verdict = guard_request(req.message)
            if verdict is not None and verdict.flagged:
                safety = {"class_name": verdict.class_name, "response": verdict.response}
                answer = verdict.response
                # Still record the assistant turn so history stays coherent.
                agent.memory.append({"role": "user", "content": req.message})
                agent.memory.append({"role": "assistant", "content": answer})
                # No tool ran this turn; never reuse a stale trace from a
                # previous turn.
                _persist_turn(agent, session_id, turn_trace=[])
                return ChatTurnResponse(
                    session_id=session_id,
                    content=answer,
                    tool_trace=[],
                    history=_history(agent),
                    safety=safety,
                    model=agent.client.model_name,
                    privacy_notice=agent.last_privacy_notice,
                )

        try:
            answer = agent.chat(req.message, welcome=req.welcome)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=f"Consultant engine error: {exc}") from exc

        _persist_turn(agent, session_id, turn_trace=agent.tool_trace)

        return ChatTurnResponse(
            session_id=session_id,
            content=answer,
            tool_trace=agent.tool_trace,
            history=_history(agent),
            safety=None,
            model=agent.client.model_name,
            privacy_notice=agent.last_privacy_notice,
        )


@router.delete("/{session_id}")
def delete_session(session_id: str) -> dict[str, str]:
    """End a session, free its memory, and purge its SQLite rows."""
    _sessions.pop(session_id)
    try:
        get_chat_store().delete_session(session_id)
    except Exception:  # noqa: BLE001 - a failed purge must not surface a 500
        logger.exception("chat delete failed for session %s", session_id)
    return {"status": "ok"}


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, req: RenameSessionRequest) -> dict[str, str]:
    """Rename a session's sidebar title."""
    store = _chat_store_or_none()
    if store is not None and not store.rename_session(session_id, req.title):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


def _hydrate_best_effort(session_id: str) -> None:
    """Rebuild the in-memory agent from SQLite if it was evicted/restarted.

    History always comes from the durable store, so a dead engine must not
    block a read — the persisted conversation still answers.
    """
    try:
        _get_session(session_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise
        # Engine unavailable (503): the durable history below still answers.


@router.get("/sessions")
def list_sessions(ids: str) -> dict[str, Any]:
    """Bulk-fetch persisted sessions by comma-separated id (sidebar list).

    The frontend owns its session-id list (localStorage) and passes it here;
    unknown ids are dropped so the client can prune stale entries.
    """
    parsed = [sid for sid in ids.split(",") if sid.strip()]
    store = _chat_store_or_none()
    if store is None:
        return {"sessions": []}
    return {"sessions": [_session_payload(r) for r in store.get_sessions(parsed)]}


@router.get("/sessions/{session_id}")
@router.get("/sessions/{session_id}/history")
def get_session(session_id: str) -> dict[str, Any]:
    """The persisted conversation (history + metadata) for resume / a sidebar row.

    ``/history`` is kept as an alias (the test-suite and earlier clients use
    it); both paths hydrate the in-memory agent so the next turn continues
    correctly across reloads and restarts.
    """
    _hydrate_best_effort(session_id)
    store = _chat_store_or_none()
    if store is None:
        raise HTTPException(status_code=404, detail="Session not found")
    row = store.get_session(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_payload(row)
