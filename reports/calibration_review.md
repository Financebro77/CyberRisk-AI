# Quantitative Model — Calibration & Assumption Audit

**Status:** review only — no code or config changed.
**Scope:** every parameter in `config/scenarios.yaml`, `config/simulation_config.yaml`, `config/uncertainty_config.yaml`, `config/calibration_benchmarks.csv`, and `config/scoring_weights.yaml` that carries an assumption.
**Grounded in:** the 500k-year validation run (EAL $4.96M · ES99 $53.6M · Hill α 2.64) from `reports/model_validation_report.md`.

---

## Part 1 — Parameter inventory: purpose, sources, confidence

### A. Scenario frequency (λ) — 7 parameters

| Scenario | λ | Purpose | Assumption/current source | Public benchmark sources | Confidence |
|---|---|---|---|---|---|
| breach | 0.75/yr | Baseline annual breach rate for a large firm | **Anchored** — DBIR 2025 "large firms disclose a breach in 12 months" | Verizon DBIR (annual), Hiscox Cyber Readiness, NetDiligence | **High** |
| ransomware | 0.40/yr | Baseline extortion rate | **Anchored** — Hiscox 2024 / DBIR 2025 ransomware rate | Hiscox, DBIR, Coalition Cyber Threat, Sophos State of Ransomware | **High** |
| BEC | 1.10/yr | Baseline BEC/wire-fraud rate | **Anchored** — FBI IC3 2024 | FBI IC3, DBIR, Mimecast, Agari | **High** (frequency) |
| cloud_outage | 0.50/yr | Baseline third-party/SaaS outage rate | **Partially anchored** — DBIR cloud outage rate; severity is mock | DBIR, Uptime Institute, Datadog outage reports | **Medium** |
| bi | 0.30/yr | Baseline business-interruption incident rate | **Judgement** — "NetDiligence BI share + mock claims layer" | NetDiligence, Allianz Risk Barometer, Aon | **Medium** |
| supply_chain | 0.25/yr | Baseline third-party compromise rate | **Judgement** — "SBOM-era breach class + mock" | DBIR (supply chain %), CISA, Kaseya/SolarWinds post-incident | **Low-Medium** |
| ot_physical | 0.10/yr | Baseline OT/ICS/physical incident rate | **Judgement** — ICS-CERT incident class, no real rate | ICS-CERT (CISA), Dragos, Mandiant, SANS | **Low** |

**Key finding:** only 3 of 7 λ values are truly benchmark-anchored. The `calibration_benchmarks.csv` (DBIR/Hiscox/IC3/ICS-CERT) supplies the values, but the **severity column of that CSV (IBM cost/record, NetDiligence ransom) is never wired into the engine** — it anchors λ only.

### B. Frequency dispersion (over-dispersion) — 7 parameters

| Parameter | Value | Purpose | Assumption | Sources | Confidence |
|---|---|---|---|---|---|
| breach dispersion | 1.5 | Burstiness (Var/Mean) of annual counts | **Judgement** — no empirical dispersion estimate | Actuarial cyber papers, insurer claims data, DBIR per-org counts | **Low** |
| ransomware dispersion | 2.0 | Campaign-bursty | **Judgement** | Sophos/Coalition per-org attack counts | **Low** |
| BEC dispersion | 1.5 | | **Judgement** | IC3 per-org complaint counts | **Low** |
| cloud_outage dispersion | 1.5 | | **Judgement** | Uptime Institute | **Low** |
| BI dispersion | 1.5 | | **Judgement** | — | **Low** |
| supply_chain dispersion | 2.0 | | **Judgement** | — | **Low** |
| OT dispersion | 1.5 | | **Judgement** | CISA | **Low** |

**This is the weakest frequency-layer assumption class** — the roadmap explicitly named it as "the work is choosing and documenting dispersion, not coding." Dispersion directly thickens the tail (ES99 +5–12% per the roadmap).

### C. Severity (scale, mu, sigma) — 21 parameters

