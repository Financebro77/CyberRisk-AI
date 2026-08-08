/** Formatting helpers for the consulting UI. */

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

/** e.g. $3.3M / $56.4M — compact currency for KPI cards. */
export function formatMoney(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${usd.format(value / 1e9)}B`;
  if (abs >= 1e6) return `${usd.format(value / 1e6)}M`;
  if (abs >= 1e3) return `${usd.format(value / 1e3)}K`;
  return usd.format(value);
}

/** Full currency, e.g. $56,416,417. */
export function formatMoneyFull(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return usd.format(value);
}

/** e.g. 62.4 */
export function formatScore(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return value.toFixed(1);
}

/** e.g. 4.8% */
export function formatPct(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

/** Human-readable scenario key -> label, matching config/scenarios.yaml. */
const SCENARIO_LABELS: Record<string, string> = {
  breach: 'Data breach',
  ransomware: 'Ransomware',
  bec: 'BEC / fraud',
  cloud_outage: 'Cloud outage',
  bi: 'Business interruption',
  supply_chain: 'Supply chain',
  ot_physical: 'OT / physical',
};

export function scenarioLabel(key: string): string {
  return SCENARIO_LABELS[key] ?? key.replace(/_/g, ' ');
}
