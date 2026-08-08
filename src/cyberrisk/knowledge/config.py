"""Ingest pipeline configuration — reusable and configurable, not hard-coded.

``IngestConfig`` holds every knob the document pipeline needs: chunk sizing,
overlap, minimum chunk length, the strategy registry, the format registry,
where the derived index is written, and per-format enabled flags.  It is a
pydantic model so a malformed config fails loudly at the boundary (the repo's
philosophy), and it can be loaded from a YAML file or built in code.

The YAML config lives at ``knowledge/pipelines/ingest/config.yaml`` — the
architecture's ``pipelines/ingest/`` design slot.  Tuning chunk sizes is a
config change, never a code change.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# Chunking strategies supported by the engine.  This is the authoritative
# set from knowledge/schemas/document.schema.json: the section-based strategies
# (by_chapter + domain aliases) and the plain fallback.
SECTION_STRATEGIES = (
    "by_chapter",
    "by_clause",
    "by_control",
    "by_obligation",
    "by_campaign",
    "by_incident",
    "by_table",
)
PLAIN_STRATEGIES = ("plain",)
CHUNK_STRATEGIES = SECTION_STRATEGIES + PLAIN_STRATEGIES

# Document formats the pipeline can ingest.
SUPPORTED_FORMATS = ("pdf", "markdown", "md", "docx", "html", "htm", "txt", "yaml", "yml")

# File extensions -> canonical format key.
FORMAT_BY_EXTENSION = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".docx": "docx",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".yaml": "yaml",
    ".yml": "yaml",
}


def format_for_path(path: str | Path) -> str | None:
    """Canonical format key for a file path, or None if unsupported."""
    return FORMAT_BY_EXTENSION.get(Path(path).suffix.lower())


class IngestConfig(BaseModel):
    """Every configurable knob for the document ingestion pipeline."""

    # Chunk sizing defaults (overridden per-document by the manifest entry's
    # ``chunking`` block when present).
    default_max_chars: int = Field(default=1200, ge=200, le=10000)
    default_overlap: int = Field(default=150, ge=0, le=2000)
    min_chunk_chars: int = Field(default=20, ge=1)
    # A paragraph shorter than this is merged into the next (avoids
    # whitespace-only or one-line chunks).
    paragraph_min_chars: int = Field(default=40, ge=1)

    # Format registry — disable a format by setting its flag False.
    enabled_formats: dict[str, bool] = Field(
        default_factory=lambda: {f: True for f in SUPPORTED_FORMATS}
    )

    # Derived output root.  Defaults to <repo>/knowledge/derived (gitignored).
    derived_root: str | Path | None = None

    # Strategy registry — the section-based strategies map to one chunker
    # implementation (section/heading splitting); 'plain' is the fallback.
    strategy_registry: dict[str, str] = Field(
        default_factory=lambda: {
            **{s: "section" for s in SECTION_STRATEGIES},
            **{p: "plain" for p in PLAIN_STRATEGIES},
        }
    )

    # Rewrite derived artifacts even when content_hash is unchanged (forced
    # full re-ingest) — off by default (incremental is the norm).
    force_reingest: bool = False

    @property
    def derived_path(self) -> Path:
        """Resolved derived output root."""
        if self.derived_root is not None:
            return Path(self.derived_root)
        # repo root: src/cyberrisk/knowledge/config.py -> src/cyberrisk ->
        # src -> repo root.
        return (
            Path(__file__).resolve().parent.parent.parent.parent
            / "knowledge"
            / "derived"
        )

    def is_format_enabled(self, fmt: str) -> bool:
        return self.enabled_formats.get(fmt, True)

    def chunker_for_strategy(self, strategy: str) -> str:
        """The chunker implementation key for a manifest strategy.

        Raises loudly for an unknown strategy so a manifest typo is caught at
        ingest, never silently mishandled.
        """
        try:
            return self.strategy_registry[strategy]
        except KeyError:
            raise ValueError(
                f"unknown chunking strategy {strategy!r}; "
                f"valid: {', '.join(CHUNK_STRATEGIES)}"
            ) from None


def load_ingest_config(path: str | Path | None = None) -> IngestConfig:
    """Load an IngestConfig from YAML (defaults to the repo's
    ``knowledge/pipelines/ingest/config.yaml``).

    Missing keys fall back to the pydantic defaults, so the YAML only needs to
    override what differs.
    """
    if path is None:
        path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "knowledge"
            / "pipelines"
            / "ingest"
            / "config.yaml"
        )
    path = Path(path)
    if not path.exists():
        return IngestConfig()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return IngestConfig(**raw)
