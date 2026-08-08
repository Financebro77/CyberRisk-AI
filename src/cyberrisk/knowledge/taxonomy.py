"""Industry taxonomy — the registered industry vocabulary + subcategories.

Reads ``knowledge/manifests/industry_taxonomy.yaml`` (the single source of
truth) and validates it.  A document that carries an ``industry`` references a
key here; a document's ``taxonomy`` list references subcategory keys.

Industries are ORTHOGONAL to content-type domains (``domains.yaml``): a
document keeps its content-type domain AND gains an industry label +
taxonomy subcategories.  Adding an industry or subcategory is a YAML edit,
never a code change.

This mirrors the ``domains.yaml`` loader pattern: validate at the boundary,
fail loudly on an unknown key.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# The six uniform subcategory keys every industry shares.
UNIFORM_SUBCATEGORIES: tuple[str, ...] = (
    "threat-landscape",
    "regulatory",
    "attack-vectors",
    "insurance-claims",
    "controls",
    "loss-characteristics",
)


class TaxonomySubcategory(BaseModel):
    key: str
    name: str = Field(min_length=1)
    description: str = ""


class Industry(BaseModel):
    key: str
    name: str = Field(min_length=1)
    description: str = ""
    subcategories: list[TaxonomySubcategory]

    @field_validator("subcategories")
    @classmethod
    def _uniform_subcategories(cls, v: list[TaxonomySubcategory]) -> list[TaxonomySubcategory]:
        keys = [s.key for s in v]
        if sorted(keys) != sorted(UNIFORM_SUBCATEGORIES):
            raise ValueError(
                f"industry must have exactly the uniform subcategories "
                f"{sorted(UNIFORM_SUBCATEGORIES)}, got {sorted(keys)}"
            )
        if len(set(keys)) != len(keys):
            raise ValueError(f"duplicate subcategory keys: {keys}")
        return v


class IndustryTaxonomy(BaseModel):
    taxonomy_schema_version: str
    industries: list[Industry]

    @model_validator(mode="after")
    def _unique_industry_keys(self) -> IndustryTaxonomy:
        keys = [i.key for i in self.industries]
        if len(set(keys)) != len(keys):
            raise ValueError(f"duplicate industry keys: {keys}")
        return self

    # ------------------------------------------------------------------
    # Lookups / validation
    # ------------------------------------------------------------------

    def industry_keys(self) -> set[str]:
        return {i.key for i in self.industries}

    def subcategory_keys(self, industry_key: str) -> set[str]:
        for industry in self.industries:
            if industry.key == industry_key:
                return {s.key for s in industry.subcategories}
        raise KeyError(f"unknown industry {industry_key!r}")

    def is_known_industry(self, key: str) -> bool:
        return key in self.industry_keys()

    def validate_industry(self, industry: str) -> None:
        """Raise loudly if ``industry`` is not a registered industry key."""
        if industry not in self.industry_keys():
            raise ValueError(
                f"unknown industry {industry!r}; registered: {sorted(self.industry_keys())}"
            )

    def validate_subcategory(self, industry: str | None, subcategory: str) -> None:
        """Raise if ``subcategory`` is not a valid key for ``industry``.

        With an industry, the subcategory must be one of that industry's
        (uniform) subcategories.  Without an industry, it must be one of the
        uniform subcategory keys.
        """
        if subcategory not in UNIFORM_SUBCATEGORIES:
            raise ValueError(
                f"unknown taxonomy subcategory {subcategory!r}; "
                f"uniform subcategories: {sorted(UNIFORM_SUBCATEGORIES)}"
            )
        if industry is not None:
            self.validate_industry(industry)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def default_taxonomy_path() -> Path:
    """Repo-root ``knowledge/manifests/industry_taxonomy.yaml``."""
    return (
        Path(__file__).resolve().parent.parent.parent.parent
        / "knowledge"
        / "manifests"
        / "industry_taxonomy.yaml"
    )


def load_industry_taxonomy(path: str | Path | None = None) -> IndustryTaxonomy:
    """Load + validate the industry taxonomy YAML.

    Raises loudly on a malformed entry (the boundary-style validation the
    knowledge layer uses everywhere).  The result is cached so repeated
    document validation does not re-read the YAML.
    """
    path = Path(path) if path is not None else default_taxonomy_path()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "industries" not in raw:
        raise ValueError(f"{path}: taxonomy must contain a top-level 'industries:' list")
    return IndustryTaxonomy(**raw)
