import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { CompanyForm } from '../components/CompanyForm';
import { ErrorBanner } from '../components/ErrorBanner';
import { RiskBadge } from '../components/RiskBadge';
import { MetricCard } from '../components/MetricCard';
import { SectionCard } from '../components/SectionCard';
import { ChartCard } from '../components/ChartCard';
import { PageHeader } from '../components/PageHeader';
import { DomainScoresChart } from '../components/charts';
import type { CompanyBrief, ScoreResponse } from '../lib/types';
import { formatScore } from '../lib/format';

export default function Assess() {
  const { data, loading, error, run } = useApi<[CompanyBrief], ScoreResponse | undefined>(
    (brief) => api.score(brief).then((r) => (r.status === 'ok' ? r : undefined)),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Advisory"
        title="Assess risk"
        description="Score the client's cyber risk profile 0–100 and identify the main drivers. Deterministic — the same brief always yields the same score."
      />

      <CompanyForm
        submitLabel="Score profile"
        loading={loading}
        onSubmit={(brief) => run(brief)}
      />

      {error && <ErrorBanner message={error} />}

      {data && (
        <div className="panel-in space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <MetricCard
              label="Composite score"
              value={formatScore(data.risk_score)}
              sub={<RiskBadge category={data.risk_category} />}
              accent
            />
            <MetricCard
              label="Client"
              value={data.firm_name}
              sub="assessed profile"
            />
            <MetricCard
              label="Assumed factors"
              value={data.assumed_factors.length}
              sub="from neutral defaults"
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ChartCard title="Domain scores" subtitle="Six weighted domains, 0-100 (higher = worse)">
              <DomainScoresChart scores={data.domain_scores} />
            </ChartCard>

            <SectionCard title="Risk drivers" subtitle="Factors above their domain average">
              <div className="flex flex-wrap gap-2">
                {data.risk_drivers.map((d) => (
                  <span
                    key={d}
                    className="rounded-full border border-risk-high/30 bg-risk-high/5 px-3 py-1 text-xs font-medium text-risk-high"
                  >
                    {d.replace(/_/g, ' ')}
                  </span>
                ))}
                {data.risk_drivers.length === 0 && (
                  <span className="text-sm text-ink-500">No factors above domain average.</span>
                )}
              </div>
            </SectionCard>
          </div>

          {data.assumed_factors.length > 0 && (
            <SectionCard
              title="Assumed factors"
              subtitle="The client did not state these; neutral defaults were applied."
            >
              <div className="flex flex-wrap gap-2">
                {data.assumed_factors.map((f) => (
                  <span key={f} className="rounded-full bg-ink-100 px-3 py-1 text-xs text-ink-600">
                    {f.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </SectionCard>
          )}
        </div>
      )}
    </div>
  );
}
