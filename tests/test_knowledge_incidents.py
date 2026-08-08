"""Historical cyber incidents tests.

Exercises the Incident model + IncidentIndex, the incident YAML ingestion
format, and the search_incidents agent tool.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cyberrisk.knowledge.incidents import (
    Incident,
    IncidentIndex,
    load_incident,
    load_incident_index,
    load_incidents_dir,
)
from cyberrisk.knowledge.taxonomy import load_industry_taxonomy

REPO = Path(__file__).parent.parent
INCIDENTS_DIR = REPO / "knowledge" / "corpus" / "incidents" / "curated"


@pytest.fixture(scope="module")
def index() -> IncidentIndex:
    return load_incident_index(INCIDENTS_DIR)


# ---------------------------------------------------------------------------
# Ingestion format
# ---------------------------------------------------------------------------


def test_load_incident_ten_fields():
    inc = load_incident(INCIDENTS_DIR / "change-healthcare-2024.yaml")
    assert inc.id == "change-healthcare-2024"
    assert inc.company == "Change Healthcare"
    assert inc.industry == "healthcare"
    assert inc.attack_type == "ransomware"
    assert inc.attack_vector
    assert inc.root_cause
    assert inc.financial_loss == pytest.approx(872_000_000)
    assert inc.operational_impact
    assert inc.regulatory_consequences
    assert inc.insurance_implications
    assert len(inc.lessons_learned) >= 3
    assert inc.incident_date == "2024-02-21"


def test_load_incidents_dir_discovers():
    incidents = load_incidents_dir(INCIDENTS_DIR)
    assert len(incidents) >= 1
    ids = {i.id for i in incidents}
    assert "change-healthcare-2024" in ids


def test_invalid_incident_missing_field_raises(tmp_path):
    from cyberrisk.knowledge.incidents import load_incident

    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\ncompany: Y\n", encoding="utf-8")  # missing required fields
    with pytest.raises(ValidationError):
        load_incident(bad)


def test_invalid_incident_bad_industry_raises(tmp_path):
    from cyberrisk.knowledge.incidents import load_incident

    bad = tmp_path / "bad-industry.yaml"
    bad.write_text(
        "id: x\ncompany: Y\nindustry: aerospace\nattack_type: ransomware\n"
        "attack_vector: a\nroot_cause: b\noperational_impact: c\n"
        "regulatory_consequences: d\ninsurance_implications: e\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="unknown industry"):
        load_incident(bad)


# ---------------------------------------------------------------------------
# IncidentIndex
# ---------------------------------------------------------------------------


def test_index_by_industry(index: IncidentIndex):
    hits = index.by_industry("healthcare")
    assert hits
    assert all(i.industry == "healthcare" for i in hits)


def test_index_by_attack_type(index: IncidentIndex):
    hits = index.by_attack_type("ransomware")
    assert hits
    assert all("ransomware" in i.attack_type.lower() for i in hits)


def test_index_by_company(index: IncidentIndex):
    hits = index.by_company("change")
    assert hits
    assert "change" in hits[0].company.lower()


def test_index_search_combined(index: IncidentIndex):
    hits = index.search(industry="healthcare", attack_type="ransomware", limit=5)
    assert hits
    # The change-healthcare incident should rank first (matches both filters).
    assert hits[0].id == "change-healthcare-2024"


def test_index_search_no_match(index: IncidentIndex):
    assert index.search(industry="energy", attack_type="BEC", limit=3) == []


def test_index_search_respects_limit():
    # Multiple incidents, limit=1.
    incs = [
        Incident(
            id=f"i{i}", company=f"Co {i}", industry="healthcare", attack_type="ransomware",
            attack_vector="v", root_cause="r", operational_impact="o",
            regulatory_consequences="rc", insurance_implications="ii",
        )
        for i in range(4)
    ]
    idx = IncidentIndex(incs)
    assert len(idx.search(industry="healthcare", limit=1)) == 1


def test_index_to_json(index: IncidentIndex):
    rows = index.to_json()
    assert rows
    required = {
        "id", "company", "industry", "attack_type", "attack_vector", "root_cause",
        "financial_loss", "operational_impact", "regulatory_consequences",
        "insurance_implications", "lessons_learned", "incident_date", "citation",
    }
    assert required <= set(rows[0].keys())


# ---------------------------------------------------------------------------
# Narrative / citation
# ---------------------------------------------------------------------------


def test_narrative_renders_citation(index: IncidentIndex):
    inc = index.by_company("change")[0]
    text = inc.narrative()
    assert "[INCIDENT]" in text
    assert "Change Healthcare" in text
    assert "ransomware" in text
    assert "[incident: change-healthcare-2024]" in text
    assert "Lessons learned:" in text


def test_industry_validated_against_taxonomy():

    taxonomy = load_industry_taxonomy()
    assert taxonomy.is_known_industry("healthcare")


# ---------------------------------------------------------------------------
# search_incidents agent tool
# ---------------------------------------------------------------------------


def test_search_incidents_tool_returns_structured():
    from cyberrisk.agent.tools import search_incidents

    out = search_incidents(industry="healthcare", limit=3)
    assert out["status"] == "ok"
    assert out["count"] >= 1
    incident = out["incidents"][0]
    assert incident["id"] == "change-healthcare-2024"
    assert incident["company"] == "Change Healthcare"
    assert "citation" in incident
    assert incident["citation"] == "[incident: change-healthcare-2024]"


def test_search_incidents_tool_no_match():
    from cyberrisk.agent.tools import search_incidents

    out = search_incidents(industry="energy", attack_type="BEC")
    assert out["status"] == "ok"
    assert out["count"] == 0
    assert out["incidents"] == []


def test_search_incidents_tool_registered_in_schemas():
    from cyberrisk.agent.tools import TOOL_SCHEMAS

    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert "search_incidents" in names
