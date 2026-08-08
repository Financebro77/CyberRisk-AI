"""Industry taxonomy tests.

Exercises the industry taxonomy manifest + validators, and the document-model
validation that constrains ``industry`` / ``taxonomy`` against it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cyberrisk.knowledge.document import ChunkingSpec, IngestDocument
from cyberrisk.knowledge.taxonomy import (
    UNIFORM_SUBCATEGORIES,
    IndustryTaxonomy,
    load_industry_taxonomy,
)

REPO = Path(__file__).parent.parent

EXPECTED_INDUSTRIES = {
    "healthcare", "finance", "retail", "manufacturing",
    "energy", "government", "technology",
}
EXPECTED_SUBCATEGORIES = {
    "threat-landscape", "regulatory", "attack-vectors",
    "insurance-claims", "controls", "loss-characteristics",
}


@pytest.fixture(scope="module")
def taxonomy() -> IndustryTaxonomy:
    return load_industry_taxonomy()


# ---------------------------------------------------------------------------
# Manifest shape
# ---------------------------------------------------------------------------


def test_load_taxonomy_has_seven_industries(taxonomy: IndustryTaxonomy):
    assert taxonomy.industry_keys() == EXPECTED_INDUSTRIES


def test_each_industry_has_uniform_subcategories(taxonomy: IndustryTaxonomy):
    for industry in taxonomy.industries:
        keys = {s.key for s in industry.subcategories}
        assert keys == EXPECTED_SUBCATEGORIES, f"{industry.key}: {keys}"
        # names are non-empty
        assert all(s.name.strip() for s in industry.subcategories)
        # descriptions are non-empty (useful for a taxonomy)
        assert all(s.description.strip() for s in industry.subcategories)


def test_uniform_subcategories_constant():
    assert set(UNIFORM_SUBCATEGORIES) == EXPECTED_SUBCATEGORIES


def test_subcategory_keys_lookup(taxonomy: IndustryTaxonomy):
    assert taxonomy.subcategory_keys("healthcare") == EXPECTED_SUBCATEGORIES


def test_subcategory_keys_unknown_raises(taxonomy: IndustryTaxonomy):
    with pytest.raises(KeyError):
        taxonomy.subcategory_keys("not-an-industry")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def test_validate_industry_known(taxonomy: IndustryTaxonomy):
    for key in EXPECTED_INDUSTRIES:
        taxonomy.validate_industry(key)  # no raise


def test_validate_industry_unknown_raises(taxonomy: IndustryTaxonomy):
    with pytest.raises(ValueError, match="unknown industry"):
        taxonomy.validate_industry("aerospace")


def test_validate_subcategory_known(taxonomy: IndustryTaxonomy):
    taxonomy.validate_subcategory("healthcare", "regulatory")
    taxonomy.validate_subcategory(None, "attack-vectors")  # no industry


def test_validate_subcategory_unknown_raises(taxonomy: IndustryTaxonomy):
    with pytest.raises(ValueError, match="unknown taxonomy subcategory"):
        taxonomy.validate_subcategory("healthcare", "patient-data")


def test_is_known_industry(taxonomy: IndustryTaxonomy):
    assert taxonomy.is_known_industry("finance")
    assert not taxonomy.is_known_industry("aerospace")


# ---------------------------------------------------------------------------
# Document-model validation against the taxonomy
# ---------------------------------------------------------------------------


def _make_doc(**overrides) -> IngestDocument:
    base = dict(
        id="corpus/regulatory/dora/x",
        domain="regulatory",
        category="regulation",
        title="A document",
        source="Test",
        license_tier="public",
        version="1",
        content_hash="sha256:" + "0" * 64,
        acquired_at="2026-01-01",
        refresh_cadence="annual",
        chunking=ChunkingSpec(strategy="plain", max_chars=500, overlap=50),
        tags=["x"],
        status="active",
    )
    base.update(overrides)
    return IngestDocument(**base)


def test_doc_valid_industry_passes():
    doc = _make_doc(industry="finance", taxonomy=["regulatory", "controls"])
    assert doc.industry == "finance"
    assert doc.taxonomy == ["regulatory", "controls"]


def test_doc_generic_no_industry_passes():
    doc = _make_doc()  # no industry, empty taxonomy
    assert doc.industry is None
    assert doc.taxonomy == []


def test_doc_taxonomy_without_industry_passes():
    # A cross-industry doc: subcategories apply, no single industry.
    doc = _make_doc(taxonomy=["threat-landscape", "attack-vectors"])
    assert doc.taxonomy == ["threat-landscape", "attack-vectors"]


def test_doc_invalid_industry_fails():
    with pytest.raises(ValidationError):
        _make_doc(industry="aerospace")


def test_doc_invalid_subcategory_fails():
    with pytest.raises(ValidationError):
        _make_doc(industry="healthcare", taxonomy=["patient-data"])


def test_doc_invalid_subcategory_without_industry_fails():
    with pytest.raises(ValidationError):
        _make_doc(taxonomy=["not-a-real-subcategory"])


# ---------------------------------------------------------------------------
# Extensibility
# ---------------------------------------------------------------------------


def test_taxonomy_industry_models():
    """Each industry exposes its name + description (extensible by YAML)."""
    taxonomy = load_industry_taxonomy()
    by_key = {i.key: i for i in taxonomy.industries}
    assert by_key["healthcare"].name == "Healthcare"
    assert "hospital" in by_key["healthcare"].description.lower()
    assert by_key["finance"].name == "Finance"
    assert by_key["technology"].name == "Technology"
