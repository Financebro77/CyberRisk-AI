"""Methodology explanation for the internally developed CyberRisk model.

The CyberRisk engine is a WHITE-BOX model: every number the consultant
reports traces back to the config YAMLs (config/scoring_weights.yaml,
config/scenarios.yaml, config/simulation_config.yaml) through documented,
deterministic mappings.  Nothing is a third-party black box, so the agent
must never hedge that a control's effect "cannot be confirmed."

``explain_model_mechanics()`` is the single source of truth the agent uses
when a client asks how a figure was produced.  It returns the four
methodology sections the agent is expected to be able to explain:

    - scoring methodology     (composite 0-100 score -> category / drivers)
    - frequency adjustments   (score -> scenario lambda via the log link)
    - severity adjustments    (revenue-scaled lognormal tail per scenario)
    - simulation methodology  (copula-coupled Monte Carlo -> loss distribution)

The engine modules themselves are NOT modified by this module; it only reads
the same config files the engine reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

# Repo root: src/cyberrisk/agent/model_mechanics.py -> src/cyberrisk -> src -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config"

# Composite score at which the log-linear frequency link leaves the calibrated
# baselines unchanged (a score of 50 neither inflates nor deflates lambda).
SCORE_REFERENCE = 50.0


@dataclass(frozen=True)
class ModelMechanics:
    """The four methodology sections returned by ``explain_model_mechanics``."""

    scoring_methodology: str
    frequency_adjustments: str
    severity_adjustments: str
    simulation_methodology: str

    def sections(self) -> dict[str, str]:
        """Ordered dict form, ready for the agent to cite."""
        return {
            "scoring_methodology": self.scoring_methodology,
            "frequency_adjustments": self.frequency_adjustments,
            "severity_adjustments": self.severity_adjustments,
            "simulation_methodology": self.simulation_methodology,
        }

    def full_text(self) -> str:
        """A single, client-ready methodology paragraph."""
        return (
            "This assessment uses an internally developed stochastic cyber risk "
            "model. Model assumptions, parameter mappings and simulation logic "
            "are documented within the Armageddon framework.\n\n"
            f"Scoring methodology: {self.scoring_methodology}\n"
            f"Frequency adjustments: {self.frequency_adjustments}\n"
            f"Severity adjustments: {self.severity_adjustments}\n"
            f"Simulation methodology: {self.simulation_methodology}"
        )


def _load_yaml(name: str) -> dict:
    """Load a config YAML as a plain dict (read-only, mirrors the engine)."""
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


def _category_bands_text(scoring: dict) -> str:
    """Describe the category bands from scoring_weights.yaml."""
    bands = scoring.get("category_bands", [])
    if not bands:
        return "Low / Medium / High / Critical (config/scoring_weights.yaml)."
    parts = []
    for band in bands:
        max_score = band.get("max_score")
        label = band.get("category", "?")
        if max_score == 100:
            parts.append(f"above {int(max_score - 25)} = {label}")
        else:
            low = int(max_score - 25) + 1
            parts.append(f"{low}-{int(max_score)} = {label}")
    return ", ".join(parts) + "."


def _revenue_reference(scenarios: dict) -> str:
    """Revenue reference in $B for the severity-scaling sentence."""
    ref = scenarios.get("revenue_reference_usd", 1_000_000_000.0)
    return f"{float(ref) / 1e9:g}"


@lru_cache(maxsize=1)
def explain_model_mechanics() -> ModelMechanics:
    """Return the internally developed model's methodology, in four sections.

    Reads only the config files (never modifies them) and returns a
    ``ModelMechanics`` dataclass.  Call ``.sections()`` for the dict form or
    ``.full_text()`` for a client-ready paragraph.  Cached: the config is
    immutable per run, and the same explanation must be reproducible.
    """
    scoring = _load_yaml("scoring_weights.yaml")
    scenarios = _load_yaml("scenarios.yaml")
    simulation = _load_yaml("simulation_config.yaml")

    domains = scoring.get("domains", [])
    n_factors = sum(len(d.get("factors", [])) for d in domains)
    n_scenarios = len(scenarios.get("scenarios", {}))

    scoring_text = (
        f"the client's profile is mapped onto {n_factors} factor ratings across "
        f"{len(domains)} weighted domains, each factor scored 0-100 on a documented "
        "evidence scale (config/scoring_weights.yaml). The composite score is the "
        "weighted mean across the domains, and maps to a risk category: "
        + _category_bands_text(scoring)
        + " Factors whose score exceeds their domain average are reported as the "
        "risk drivers."
    )

    freq_text = (
        "each scenario has a baseline annual frequency lambda calibrated from "
        "public benchmarks (config/scenarios.yaml). The composite risk score "
        "scales those baselines through a log-linear link: "
        f"lambda_scaled = lambda_baseline * exp(k * (score - {SCORE_REFERENCE:.0f})/100). "
        "A score of 50 keeps the calibrated baselines unchanged; a higher score "
        "raises scenario frequencies, a lower score lowers them. Access controls "
        "(e.g. MFA, privileged access) feed the factors that move this "
        "frequency channel."
    )

    sev_text = (
        "per-event severity follows the configured lognormal tail per scenario "
        f"(config/scenarios.yaml), revenue-scaled as scale * (revenue / {_revenue_reference(scenarios)}bn)^exponent. "
        "Resilience controls (e.g. backups, DR testing, incident response) "
        "feed the factors that mitigate this severity channel."
    )

    sim_text = (
        f"a Monte Carlo engine simulates {simulation.get('default_years', 100_000):,} "
        "independent annual loss scenarios (config/simulation_config.yaml). Scenario "
        "frequencies are coupled through a copula, event counts and severities are "
        "drawn per scenario, and losses are aggregated per year -- including "
        "catastrophe-year clustering (~1 year in 20 carries a ~2x loss multiplier). "
        f"The result is the annual loss distribution across the {n_scenarios} scenarios, "
        "from which EAL, VaR 95/99, Expected Shortfall 95/99 and the 1-in-N-year PMLs "
        "are read directly."
    )

    return ModelMechanics(
        scoring_methodology=scoring_text,
        frequency_adjustments=freq_text,
        severity_adjustments=sev_text,
        simulation_methodology=sim_text,
    )
