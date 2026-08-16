import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { SectionCard } from '../components/SectionCard';
import { Spinner } from '../components/Spinner';
import { ErrorBanner } from '../components/ErrorBanner';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import type { MethodologyResponse } from '../lib/types';

/** The eight-step consulting methodology flow. */
const FLOW = [
  { step: 'Input company information', note: 'Industry, revenue, data volume, security posture.' },
  { step: 'Risk scoring', note: 'A weighted model scores the profile 0–100 across six domains.' },
  { step: 'Threat and vulnerability assessment', note: 'Exposure, targeting, and control maturity feed the score.' },
  { step: 'Frequency / severity cyber loss modelling', note: 'Each scenario has a calibrated event rate and loss distribution.' },
  { step: 'Monte Carlo simulation', note: '100,000 simulated years build an annual loss distribution.' },
  { step: 'EAL, VaR, Expected Shortfall', note: 'Expected annual loss, tail thresholds, and tail means.' },
  { step: 'Insurance analysis', note: 'Policy limit and retention are tested against the loss distribution.' },
  { step: 'Risk recommendations', note: 'Control improvements and insurance guidance you can act on.' },
];

const SECTIONS: Array<{ key: keyof MethodologyResponse['sections']; title: string }> = [
  { key: 'scoring_methodology', title: 'Scoring methodology' },
  { key: 'frequency_adjustments', title: 'Frequency adjustments' },
  { key: 'severity_adjustments', title: 'Severity adjustments' },
  { key: 'simulation_methodology', title: 'Simulation methodology' },
];

function Flow() {
  return (
    <section className="py-16 lg:py-20">
      <div className="mx-auto max-w-3xl px-6 lg:px-8">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">The method</p>
        <h1 className="mt-4 font-serif text-3xl font-medium tracking-tight text-ink-900 lg:text-4xl">
          How the model works
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-ink-600">
          From a few facts about your company to a dollar-denominated view of cyber risk —
          a transparent, reproducible eight-step pipeline.
        </p>

        <ol className="mt-10 space-y-0">
          {FLOW.map((item, i) => (
            <li key={item.step} className="relative flex gap-5 pb-8 last:pb-0">
              {i < FLOW.length - 1 && (
                <span className="absolute left-[15px] top-8 h-full w-px bg-ink-200" />
              )}
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent/30 bg-accent/10 text-xs font-bold text-accent">
                {i + 1}
              </span>
              <div>
                <h3 className="text-base font-semibold text-ink-900">{item.step}</h3>
                <p className="mt-1 text-sm leading-relaxed text-ink-600">{item.note}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function MethodologySections() {
  const [data, setData] = useState<MethodologyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .methodology()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load methodology'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="border-t border-ink-100 bg-ink-50 py-16 lg:py-20">
      <div className="mx-auto max-w-4xl px-6 lg:px-8">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">The detail</p>
        <h2 className="mt-4 font-serif text-3xl font-medium tracking-tight text-ink-900">
          A white-box model — every number is traceable
        </h2>
        <p className="mt-3 text-sm text-ink-600">
          Each reported figure traces back to documented configuration and deterministic
          logic. Nothing is a black box.
        </p>

        {loading && <div className="mt-8"><Spinner label="Loading methodology…" /></div>}
        {error && <div className="mt-8"><ErrorBanner message={error} /></div>}

        {data && (
          <div className="mt-8 space-y-4">
            {SECTIONS.map(({ key, title }) => (
              <SectionCard key={key} title={title}>
                <p className="text-sm leading-relaxed text-ink-600">{data.sections[key]}</p>
              </SectionCard>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="py-16">
      <div className="mx-auto max-w-3xl px-6 text-center lg:px-8">
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink-900">
          <ShieldCheck className="h-5 w-5 text-accent" />
          See it applied to your company
        </div>
        <p className="mx-auto mt-3 max-w-xl text-ink-600">
          Answer a few questions and get your risk score, expected annual loss, and insurance guidance.
        </p>
        <div className="mt-6">
          <Link
            to="/consult"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition-colors hover:bg-brand-500"
          >
            Start your assessment <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}

export default function HowItWorks() {
  return (
    <div className="min-h-screen bg-ink-50 font-sans">
      <Flow />
      <MethodologySections />
      <Cta />
    </div>
  );
}
