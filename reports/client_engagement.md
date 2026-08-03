# Cyber Risk Advisory — Atlas Global Logistics Group

**Prepared by:** CyberRiskAI (Marsh practice demo)
**Date:** 2026-08-02
**Model:** full Phase-1-3 engine (NegBin frequency, Student-t dependence, catastrophe years) + scoring + policy transform
**Simulation:** 100,000 simulated years
**Run:** `python examples/run_client_engagement.py` · log `data/output/validation/client_engagement.log`

---

## 1. Client Profile

| Attribute | Detail |
|---|---|
| **Company** | Atlas Global Logistics Group (AGL) |
| **Industry** | Multinational third-party logistics (3PL) & supply-chain operator |
| **Revenue** | $6.5bn; 32,000 employees; 45 countries |
| **Business** | 24/7 global freight network on ~120 critical IT systems (TMS/WMS, customs clearance, port integrations); ~80% cloud-hosted |
| **Data** | 4m+ shipper accounts; 900k+ customs filings |
| **Cyber concerns raised** | (1) A ransomware event would halt the freight network — the entire revenue stream; (2) regulatory & class-action exposure from client/customs data; (3) is the $25M program adequate?; (4) where to invest next |

---

## 2. Client Interview — Information Gathered

The agent established the eight facts a broker needs before advising. **Interview questions** (what a real first meeting covers):

| Dimension | Question the agent asked | Client's answer |
|---|---|---|
| Industry | What industry do you operate in? | Logistics / supply chain |
| Revenue | What is your annual revenue? | $6.5bn, 32,000 staff, 45 countries |
| Customer data volume | How many records, how sensitive? | 4m+ shipper accounts, 900k customs filings |
| Technology dependency | How dependent on IT / third parties? | Very high (24/7 network, 80% cloud) |
| Security controls | What controls are in place? | Strong on IT (MFA, SIEM, patching); OT/warehouse gaps |
| Previous incidents | Any incidents in last 3-5 years? | 1 significant ransomware attempt (contained) |
| Existing coverage | Current limits / retentions? | $25M limit / $1M retention / no sub-limit |
| Risk appetite | How much will you retain? | Retain up to $1M, sensitive to premium |

---

## 3. Risk Assessment

**Composite risk score: 54.5 / 100 — HIGH**

Domain breakdown (higher = worse):

| Domain | Score |
|---|---|
| Threat & Exposure | 77.0 |
| Vulnerability Management | 66.8 |
| Third-Party / Supply-Chain Risk | 59.0 |
| Endpoint & Data Resilience | 39.5 |
| Identity & Access Control | 39.2 |
| Resilience & Governance | 31.5 |

**Key risk drivers** (where risk concentrates): industry targeting, open critical vulnerabilities, privileged access, IAM governance, EDR coverage, DR testing.

**Reading:** AGL is a *highly-targeted* operator (logistics is a top-3 attacked sector) with strong *IT* controls but real *OT/warehouse* gaps and deep third-party exposure. The score reflects a defensible "strong but exposed" profile — not a failing one.

---

## 4. Loss Modelling

Score-driven Monte Carlo (100,000 years, Student-t dependence, catastrophe years enabled):

| Measure | Value | Meaning |
|---|---|---|
| **Expected Annual Loss (EAL)** | **$5.45M** | average loss per year |
| **VaR 99%** | $44.1M | 99 of 100 years stay below this |
| **P99.5** (1-in-200 yr) | $57.5M | a 1-in-200 event |
| **P99.9** (1-in-1000 yr) | $110.2M | a 1-in-1000 event |
| **ES 99% (Expected Shortfall)** | **$72.3M** | average loss *given* a 1-in-100 year |

**Scenario contribution to EAL:** ransomware 20.4% · breach 16.3% · cloud outage 16.1% · BEC 15.2% · supply chain 14.4% · BI 9.7% · OT/physical 7.9%.

---

## 5. VaR / Expected Shortfall Interpretation

- **VaR 99% ($44.1M)** answers "how bad is a normal bad year?" — it's the loss you stay under 99% of the time.
- **ES 99% ($72.3M)** answers the harder question "if a 1-in-100 year happens, how bad is it *on average*?" It is the decision-relevant number, because it captures how bad the bad years really get — the entire reason ES is reported alongside VaR.
- **ES99 / EAL = 13.3×** — the "catastrophe multiplier": a single 1-in-100 event can be worth **over 13 years of average losses.** This is the defining signature of cyber catastrophe risk.

