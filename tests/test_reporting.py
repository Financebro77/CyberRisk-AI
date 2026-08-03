"""Reporting tests (Phase 4)."""

from pathlib import Path

import numpy as np

from cyberrisk.calibration import load_config
from cyberrisk.reporting.excel import write_report
from cyberrisk.simulation import simulate

REPO = Path(__file__).parent.parent


def test_write_report_creates_workbook(tmp_path):
    cfg = load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )
    result = simulate(cfg, n_years=5_000)
    out = tmp_path / "report.xlsx"
    path = write_report(result, out_path=out)
    assert Path(path).exists()
    assert out.suffix == ".xlsx"
    assert out.stat().st_size > 0


def test_write_report_with_policy(tmp_path):
    from cyberrisk.policy_transform import (
        PolicyStructure,
        transform_events_to_years,
    )

    cfg = load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )
    result = simulate(cfg, n_years=5_000, return_events=True)
    policy = PolicyStructure(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=5_000_000.0,
    )
    ev = result.events
    pm = transform_events_to_years(
        ev[:, 2], ev[:, 0], ev[:, 1],
        n_years=result.years,
        scenario_keys=result.scenario_keys,
        policy=policy,
    )
    out = tmp_path / "report_with_policy.xlsx"
    path = write_report(result, policy_metrics=pm, out_path=out)
    assert Path(path).exists()
