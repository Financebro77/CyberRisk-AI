"""Knowledge-to-model mappings — DOCUMENTATION ONLY. No parameter changes.

Reads ``knowledge/mappings/control_evidence.yaml``, which records which
authoritative evidence sources support each control's effect on the model
(frequency vs severity) and the engine module the effect operates through.

The mapping is for AUDITABILITY and consultant explanation: it documents the
relationship between a control, its evidence, and the model's mechanics.  It
does NOT modify any engine parameter.  Changing a parameter requires an
explicit, approved calibration change.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

# The documented model effects + affected modules.
IMPACTS = ("Frequency reduction", "Severity reduction")
AFFECTED_MODULES = ("frequency.py", "severity.py")


class ControlEvidence(BaseModel):
    """One control's documented evidence + model impact (documentation only)."""

    control: str = Field(min_length=2)
    evidence_sources: list[str] = Field(min_length=1)
    cyberrisk_impact: str
    affected_module: str
    notes: str = ""

    @model_validator(mode="after")
    def _impact_valid(self) -> ControlEvidence:
        if self.cyberrisk_impact not in IMPACTS:
            raise ValueError(
                f"cyberrisk_impact must be one of {IMPACTS}, got {self.cyberrisk_impact!r}"
            )
        if self.affected_module not in AFFECTED_MODULES:
            raise ValueError(
                f"affected_module must be one of {AFFECTED_MODULES}, got {self.affected_module!r}"
            )
        return self


class ControlMapping(BaseModel):
    controls: list[ControlEvidence]

    @model_validator(mode="after")
    def _unique_controls(self) -> ControlMapping:
        names = [c.control for c in self.controls]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate control names: {names}")
        return self

    def control_names(self) -> list[str]:
        return [c.control for c in self.controls]

    def by_impact(self, impact: str) -> list[ControlEvidence]:
        return [c for c in self.controls if c.cyberrisk_impact == impact]

    def evidence_for(self, control: str) -> list[str]:
        for c in self.controls:
            if c.control == control:
                return c.evidence_sources
        return []


def default_mapping_path() -> Path:
    """Repo-root ``knowledge/mappings/control_evidence.yaml``."""
    return (
        Path(__file__).resolve().parent.parent.parent.parent
        / "knowledge"
        / "mappings"
        / "control_evidence.yaml"
    )


def load_control_mapping(path: str | Path | None = None) -> ControlMapping:
    """Load + validate the control-evidence mapping.

    Optionally validates that every ``evidence_sources`` entry resolves to an
    approved source in the registry (when the registry is available), keeping
    the mapping consistent with the approved-source list.
    """
    path = Path(path) if path is not None else default_mapping_path()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "controls" not in raw:
        raise ValueError(f"{path}: mapping must contain a top-level 'controls:' list")
    mapping = ControlMapping(**raw)

    # Validate evidence sources against the registry when present.
    from cyberrisk.knowledge.sources import load_source_registry

    try:
        registry = load_source_registry()
        approved = set(registry.approved_names())
        for c in mapping.controls:
            for src in c.evidence_sources:
                if src not in approved:
                    raise ValueError(
                        f"evidence source {src!r} for control {c.control!r} "
                        f"is not in the approved source registry"
                    )
    except FileNotFoundError:
        pass  # registry not present yet — skip cross-validation
    return mapping
