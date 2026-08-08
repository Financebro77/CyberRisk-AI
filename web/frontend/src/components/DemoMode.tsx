import type { CompanyFormHandle } from './CompanyForm';
import { DEMO_COMPANIES, type DemoCompany } from '../lib/demoCompanies';
import { Building2, Play, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react';

interface DemoModeProps {
  formRef: React.RefObject<CompanyFormHandle | null>;
  busy: boolean;
}

const POSTURE: Record<
  DemoCompany['posture'],
  { icon: React.ComponentType<{ className?: string }>; iconCls: string; dot: string; label: string }
> = {
  Strong: { icon: ShieldCheck, iconCls: 'text-emerald-500', dot: 'bg-emerald-500', label: 'Strong posture' },
  Moderate: { icon: ShieldQuestion, iconCls: 'text-amber-500', dot: 'bg-amber-500', label: 'Moderate posture' },
  Weak: { icon: ShieldAlert, iconCls: 'text-red-500', dot: 'bg-red-500', label: 'Weak posture' },
};

/**
 * Demo Mode — five realistic companies a recruiter can click to populate the
 * assessment form and immediately run the simulation.  Everything is backend
 * data; the profiles are realistic full briefs spanning the calibrated
 * industries.
 */
export function DemoMode({ formRef, busy }: DemoModeProps) {
  const select = (c: DemoCompany) => {
    if (busy) return;
    formRef.current?.loadCompany(c.brief, { submit: true });
  };

  return (
    <section className="rounded-2xl border border-brand-500/20 bg-gradient-to-br from-brand-50/70 via-white to-ink-50 p-6 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Building2 className="h-5 w-5" />
        </div>
        <div>
          <h3 className="text-base font-semibold text-ink-900">Demo Mode</h3>
          <p className="text-xs text-ink-500">
            Click a company to populate the assessment and run the model — no typing required.
          </p>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {DEMO_COMPANIES.map((c) => {
          const { icon: PostureIcon, iconCls, dot, label } = POSTURE[c.posture];
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => select(c)}
              disabled={busy}
              aria-label={`Run ${c.name} assessment`}
              className="tappable card group flex flex-col p-4 text-left disabled:cursor-not-allowed disabled:opacity-60"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-ink-900">{c.name}</span>
                <PostureIcon className={`h-4 w-4 ${iconCls}`} />
              </div>
              <p className="mt-1 text-[11px] leading-snug text-ink-500">{c.blurb}</p>
              <div className="mt-auto flex items-center gap-2 border-t border-ink-100 pt-2.5">
                <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
                <span className="text-[10px] uppercase tracking-wide text-ink-500">{label}</span>
              </div>
              <div className="mt-2 flex items-center gap-1.5 text-xs font-semibold text-brand-600 opacity-0 transition-opacity group-hover:opacity-100">
                <Play className="h-3 w-3" /> Run assessment
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
