"""CyberRisk quantitative engine (re-export shim).

The canonical engine lives in the ``cyberrisk`` package (``src/cyberrisk/``)
and is the installed, import-stable home of the numerical core.  This package
provides a convenience namespace so the code can also be addressed as
``engine.*`` (matching the repository's logical structure) without moving or
duplicating any code.

    from engine.simulation import simulate      # == cyberrisk.simulation.simulate
    from engine.scoring import compute_score    # == cyberrisk.scoring.compute_score

The canonical modules re-exported here:

    audit, benchmark, calibration, copulas, credibility, frequency,
    metrics, policy_transform, privacy, scoring, sensitivity, severity,
    simulation, uncertainty
"""

from __future__ import annotations

from cyberrisk import (  # noqa: F401
    count_distributions,
    compute_metrics,
    dependent_uniforms,
    rvs_counts,
    rvs_severities,
    severity_distributions,
    simulate,
    student_t_uniforms,
)
