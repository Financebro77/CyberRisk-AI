import type { ReactNode } from 'react';

interface MetricCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  sub?: ReactNode;
  accent?: boolean;
  /** Optional color tone for the value (semantic: green/amber/red). */
  tone?: 'default' | 'success' | 'warn' | 'danger';
}

const TONE: Record<string, string> = {
  default: 'text-ink-900',
  success: 'text-emerald-600',
  warn: 'text-amber-600',
  danger: 'text-risk-high',
};

/** Labeled KPI card used across the dashboard and model pages. */
export function MetricCard({ label, value, hint, sub, accent, tone = 'default' }: MetricCardProps) {
  return (
    <div
      className={`card group relative p-4 transition-transform duration-200 ${
        accent
          ? 'border-accent/30 bg-gradient-to-br from-accent/10 to-ink-50'
          : 'hover:shadow-md'
      }`}
    >
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-500">
        {label}
      </div>
      <div className={`mt-1.5 font-mono text-2xl font-semibold tabular-nums tracking-tight ${accent ? 'text-accent' : TONE[tone]}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-sm text-ink-600">{sub}</div>}
      {hint && <div className="mt-1 text-xs text-ink-400">{hint}</div>}
    </div>
  );
}
