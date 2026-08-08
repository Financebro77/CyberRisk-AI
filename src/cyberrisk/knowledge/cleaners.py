"""Text cleaning for ingested documents.

Extractors return raw-ish text; cleaners turn it into clean, consistent text
suitable for chunking and (later) embedding:

    * strip BOM / normalise line endings to \\n,
    * normalise Unicode (NFKC) and fold smart quotes/dashes to ASCII where safe,
    * collapse runs of blank lines and trailing whitespace,
    * preserve paragraph boundaries (a blank line separates paragraphs — we do
      NOT join everything into one blob, which would wreck semantic chunking).

Cleaning is deterministic and idempotent: cleaning an already-clean string is
a no-op, so re-ingesting a document yields identical text.
"""

from __future__ import annotations

import re
import unicodedata

# Line endings -> \n
_LINE_END_RE = re.compile(r"\r\n|\r|\n")

# One or more blank lines -> a single blank line (paragraph separator).
# Matches any run of 2+ newlines (with optional horizontal whitespace between)
# so "\\n\\n", "\\n\\n\\n", "\\n \\n" all collapse to a single paragraph break.
_BLANK_LINE_RE = re.compile(r"(?:\n[ \t]*){2,}\n*")

# Horizontal whitespace at line ends.
_TRAILING_WS_RE = re.compile(r"[ \t]+(?=\n)")

# Runs of spaces within a line -> single space (but not leading indentation).
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")

# Non-printable control chars (excluding \n, \t which carry structure).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Smart quotes / dashes / ellipsis -> ASCII equivalents.
_SMART_FOLDS = {
    "‘": "'",  # left single quote
    "’": "'",  # right single quote
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "–": "-",  # en dash
    "—": "-",  # em dash
    "…": "...",  # ellipsis
    " ": " ",  # non-breaking space
}


def _fold_smart_chars(text: str) -> str:
    """Fold smart quotes/dashes/ellipsis/nbsp to ASCII equivalents."""
    return "".join(_SMART_FOLDS.get(ch, ch) for ch in text)


def normalize_unicode(text: str) -> str:
    """NFKC normalise + fold smart punctuation to ASCII-safe forms."""
    text = unicodedata.normalize("NFKC", text)
    return _fold_smart_chars(text)


def clean_text(text: str) -> str:
    """Full cleaning pipeline: line endings, unicode, whitespace, control chars.

    Idempotent: applying it twice yields the same result.
    """
    if not text:
        return ""
    # Normalise line endings and strip any BOM.
    text = text.lstrip("﻿")
    text = _LINE_END_RE.sub("\n", text)
    # Drop control characters that carry no structure.
    text = _CONTROL_CHARS_RE.sub("", text)
    # Unicode + smart punctuation.
    text = normalize_unicode(text)
    # Collapse trailing whitespace on lines.
    text = _TRAILING_WS_RE.sub("", text)
    # Collapse runs of blank lines to a single paragraph separator.
    text = _BLANK_LINE_RE.sub("\n\n", text)
    # Collapse in-line runs of spaces (keep single spaces).
    text = _MULTI_SPACE_RE.sub(" ", text)
    # Trim leading/trailing whitespace and blank lines.
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    """Split cleaned text into non-empty paragraphs (blank-line separated).

    Returns the paragraph strings in order; empty/whitespace-only paragraphs
    are dropped.  Used by the 'plain' chunker to build paragraph-merge chunks.
    """
    return [p.strip() for p in text.split("\n\n") if p.strip()]
