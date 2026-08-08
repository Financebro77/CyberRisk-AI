"""Document model — one manifest-registered document, resolved to a file.

The pipeline reads ``corpus_manifest.yaml`` (the single source of truth) and
materialises each active entry into an ``IngestDocument``: the manifest
metadata (title, source, license tier, version, chunking strategy) joined
with the resolved source file and its format.  The content hash is verified
against the manifest so a stale registry is caught loudly.

This mirrors the dataset loader's ``DatasetManifestEntry`` but for authored
documents: the manifest is authoritative, the code only reads it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from cyberrisk.knowledge.config import CHUNK_STRATEGIES, format_for_path
from cyberrisk.knowledge.taxonomy import load_industry_taxonomy

LicenseTier = Literal["public", "licensed", "proprietary", "client-confidential"]
DocStatus = Literal["active", "deprecated", "example"]

# Refresh cadences mirrored from the schema.
RefreshCadence = Literal[
    "daily", "weekly", "monthly", "quarterly", "annual", "on_revision"
]


class ChunkingSpec(BaseModel):
    """The ``chunking`` block from a manifest entry (strategy/max_chars/overlap)."""

    strategy: str
    max_chars: int = Field(ge=200, le=10000)
    overlap: int = Field(ge=0, le=2000)

    @model_validator(mode="after")
    def _strategy_valid(self) -> ChunkingSpec:
        if self.strategy not in CHUNK_STRATEGIES:
            raise ValueError(
                f"unknown chunking strategy {self.strategy!r}; "
                f"valid: {', '.join(CHUNK_STRATEGIES)}"
            )
        return self


class IngestDocument(BaseModel):
    """One manifest-registered document, resolved to a real source file.

    All metadata comes from ``corpus_manifest.yaml``; ``source_path`` is the
    resolved file under ``knowledge/corpus/<domain>/<category>/``.
    """

    id: str = Field(
        pattern=r"^corpus/[a-z0-9._-]+(/[a-zA-Z0-9._-]+)*$",
        description="Unique, namespaced: corpus/<domain>/<category>/<doc> (any depth)",
    )
    domain: str
    category: str
    title: str = Field(min_length=3)
    source: str = Field(min_length=2)
    license_tier: LicenseTier
    version: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    acquired_at: str
    # Optional descriptive metadata (carried into the vector store).  These are
    # the fields the embedding pipeline preserves per chunk: publication date,
    # industry, and a source confidence level.  All optional so existing
    # manifest entries load unchanged.
    publication_date: str | None = Field(default=None, description="YYYY-MM-DD")
    industry: str | None = Field(
        default=None,
        description="Industry key from industry_taxonomy.yaml (e.g. 'healthcare', 'finance'). "
        "Optional — a generic doc has none.",
    )
    # Taxonomy subcategory keys this document covers (e.g. ["regulatory",
    # "insurance-claims"]), from the uniform subcategories in the taxonomy.
    taxonomy: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    refresh_cadence: RefreshCadence
    chunking: ChunkingSpec
    # Tags may be numeric in the manifest ("2024" year tags); coerce to str.
    tags: list[str] = Field(min_length=1)
    status: DocStatus = "active"
    source_path: str = ""  # absolute path resolved at load; set by pipeline

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_to_str(cls, v):
        return [str(t) for t in v]

    @model_validator(mode="after")
    def _validate_industry_taxonomy(self) -> IngestDocument:
        """Validate ``industry``/``taxonomy`` against the registered taxonomy.

        An industry, when present, must be a registered industry key.  Each
        taxonomy subcategory must be one of the uniform subcategory keys.  A
        generic document (no industry, empty taxonomy) is fine.  The taxonomy
        is loaded lazily (cached) so repeated validation does not re-read YAML.
        """
        taxonomy = load_industry_taxonomy()
        if self.industry is not None:
            taxonomy.validate_industry(self.industry)
        for subcat in self.taxonomy:
            taxonomy.validate_subcategory(self.industry, subcat)
        return self

    @property
    def fmt(self) -> str | None:
        """Canonical format of the source file.

        Falls back to the resolved path when ``source_path`` hasn't been set
        (e.g. a manifest-loaded doc before ingestion), so ``fmt`` works in both
        the resolve-only and the ingest path.
        """
        path = self.source_path or self.relative_path()
        return format_for_path(path)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def relative_path(self) -> Path:
        """The document file's path relative to the corpus root (from id)."""
        # id = "corpus/<domain>/<category>/<doc>" -> strip "corpus/".
        return Path(self.id.removeprefix("corpus/"))

    def display_id(self) -> str:
        """Short stable key for filenames (id with 'corpus/' stripped)."""
        return self.id.removeprefix("corpus/").replace("/", "__")
