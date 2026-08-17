"""Chat persistence — the SQLite store and the API surface around it.

The durable half of the chat store (see ``api/chat_store.py``): a session and
its turns survive page reloads AND server restarts, the UI can re-render
charts on resume (per-message ``tool_trace``), and persistence is best-effort
— a store failure must never break a consult.

The LLM client is faked (``FakeClient`` / ``ScriptedClient``) so no network is
touched; the DB lives at a per-test tmp path via the ``_isolate_chat_db``
conftest fixture.
"""

from __future__ import annotations

import pytest

from cyberrisk.api import chat as chat_module
from cyberrisk.api.chat_store import ChatStore, DEFAULT_TITLE
from cyberrisk.llm.base import ChatResponse


class FakeClient:
    """No-network LLM client: every turn returns a canned answer."""

    model_name = "fake-model"

    def __init__(self, content: str = "Persisted answer.") -> None:
        self.content = content

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        return ChatResponse(content=self.content)


class ScriptedClient:
    """Plays back a script of ChatResponses (tool round then answer)."""

    model_name = "scripted-model"

    def __init__(self, script):
        self.script = list(script)

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        if not self.script:
            return ChatResponse(content="done")
        return self.script.pop(0)


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """Every test uses a canned LLM so no provider key/network is needed."""
    monkeypatch.setattr(
        "cyberrisk.agent.agent_controller.create_llm_client",
        lambda config: FakeClient(),
    )


@pytest.fixture(autouse=True)
def _clear_in_memory_sessions():
    """The in-memory session store is module-global; isolate between tests."""
    chat_module._sessions.clear()
    yield
    chat_module._sessions.clear()


@pytest.fixture()
def store() -> ChatStore:
    """The per-test SQLite store (tmp path via the conftest fixture)."""
    return chat_module.get_chat_store()


def _turn(client, session_id: str, message: str):
    return client.post(f"/api/chat/{session_id}/turns", json={"message": message})


# ---------------------------------------------------------------------------
# Persistence writes
# ---------------------------------------------------------------------------


def test_turn_persists_rows_and_auto_titles(client, store):
    sid = client.post("/api/chat/sessions").json()["session_id"]
    r = _turn(client, sid, "Assess our retail business please")
    assert r.status_code == 200

    row = store.get_session(sid)
    assert row is not None
    # Auto-title from the first user message (truncated to the store's limit).
    assert row["title"] == "Assess our retail business please"
    roles = [m["role"] for m in row["history"]]
    assert "user" in roles
    assert "assistant" in roles
    # The system prompt is re-seeded on resume, never stored as a row.
    assert "system" not in roles


def test_session_exists_before_first_turn(client, store):
    sid = client.post("/api/chat/sessions").json()["session_id"]
    row = store.get_session(sid)
    assert row is not None
    assert row["title"] == DEFAULT_TITLE
    assert row["history"] == []


# ---------------------------------------------------------------------------
# Resume across a simulated server restart
# ---------------------------------------------------------------------------


def test_resume_after_restart_continues(client, store):
    sid = client.post("/api/chat/sessions").json()["session_id"]
    assert _turn(client, sid, "First question").status_code == 200

    # Simulated server restart: the in-memory session (agent + lock) is gone.
    chat_module._sessions.clear()

    # The next turn must restore the agent from SQLite and continue.
    r = _turn(client, sid, "Second question")
    assert r.status_code == 200

    row = store.get_session(sid)
    user_msgs = [m["content"] for m in row["history"] if m["role"] == "user"]
    assert user_msgs == ["First question", "Second question"]