| Scenario | scale | mu | sigma | Purpose | Assumption | Sources | Confidence |
|---|---|---|---|---|---|---|---|
| breach | $320k | 0.60 | 1.10 | Per-event loss ($) + tail weight | **ALL mock claims layer** — no real claims | IBM CODB (per-record), NetDiligence claims, HHS breach portal | **Low** |
| ransomware | $510k | 0.75 | 1.30 | | **mock** | NetDiligence (median ransom $150k — *different concept*), Sophos, Chainalysis | **Low** |
| BEC | $240k | 0.55 | 1.00 | | **mock** | IC3 (loss per complaint), FBI | **Low** |
| cloud_outage | $450k | 0.60 | 1.15 | | **mock** | Cloud outage cost studies | **Low** |
| BI | $380k | 0.70 | 1.20 | | **mock** | Allianz, NetDiligence BI | **Low** |
| supply_chain | $520k | 0.80 | 1.35 | | **mock** | Post-incident analyses (SolarWinds, MOVEit) | **Low** |
| ot_physical | $610k | 0.90 | 1.40 | | **mock** | Dragos, ICS-CERT | **Low** |

**This is the biggest gap in the model.** Every dollar the consultant quotes traces to severity, and every severity parameter is a documented mock. The validation report's Phase-3 priority #9 ("severity revalidation on sector claims data") is exactly this. The `severity_scale_cv=0.30` uncertainty band acknowledges it.

### D. Revenue exponents — 7 parameters

| Scenario | exponent | Purpose | Assumption | Sources | Confidence |
|---|---|---|---|---|---|
| breach | 0.60 | How severity scales with firm revenue | **Judgement** — "reasonable but unvalidated against claims" | IBM CODB by size, claims data | **Low** |
| ransomware | 0.60 | | **Judgement** | — | **Low** |
| BEC | 0.55 | | **Judgement** | — | **Low** |
| cloud_outage | 0.75 | | **Judgement** | — | **Low** |
| BI | 0.80 | | **Judgement** — highest, BI scales most with size | Allianz, claims | **Low** |
| supply_chain | 0.70 | | **Judgement** | — | **Low** |
| ot_physical | 0.70 | | **Judgement** | — | **Low** |

The single-exponent-per-scenario assumption ignores sector, margin mix, and data sensitivity. The roadmap flags this as "the driver relationship unvalidated against claims."

### E. Dependence (copula loadings) — 7 parameters

| Scenario | loading | Purpose | Assumption | Sources | Confidence |
|---|---|---|---|---|---|
| breach | 0.55 | Cross-scenario correlation in a bad cyber year | **Judgement** — "set by judgement + sensitivity sweep" | No direct public source; correlated-loss evidence is qualitative | **Low-Medium** |
| ransomware | 0.70 | | **Judgement** (highest — campaigns) | | **Low** |
| BEC | 0.40 | | **Judgement** | | **Low** |
| cloud_outage | 0.50 | | **Judgement** | | **Low** |
| BI | 0.55 | | **Judgement** | | **Low** |
| supply_chain | 0.65 | | **Judgement** | | **Low** |
| ot_physical | 0.60 | | **Judgement** | | **Low** |

Plus **copula_nu = 5.0** (Student-t d.o.f., default recommendation; sensitivity sweep ν∈{3,5,10,∞}). The roadmap explicitly notes the aggregate uplift is "modest at these λs" and residual uncertainty remains.

### F. Catastrophe-year (systemic) parameters — 3

| Parameter | Value | Purpose | Assumption | Sources | Confidence |
|---|---|---|---|---|---|
| catastrophe_probability | 0.05 | ~1-in-20 "everything costs more" year | **Judgement** | No empirical basis; qualitative | **Low** |
| catastrophe_multiplier_mean | 2.0 | Loss multiplier in those years | **Judgement** | Campaign-year analyses (MOVEit, SolarWinds) | **Low** |
| catastrophe_multiplier_cv | 0.5 | Uncertainty on the multiplier | **Judgement** | — | **Low** |

