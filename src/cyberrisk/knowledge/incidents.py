"""Historical cyber incidents — structured knowledge + field-queried retrieval.

Each incident is a YAML file under ``knowledge/corpus/incidents/curated/`` with
the ten requested fields (company, industry, attack_type, attack_vector,
root_cause, financial_loss, operational_impact, regulatory_consequences,
insurance_implications, lessons_learned).  This module:

    * validates an Incident against the industry taxonomy,
    * loads the incidents directory (discovers ``*.yaml``),
    * provides an ``IncidentIndex`` for field-queried retrieval
      (by industry / attack type / company),
    * renders a citation-carrying narrative for the RAG context and the
      ``search_incidents`` agent tool.

New incidents = drop a YAML file.  No code change.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from cyberrisk.knowledge.taxonomy import load_industry_taxonomy


def default_incidents_dir() -> Path:
    """Repo-root ``knowledge/corpus/incidents/curated``."""
    return (
        Path(__file__).resolve().parent.parent.parent.parent
        / "knowledge"
        / "corpus"
        / "incidents"
        / "curated"
    )


class Incident(BaseModel):
    """One historical cyber incident, validated against the taxonomy."""

    id: str = Field(description="Unique slug; used in the [incident: <id>] citation")
    company: str = Field(min_length=1)
    industry: str | None = Field(
        default=None, description="Taxonomy key from industry_taxonomy.yaml"
    )
    attack_type: str = Field(min_length=1)
    attack_vector: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    financial_loss: float | None = Field(default=None, ge=0.0, description="USD")
    operational_impact: str = Field(min_length=1)
    regulatory_consequences: str = Field(min_length=1)
    insurance_implications: str = Field(min_length=1)
    lessons_learned: list[str] = Field(default_factory=list)
    incident_date: str | None = Field(default=None, description="YYYY-MM-DD")
    # Attribution: the source label for the incident (e.g. "HHS OCR + press").
    # Optional — narrative() falls back to "curated incident knowledge".
    source_label: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_industry(self) -> Incident:
        """The industry, when present, must be a registered taxonomy key."""
        if self.industry is not None:
            load_industry_taxonomy().validate_industry(self.industry)
        return self

    @property
    def citation(self) -> str:
        return f"[incident: {self.id}]"

    def narrative(self) -> str:
        """A single renderable narrative block for chunking / RAG context.

        Includes the structured fields AND the citation marker, so a retrieved
        incident is a complete, self-citing unit the guard can verify.
        """
        loss = f"${self.financial_loss:,.0f}" if self.financial_loss is not None else "not disclosed"
        # Attribution metadata the consultant copies into its Source /
        # Published / Confidence / Section blocks per the evidence rules.
        date = self.incident_date or "not stated"
        source = self.source_label or "curated incident knowledge"
        lines = [
            f"[INCIDENT] {self.company} | {self.industry or 'cross-industry'} | {self.attack_type}",
            f"Source: {source}",
            f"Published: {date}",
            f"Attack vector: {self.attack_vector}",
            f"Root cause: {self.root_cause}",
            f"Financial loss: {loss}",
            f"Operational impact: {self.operational_impact}",
            f"Regulatory consequences: {self.regulatory_consequences}",
            f"Insurance implications: {self.insurance_implications}",
            "Lessons learned:",
        ]
        lines += [f"  - {lesson}" for lesson in self.lessons_learned]
        lines.append(self.citation)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON-serialisable view for the search_incidents tool."""
        return {
            "id": self.id,
            "company": self.company,
            "industry": self.industry,
            "attack_type": self.attack_type,
            "attack_vector": self.attack_vector,
            "root_cause": self.root_cause,
            "financial_loss": self.financial_loss,
            "operational_impact": self.operational_impact,
            "regulatory_consequences": self.regulatory_consequences,
            "insurance_implications": self.insurance_implications,
            "lessons_learned": self.lessons_learned,
            "incident_date": self.incident_date,
            "source_label": self.source_label,
            "citation": self.citation,
        }


class IncidentIndex:
    """Field-queried retrieval over the incidents directory."""

    def __init__(self, incidents: list[Incident]) -> None:
        self.incidents = list(incidents)

    # ------------------------------------------------------------------
    # Field lookups (case-insensitive substring match)
    # ------------------------------------------------------------------

    def by_industry(self, industry: str) -> list[Incident]:
        industry = industry.lower()
        return [i for i in self.incidents if (i.industry or "").lower() == industry]

    def by_attack_type(self, attack_type: str) -> list[Incident]:
        attack_type = attack_type.lower()
        return [i for i in self.incidents if attack_type in i.attack_type.lower()]

    def by_company(self, company: str) -> list[Incident]:
        company = company.lower()
        return [i for i in self.incidents if company in i.company.lower()]

    # ------------------------------------------------------------------
    # Combined search
    # ------------------------------------------------------------------

    def search(
        self,
        industry: str | None = None,
        attack_type: str | None = None,
        company: str | None = None,
        limit: int = 3,
    ) -> list[Incident]:
        """Return incidents matching ANY provided filter, ranked by
        number of matching filters (most-specific first), capped at ``limit``."""
        results = self.incidents
        filters = [
            (industry, lambda i: (i.industry or "").lower() == industry.lower() if industry else False),
            (attack_type, lambda i: attack_type.lower() in i.attack_type.lower() if attack_type else False),
            (company, lambda i: company.lower() in i.company.lower() if company else False),
        ]
        # Rank by how many filters match.
        def _score(i: Incident) -> int:
            return sum(1 for _val, fn in filters if fn(i))

        scored = [(i, _score(i)) for i in results]
        scored = [(i, s) for i, s in scored if s > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [i for i, _s in scored[:max(1, limit)]]

    def to_json(self) -> list[dict]:
        return [i.to_dict() for i in self.incidents]

    def __len__(self) -> int:
        return len(self.incidents)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_incident(path: str | Path) -> Incident:
    """Load + validate one incident YAML."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: incident YAML must be a mapping")
    return Incident(**raw)


def load_incidents_dir(dir_path: str | Path | None = None) -> list[Incident]:
    """Discover + validate all ``*.yaml`` incidents in a directory.

    Fails loudly on a malformed incident (the boundary-style validation the
    knowledge layer uses everywhere).
    """
    dir_path = Path(dir_path) if dir_path is not None else default_incidents_dir()
    incidents = []
    for path in sorted(dir_path.glob("*.yaml")):
        incidents.append(load_incident(path))
    return incidents


@lru_cache(maxsize=1)
def load_incident_index(dir_path: str | Path | None = None) -> IncidentIndex:
    """Cached IncidentIndex over the incidents directory (idempotent per run)."""
    return IncidentIndex(load_incidents_dir(dir_path))
