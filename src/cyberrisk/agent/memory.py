"""Session memory for the consultant agent.

Two lightweight stores:

    * ConversationMemory -- an ordered, OpenAI/DeepSeek-format message list
      (including `tool` role messages) that the controller feeds back to the
      model every round.  This is what lets the agent refer back to earlier
      turns and to tool results it already received.
    * ClientFacts -- the agent's running `CompanyBrief`, accumulated from
      the conversation so the model does not have to re-ask questions the
      client already answered.

Neither store knows anything about the LLM or the engine; both are plain
data containers, safe to persist as JSON under data/agent_memory/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from cyberrisk.agent.schemas import CompanyBrief


@dataclass
class ConversationMemory:
    """Ordered OpenAI-format message history for the agent loop."""

    messages: list[dict] = field(default_factory=list)

    def append(self, message: dict) -> None:
        self.messages.append(message)

    def extend(self, messages: list[dict]) -> None:
        self.messages.extend(messages)

    def get(self) -> list[dict]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()

    def drop_tool_results(self) -> list[dict]:
        """Remove all `role: tool` messages (used when re-entering a turn)."""
        kept = [m for m in self.messages if m.get("role") != "tool"]
        self.messages = kept
        return kept

    def save(self, path: str | Path) -> None:
        """Persist the conversation as JSON (best-effort).

        Privacy: when ``allow_client_data_storage`` is False (the default,
        see config/privacy.yaml), the persisted payload is scrubbed of
        personal data before it is written.  Secrets are always scrubbed.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _scrub_messages(self.messages)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: str | Path) -> None:
        path = Path(path)
        if path.exists():
            self.messages = json.loads(path.read_text(encoding="utf-8"))


def _scrub_messages(messages: list[dict]) -> list[dict]:
    """Return a copy of ``messages`` with personal data scrubbed.

    Personal data (emails, phones, names, local paths) is removed when the
    privacy policy disallows client-data storage; secrets are always removed.
    """
    try:
        from cyberrisk.privacy import load_privacy_config, sanitise_log

        policy = load_privacy_config()
    except ImportError:  # pragma: no cover - privacy module always present
        return list(messages)

    scrubbed: list[dict] = []
    for m in messages:
        out = dict(m)
        if isinstance(out.get("content"), str):
            content = out["content"]
            if not policy.allow_client_data_storage:
                content = sanitise_log(content)
            else:
                from cyberrisk.privacy import redact_pii

                content = redact_pii(content)
            out["content"] = content
        scrubbed.append(out)
    return scrubbed


@dataclass
class ClientFacts:
    """Accumulated picture of the client across conversation turns."""

    brief: CompanyBrief = field(default_factory=CompanyBrief)

    def update(self, partial: CompanyBrief) -> None:
        """Layer new facts onto the running brief (only provided fields win)."""
        self.brief = self.brief.merge(partial)

    def is_simulation_ready(self) -> bool:
        return not self.brief.missing_for_simulation()