**This is the largest tail swing** (ES99 +12.5%, P99.9 +17.7%) and the **least validated** — the roadmap explicitly says "largest swing, but also the least validated." It's the single biggest deep-tail assumption.

### G. Score→λ link (elasticity) — 2

| Parameter | Value | Purpose | Assumption | Sources | Confidence |
|---|---|---|---|---|---|
| SCORE_REFERENCE | 50.0 | Score at which λ stays at baseline | **Design choice** — a 50-scored firm keeps calibrated λ | None (normalisation) | **High** (definitional) |
| k (score_k) | 1.0 | How strongly a composite score changes λ | **Judgement** — exp(k·(score−50)/100); k=1 is a coarse default | None; could calibrate from observed controls→frequency | **Medium** |

### H. Uncertainty-layer CVs — 5

| Parameter | Value | Purpose | Assumption | Confidence |
|---|---|---|---|---|
| lambda_cv | 0.30 | ±30% plausible on λ | **Judgement** — "deliberately modest" | **Medium** |
| severity_scale_cv | 0.30 | ±30% on severity scale | **Judgement** | **Medium** |
| severity_sigma_cv | 0.15 | ±15% on tail weight | **Judgement** — sigma CV is the biggest ES99/PML driver | **Medium** |
| loading_sd | 0.10 | ±0.10 on copula loadings | **Judgement** | **Medium** |
| copula_nu_sd | 1.0 | ±1 on t-d.o.f. | **Judgement** | **Medium** |

### I. Scoring weights + evidence scales — 6 domains, 18 factors

| Parameter | Value | Purpose | Assumption | Sources | Confidence |
|---|---|---|---|---|---|
| domain weights | threat 0.20, vuln 0.20, access 0.20, endpoint 0.15, third-party 0.15, governance 0.10 | Relative importance of exposure areas | **Judgement** — no empirical calibration to observed risk | NIST/CIS expert weighting, ISO 27001 mapping (framework→factor) | **Medium** |
| evidence scales | 18 factors, qualitative→0-100 | Map ratings to scores | **Judgement** — linear spacing by design | NIST CSF / CIS evidence categories | **Medium** |
| category_bands | 25/50/75/100 | Risk category thresholds | **Judgement** — arbitrary bands | No industry standard | **Medium** |

---

## Part 2 — Confidence separation

### ✅ High-confidence parameters (empirically anchored)

| Parameter | Basis |
|---|---|
| **breach λ** (0.75) | DBIR 2025 "large firms disclose a breach in 12 months" |
| **ransomware λ** (0.40) | Hiscox 2024 / DBIR 2025 ransomware rate |
| **BEC λ** (1.10) | FBI IC3 2024 complaint rate |
| **SCORE_REFERENCE** (50) | Definitional normalisation |
| **EAL** (the aggregate metric) | Analytic anchor matches simulated to 0.2% (validation §2) |
| **Return-period PML basis** | Bootstrap-stable, SE 1.7% on P99.9 (Phase 1) |

### 🟡 Medium-confidence parameters (partially anchored or defensible-judgement)

| Parameter | Basis / caveat |
|---|---|
| **cloud_outage λ** (0.50) | DBIR-anchored frequency, but severity is mock |
| **BI λ** (0.30) | NetDiligence share, but frequency is judgement |
| **score→λ elasticity k** (1.0) | Defensible default, no calibration |
| **domain weights / evidence scales / bands** | Expert-judgement; could map to NIST/CIS evidence |
| **uncertainty-layer CVs** | "Deliberately modest" judgement; internally consistent |
| **copula loadings** (0.40–0.70) | Judgement but sensitivity-swept; Student-t direction is unambiguous |

### 🔴 Low-confidence parameters (mock or pure judgement — the highest-value replacement targets)

| Parameter | Why |
|---|---|
| **All severity scale/mu/sigma (21)** | Mock claims layer; the dollar output rests on it |
| **Revenue exponents (7)** | "Reasonable but unvalidated against claims" (roadmap) |
| **Frequency dispersions (7)** | No empirical dispersion estimate; directly thickens the tail |
| **Catastrophe-year p/multiplier/CV (3)** | Least validated, largest tail swing |
| **OT λ** (0.10) | No real ICS-CERT rate, just an incident class |
| **supply_chain λ** (0.25) | "SBOM-era breach class + mock" |

