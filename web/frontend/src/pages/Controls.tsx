import { useState } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { CompanyForm } from '../components/CompanyForm';
import { ErrorBanner, NeedsMoreInfo } from '../components/ErrorBanner';
import { MetricCard } from '../components/MetricCard';
import { SectionCard } from '../components/SectionCard';
import { ChartCard } from '../components/ChartCard';
import { BeforeAfterChart } from '../components/charts';
import type { CompanyBrief, ControlImprovementResponse } from '../lib/types';
import { formatMoney, formatPct } from '../lib/format';

const CONTROL_OPTIONS = [
  'implement MFA',
  'improve segmentation',
  'reduce privileged access',
  'add immutable backups',
  'add backups',
];

export default function Controls() {
  const [control, setControl] = useState(CONTROL_OPTIONS[0]);

  const { data, loading, error, run } = useApi<[CompanyBrief], ControlImprovementResponse | 'insufficient' | undefined>(
    (brief) =>
      api.controlsImprovement({ ...brief, control_change: control }).then((r) =>
        r.status === 'ok' ? r : r.status === 'insufficient_info' ? 'insufficient' : undefined,
      ),
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-ink-900">Control improvement</h2>
        <p className="mt-1 text-sm text-ink-500">
          Model the loss reduction from a specific control change — the engine re-scores the
          profile, re-runs the seeded simulation and reports before vs after.
        </p>
      </div>

      <CompanyForm
        submitLabel="Run scenario"
        loading={loading}
        onSubmit={(brief) => run(brief)}
      >
        <div className="mt-6 rounded-lg border border-ink-200 bg-ink-50 p-4">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-ink-500">
            Control change
          </div>
          <div className="flex flex-wrap gap-2">
            {CONTROL_OPTIONS.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => setControl(opt)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                  control === opt
                    ? 'bg-brand-600 text-white'
                    : 'bg-white text-ink-600 ring-1 ring-ink-200 hover:bg-ink-100'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      </CompanyForm>

      {error && <ErrorBanner message={error} />}
      {data === 'insufficient' && <NeedsMoreInfo needed={['revenue_usd', 'security_controls']} />}

      {data && data !== 'insufficient' && (
        <div className="space-y-6">
          <SectionCard title={data.label} subtitle={`Factor: ${data.factor_key.replace(/_/g, ' ')} → ${data.target_rating.replace(/_/g, ' ')}`}>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <MetricCard label="EAL reduction" value={formatMoney(data.impact.loss_reduction)} accent />
              <MetricCard label="Improvement" value={formatPct(data.impact.percentage_improvement)} />
              <MetricCard label="Target rating" value={data.target_rating.replace(/_/g, ' ')} />
            </div>
          </SectionCard>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ChartCard title="Before vs after" subtitle="EAL / VaR 99 / ES 99, USD">
              <BeforeAfterChart before={data.before} after={data.after} />
            </ChartCard>

            <SectionCard title="Detailed comparison">
              <div className="space-y-3">
                {(['eal', 'var_99', 'es_99'] as const).map((k) => (
                  <div key={k} className="flex items-center justify-between rounded-lg bg-ink-50 px-4 py-3">
                    <span className="text-sm font-medium text-ink-700">{k.toUpperCase()}</span>
                    <div className="flex items-center gap-3 text-sm tabular-nums">
                      <span className="text-ink-500">{formatMoney(data.before[k])}</span>
                      <span className="text-ink-300">→</span>
                      <span className="font-semibold text-brand-600">{formatMoney(data.after[k])}</span>
                    </div>
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>
        </div>
      )}
    </div>
  );
}
