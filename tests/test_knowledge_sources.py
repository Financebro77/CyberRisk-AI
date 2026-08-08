"""Authoritative source registry + knowledge-to-model mapping tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cyberrisk.knowledge.mappings import (
    ControlMapping,
    load_control_mapping,
)
from cyberrisk.knowledge.sources import (
    SOURCE_CATEGORIES,
    Source,
    SourceRegistry,
    load_source_registry,
)

REPO = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def registry() -> SourceRegistry:
    return load_source_registry()


@pytest.fixture(scope="module")
def mapping() -> ControlMapping:
    return load_control_mapping()


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------


def test_registry_has_approved_sources(registry: SourceRegistry):
    assert len(registry) >= 10
    assert "Verizon Data Breach Investigations Report (DBIR)" in registry.approved_names()
    assert "NIST Cybersecurity Framework (CSF)" in registry.approved_names()
    assert "CISA Known Exploited Vulnerabilities (KEV)" in registry.approved_names()


def test_approval_gate(registry: SourceRegistry):
    assert registry.is_approved("NIST Cybersecurity Framework (CSF)")
    assert registry.is_approved("Verizon Data Breach Investigations Report (DBIR)")
    assert not registry.is_approved("Some Random Blog")  # unknown -> not approved


def test_categories_covered(registry: SourceRegistry):
    cats = registry.categories_covered()
    assert "cybersecurity_framework" in cats
    assert "breach_statistics" in cats
    assert "regulatory_guidance" in cats


def test_suitability(registry: SourceRegistry):
    # Framework sources support risk-scoring but not calibration.
    nist = registry.get("NIST Cybersecurity Framework (CSF)")
    assert nist.suitable_for.rag_retrieval is True
    assert nist.suitable_for.model_calibration is False
    assert nist.suitable_for.risk_scoring_support is True
    # DBIR supports calibration.
    dbir = registry.get("Verizon Data Breach Investigations Report (DBIR)")
    assert dbir.suitable_for.model_calibration is True


def test_reliability_and_license_validated():
    with pytest.raises(ValidationError):
        Source(source_name="Bad", publisher="X", category="cybersecurity_framework",
               reliability_rating="very-high", licensing_status="public_domain")
    with pytest.raises(ValidationError):
        Source(source_name="Bad", publisher="X", category="not-a-category",
               reliability_rating="high", licensing_status="public_domain")


def test_source_category_constants():
    assert "vulnerability_database" in SOURCE_CATEGORIES
    assert "cyber_insurance" in SOURCE_CATEGORIES


# ---------------------------------------------------------------------------
# Knowledge-to-model mapping
# ---------------------------------------------------------------------------


def test_mapping_loads(mapping: ControlMapping):
    assert len(mapping.controls) >= 4
    assert mapping.control_names()


def test_mapping_impacts(mapping: ControlMapping):
    freq = mapping.by_impact("Frequency reduction")
    sev = mapping.by_impact("Severity reduction")
    assert freq and sev
    # MFA is a frequency-reduction control.
    mfa = next(c for c in mapping.controls if c.control == "Multi-factor authentication")
    assert mfa.cyberrisk_impact == "Frequency reduction"
    assert mfa.affected_module == "frequency.py"
    # Immutable backups is severity.
    bak = next(c for c in mapping.controls if c.control == "Immutable backups")
    assert bak.cyberrisk_impact == "Severity reduction"
    assert bak.affected_module == "severity.py"


def test_mapping_evidence_is_approved(mapping: ControlMapping, registry: SourceRegistry):
    # Every evidence source in the mapping must be an approved registry source.
    for c in mapping.controls:
        for src in c.evidence_sources:
            assert registry.is_approved(src), f"{src} not approved for {c.control}"


def test_mapping_invalid_impact_rejected():
    from cyberrisk.knowledge.mappings import ControlEvidence

    with pytest.raises(ValidationError):
        ControlEvidence(control="X", evidence_sources=["Y"],
                        cyberrisk_impact="Cost reduction", affected_module="frequency.py")
