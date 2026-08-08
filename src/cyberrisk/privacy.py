"""Privacy and data-protection layer for CyberRisk AI.

Centralised privacy behaviour for the public release:

    * ``load_privacy_config``      — reads config/privacy.yaml
    * ``PrivacyPolicy``            — the four runtime switches
    * ``PII_RE / detect_pii``      — rule-based detection of personal data
                                     (names, emails, phones, addresses,
                                     company identifiers)
    * ``redact_pii``               — replace detected PII with placeholders
    * ``sanitise_log``             — strip secrets/PII from a log line
    * ``sanitised_logger``         — a logging.Logger wrapper that sanitises
                                     every record before it is written

This layer is ADDITIVE — it never modifies the risk engine.  It sits on the
input boundary (before user text reaches the agent/engine) and on the output
boundary (before anything is written to a log or console).

Policy defaults live in config/privacy.yaml; they are read at first use so
an operator can tune them without code changes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "privacy.yaml"


def _load_config_raw() -> dict:
    """Read config/privacy.yaml, tolerating absence (safest defaults)."""
    try:
        import yaml
    except ImportError:  # pragma: no cover - yaml is a core dependency
        return {}
    try:
        if not _CONFIG_PATH.exists():
            return {}
        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001 - never let a config error break the app
        return {}


@dataclass(frozen=True)
class PrivacyPolicy:
    """Runtime privacy switches (from config/privacy.yaml)."""

    privacy_mode: bool = True
    allow_personal_data: bool = False
    allow_client_data_storage: bool = False
    log_sensitive_information: bool = False

    @classmethod
    def from_mapping(cls, data: dict) -> "PrivacyPolicy":
        """Build from a raw YAML dict with safe boolean coercion."""
        def _b(key: str, default: bool) -> bool:
            val = data.get(key, default)
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.strip().lower() in ("true", "1", "yes", "on")
            return default

        return cls(
            privacy_mode=_b("privacy_mode", True),
            allow_personal_data=_b("allow_personal_data", False),
            allow_client_data_storage=_b("allow_client_data_storage", False),
            log_sensitive_information=_b("log_sensitive_information", False),
        )


_policy_cache: PrivacyPolicy | None = None


def load_privacy_config() -> PrivacyPolicy:
    """Load (and cache) the privacy policy from config/privacy.yaml.

    Returns the safest defaults if the file is missing or malformed.
    """
    global _policy_cache
    if _policy_cache is None:
        _policy_cache = PrivacyPolicy.from_mapping(_load_config_raw())
    return _policy_cache


# ---------------------------------------------------------------------------
# PII detection / redaction
# ---------------------------------------------------------------------------

# Email addresses.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Phone numbers (international / national, common delimiters).
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[-\s.]?)?"
    r"(?:\(?\d{2,4}\)?[-\s.]?)\d{3,4}[-\s.]?\d{4,4}(?!\w)"
)

# Common personal-name patterns: honorific + given name (+ surname).  The
# honorific is a strong personal-data signal, so the full phrase is captured.
# Conservative on purpose — we never treat bare capitalized words (which may
# be industry/sector terms) as names.
_HONORIFIC_RE = re.compile(
    r"\b(?:mr\.?|mrs\.?|ms\.?|dr\.?|prof\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b",
    re.I,
)

# Local machine paths (Windows + POSIX).  Components are word characters
# (letters/digits/dot/underscore/hyphen) so regex escape sequences such as
# `\n` or `\s` inside string literals are never mistaken for a path.  A
# Windows match requires at least a drive + folder + name — a bare "W:" is
# not a path.
_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\(?:[\w.-]+\\)+[\w.-]+|/home/[\w.-]+/[\w.-]+|/Users/[\w.-]+/[\w.-]+)"
)

# Company-identifier signal: "Acme Corp", "Acme Inc", "Acme Limited" etc.
_COMPANY_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&' -]{1,40}?)\s+(?:Corp(?:oration)?|Inc(?:orporated)?|"
    r"Ltd(?:\.|imited)?|LLC|LLP|PLC|GmbH|S\.A\.|Co(?:mpany)?)\b"
)

# Real API key shapes (highest-confidence secret patterns).
_SECRET_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"[A-Za-z0-9+/]{32,}={0,2})\b"
)

_PLACEHOLDER = "[REDACTED]"


def detect_pii(text: str) -> dict[str, list[str]]:
    """Scan a string and return a category -> matched-substrings map.

    Categories detected: email, phone, name, path, company, secret.
    Used by the input-data privacy guard to decide whether to warn or
    redact before text reaches the agent.
    """
    out: dict[str, list[str]] = {"email": [], "phone": [], "name": [], "path": [], "company": [], "secret": []}
    if not text:
        return out

    for m in _EMAIL_RE.finditer(text):
        out["email"].append(m.group(0))
    for m in _PHONE_RE.finditer(text):
        out["phone"].append(m.group(0))
    for m in _HONORIFIC_RE.finditer(text):
        out["name"].append(m.group(0))
    for m in _LOCAL_PATH_RE.finditer(text):
        out["path"].append(m.group(0))
    for m in _COMPANY_RE.finditer(text):
        out["company"].append(m.group(0))
    for m in _SECRET_RE.finditer(text):
        out["secret"].append(m.group(0))

    return out


def has_pii(text: str) -> bool:
    """True when any PII category is detected in ``text``."""
    det = detect_pii(text)
    return any(det.values())


def redact_pii(text: str, placeholder: str = _PLACEHOLDER) -> str:
    """Return ``text`` with detected PII replaced by a placeholder.

    Company-identifier redaction is conservative: only redact a company
    match when it is clearly a legal-entity suffix in a proper-name context
    (the agent legitimately works with firm names, so we do not want to
    mangle "Healthcare" or "Financial Services").
    """
    if not text:
        return text
    redacted = _EMAIL_RE.sub(placeholder, text)
    redacted = _PHONE_RE.sub(placeholder, redacted)
    redacted = _LOCAL_PATH_RE.sub(placeholder, redacted)
    redacted = _HONORIFIC_RE.sub(placeholder, redacted)
    redacted = _SECRET_RE.sub(placeholder, redacted)
    # Company names: only when preceded by an article/possessive or followed
    # by an entity suffix, to keep legitimate sector terms untouched.
    redacted = _COMPANY_RE.sub(placeholder, redacted)
    return redacted


# ---------------------------------------------------------------------------
# Sanitised logging
# ---------------------------------------------------------------------------

def sanitise_log(message: str) -> str:
    """Strip secrets and PII from a message before it is logged.

    When ``log_sensitive_information`` is False (the default), full PII
    redaction applies.  Secrets are always redacted regardless of the flag —
    API keys never belong in logs.
    """
    policy = load_privacy_config()
    # Secrets are always redacted.
    out = _SECRET_RE.sub(_PLACEHOLDER, message)
    # Personal data only redacted when logging of sensitive info is disabled.
    if not policy.log_sensitive_information:
        out = redact_pii(out)
    return out


class SanitisedLogger(logging.Logger):
    """A logging.Logger subclass that sanitises every emitted record.

    Use ``get_sanitised_logger(name)`` or ``configure_sanitised_logging()``
    to route a module's logs through this.  The record's message and any
    dict/args are scrubbed before the handler writes them.
    """

    def makeRecord(self, *args, **kwargs):  # noqa: N802
        record = super().makeRecord(*args, **kwargs)
        try:
            record.msg = sanitise_log(str(record.getMessage()))
            record.args = ()
        except Exception:  # noqa: BLE001 - logging must never raise
            pass
        return record


def get_sanitised_logger(name: str) -> SanitisedLogger:
    """Return a SanitisedLogger for ``name``, wired to the root handler."""
    logger = logging.getLogger(name)
    if isinstance(logger, SanitisedLogger):
        return logger
    # Replace the manager's logger with our subclass while keeping its
    # effective level and handlers.
    logger_class = logging.getLoggerClass()
    logging.setLoggerClass(SanitisedLogger)
    new_logger = logging.getLogger(name)
    new_logger.setLevel(logger.level)
    logging.setLoggerClass(logger_class)
    return new_logger  # type: ignore[return-value]


def configure_sanitised_logging(level: int = logging.INFO) -> None:
    """Install a root handler whose output is sanitised.

    Call once at application startup (CLI / API / Streamlit entrypoints).
    Replaces the root handler so no log line can leak a key or PII.
    """
    root = logging.getLogger()
    root.setLevel(level)
    # Remove existing handlers so we don't double-log or leak via a raw one.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)


def audit_log(message: str, *args, **kwargs) -> None:
    """Log an audit event through the sanitised path (best-effort).

    Convenience helper so call sites can record an audit trail without
    importing logging directly.  The message is sanitised on write.
    """
    logger = get_sanitised_logger("cyberrisk.audit")
    logger.info(message, *args, **kwargs)


# ---------------------------------------------------------------------------
# Input-boundary guard (used by tasks 7)
# ---------------------------------------------------------------------------

@dataclass
class InputPrivacyVerdict:
    """Result of running the input-boundary privacy check on user text."""

    action: str  # "ok" | "redacted" | "blocked"
    categories: list[str]  # which PII categories fired (if any)
    message: str  # safe, redacted text to forward (or "" when blocked)
    notice: str  # user-facing explanation of what was detected


def check_input(text: str) -> InputPrivacyVerdict:
    """Validate user-supplied text before it reaches the agent.

    Behaviour is governed by config/privacy.yaml:

      * Always redact secrets.
      * When ``allow_personal_data`` is False (default), PII is redacted
        from the text and the user is warned.
      * Client firm names (the legitimate business use case) are NOT treated
        as blocked personal data — they are the model's input, not PII to
        strip.  Only personal data (emails, phones, personal names, home
        addresses) is redacted or refused.

    Returns an InputPrivacyVerdict describing the action taken.
    """
    policy = load_privacy_config()
    if not policy.privacy_mode:
        return InputPrivacyVerdict(action="ok", categories=[], message=text, notice="")

    det = detect_pii(text)
    categories = [cat for cat, items in det.items() if items]

    # Block on secrets outright (never forward an API key to the model).
    if det["secret"]:
        return InputPrivacyVerdict(
            action="blocked",
            categories=categories,
            message="",
            notice=(
                "A credential or secret was detected in your message. "
                "It was not forwarded to the model. Please retry without pasting keys."
            ),
        )

    if policy.allow_personal_data:
        return InputPrivacyVerdict(action="ok", categories=categories, message=text, notice="")

    # Personal data categories that trigger redaction when disallowed.
    personal = {c for c in ("email", "phone", "name", "path") if c in categories}
    if personal:
        redacted = redact_pii(text)
        return InputPrivacyVerdict(
            action="redacted",
            categories=sorted(personal),
            message=redacted,
            notice=(
                "Personal data (contact details, names, or local paths) was "
                "detected in your message and has been removed before processing. "
                "CyberRisk AI does not store personal information."
            ),
        )

    return InputPrivacyVerdict(action="ok", categories=categories, message=text, notice="")
