# Model Methodology

This document explains **how the numbers are produced** — the statistical
methods behind the risk score, expected annual loss, tail measures, and
insurance analysis, plus the explicit assumptions the model makes.

> CyberRisk AI produces **probabilistic risk estimates, not guaranteed
> predictions**. The model is deterministic when seeded, but its outputs are
> only as good as the inputs and the calibration assumptions below. Better
> input data reduces uncertainty; it does not remove it.

---

## 1. Risk scoring

### 1.1 The 18-factor model

The engine scores a company's cyber posture across **18 factors**, grouped
into weighted domains. Every factor maps a qualitative or quantitative control
rating to a **0–100 score (higher = higher risk)** via a configured
`evidence_scale`, keeping the model explainable for client communication.

The factor set covers (configured in `config/scoring_weights.yaml`):

| Domain | Example factors |
|---|---|
| **External exposure** | external attack surface, industry targeting, patch cadence |
| **Access & identity** | MFA coverage, privileged access management, SSO |
| **Endpoint & data** | EDR coverage, data sensitivity, data-at-rest protection |
| **Resilience** | backup frequency, incident response readiness |
| **Governance** | vendor/contractual security, supply-chain visibility, prior incidents |

### 1.2 Scoring method

For each domain:

```
domain_score = Σ(factor_weight × factor_score) / Σ(factor_weight)   # over provided factors
```

- Weights are **renormalised over the factors actually provided**, so a
  partial profile still yields a 0–100 domain score.
- A domain with no provided factors defaults to a **neutral 50**.

The **composite score** is the weighted mean of the domain scores,
re-normalised over the domains that have at least one scored factor. If
nothing is provided, the composite defaults to 50.

### 1.3 Risk categories

The composite score maps to a category via `category_bands` in
`config/scoring_weights.yaml`:

| Score | Category |
|---|---|
| 0 – 25 | **Low** |
| 25 – 50 | **Medium** |
| 50 – 75 | **High** |
| 75 – 100 | **Critical** |

### 1.4 Risk drivers

Factors whose score exceeds the domain average are flagged as **risk
drivers** — the places where risk concentrates and remediation moves the
score most.

### 1.5 Linking the score to loss

The composite score feeds the loss engine through a **log-linear frequency
link**: a worse score raises the scenario frequency parameters, which in turn
raises expected loss and tail risk. The exact transform lives in
`scoring.py` / `simulation.py` and is part of the auditable calibration.

---

## 2. Expected Annual Loss (EAL)

EAL is the **mean of the simulated annual loss distribution**:

```
EAL = (1 / N) Σ_t  total_loss_t
```

where `N` is the number of simulated years (default 100,000) and
`total_loss_t` is the aggregate cyber loss in simulated year `t`.

- EAL is the **headline number for pricing** — the average amount the firm
  should expect to lose per year from cyber events.
- It is also computed **per scenario** (`aal_by_scenario`), so the model can
  report that, say, ransomware is 40% of expected annual loss.

**Interpretation:** EAL is an average, so a single severe tail year can pull
it up. It is *not* a worst case — that is what VaR / ES measure.

---

## 3. Value-at-Risk (VaR)

VaR is a **loss threshold** at a given confidence level:

```
VaR_q  =  q-th sample quantile of the annual loss distribution
```

The engine reports **VaR 95** and **VaR 99**:

- **VaR 95** — the loss exceeded with 5% probability in any year (a 1-in-20
  event).
- **VaR 99** — the loss exceeded with 1% probability in any year (a 1-in-100
  event).

In plain terms, if VaR 99 is $27M, the firm's loss **stays below $27M in 99
of 100 modelled years** — and exceeds it in the remaining 1.

> VaR is a **threshold**, not a probability and not a point-mass prediction.
> It does not say *how bad* the worst 1% of years are — that is ES's job.

---

## 4. Expected Shortfall (ES)

Expected Shortfall is the **conditional tail mean** — the average loss *given
that* the loss exceeds the VaR threshold:

```
ES_q  =  mean(total_loss  |  total_loss  ≥  VaR_q)
```

The engine reports **ES 95** and **ES 99**:

- **ES 99** — the *average loss in the worst 1% of years*. For a firm with
  VaR 99 of $27M and ES 99 of $43M, the average loss across the worst 1% of
  years is $43M — substantially above the threshold.

**Why ES matters:** VaR hides the shape of the tail. Two firms can have the
same VaR 99 but very different ES 99 if one has a fatter tail. ES is the
measure that matters for **capital allocation and reinsurance** — it captures
how bad the tail really is.

### A worked comparison (from the example assessment)

| Metric | Value | Meaning |
|---|---|---|
| EAL | $3.62M | Average annual loss |
| VaR 99 | $27.42M | Exceeded in 1% of years |
| ES 99 | $42.71M | Average loss in the worst 1% of years |

The gap between VaR 99 ($27M) and ES 99 ($43M) signals a **fat tail**: when a
1-in-100 event happens, it tends to be far worse than the threshold itself.

