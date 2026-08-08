import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { SectionCard } from '../components/SectionCard';
import { Spinner } from '../components/Spinner';
import { ErrorBanner } from '../components/ErrorBanner';
import type { MethodologyResponse } from '../lib/types';

const SECTIONS: Array<{ key: keyof MethodologyResponse['sections']; title: string }> = [
  { key: 'scoring_methodology', title: 'Scoring methodology' },
  { key: 'frequency_adjustments', title: 'Frequency adjustments' },
  { key: 'severity_adjustments', title: 'Severity adjustments' },
  { key: 'simulation_methodology', title: 'Simulation methodology' },
];

export default function Methodology() {
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
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-ink-900">How the model works</h2>
        <p className="mt-1 text-sm text-ink-500">
          This is a white-box model: every reported number traces back to the documented
          configuration and deterministic logic in <code className="rounded bg-ink-100 px-1.5 py-0.5 text-xs">config/*.yaml</code>.
        </p>
      </div>

      {loading && <Spinner label="Loading methodology…" />}
      {error && <ErrorBanner message={error} />}

      {data && (
        <div className="space-y-4">
          {SECTIONS.map(({ key, title }) => (
            <SectionCard key={key} title={title}>
              <p className="text-sm leading-relaxed text-ink-600">{data.sections[key]}</p>
            </SectionCard>
          ))}

          <SectionCard title="Model limitations" subtitle="Mandatory disclosure appended to every advisory report">
            <div className="rounded-lg border border-ink-200 bg-ink-50 p-4">
              <ol className="list-inside list-decimal space-y-1.5 text-sm text-ink-600">
                <li>All model inputs are estimates; results are indicative, not a guarantee of actual loss.</li>
                <li>The model is calibrated from public benchmarks and mock data, not the client's loss history.</li>
                <li>Scenario correlations are modelled through a copula and carry estimation uncertainty.</li>
                <li>Outputs are not a substitute for professional actuarial advice on a specific risk.</li>
              </ol>
            </div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}
