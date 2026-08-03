# Model Improvement Roadmap — CyberRiskAI Loss Engine

**Role:** senior actuarial model developer, cyber risk & insurance capital
**Basis:** first validation cycle (see `reports/model_validation_report.md`)
**Validated baseline (500k-year run, 7 scenarios, $1.0bn revenue, seed 20240817):**
EAL **$4.96M** · VaR99 **$34.2M** · ES99 **$53.6M** · ES99/EAL **10.8×** · Hill α **2.64** · Gaussian-copula dependence uplift on ES99 **+8%**
Analytic EAL anchor: **$4.95M** (0.2% from simulated)

> **STATUS: Phases 1, 2 & 3 complete.** Phase 1 = return-period PML + Student-t copula.
> Phase 2 = credibility + parameter-uncertainty 90% bands.
> Phase 3 = NegBin burstiness + catastrophe-year event clustering.
> 196 tests green. See `model_validation_report.md` §6, §7 & §8.
> **Remaining (stretch):** severity revalidation on claims data; regime/systemic index.

---

## 1. Model Gap Analysis

| # | Finding | Current state | The gap | Severity | Effort | Data need | Phase |
|---|---|---|---|---|---|---|---|
| 1 | **Dependence** | One-factor Gaussian copula (loadings 0.40–0.70) | Gaussian has **zero upper-tail dependence** (λ_U → 0 as u→1); measures only 8% ES99 uplift, but cyber is contagion-correlated (ransomware-as-a-service, shared clouds, MOVEit/SolarWinds-class supply-chain) | **High** | Med | None — ν set by judgement + sensitivity sweep | **1** |
| 2 | **Parameter uncertainty** | Point estimates for all λ, μ, σ, loadings | No confidence band on ES99; no credibility blending of firm-specific vs sector-prior calibration | **High** | Med–High | Benchmark/mock resampling; firm claims if available | **2** |
| 3 | **PML definition** | `max_single_year` reported | Statistically unstable: grows $73M→$397M across 1k→500k years; not a population risk measure | Med (defensibility) | **Low** | None | **1** |
| 4 | **Frequency** | Poisson | Var=Mean assumption; real single-firm counts over-dispersed (bursts) | Med | Low | Defensible dispersion estimate | **2** |
| 5 | **Severity scaling** | `revenue^exp` (exp 0.55–0.80) | Driver relationship unvalidated against claims; ignores sector, margin, data sensitivity, contractual exposure | Med–High | High | Claims/benchmark by sector (IBM CODB, licensed Advisen/Cyence) | **3** |
| 6 | **Event clustering** | Independent annual events | No within-year severity clustering in catastrophe years; annual aggregate tail understated at deep quantiles | Med–High (deep tail) | High | Hard to source; judgement + scenario work | **3** |

**Guiding principle for prioritisation:** *correct systematic bias before quantifying residual uncertainty, and only spend effort on changes that move the client decision (limits, retention, premium) defensibly.* Issues 1 and 3 fail the model on bias and on *communicability* respectively, and both are cheap relative to their value.

---

## 2. Recommended Implementation Order

### Phase 1 — High-impact improvements (correct the tail; get to defensible numbers)
1. **Return-period PML basis (P99.0 / P99.5 / P99.9)** — replace `max_single_year` in metrics/reporting with 1-in-100 / 1-in-200 / 1-in-1000 quantiles + bootstrap SE. Zero model risk, immediate defensibility, and required before any new tail numbers are quoted.
2. **Student-t copula dependence model (Option A)** — swap the copula's uniform generator for the t-version while preserving the `(n_scenarios, n_years)` uniform-grid contract. Default ν = 5 with sensitivity sweep ν ∈ {3, 5, 10, ∞}. Chunk-stability / reproducibility design carries over unchanged.
3. **Re-run the validation harness** — old-vs-new comparison of ES99 / P99.5 / P99.9; quantify the uplift; update the validation report.

