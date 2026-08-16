import { describe, it, expect } from 'vitest';
import { randomizeDemoCompany } from '../demoRandom';
import { DEMO_COMPANIES } from '../demoCompanies';

const INDUSTRIES = DEMO_COMPANIES.map((c) => c.brief.industry);

describe('randomizeDemoCompany', () => {
  it('returns a full, model-able brief from the demo pool', () => {
    const company = randomizeDemoCompany();
    expect(INDUSTRIES).toContain(company.brief.industry);
    expect(company.brief.firm_name).toBeTruthy();
    expect(company.brief.revenue_usd).toBeGreaterThan(0);
    expect(company.brief.customer_records).toBeGreaterThan(0);
    expect(company.brief.employees).toBeGreaterThan(0);
    // The insurance knobs the SPA exposes must be present on every draw.
    expect(company.brief.policy_limit).toBeGreaterThan(0);
    expect(company.brief.retention).toBeGreaterThan(0);
  });

  it('keeps revenue within realistic bounds', () => {
    for (let i = 0; i < 20; i++) {
      const revenue = randomizeDemoCompany().brief.revenue_usd!;
      expect(revenue).toBeGreaterThanOrEqual(100_000_000);
      expect(revenue).toBeLessThanOrEqual(5_000_000_000);
    }
  });

  it('varies across repeated draws', () => {
    const revenues = new Set<number>();
    for (let i = 0; i < 30; i++) {
      revenues.add(randomizeDemoCompany().brief.revenue_usd!);
    }
    expect(revenues.size).toBeGreaterThan(1);
  });
});