---

## Part 3 — Calibration roadmap (what to replace first)

Ranking by **impact on the client decision × how replaceable it is with public/empirical data**.

| Priority | Assumption to replace | Current | Empirical replacement | Public data source | Why this order |
|---|---|---|---|---|---|
| **1** | **Breach severity** (scale/mu/sigma) | mock | Fit lognormal to real per-event breach costs | **IBM CODB by sector, NetDiligence Cyber Claims Study, HHS Breach Portal** | The dollar output the consultant quotes rests on it; the loader seam (`build_calibrated_config`) already supports severity ingestion — lowest-effort, highest-value |
| **2** | **Ransomware severity** | mock | Fit to ransom + extortion + response costs | **NetDiligence (detailed tables), Sophos State of Ransomware, Chainalysis** | Ransomware is the top tail driver; NetDiligence already has the numbers |
| **3** | **Revenue exponents** | 0.55–0.80 judgement | Regress severity on revenue by sector | IBM CODB by firm size, claims data | Second-most sensitive link after severity; the roadmap explicitly names it |
| **4** | **Frequency dispersions** | 1.5–2.0 judgement | Estimate Var/Mean from per-org annual counts | DBIR per-org data, Coalition, Sophos | Thickens the tail (ES99 +5–12%); the roadmap calls it "the work is choosing dispersion, not coding" |
| **5** | **BI λ + severity** | judgement | Fit to BI claims | NetDiligence BI, Allianz Risk Barometer | High absolute exposure for mid/large firms |
| **6** | **OT λ** | 0.10 judgement | Real ICS-CERT/CISA incident rate | **ICS-CERT annual reports, Dragos, Mandiant** | Manufacturing/energy clients; rarest but most extreme |
| **7** | **supply_chain λ** | 0.25 judgement | Post-incident frequency (SolarWinds/MOVEit class) | CISA KEV, incident databases | Post-2020 attack class |
| **8** | **Catastrophe-year parameters** | p=0.05, mult=2.0 judgement | Calibrate to campaign years | MOVEit/SolarWinds/WannaCry era loss data, insurer aggregation models | Largest swing but hardest to source — do after the direct-severity items |
| **9** | **Copula loadings + ν** | judgement | Fit to correlated-loss events | Qualitative today; insurer correlation studies | After scenario marginals are solid, the dependence layer can be re-fitted |
| **10** | **Score→λ elasticity + weights** | judgement | Map framework evidence to observed frequency | NIST CSF / CIS + claims | Framework mapping is expert-work; the engine consumes config, so it's a data change |

**Sequencing logic:** *correct the systematic bias before measuring residual uncertainty* (the roadmap's own principle). The severity layer (P1–P2) is the bias in every quoted dollar; revenue exponents (P3) and dispersion (P4) follow; the catastrophe-year and copula tail assumptions (P8–P9) are the largest but least sourceable, so they're deferred until the marginal distributions are empirical.

**How to execute (zero engine changes):** every item above is a **data change** through the machinery already built — drop a sector table into `knowledge/datasets/benchmarks/severity/`, register it in `dataset_manifest.yaml`, and `build_calibrated_config()` pushes severity + frequency into the engine via the existing `BenchmarkSet` seam. The `uncertainty_config.yaml` CVs then quantify how much each replacement tightened the band.

---

## Bottom line

Of the ~60 calibrated parameters, **only ~7 are high-confidence** (the frequency anchors + definitional constants). The **severity layer (21 params), revenue exponents (7), dispersions (7), and catastrophe-year params (3) are the critical low-confidence set** — together they produce every dollar the consultant quotes, and none of them is empirically fitted. The good news: the ingestion machinery built this session means replacing them is now a **data-drop, not a code change**, and the roadmap above is ordered by value-per-effort.
