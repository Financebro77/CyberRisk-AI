"""Validation suite: scoring engine.

Insurance relevance:
  - A firm with worse controls must ALWAYS out-score a firm with better
    controls (monotonicity).  If this fails, the score cannot rank clients
    for pricing / portfolio mix.
  - Category boundaries must be respected exactly (a 75.0 score -> High,
    a 75.1 -> Critical); a misplaced boundary mis-buckets clients and
    changes the insurance recommendation the agent produces.
  - The score must be independent of HOW weights are scaled (only their
    ratios matter) -- the calibration interface should not let a global
    weight renormalisation silently change rankings.
  - Risk drivers are the factors that need intervention; they must track
    which inputs actually move the score.
"""

from __future__ import annotations

import numpy as np
import pytest

from cyberrisk.scoring import CompanyProfile, compute_score

from . import make_profile


def _all_factor_keys(weights) -> list[str]:
    return [f.key for d in weights.domains for f in d.factors]


def _profile_with_all(weights, value: float) -> CompanyProfile:
    return make_profile({k: value for k in _all_factor_keys(weights)})


# ---------------------------------------------------------------- monotonicity
def test_worse_profile_outscores_better(weights):
    """Monotonicity: worse controls -> strictly higher composite."""
    low = compute_score(_profile_with_all(weights, 20.0), weights)
    high = compute_score(_profile_with_all(weights, 80.0), weights)
    assert high.composite_score > low.composite_score


def test_monotonicity_is_strict_for_any_single_factor(weights):
    """Raising ONE factor must never lower the composite (elementwise)."""
    keys = _all_factor_keys(weights)
    base = {k: 50.0 for k in keys}
    r_base = compute_score(make_profile(base), weights).composite_score
    for k in keys:
        bumped = dict(base)
        bumped[k] = 95.0
        r_bumped = compute_score(make_profile(bumped), weights).composite_score
        assert r_bumped >= r_base, f"factor {k} broke monotonicity"


# ---------------------------------------------------------------- category bands
def test_category_band_boundaries(weights):
    """Score exactly on a boundary maps to the band that includes it."""
    for band in weights.category_bands:
        max_score = float(band["max_score"])
        cat = band["category"]
        profile = _profile_with_all(weights, max_score)
        scored = compute_score(profile, weights)
        # all factors at the same value -> composite equals that value
        assert scored.composite_score == pytest.approx(max_score, abs=0.01)
        assert scored.risk_category == cat


def test_just_above_boundary_goes_to_next_band(weights):
    """A hair above a boundary must move to the next category."""
    for band in weights.category_bands[:-1]:
        max_score = float(band["max_score"])
        profile = _profile_with_all(weights, max_score + 0.1)
        scored = compute_score(profile, weights)
        assert scored.composite_score > max_score
        assert scored.risk_category != band["category"]


# ---------------------------------------------------------------- weight invariance
def test_score_invariant_to_global_weight_scaling(weights):
    """Scaling ALL weights by a constant must not change the composite.

    Only the RELATIVE weights matter.  This guards against the calibration
    interface accidentally renormalising weights and shifting scores.
    """
    base = compute_score(make_profile({k: 60.0 for k in _all_factor_keys(weights)}), weights)

    scaled_domains = [
        d.model_copy(update={"weight": d.weight * 2.0}) for d in weights.domains
    ]
    # also scale each factor weight to keep intra-domain ratios identical
    scaled_domains = [
        d.model_copy(
            update={
                "factors": [f.model_copy(update={"weight": f.weight * 3.0}) for f in d.factors]
            }
        )
        for d in scaled_domains
    ]
    scaled_weights = weights.model_copy(update={"domains": scaled_domains})
    rescaled = compute_score(make_profile({k: 60.0 for k in _all_factor_keys(weights)}), scaled_weights)
    assert rescaled.composite_score == pytest.approx(base.composite_score, abs=1e-9)


# ---------------------------------------------------------------- driver detection
def test_risk_drivers_identify_outlier_factor(weights):
    """The single worst factor in an otherwise-good domain must be flagged."""
    d0 = weights.domains[0]
    scores = {k: 20.0 for k in _all_factor_keys(weights)}
    scores[d0.factors[0].key] = 95.0  # one standout weak factor
    scored = compute_score(make_profile(scores), weights)
    assert d0.factors[0].key in scored.risk_drivers


# ---------------------------------------------------------------- composite exactness
def test_composite_is_weighted_domain_mean(weights):
    """Composite = weighted mean of domain scores (renormalised over present)."""
    keys = _all_factor_keys(weights)
    scores = {k: float(i % 100) for i, k in enumerate(keys)}
    scored = compute_score(make_profile(scores), weights)
    present = [
        d for d in weights.domains
        if any(f.key in scores for f in d.factors)
    ]
    w = sum(d.weight for d in present)
    expected = sum(d.weight * scored.domain_scores[d.key] for d in present) / w
    assert scored.composite_score == pytest.approx(expected, abs=1e-9)


def test_empty_profile_returns_neutral(weights):
    """No data -> neutral 50 (neither low nor high risk)."""
    scored = compute_score(make_profile({}), weights)
    assert scored.composite_score == 50.0


def test_missing_single_domain_renormalises(weights):
    """Dropping one whole domain must not bias the composite to 0/100."""
    keys = _all_factor_keys(weights)
    dropped = {k: v for k, v in zip(keys, np.linspace(10, 90, len(keys)))}
    # drop the first domain's factors
    for f in weights.domains[0].factors:
        dropped.pop(f.key, None)
    scored = compute_score(make_profile(dropped), weights)
    assert 0 <= scored.composite_score <= 100
    # dropped domain still reports a neutral domain score (no NaN)
    assert scored.domain_scores[weights.domains[0].key] == 50.0


def test_score_bounded_and_valid(weights):
    """Composite always in [0,100] for any valid input."""
    keys = _all_factor_keys(weights)
    rng = np.random.default_rng(0)
    for _ in range(5):
        scores = {k: float(rng.uniform(0, 100)) for k in keys}
        scored = compute_score(make_profile(scores), weights)
        assert 0.0 <= scored.composite_score <= 100.0
        assert scored.risk_category in {"Low", "Medium", "High", "Critical"}
