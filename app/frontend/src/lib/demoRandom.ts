import type { CompanyBrief } from './types';
import { DEMO_COMPANIES, type DemoCompany } from './demoCompanies';

/**
 * Demo Mode randomization — every "Load Demo Company" press produces a fresh
 * company: a random base profile from the pool with its numeric inputs jittered
 * in realistic ranges (revenue, data volumes, headcount, incident history,
 * policy limit, retention).  One security-control select is occasionally varied
 * so the assembled controls text — and therefore the risk score — differs
 * between presses.
 */

function randBetween(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

/** Round a value up/down to the nearest step (e.g. 1M for revenue). */
function roundTo(n: number, step: number): number {
  return Math.max(step, Math.round(n / step) * step);
}

const POLICY_LIMIT_FACTORS = [0.5, 0.75, 1, 1.5, 2] as const;
const RETENTION_FACTORS = [0.25, 0.5, 0.75, 1, 1.5] as const;
const MFA_LEVELS = ['Comprehensive', 'Partial', 'None'] as const;
const VULN_CADENCE = ['Continuous', 'Weekly', 'Monthly'] as const;

export function randomizeDemoCompany(): DemoCompany {
  const base = pick(DEMO_COMPANIES);
  const brief: CompanyBrief = { ...base.brief };

  brief.revenue_usd = roundTo(
    (brief.revenue_usd ?? 250_000_000) * randBetween(0.7, 1.5),
    1_000_000,
  );
  brief.customer_records = Math.max(
    1_000,
    Math.round((brief.customer_records ?? 100_000) * randBetween(0.7, 1.4)),
  );
  brief.employees = Math.max(
    50,
    Math.round((brief.employees ?? 1_000) * randBetween(0.8, 1.25)),
  );
  brief.previous_incidents = Math.floor(Math.random() * 5);

  // The insurance knobs the SPA exposes, regenerated each press.
  brief.policy_limit = roundTo(
    (brief.policy_limit ?? 20_000_000) * pick(POLICY_LIMIT_FACTORS),
    1_000_000,
  );
  brief.retention = roundTo(
    (brief.retention ?? 500_000) * pick(RETENTION_FACTORS),
    50_000,
  );

  // Vary a control now and then so the risk score can move between presses.
  if (Math.random() < 0.6) brief.mfa_coverage = pick(MFA_LEVELS);
  if (Math.random() < 0.5) brief.vulnerability_management = pick(VULN_CADENCE);

  return { ...base, brief };
}
