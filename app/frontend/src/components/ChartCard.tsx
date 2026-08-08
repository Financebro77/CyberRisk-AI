import type { ReactNode } from 'react';

/** Consistent frame for Recharts visualizations across pages. */
export function ChartCard({
  title,
  subtitle,
  height = 280,
  children,
}: {
  title: string;
  subtitle?: string;
  height?: number;
  children: ReactNode;
}) {
  return (
    <div className="card p-4 transition-shadow duration-200 hover:shadow-md">
      <div className="mb-3">
        <div className="text-sm font-semibold text-ink-900">{title}</div>
        {subtitle && <div className="text-xs text-ink-500">{subtitle}</div>}
      </div>
      {/* The chart is a data visualisation — label it for screen readers. */}
      <div style={{ height }} role="img" aria-label={`${title}${subtitle ? ` — ${subtitle}` : ''}`}>
        {children}
      </div>
    </div>
  );
}
