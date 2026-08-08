"""Authoritative source registry — the approval gate for the knowledge corpus.

Reads ``knowledge/manifests/authoritative_sources.yaml`` (the single source of
truth) and validates it.  The populate workflow consults this registry BEFORE
ingesting a document: a document whose source is not registered (or not
approved) is skipped + logged — the "every source must pass a quality
assessment" requirement made structural.

The registry also records each source's suitability for the pipeline stages
(rag_retrieval / model_calibration / risk_scoring_support), so a source's
permitted use is explicit and auditable.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# The registered categories.
SOURCE_CATEGORIES = (
    "cybersecurity_framework",
    "threat_intelligence",
    "vulnerability_database",
    "breach_statistics",
    "cyber_insurance",
    "regulatory_guidance",
    "incident_database",
)


class SourceSuitability(BaseModel):
    rag_retrieval: bool = True
    model_calibration: bool = False
    risk_scoring_support: bool = False


class Source(BaseModel):
    """One registered authoritative source."""

    source_name: str = Field(min_length=2)
    publisher: str = Field(min_length=2)
    url: str = ""
    document_type: str = Field(min_length=2)
    category: str
    publication_frequency: str = "irregular"
    industry_relevance: str = "all"
    reliability_rating: str = "medium"
    licensing_status: str = "open"
    permitted_usage: str = ""
    suitable_for: SourceSuitability = Field(default_factory=SourceSuitability)
    # A source can be registered but NOT approved (e.g. pending licence review).
    approved: bool = True

    @field_validator("category")
    @classmethod
    def _category_valid(cls, v: str) -> str:
        if v not in SOURCE_CATEGORIES:
            raise ValueError(
                f"unknown source category {v!r}; valid: {sorted(SOURCE_CATEGORIES)}"
            )
        return v

    @field_validator("reliability_rating")
    @classmethod
    def _rating_valid(cls, v: str) -> str:
        if v not in ("high", "medium", "low"):
            raise ValueError(f"reliability_rating must be high/medium/low, got {v!r}")
        return v

    @field_validator("licensing_status")
    @classmethod
    def _license_valid(cls, v: str) -> str:
        if v not in ("public_domain", "open", "proprietary"):
            raise ValueError(
                f"licensing_status must be public_domain/open/proprietary, got {v!r}"
            )
        return v


class SourceRegistry(BaseModel):
    sources: list[Source]

    @model_validator(mode="after")
    def _unique_names(self) -> SourceRegistry:
        names = [s.source_name for s in self.sources]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate source names: {names}")
        return self

    # ------------------------------------------------------------------
    # Lookups / approval gate
    # ------------------------------------------------------------------

    def is_approved(self, source_name: str) -> bool:
        """True if ``source_name`` is a registered AND approved source.

        This is the approval gate: an unregistered or unapproved source is
        never ingested.
        """
        return any(
            s.source_name == source_name and s.approved for s in self.sources
        )

    def get(self, source_name: str) -> Source | None:
        for s in self.sources:
            if s.source_name == source_name:
                return s
        return None

    def approved_names(self) -> list[str]:
        return [s.source_name for s in self.sources if s.approved]

    def by_category(self, category: str) -> list[Source]:
        return [s for s in self.sources if s.category == category]

    def categories_covered(self) -> set[str]:
        return {s.category for s in self.sources}

    def suitable_for(self, stage: str) -> list[Source]:
        """Sources whose ``suitable_for.<stage>`` is True."""
        out = []
        for s in self.sources:
            if getattr(s.suitable_for, stage, False):
                out.append(s)
        return out

    def __len__(self) -> int:
        return len(self.sources)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def default_sources_path() -> Path:
    """Repo-root ``knowledge/manifests/authoritative_sources.yaml``."""
    return (
        Path(__file__).resolve().parent.parent.parent.parent
        / "knowledge"
        / "manifests"
        / "authoritative_sources.yaml"
    )


def load_source_registry(path: str | Path | None = None) -> SourceRegistry:
    """Load + validate the source registry YAML.

    Raises loudly on a malformed entry (boundary-style validation).  The
    result is cached so repeated approval checks don't re-read the YAML.
    """
    path = Path(path) if path is not None else default_sources_path()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "sources" not in raw:
        raise ValueError(f"{path}: registry must contain a top-level 'sources:' list")
    return SourceRegistry(**raw)
