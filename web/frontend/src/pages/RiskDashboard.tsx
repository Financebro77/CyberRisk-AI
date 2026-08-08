import { useCallback, useRef } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { CompanyForm, type CompanyFormHandle } from '../components/CompanyForm';
import { DemoMode } from '../components/DemoMode';
import { ErrorBanner, NeedsMoreInfo } from '../components/ErrorBanner';
import { MetricCard } from '../components/MetricCard';
import { RiskBadge } from '../components/RiskBadge';
import { SectionCard } from '../components/SectionCard';
import { ChartCard } from '../components/ChartCard';
import { PageHeader } from '../components/PageHeader';
import { SkeletonChart, SkeletonMetricRow } from '../components/Skeleton';
import {
  LossDistributionChart,
  LossExceedanceChart,
  InsuranceWaterfallChart,
  ScenarioContributionChart,
} from '../components/charts';
import type { CompanyBrief, InsuranceResponse, PolicyInput, SimulationResponse } from '../lib/types';
import { formatMoney, formatMoneyFull, formatPct, formatScore } from '../lib/format';

/** Default policy terms — mirrors the backend PolicyInput defaults. */
const POLICY_DEFAULTS: PolicyInput = {
  per_occurrence_deductible: 250_000,
  per_occurrence_limit: 5_000_000,
  annual_aggregate_deductible: 1_000_000,
  annual_aggregate_limit: 20_000_000,
  coinsurance: 0,
};

interface SimResult {
  sim: SimulationResponse | null;
  insurance: InsuranceResponse | null;
}

