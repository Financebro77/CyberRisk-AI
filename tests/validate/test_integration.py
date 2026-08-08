"""End-to-end integration: score -> simulation -> metrics -> policy.

The single most important validation: a firm with better cyber controls
must BOTH out-score a weaker firm AND carry lower modelled loss (EAL, VaR,
ES) under an identical policy structure.  If the score says one thing and
the loss model says another, the two halves of the platform disagree and
the consultant recommendation would be incoherent.
"""

from __future__ import annotations


from cyberrisk.metrics import compute_metrics
from cyberrisk.policy_transform import PolicyStructure, transform_events_to_years
from cyberrisk.scoring import compute_score
from cyberrisk.simulation import simulate


def _all_keys(weights):
    return [f.key for d in weights.domains for f in d.factors]


def _profile_with(weights, value):
    from cyberrisk.scoring import CompanyProfile

    return CompanyProfile(firm_name="test", factor_scores={k: value for k in _all_keys(weights)})


def test_good_firm_scores_better_and_losses_less(weights, config):
    good = compute_score(_profile_with(weights, 20.0), weights)
    weak = compute_score(_profile_with(weights, 80.0), weights)
    assert good.composite_score < weak.composite_score

    # identical simulation engine, only the score differs
    m_good = compute_metrics(simulate(config, n_years=100_000, score=good.composite_score))
    m_weak = compute_metrics(simulate(config, n_years=100_000, score=weak.composite_score))
    assert m_good.eal < m_weak.eal
    assert m_good.var_99 < m_weak.var_99
    assert m_good.es_99 < m_weak.es_99


def test_policy_transfer_preserves_good_vs_weak_ordering(weights, config):
    """Under an identical policy, the good firm retains AND transfers less."""
    good = compute_score(_profile_with(weights, 20.0), weights)
    weak = compute_score(_profile_with(weights, 80.0), weights)

    policy = PolicyStructure(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=5_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=20_000_000.0,
    )

    def retained_eal(score):
        result = simulate(config, n_years=80_000, score=score, return_events=True)
        ev = result.events
        out = transform_events_to_years(
            ev[:, 2], ev[:, 0], ev[:, 1],
            n_years=result.years,
            scenario_keys=result.scenario_keys,
            policy=policy,
        )
        return out["retained"].mean(), out["transferred"].mean()

    g_ret, g_tra = retained_eal(good.composite_score)
    w_ret, w_tra = retained_eal(weak.composite_score)
    assert g_ret < w_ret
    assert g_tra < w_tra


def test_risk_drivers_align_with_loss_drivers(weights, config):
    """A firm weak on high-weight factors drives higher loss than weak on low-weight."""
    from cyberrisk.scoring import CompanyProfile

    keys = _all_keys(weights)
    # neutral everywhere
    base = {k: 50.0 for k in keys}
    # degrade ONLY the access_control domain (weight 0.20)
    weak_access = dict(base)
    for f in weights.domains[2].factors:
        weak_access[f.key] = 90.0

    score_access = compute_score(CompanyProfile(firm_name="a", factor_scores=weak_access), weights)
    score_neutral = compute_score(CompanyProfile(firm_name="b", factor_scores=base), weights)

    m_access = compute_metrics(simulate(config, n_years=80_000, score=score_access.composite_score))
    m_neutral = compute_metrics(simulate(config, n_years=80_000, score=score_neutral.composite_score))
    assert m_access.eal > m_neutral.eal