---

## 5. Insurance analysis

The insurance module (`policy_transform.py`) projects every simulated year of
loss through the policy structure to compute **what the client retains** vs
**what the insurer pays**.

### 5.1 Policy structure

| Term | Meaning |
|---|---|
| `per_occurrence_deductible` | Amount the insured carries per event before cover |
| `per_occurrence_limit` | Maximum insurer payout per event (`None` = unlimited) |
| `annual_aggregate_deductible` | Deductible on the year's total transferred losses |
| `annual_aggregate_limit` | Maximum insurer payout per policy year |
| `coinsurance` | Share of the above-deductible amount the insured keeps (0.10 = keeps 10%) |
| `sub_limits` | Per-scenario caps (e.g. ransomware sub-limit) |

### 5.2 The mechanics

**Per occurrence** (each event, scenario `s`):

```
insurer = min(event_loss, sub_limit[s])
insurer = max(insurer - occurrence_deductible, 0)
insurer = insurer × (1 - coinsurance)
insurer = min(insurer, occurrence_limit)         # if set
retained = event_loss - insurer
transferred = insurer
```

**Annual aggregate** (per policy year — the aggregate resets each year):

```
after_agg_deduct = max(year_transferred - agg_deductible, 0)
after_agg_limit  = min(after_agg_deduct, agg_limit)      # if set
final_transferred = after_agg_limit
final_retained = year_retained + (year_transferred - after_agg_limit)
```

Any amount not paid (deductible shortfall or above the aggregate limit) is
**pushed back to retained loss** — so residual exposure is always real.

### 5.3 What it reports

For each structure, the engine returns:

- **Ground-up loss** — total loss before insurance (EAL, tail quantiles).
- **Insurance response** — what the insurer pays, the retained amount, and
  the probability the annual limit is exhausted.
- **Client retained loss** — gross loss minus insurance recovery =
  **residual uncovered exposure** at the P99.9 tail.
- **Evaluation** — a plain-language read of whether the structure is adequate.

The `insurance/optimise` route additionally sweeps a grid of limit/retention
combinations over the *same cached simulation* and recommends the structure
that best closes the residual-exposure gap per dollar of additional limit.

---

## 6. Model assumptions

These are the explicit, auditable assumptions the model makes. They live in
`config/scenarios.yaml` and `config/simulation_config.yaml` and should be
reviewed as calibration inputs, not facts.

### 6.1 Frequency & severity

- **Frequency** is modelled per scenario with a **negative-binomial** count
  distribution (mean `λ` per year), allowing over-dispersion relative to a
  pure Poisson.
- **Severity** is modelled with a **heavy-tailed lognormal** distribution per
  scenario, calibrated to mock claim data (e.g. ransomware E[S] ≈ $1.1M, BEC
  ≈ $420k, supply-chain ≈ $1.16M with a very heavy tail).
- The seven scenarios cover data breach, ransomware, BEC, cloud outage,
  business interruption, supply chain, and OT/physical.

### 6.2 Dependence

- Scenario frequencies are linked by a **Student-t copula** (ν = 5) — the
  default — which adds **genuine upper-tail dependence**: correlated bad
  years. Setting `copula_model: gaussian` removes upper-tail dependence
  (Phase-1 fallback).

### 6.3 Catastrophe ("catastrophe years") clustering

- **~1 year in 20** is a catastrophe year (`catastrophe_probability: 0.05`).
- In those years, all losses are multiplied by a mean **2×** factor with 50%
  coefficient of variation.
- This models the real-world phenomenon that when several things go wrong at
  once, everything costs more.

### 6.4 Determinism & Monte Carlo noise

- The engine is **deterministic when seeded** (`seed: 20240817` default):
  the same profile always yields the same score, distribution, and metrics.
- **Monte Carlo noise** is quantified by bootstrap standard errors
  (`metrics.bootstrap_se`) on EAL, VaR, ES, and PML. Heavy-tailed annual
  losses need a sizeable sample for a stable ES99 / P99.9.

### 6.5 Parameter uncertainty & credibility

- `uncertainty.py` provides **parameter-uncertainty bands** around point
  estimates (a separate concern from Monte Carlo noise).
- `credibility.py` blends the **industry baseline** with a client's **own
  observed loss history** — a clean record improves the rate; a troubled
  record worsens it — while never discarding the sector prior entirely.

### 6.6 What the model does NOT assert

- It is **not a prediction of a specific future breach**.
- It is **not a guarantee** of loss, recovery, or insurer payment.
- Its outputs are **only as accurate as the calibration data and client
  inputs** — incomplete or low-quality inputs widen uncertainty.
- A single sample maximum is **not** reported as a PML; return-period PMLs
  (P99.0 / P99.5 / P99.9) are the statistically stable tail measures.

---

*Next: [deployment.md](deployment.md) for running it, or
[architecture.md](architecture.md) for how the pieces fit.*
