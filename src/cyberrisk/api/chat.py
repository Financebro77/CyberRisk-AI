"""Stateful chat-session routes for the CyberRisk consultant agent.

The frontend holds a session id; the backend owns the ``CyberRiskAgent``
(and its ``ConversationMemory`` / ``ClientFacts``) so the client does not
need to resend history every turn.

Every quantitative figure the model reports comes from a tool call the agent
actually executed -- the controller records a ``tool_trace`` per turn and the
UI renders charts ONLY from those tool results.  Nothing here invents numbers.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.api.store import BoundedStore

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


def _get_session(session_id: str) -> tuple[CyberRiskAgent, threading.Lock]:
    """The agent and its per-session lock (raises 404 when absent)."""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _create_agent() -> CyberRiskAgent:
    try:
        return CyberRiskAgent()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"The consultant engine is not configured: {exc}",
        ) from exc


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
    """End a session and free its memory."""
    _sessions.pop(session_id)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/history")
def session_history(session_id: str) -> dict[str, Any]:
    """Return the UI-safe conversation history for a session."""
    agent, session_lock = _get_session(session_id)
    with session_lock:
        return {"session_id": session_id, "history": _history(agent)}