For a CFO: *"expect a normal year to cost ~$5M; but the year you fear — the ransomware event that halts the network — is on average a ~$72M event, and a 1-in-1000 one is over $110M."*

---

## 6. Insurance Response & Client Retained Loss

**Current program:** $25M limit / $1M retention / $25M aggregate, no sub-limit.

**Section 1 — GROUND-UP CYBER LOSS (before insurance recovery):**

| Measure | Value |
|---|---|
| EAL | $5.45M |
| VaR 99% | $44.1M |
| ES 99% | $72.3M |
| P99.9 (1-in-1000 yr) | $110.2M |

**Section 2 — INSURANCE RESPONSE:**

| Metric | Value |
|---|---|
| Policy limit | $25.00M |
| Retention | $1.00M |
| Covered loss (transferred EAL) | $2.32M |
| Insurer payment (transferred EAL) | $2.32M |
| P(annual limit exhausted) | **1.74%** |

**Section 3 — CLIENT RETAINED LOSS:**

| Metric | Value |
|---|---|
| Retained EAL (firm self-funds) | $3.12M |
| Retained ES 99% (worst-year self-funding) | **$47.4M** |

For a **$110.2M** extreme (1-in-1000) loss event:
- **Client retention:** $1M
- **Insurance recovery:** $25M maximum
- **Residual uncovered exposure:** **$84.2M** the client retains after insurance

The $25M tower covers a *typical* 1-in-100 tail ($72M is partially covered), but a **P99.9 event ($110M) would exhaust the limit**, leaving a residual uncovered exposure of **$84.2M** after the policy pays — and in 1.74% of modelled years the client self-funds $47M+ in the tail. The retained ES99 of $47.4M is far above the client's stated $1M appetite.

**Conclusion:** the current program is sized for ordinary years, not for the catastrophe the client explicitly fears. **A 1-in-1000 cyber event leaves a residual uncovered exposure of ~$84M after insurance.**

---

## 7. Risk Mitigation Recommendations

1. **Immediate remediation of critical vulnerabilities** — the OT/warehouse patching lag is the single biggest controllable driver.
2. **Enforce least-privilege and privileged access control** — OT users and privileged accounts are under-governed; this is where a ransomware foothold begins.
3. **Raise the cyber limit / add a ransomware sub-limit** — the retained-loss analysis shows the $25M tower is exhausted in ~1.7% of years; a higher limit (e.g. $50M+) or a ransomware sub-limit closes the residual tail exposure.
4. **Stress-test the incident response plan** — with a 24/7 revenue stream, recovery time is the leverage: faster restore = smaller BI loss.
5. **Review third-party assessment cadence** — the 3PL partner network is a top exposure; validate the controls of the most critical partners.

---

## 8. Executive Summary

**Atlas Global Logistics Group — Cyber Risk Assessment**

> AGL carries a **HIGH** cyber risk profile (score 54.5/100): a highly-targeted, data-rich, 24/7 operator with strong IT controls but real OT and supply-chain gaps. Modelled exposure is **$5.45M expected annually**, rising to **$72.3M on average in a 1-in-100 year** and **$110M+ at 1-in-1000** — a tail worth over 13 years of average losses.
>
> **The $25M program is under-sized for the risk it protects.** It covers ordinary years but is exhausted in ~1.7% of modelled years, leaving a residual uncovered exposure of up to **$84M** on a 1-in-1000 event — and self-funding of **$47M** in the tail it most fears, far above its stated $1M appetite.
>
> **Priority actions:** (1) remediate OT critical vulnerabilities and enforce least-privilege; (2) raise the limit and add a ransomware sub-limit to close the residual tail exposure; (3) stress-test recovery to shorten business interruption; (4) tighten third-party controls.

---

*This deliverable was generated end-to-end by CyberRiskAI from the client's answers: scoring → loss simulation → VaR/ES → insurance response → client retained loss → mitigation → summary. Figures are from the validated model run in `data/output/validation/client_engagement.log`.*