def test_history_returns_tool_trace(client, monkeypatch):
    """A tool turn records a trace on the final assistant message so the UI
    can re-render charts after a resume."""
    script = [
        ChatResponse(
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "generate_demo_assessment",
                    "arguments": {"sector": "Retail"},
                }
            ]
        ),
        ChatResponse(content="Here is the demo assessment."),
    ]
    monkeypatch.setattr(
        "cyberrisk.agent.agent_controller.create_llm_client",
        lambda config: ScriptedClient(script),
    )
    sid = client.post("/api/chat/sessions").json()["session_id"]
    assert _turn(client, sid, "Run a demo").status_code == 200

    history = client.get(f"/api/chat/sessions/{sid}/history").json()["history"]
    traces = [m.get("tool_trace") for m in history if m["role"] == "assistant"]
    assert any(t for t in traces), "an assistant message should carry the tool trace"
    trace = next(t for t in traces if t)
    assert trace[0]["name"] == "generate_demo_assessment"


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def test_resume_preserves_tool_calls(client, store, monkeypatch):
    """The LLM tool loop depends on tool_calls/tool_call_id surviving a server
    restart: a resumed session must send them back verbatim (an assistant
    tool-call row without its ``tool_calls`` is malformed for DeepSeek)."""
    script = [
        ChatResponse(
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "generate_demo_assessment",
                    "arguments": {"sector": "Retail"},
                }
            ]
        ),
        ChatResponse(content="Here is the demo assessment."),
    ]
    monkeypatch.setattr(
        "cyberrisk.agent.agent_controller.create_llm_client",
        lambda config: ScriptedClient(script),
    )
    sid = client.post("/api/chat/sessions").json()["session_id"]
    assert _turn(client, sid, "Run a demo").status_code == 200

    # The assistant tool-call row and its tool result are persisted in full.
    stored = store.get_session(sid)
    calls = [m for m in stored["history"] if m.get("tool_calls")]
    tools = [m for m in stored["history"] if m["role"] == "tool" and m.get("tool_call_id")]
    assert calls and calls[0]["tool_calls"][0]["id"] == "call_1"
    assert tools and tools[0]["tool_call_id"] == "call_1"

    # Simulated server restart: resume must rebuild memory from the store with
    # the same tool loop shape the agent originally produced.
    chat_module._sessions.clear()
    agent, _lock = chat_module._get_session(sid)
    rebuilt = agent.memory.get()
    rebuilt_calls = [m for m in rebuilt if m.get("tool_calls")]
    rebuilt_tools = [m for m in rebuilt if m.get("tool_call_id")]
    assert rebuilt_calls and rebuilt_calls[0]["tool_calls"][0]["id"] == "call_1"
    assert rebuilt_tools and rebuilt_tools[0]["tool_call_id"] == "call_1"


def test_rename_session(client, store):
    sid = client.post("/api/chat/sessions").json()["session_id"]
    assert _turn(client, sid, "Hello there").status_code == 200

    r = client.patch(f"/api/chat/sessions/{sid}", json={"title": "Acme engagement"})
    assert r.status_code == 200
    assert store.get_session(sid)["title"] == "Acme engagement"


def test_delete_purges_sqlite(client, store):
    sid = client.post("/api/chat/sessions").json()["session_id"]
    assert _turn(client, sid, "Hello").status_code == 200

    assert client.delete(f"/api/chat/{sid}").status_code == 200
    assert store.get_session(sid) is None
    assert client.get(f"/api/chat/sessions/{sid}/history").status_code == 404


def test_bulk_list_sessions(client, store):
    sid_a = client.post("/api/chat/sessions").json()["session_id"]
    sid_b = client.post("/api/chat/sessions").json()["session_id"]
    assert _turn(client, sid_a, "Hello A").status_code == 200
    assert _turn(client, sid_b, "Hello B").status_code == 200

    r = client.get(f"/api/chat/sessions?ids={sid_a},{sid_b},bogus")
    assert r.status_code == 200
    ids = {s["session_id"] for s in r.json()["sessions"]}
    assert ids == {sid_a, sid_b}


def test_per_session_isolation(client):
    sid_a = client.post("/api/chat/sessions").json()["session_id"]
    sid_b = client.post("/api/chat/sessions").json()["session_id"]
    assert _turn(client, sid_a, "Only in A").status_code == 200
    assert _turn(client, sid_b, "Only in B").status_code == 200

    user_a = [
        m["content"]
        for m in client.get(f"/api/chat/sessions/{sid_a}/history").json()["history"]
        if m["role"] == "user"
    ]
    user_b = [
        m["content"]
        for m in client.get(f"/api/chat/sessions/{sid_b}/history").json()["history"]
        if m["role"] == "user"
    ]
    assert user_a == ["Only in A"]
    assert user_b == ["Only in B"]


# ---------------------------------------------------------------------------
# Non-fatal persistence
# ---------------------------------------------------------------------------


def test_persistence_failure_does_not_break_turn(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(chat_module, "get_chat_store", boom)

    # create_session's write-through fails too — still 200 with an id.
    sid = client.post("/api/chat/sessions").json()["session_id"]
    r = _turn(client, sid, "Hello")
    assert r.status_code == 200
    assert r.json()["content"]
