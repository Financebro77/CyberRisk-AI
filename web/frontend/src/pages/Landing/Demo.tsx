import { Link } from 'react-router-dom';
import { Building2, ArrowRight } from 'lucide-react';
import { DEMO_COMPANIES } from '../../lib/demoCompanies';
import { Reveal } from '../../components/Reveal';

/**
 * Landing-page Demo section — the five one-click company profiles a recruiter
 * can run without entering data.
 */
export function Demo() {
  return (
    <section className="bg-white py-20">
      <div className="mx-auto max-w-6xl px-8">
        <Reveal className="text-center">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600 text-white">
            <Building2 className="h-5 w-5" />
          </div>
          <h2 className="mt-4 font-serif text-4xl font-medium tracking-tight text-ink-900">
            Explore with a real client — no typing required
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-lg text-ink-500">
            Five realistic companies across the industries we calibrate. Click one and the
            platform assesses it, runs the Monte Carlo model and structures insurance.
          </p>
        </Reveal>

        <Reveal stagger className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {DEMO_COMPANIES.map((c) => (
            <div key={c.id} className="flex h-full flex-col rounded-xl border border-ink-200 bg-ink-50 p-5 transition-all hover:-translate-y-1 hover:border-brand-500/50 hover:shadow-lg">
              <div className="text-sm font-semibold text-ink-900">{c.name}</div>
              <div className="mt-1 text-xs leading-snug text-ink-500">{c.blurb}</div>
              <div className="mt-auto pt-4">
                <Link
                  to="/app"
                  className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700"
                >
                  Open assessment <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}
