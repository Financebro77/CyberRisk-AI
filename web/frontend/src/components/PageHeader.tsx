import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  /** Right-aligned actions (buttons, badges). */
  actions?: ReactNode;
  /** Optional eyebrow label above the title. */
  eyebrow?: string;
}

/** Consistent page heading with optional actions — enterprise consulting style. */
export function PageHeader({ title, description, actions, eyebrow }: PageHeaderProps) {
  return (
    <div className="panel-in mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-brand-600">
            {eyebrow}
          </div>
        )}
        <h2 className="text-2xl font-semibold tracking-tight text-ink-900">{title}</h2>
        {description && <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-500">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