### Phase 2 — Advanced enhancements (quantify uncertainty; thicken frequency) — DONE
4. ✅ **Parameter uncertainty / credibility layer (Option B)** — `credibility.py` (limited-fluctuation Z=T/(T+K) blending firm history vs baseline) + `uncertainty.py` (200 perturbed runs, median + 90% band on EAL/VaR/ES/PML). Bands widen with tail depth — ES99 ±135% rel width vs EAL ±69%. See `model_validation_report.md` §7.
5. **Negative-binomial frequency** with a defensible dispersion parameter (engine already supports it; the work is choosing and documenting dispersion, not coding).
6. **Severity-driver sensitivity study** — document how EAL/VaR/ES respond to the revenue exponents and to alternative severity models; do NOT re-calibrate yet (that needs Phase 3 data).

### Phase 3 — Frequency & clustering realism — DONE
7. ✅ **Negative-binomial frequency (burstiness)** — `freq_dispersion` (Var/Mean) per scenario; all 7 scenarios on NegBin, dispersions 1.5–2.0. Mean preserved, tail thickened.
8. ✅ **Event clustering (catastrophe years)** — `catastrophe_probability` × `catastrophe_multiplier` (clamped ≥ 1). ES99 +12.5%, P99.9 +17.7%, EAL +5.1%. See `model_validation_report.md` §8.

### Phase 4 — Future research (data-driven refinement) — STRETCH
9. **Severity revalidation** on sector claims data (IBM CODB by sector, or licensed Advisen/Cyence event tables).
10. **Regime-switching / systemic-cyber index** — peace vs ransomware-campaign years; portfolio-level analysis.
11. *(Stretch)* heavy-tailed factor model and a systemic-cyber index for portfolio-level analysis.

---

## 3. Expected Impact on Model Outputs and Insurance Recommendations

Directional estimates, to be confirmed by re-validation. EAL is unaffected by any change that preserves marginals (copula, NegBin-mean-preserving, clustering) — this is why EAL is the stable, trustworthy headline.

| Change | EAL | VaR99 | ES99 | PML (P99.9) | Insurance recommendation impact |
|---|---|---|---|---|---|
| Return-period PML | 0 | 0 | 0 | becomes a stable statistic | Limits quoted on a 1-in-N basis — matches how a broker actually sizes limits; removes the misleading single-max figure |
| **Student-t copula (A)** | ~0 | **+5–12%** | **+10–20%** | **+15–30%** | Higher recommended limits and more tail loading in pricing; the underinsured-tail error is reduced |
| Uncertainty/credibility (B) | ~0 (adds band) | band | **90% band ≈ ±30–50%** around point | band | Limits given as a defensible range; supports "X% confidence retained loss ≤ Y% of revenue" capital-style statements |
| NegBin frequency | 0 | +3–8% | +5–12% | +8–15% | Modest tail uplift; higher premium basis |
| Severity revalidation | ± (data-driven) | ± | ± | ± | Re-weights scenario dominance; may shift which drivers matter |
| Event clustering | 0 | +10–20% | +20–40% (deep) | +30–60% | Materially higher catastrophe PML; largest swing, but also the least validated — hence Phase 3 |

**Net message for a client:** Phase 1 lifts the *tail numbers that drive the recommendation*; Phase 2 puts *credible bands* around them; Phase 3 *grounds the drivers in data*.

---

## 4. Decision: Option A (Student-t copula) vs Option B (credibility/uncertainty)

### Recommendation: **Option A first** — implement the Student-t copula now, and defer the credibility/uncertainty layer to Phase 2 (where it wraps the corrected tail).

### Reasoning — from a Marsh/Aon cyber risk advisory perspective

**1. The Gaussian copula is a systematic bias, not noise.** We *measured* the dependence uplift at only +8% on ES99. Cyber's defining feature is that extreme events co-occur — the same campaign, the same breached vendor, the same cloud. A Gaussian copula structurally cannot produce that (λ_U = 0), so every tail figure is *low in expectation*. If we add uncertainty bands now, we would be drawing precise-looking intervals around a point that is itself biased downward on the exact quantity (tail PML) that drives limit recommendations. As an actuary: **correct the bias before you measure the variance around it.** A confidence band around a biased estimator is wasted precision — worse, it can be actively misleading in a client submission.