export default function RiskDashboard() {
  const formRef = useRef<CompanyFormHandle>(null);
  const { data, loading, error, run, reset } = useApi<[CompanyBrief], SimResult | 'insufficient' | undefined>(
    useCallback(async (brief: CompanyBrief) => {
      const policy: PolicyInput = {
        per_occurrence_deductible: brief.retention ?? POLICY_DEFAULTS.per_occurrence_deductible,
        per_occurrence_limit: brief.policy_limit ?? POLICY_DEFAULTS.per_occurrence_limit,
        annual_aggregate_deductible: POLICY_DEFAULTS.annual_aggregate_deductible,
        annual_aggregate_limit: POLICY_DEFAULTS.annual_aggregate_limit,
        coinsurance: 0,
      };

      const [simRes, insRes] = await Promise.all([
        api.simulate(brief),
        api.insurance({ ...brief, ...policy }),
      ]);

      if (simRes.status === 'insufficient_info' || insRes.status === 'insufficient_info') return 'insufficient';
      if (simRes.status !== 'ok' || insRes.status !== 'ok') return undefined;

      return { sim: simRes, insurance: insRes };
    }, []),
  );

  // Keep the last submitted brief so a failed run can be retried.
  const lastBrief = useRef<CompanyBrief | null>(null);

  const handleRun = useCallback(
    (brief: CompanyBrief) => {
      lastBrief.current = brief;
      reset();
      void run(brief);
    },
    [reset, run],
  );

  const hasData = data && data !== 'insufficient';
  const sim = hasData ? data.sim : null;
  const ins = hasData ? data.insurance : null;

  // Policy adequacy: insurer covers EAL transferred; residual uncovered remains.
  const policyAdequacy = hasData && ins ? ins.insurance_response.policy_limit > 0 : false;
  const adequacyPct =
    hasData && ins && ins.ground_up_loss.eal > 0
      ? Math.min(100, (ins.insurance_response.insurer_payment / ins.ground_up_loss.eal) * 100)
      : 0;

  // Top risk drivers: highest-scoring factors from the score response.
  const topDrivers = hasData && sim ? sim.risk_drivers.slice(0, 5) : [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Consulting workspace"
        title="Risk Dashboard"
        description="End-to-end cyber risk view — simulated losses, insurance adequacy and residual exposure, all from the Monte Carlo engine."
      />

      <DemoMode formRef={formRef} busy={loading} />

      <CompanyForm
        ref={formRef}
        submitLabel="Run Assessment"
        loading={loading}
        onSubmit={handleRun}
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={lastBrief.current ? () => handleRun(lastBrief.current!) : undefined}
        />
      )}
      {data === 'insufficient' && <NeedsMoreInfo needed={['revenue_usd', 'security_controls']} />}

      {/* Skeleton loading while the simulation runs. */}
      {loading && (
        <div className="space-y-6">
          <SkeletonMetricRow count={4} />
          <SkeletonMetricRow count={4} />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <SkeletonChart />
            <SkeletonChart />
          </div>
        </div>
      )}

      {hasData && sim && ins && (
        <div className="panel-in space-y-6">
          {/* ---- Headline metrics ---- */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MetricCard label="Risk score" value={formatScore(sim.risk_score)} sub={<RiskBadge category={sim.risk_category} />} accent />
            <MetricCard label="Expected annual loss" value={formatMoney(sim.eal)} sub="simulated mean" />
            <MetricCard label="VaR 95%" value={formatMoney(sim.var_95)} sub="1-in-20 tail" />
            <MetricCard label="VaR 99%" value={formatMoney(sim.var_99)} sub="1-in-100 tail" />
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MetricCard label="Expected shortfall" value={formatMoney(sim.es_99)} sub="tail beyond VaR 99" />
            <MetricCard label="Policy adequacy" value={formatPct(adequacyPct / 100)} sub={policyAdequacy ? 'covered by program' : 'no active limit'} accent />
            <MetricCard label="Residual exposure" value={formatMoney(ins.client_retained_loss.residual_exposure_at_p99_9)} sub="at 1-in-1000-year loss" />
            <MetricCard label="Client retained EAL" value={formatMoney(ins.client_retained_loss.retained_eal)} sub="after insurance" />
          </div>

          {/* ---- Charts ---- */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ChartCard title="Loss distribution" subtitle="Annual loss quantiles (p50 → p99.9), backend-simulated">
              <LossDistributionChart quantiles={sim.loss_distribution} />
            </ChartCard>
            <ChartCard title="Loss exceedance curve" subtitle="Probability of loss ≥ level, from the engine's simulated sample">
              <LossExceedanceChart points={sim.loss_exceedance} />
            </ChartCard>
            <ChartCard title="Risk breakdown" subtitle="Scenario contribution to expected annual loss">
              <ScenarioContributionChart contribution={sim.scenario_contribution} />
            </ChartCard>
            <ChartCard title="Insurance waterfall" subtitle="Ground-up EAL → retention → insurer payment → residual">
              <InsuranceWaterfallChart
                groundUp={ins.ground_up_loss.eal}
                retention={ins.policy.per_occurrence_deductible ?? 0}
                insurerPayment={ins.insurance_response.insurer_payment}
                residual={ins.client_retained_loss.residual_exposure_at_p99_9}
              />
            </ChartCard>
          </div>

          {/* ---- Drivers + scenario contributions (detail) ---- */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <SectionCard title="Top risk drivers" subtitle="Factors driving the composite score">
              <div className="flex flex-wrap gap-2">
                {topDrivers.map((d) => (
                  <span
                    key={d}
                    className="rounded-full border border-risk-high/30 bg-risk-high/5 px-3 py-1 text-xs font-medium text-risk-high"
                  >
                    {d.replace(/_/g, ' ')}
                  </span>
                ))}
                {topDrivers.length === 0 && (
                  <span className="text-sm text-ink-500">No factors above domain average.</span>
                )}
              </div>
            </SectionCard>

            <SectionCard title="Scenario contributions" subtitle="Share of EAL per scenario, from the model">
              <div className="space-y-2.5">
                {Object.entries(sim.scenario_contribution)
                  .sort((a, b) => b[1] - a[1])
                  .map(([key, val]) => (
                    <div key={key} className="flex items-center justify-between rounded-lg bg-ink-50 px-3 py-2">
                      <span className="text-sm text-ink-700">{key.replace(/_/g, ' ')}</span>
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-28 overflow-hidden rounded-full bg-ink-200">
                          <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(100, val * 100)}%` }} />
                        </div>
                        <span className="w-12 text-right text-xs tabular-nums text-ink-500">{formatPct(val)}</span>
                      </div>
                    </div>
                  ))}
              </div>
            </SectionCard>
          </div>

          {/* ---- Model provenance ---- */}
          <div className="flex items-center gap-2 rounded-lg border border-ink-200 bg-ink-50/60 px-4 py-3 text-xs text-ink-500">
            <span className="status-dot h-2 w-2 rounded-full bg-emerald-500 text-emerald-500" />
            <span>
              {sim.n_years.toLocaleString()} simulated years · EAL {formatMoneyFull(sim.eal)} · VaR95{' '}
              {formatMoneyFull(sim.var_95)} · ES99 {formatMoneyFull(sim.es_99)} · PML 1-in-1000{' '}
              {formatMoneyFull(sim.pml_1in1000)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
