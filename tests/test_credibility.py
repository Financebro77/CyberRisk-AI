"""Credibility module tests (Phase 2)."""

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from cyberrisk.calibration import load_config
from cyberrisk.credibility import (
    FirmExperience,
    apply_credibility,
    blend_lambda,
    credibility_weight,
)

REPO = Path(__file__).parent.parent


def _config():
    return load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )


def test_credibility_weight_half_at_threshold():
    """At T == K the firm and the baseline each get 50% weight."""
    assert credibility_weight(3.0, 3.0) == pytest.approx(0.5)
    assert credibility_weight(5.0, 5.0) == pytest.approx(0.5)


def test_credibility_weight_monotonic():
    """More experience -> more credibility (never decreases)."""
    zs = [credibility_weight(t, k=3) for t in (1, 2, 3, 5, 10, 20)]
    assert all(b >= a for a, b in zip(zs, zs[1:]))


def test_credibility_weight_bounded_under_one():
    """Z is always in [0, 1) -- never reaches full firm credibility."""
    assert 0.0 <= credibility_weight(0, 3) < 1.0
    assert 0.0 <= credibility_weight(1000, 3) < 1.0  # large but < 1
    assert credibility_weight(0, 3) == 0.0


def test_credibility_weight_invalid():
    with pytest.raises(ValueError):
        credibility_weight(-1, 3)
    with pytest.raises(ValueError):
        credibility_weight(5, 0)


def test_blend_lambda_convex():
    """Blend is a convex combination: lies strictly between the two rates."""
    lam_firm, lam_base = 0.2, 0.8
    for z in (0.0, 0.3, 0.7, 0.999):
        blended = blend_lambda(lam_firm, lam_base, z)
        assert min(lam_firm, lam_base) <= blended <= max(lam_firm, lam_base)
    # boundary
    assert blend_lambda(0.2, 0.8, 0.0) == pytest.approx(0.8)  # baseline only
    assert blend_lambda(0.2, 0.8, 0.999) == pytest.approx(0.2, abs=0.001)


def test_blend_invalid_z():
    with pytest.raises(ValueError):
        blend_lambda(0.2, 0.8, 1.0)
    with pytest.raises(ValueError):
        blend_lambda(0.2, 0.8, -0.1)


def test_firm_experience_lambda():
    """lambda_firm = incidents / years."""
    exp = FirmExperience(scenario_key="breach", incidents=2, years=4)
    assert exp.lambda_firm == pytest.approx(0.5)
    clean = FirmExperience(scenario_key="breach", incidents=0, years=5)
    assert clean.lambda_firm == 0.0


def test_firm_experience_validation():
    with pytest.raises(ValidationError):
        FirmExperience(scenario_key="breach", incidents=-1, years=5)
    with pytest.raises(ValidationError):
        FirmExperience(scenario_key="breach", incidents=0, years=0)


def test_apply_credibility_blends_correctly():
    cfg = _config()
    exp = [
        FirmExperience(scenario_key="breach", incidents=1, years=5),
        FirmExperience(scenario_key="bec", incidents=0, years=5),
    ]
    res = apply_credibility(cfg, exp, k=3)
    z = credibility_weight(5, 3)  # 0.625
    for s in res.config.scenarios:
        if s.key == "breach":
            expected = z * (1 / 5) + (1 - z) * 0.75
            assert s.frequency.lambda_annual == pytest.approx(expected)
        elif s.key == "bec":
            expected = z * 0.0 + (1 - z) * 1.10
            assert s.frequency.lambda_annual == pytest.approx(expected)
        else:
            # untouched scenarios keep baseline
            assert s.frequency.lambda_annual == pytest.approx(
                next(x.frequency.lambda_annual for x in cfg.scenarios if x.key == s.key)
            )


def test_apply_credibility_annotations_and_weights():
    cfg = _config()
    exp = [FirmExperience(scenario_key="breach", incidents=1, years=5)]
    res = apply_credibility(cfg, exp, k=3)
    for s in res.config.scenarios:
        if s.key == "breach":
            assert "credibility_weight" in s.annotation
            assert "lambda_credible" in s.annotation
            assert float(s.annotation["credibility_weight"]) == pytest.approx(credibility_weight(5, 3))
    # untouched scenarios report weight 0
    assert res.weights_by_scenario["ransomware"] == 0.0
    assert res.weights_by_scenario["breach"] > 0.0


def test_apply_credibility_unknown_scenario_rejected():
    cfg = _config()
    with pytest.raises(ValueError):
        apply_credibility(cfg, [FirmExperience(scenario_key="nope", incidents=1, years=5)], k=3)


def test_clean_record_lowers_rate_but_not_to_zero():
    """A clean record (0 incidents) lowers the rate but never to zero."""
    cfg = _config()
    res = apply_credibility(cfg, [FirmExperience(scenario_key="bec", incidents=0, years=5)], k=3)
    for s in res.config.scenarios:
        if s.key == "bec":
            assert s.frequency.lambda_annual > 0.0  # (1-Z)*baseline > 0
            assert s.frequency.lambda_annual < 1.10  # lower than baseline