**2. Option A moves the number that changes the client's decision.** The decision a CFO cares about is "how much limit, at what retention, for what premium." That decision is driven by return-period PML and ES — precisely what the copula understates. Option B, by contrast, changes the *language* (point → range) but not the point estimate itself. In a brokerage, the defensible *point* comes first; the band refines it.

**3. Option A is contained and inherits the validation design.** The engine consumes only the uniform grid from the copula, so the swap is isolated to `copulas.py`, and the chunk-stability/reproducibility machinery (already proven in validation) carries over untouched. We can re-run the harness for an old-vs-new comparison within one working session. Option B is a larger build (bootstrap/Bayesian machinery, credibility formulas, more communication surface) and is better attempted against an already-corrected baseline.

**4. Option B actually gets *more* valuable after A.** ν (the t-copula degrees of freedom) becomes a parameter to band in the uncertainty layer. Doing A first means Phase 2's credibility analysis covers the complete parameter set — including the new one. Sequencing A→B is the coherent order; B is the natural first item of Phase 2, not a rival to A.

**5. The error direction matters for a broker.** Under-recommending limits is the worse failure mode: the client is underinsured precisely in the catastrophe scenarios that sink firms, and the broker's professional liability runs in that direction. Even if ν is judgment-set (ν=5 default, sweep ν∈{3,5,10,∞}), the uplift direction is unambiguous and the sensitivity range can be reported honestly — which is itself a partial answer to the uncertainty question.

### Honest counterargument, and why it does not change the call
Option B is *cheaper* and answers the governance/regulatory push for "ranges." If the immediate consumer of the model were a risk committee demanding an uncertainty band tomorrow, B would win on speed. But the primary consumer here is the advisory/limit-setting workflow, whose output is wrong in expectation under the Gaussian copula. That tips it decisively to A.

### RESOLVED — Option A implemented (Phase 1)
Option A (Student-t copula) was chosen and is now **implemented and re-validated**:
- `copulas.py` gained `student_t_uniforms()` + `copula_uniforms()` dispatcher.
- Config defaults to `copula_model: student_t`, `copula_nu: 5.0`.
- Copula-level upper-tail dependence χ(0.99) = **2.41×** the Gaussian value; EAL invariant (ratio 1.0000).
- Return-period PML (P99.0/P99.5/P99.9) + bootstrap SE implemented and stable (P99.9 SE = 1.7%).

**Phase 2 (Option B, the natural next step):** parameter-uncertainty / credibility layer — now bands the corrected tail, including the new ν parameter.

---

## 5. Sequencing & Dependencies

```
Phase 1
  P1.1 Return-period PML        (no dependency; pure win)
  P1.2 Student-t copula         (depends on P1.1 for a clean before/after)
  P1.3 Re-validation            (compares old vs new ES99 / P99.5 / P99.9)
          │
Phase 2
  P2.1 Uncertainty/credibility  (depends on P1.2 — bands the corrected tail, incl. ν)
  P2.2 NegBin frequency         (independent; needs dispersion decision)
  P2.3 Severity sensitivity     (documentation; informs P3.1)
          │
Phase 3
  P3.1 Severity revalidation    (needs claims data)
  P3.2 Event clustering         (largest tail swing; least validated)
  P3.3 Stretch: regime / systemic index
```

Each phase ends with a validation-harness run and a report update — the engine's reproducibility contract makes every change auditable against the baseline.

---

## 6. Validation approach per phase

- **Phase 1:** re-run `run_model_validation.py`; report ES99/P99.5/P99.9 before-vs-after; confirm EAL unchanged (marginals preserved) and Hill α / LEC shape updated. Confirm chunk-stability still holds with the t-copula.
- **Phase 2:** bootstrap/perturbation band on ES99 and PML; sensitivity of the band to the dispersion parameter and to ν; credibility weight sensitivity.
- **Phase 3:** refit severity against claims data; back-test the clustering model on known campaign years; document the PML swing.
