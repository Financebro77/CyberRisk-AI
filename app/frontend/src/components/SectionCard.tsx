import type { ReactNode } from 'react';

interface SectionCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  /** Extra element (button, badge) aligned to the heading row. */
  action?: ReactNode;
}

/** White card with a section heading — the core consulting layout unit. */
export function SectionCard({ title, subtitle, children, className = '', action }: SectionCardProps) {
  return (
    <section className={`card p-6 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-ink-900">{title}</h3>
          {subtitle && <p className="mt-0.5 text-sm text-ink-500">{subtitle}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </section>
  );
}
