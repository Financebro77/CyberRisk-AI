import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { CompanyForm } from '../components/CompanyForm';
import { ErrorBanner, NeedsMoreInfo } from '../components/ErrorBanner';
import { Spinner } from '../components/Spinner';
import { MetricCard } from '../components/MetricCard';
import { ChartCard } from '../components/ChartCard';
import { PageHeader } from '../components/PageHeader';
import {
  AalByScenarioChart,
  LossDistributionChart,
  ScenarioContributionChart,
} from '../components/charts';
import type { CompanyBrief, SimulationResponse } from '../lib/types';
import { formatMoney, formatMoneyFull, formatPct } from '../lib/format';

export default function LossSimulation() {
  const { data, loading, error, run } = useApi<[CompanyBrief], SimulationResponse | 'insufficient' | undefined>(
    (brief) =>
      api.simulate(brief).then((r) => (r.status === 'ok' ? r : r.status === 'insufficient_info' ? 'insufficient' : undefined)),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Advisory"
        title="Cyber Risk Assessment"
        description="Monte Carlo simulation of annual losses — EAL, Value-at-Risk, Expected Shortfall and 1-in-N-year PMLs across seven calibrated scenarios."
      />

      <CompanyForm
        submitLabel="Run Assessment"
        loading={loading}
        onSubmit={(brief) => run(brief)}
      />

      {error && <ErrorBanner message={error} />}
      {data === 'insufficient' && <NeedsMoreInfo needed={['revenue_usd', 'security_controls']} />}

      {/* Loading animation while the simulation runs server-side. */}
      {loading && (
        <Spinner label="Running Monte Carlo simulation — 10,000 paths, 7 scenarios…" />
      )}

      {data && data !== 'insufficient' && (
        <div className="panel-in space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Expected annual loss" value={formatMoney(data.eal)} sub={`${data.n_years.toLocaleString()} simulated years`} accent />
            <MetricCard label="VaR 95%" value={formatMoney(data.var_95)} sub="1-year, 95% confidence" />
            <MetricCard label="VaR 99%" value={formatMoney(data.var_99)} sub="1-year, 99% confidence" />
            <MetricCard label="ES 99%" value={formatMoney(data.es_99)} sub="expected shortfall" />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="PML 1-in-200" value={formatMoney(data.pml_1in200)} sub="1-in-200-year loss" />
            <MetricCard label="PML 1-in-1000" value={formatMoney(data.pml_1in1000)} sub="1-in-1000-year loss" />
            <MetricCard label="P(loss-free year)" value={formatPct(data.prob_zero_loss)} sub="probability of no loss" />
            <MetricCard label="Risk score" value={data.risk_score.toFixed(1)} sub={data.risk_category} />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ChartCard title="Loss distribution" subtitle="Annual loss quantiles (p50 → p99.9)">
              <LossDistributionChart quantiles={data.loss_distribution} />
            </ChartCard>
            <ChartCard title="AAL by scenario" subtitle="Average annual loss per scenario, USD">
              <AalByScenarioChart aal={data.aal_by_scenario} />
            </ChartCard>
          </div>

          <ChartCard title="Scenario contribution" subtitle="Share of expected annual loss per scenario">
            <ScenarioContributionChart contribution={data.scenario_contribution} />
          </ChartCard>

          {data.scenario_contribution_detail.length > 0 && (
            <div className="rounded-xl border border-ink-200 bg-white shadow-sm">
              <div className="border-b border-ink-200 px-6 py-4">
                <h3 className="text-base font-semibold text-ink-900">Per-scenario analysis</h3>
                <p className="text-sm text-ink-500">Frequency / severity drivers and recommended controls, linked to the model.</p>
              </div>
              <div className="divide-y divide-ink-100">
                {data.scenario_contribution_detail.map((s) => (
                  <div key={s.scenario_key} className="grid grid-cols-1 gap-4 px-6 py-4 md:grid-cols-3">
                    <div>
                      <div className="text-sm font-semibold text-ink-900">{s.scenario_name}</div>
                      <div className="text-xs text-ink-500">
                        {formatPct(s.contribution)} of EAL · {formatMoneyFull(s.aal)}
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Drivers</div>
                      <div className="flex flex-wrap gap-1.5">
                        {[...s.frequency_drivers, ...s.severity_drivers].map((d) => (
                          <span key={d} className="rounded-full bg-ink-100 px-2 py-0.5 text-[11px] text-ink-600">{d}</span>
                        ))}
                        {s.frequency_drivers.length + s.severity_drivers.length === 0 && (
                          <span className="text-xs text-ink-400">—</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Recommended controls</div>
                      <div className="flex flex-wrap gap-1.5">
                        {s.recommended_controls.map((c) => (
                          <span key={c} className="rounded-full bg-brand-100 px-2 py-0.5 text-[11px] font-medium text-brand-600">{c}</span>
                        ))}
                        {s.recommended_controls.length === 0 && (
                          <span className="text-xs text-ink-400">—</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
