import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { CompanyForm } from '../components/CompanyForm';
import { ErrorBanner } from '../components/ErrorBanner';
import { Spinner } from '../components/Spinner';
import { MetricCard } from '../components/MetricCard';
import { SectionCard } from '../components/SectionCard';
import { PageHeader } from '../components/PageHeader';
import { InsuranceOptimiseChart } from '../components/InsuranceOptimiseChart';
import type {
  CompanyBrief,
  InsuranceOptimiseResponse,
  InsuranceResponse,
  PolicyInput,
} from '../lib/types';
import { formatMoney, formatPct } from '../lib/format';
import { Check, ShieldHalf, TrendingUp } from 'lucide-react';

/** Default policy terms — mirrors the backend PolicyInput defaults. */
const POLICY_DEFAULTS: PolicyInput = {
  per_occurrence_deductible: 250_000,
  per_occurrence_limit: 5_000_000,
  annual_aggregate_deductible: 1_000_000,
  annual_aggregate_limit: 20_000_000,
  coinsurance: 0,
};

/** Slider bounds, in USD — chosen from the model's scale (PML 1-in-1000). */
const LIMIT_MIN = 1_000_000;
const LIMIT_MAX = 60_000_000;
const LIMIT_STEP = 500_000;
const RET_MIN = 100_000;
const RET_MAX = 5_000_000;
const RET_STEP = 50_000;

interface LiveState {
  loading: boolean;
  data: InsuranceResponse | null;
  error: string | null;
}

interface GapSource {
  gross_loss_at_p99_9: number;
  insurance_recovery_at_p99_9: number;
}

/** Coverage gap = gross 1-in-1000 loss minus insurance recovery (backend data). */
function coverageGap(d: GapSource): number {
  return Math.max(0, d.gross_loss_at_p99_9 - d.insurance_recovery_at_p99_9);
}

export default function InsuranceOptimiser() {
  // Client profile + policy terms for the "current" structure.
  const [brief, setBrief] = useState<CompanyBrief | null>(null);
  const [policy] = useState<PolicyInput>(POLICY_DEFAULTS);

  // Optimisation result (current + recommended).
  const [opt, setOpt] = useState<InsuranceOptimiseResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  // Live re-evaluation when sliders move.
  const [live, setLive] = useState<LiveState>({ loading: false, data: null, error: null });
  const [sliderLimit, setSliderLimit] = useState<number>(POLICY_DEFAULTS.per_occurrence_limit ?? 5_000_000);
  const [sliderRet, setSliderRet] = useState<number>(POLICY_DEFAULTS.per_occurrence_deductible ?? 250_000);
  const debounceRef = useRef<number | null>(null);
  const requestSeq = useRef(0);

  /** Fire a re-evaluation for the current slider values (debounced). */
  const reEvaluate = useCallback(
    (limit: number, retention: number) => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      const seq = ++requestSeq.current;
      setLive((s) => ({ ...s, loading: true, error: null }));
      debounceRef.current = window.setTimeout(async () => {
        if (!brief) {
          setLive({ loading: false, data: null, error: null });
          return;
        }
        try {
          const body = {
            ...brief,
            per_occurrence_deductible: retention,
            per_occurrence_limit: limit,
            annual_aggregate_deductible: policy.annual_aggregate_deductible,
            annual_aggregate_limit: limit,
            coinsurance: 0,
          };
          const res = await api.insurance(body);
          if (seq !== requestSeq.current) return; // stale response
          if (res.status === 'ok') setLive({ loading: false, data: res, error: null });
          else if (res.status === 'insufficient_info') setLive({ loading: false, data: null, error: 'Insufficient info' });
          else setLive({ loading: false, data: null, error: 'Model returned an error' });
        } catch (err) {
          if (seq !== requestSeq.current) return;
          setLive({ loading: false, data: null, error: err instanceof Error ? err.message : 'Request failed' });
        }
      }, 250);
    },
    [brief, policy.annual_aggregate_deductible],
  );

  const handleRun = useCallback(
    async (b: CompanyBrief) => {
      setRunning(true);
      setRunError(null);
      try {
        const body = {
          ...b,
          per_occurrence_deductible: b.retention ?? policy.per_occurrence_deductible,
          per_occurrence_limit: b.policy_limit ?? policy.per_occurrence_limit,
          annual_aggregate_deductible: policy.annual_aggregate_deductible,
          annual_aggregate_limit: b.policy_limit ?? policy.per_occurrence_limit,
          coinsurance: 0,
        };
        const res = await api.insuranceOptimise(body);
        if (res.status === 'ok') {
          setOpt(res);
          setBrief(b);
          // Seed sliders from the current structure.
          const curLimit = res.current.insurance_response.policy_limit;
          const curRet = res.current.insurance_response.retention;
          setSliderLimit(curLimit);
          setSliderRet(curRet);
          setLive({ loading: false, data: null, error: null });
        } else if (res.status === 'insufficient_info') {
          setRunError('Add revenue and security controls to run the model.');
        } else {
          setRunError('Model returned an error.');
        }
      } catch (err) {
        setRunError(err instanceof Error ? err.message : 'Something went wrong');
      } finally {
        setRunning(false);
      }
    },
    [policy.per_occurrence_deductible, policy.per_occurrence_limit],
  );

  // Trigger a re-evaluation once a result is in and the brief is set.
  const didInitial = useRef(false);
  useEffect(() => {
    if (opt && brief && !didInitial.current) {
      didInitial.current = true;
      reEvaluate(sliderLimit, sliderRet);
    }
  }, [opt, brief, reEvaluate, sliderLimit, sliderRet]);

  const liveData = live.data;
  const current = opt?.current ?? null;
  const recommended = opt?.recommended ?? null;

  const gap = liveData
    ? coverageGap(liveData.client_retained_loss)
    : current
      ? coverageGap(current.client_retained_loss)
      : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Risk & insurance"
        title="Insurance Optimisation"
        description="Compare your current structure against the model's recommendation, then drag the sliders to re-evaluate coverage in real time."
      />

      <CompanyForm
        submitLabel="Optimise insurance"
        loading={running}
        onSubmit={handleRun}
      />

      {runError && <ErrorBanner message={runError} />}
      {running && <Spinner label="Running insurance optimisation across limit / retention grid…" />}

      {!opt && !running && !runError && (
        <div className="card flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
          <ShieldHalf className="h-8 w-8 text-brand-500/60" />
          <p className="text-sm text-ink-600">
            Enter a company profile and click <strong>Optimise insurance</strong> to see your
            current vs recommended structure.
          </p>
        </div>
      )}

      {opt && current && recommended && (
        <div className="panel-in space-y-6">
          {/* Sliders */}
          <SectionCard
            title="Adjust your structure"
            subtitle="Changes re-evaluate the model instantly (debounced)."
          >
            <div className="grid gap-6 lg:grid-cols-2">
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label htmlFor="sl-limit" className="text-sm font-medium text-ink-700">Policy limit</label>
                  <span className="font-mono text-sm text-ink-900">{formatMoney(sliderLimit)}</span>
                </div>
                <input
                  id="sl-limit"
                  type="range"
                  min={LIMIT_MIN}
                  max={LIMIT_MAX}
                  step={LIMIT_STEP}
                  value={sliderLimit}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setSliderLimit(v);
                    reEvaluate(v, sliderRet);
                  }}
                  className="w-full accent-brand-600"
                />
                <div className="mt-1 flex justify-between text-[11px] text-ink-400">
                  <span>{formatMoney(LIMIT_MIN)}</span>
                  <span>{formatMoney(LIMIT_MAX)}</span>
                </div>
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label htmlFor="sl-ret" className="text-sm font-medium text-ink-700">Retention</label>
                  <span className="font-mono text-sm text-ink-900">{formatMoney(sliderRet)}</span>
                </div>
                <input
                  id="sl-ret"
                  type="range"
                  min={RET_MIN}
                  max={RET_MAX}
                  step={RET_STEP}
                  value={sliderRet}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setSliderRet(v);
                    reEvaluate(sliderLimit, v);
                  }}
                  className="w-full accent-brand-600"
                />
                <div className="mt-1 flex justify-between text-[11px] text-ink-400">
                  <span>{formatMoney(RET_MIN)}</span>
                  <span>{formatMoney(RET_MAX)}</span>
                </div>
              </div>
            </div>
            <div className="mt-2 flex items-center gap-2 text-xs text-ink-500">
              {live.loading && <Spinner small label="Re-evaluating…" />}
              {!live.loading && liveData && <span className="text-emerald-600">✓ Updated from the model</span>}
              {live.error && <span className="text-risk-high">{live.error}</span>}
            </div>
          </SectionCard>

          {/* Headline comparison: live vs current vs recommended */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Your retention" value={formatMoney(sliderRet)} sub="drag to change" accent />
            <MetricCard label="Policy limit" value={formatMoney(sliderLimit)} sub="drag to change" accent />
            <MetricCard label="Coverage gap" value={formatMoney(gap)} sub="gross p99.9 − recovery" />
            <MetricCard label="Prob. exhaustion" value={formatPct(liveData?.insurance_response.p_annual_limit_exhausted ?? current.insurance_response.p_annual_limit_exhausted)} sub="annual limit exhausted" />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Expected recovery" value={formatMoney(liveData?.insurance_response.insurer_payment ?? current.insurance_response.insurer_payment)} sub="insurer pays (EAL)" />
            <MetricCard label="Residual exposure" value={formatMoney(liveData?.client_retained_loss.residual_exposure_at_p99_9 ?? current.client_retained_loss.residual_exposure_at_p99_9)} sub="at 1-in-1000-year loss" />
            <MetricCard label="Retained EAL" value={formatMoney(liveData?.client_retained_loss.retained_eal ?? current.client_retained_loss.retained_eal)} sub="after insurance" />
            <MetricCard label="Evaluation" value={<span className="text-sm">{liveData?.evaluation.summary.slice(0, 42) ?? current.evaluation.summary.slice(0, 42)}…</span>} sub={liveData?.evaluation.residual_uncovered ? 'residual remains' : 'fully covered'} />
          </div>

          {/* Current vs Recommended comparison chart */}
          <SectionCard title="Current vs recommended" subtitle="The model's recommendation, evaluated on the same Monte Carlo engine">
            <div className="h-72">
              <InsuranceOptimiseChart
                current={{ policyLimit: current.insurance_response.policy_limit, retention: current.insurance_response.retention, insurerPayment: current.insurance_response.insurer_payment, residual: current.client_retained_loss.residual_exposure_at_p99_9 }}
                recommended={{ policyLimit: recommended.policy_limit, retention: recommended.retention, insurerPayment: recommended.insurer_payment, residual: recommended.residual_exposure }}
                live={liveData ? { policyLimit: sliderLimit, retention: sliderRet, insurerPayment: liveData.insurance_response.insurer_payment, residual: liveData.client_retained_loss.residual_exposure_at_p99_9 } : null}
              />
            </div>
            <div className="mt-3 rounded-lg border border-brand-500/20 bg-brand-50 px-4 py-3 text-sm text-ink-700">
              <div className="flex items-center gap-2 font-semibold text-brand-700">
                <TrendingUp className="h-4 w-4" />
                Recommended: {formatMoney(recommended.policy_limit)} limit · {formatMoney(recommended.retention)} retention
              </div>
              <p className="mt-1 text-xs text-ink-600">{recommended.evaluation.summary}</p>
            </div>
          </SectionCard>

          {/* Detailed comparison table */}
          <SectionCard title="Structure comparison" subtitle="Backend-evaluated figures">
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-ink-200 text-left text-xs uppercase tracking-wide text-ink-400">
                    <th className="py-2 pr-4 font-semibold">Metric</th>
                    <th className="py-2 pr-4 font-semibold">Current</th>
                    <th className="py-2 pr-4 font-semibold">Recommended</th>
                    <th className="py-2 font-semibold">Your slider setting</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {[
                    { label: 'Policy limit', cur: current.insurance_response.policy_limit, rec: recommended.policy_limit, live: liveData?.insurance_response.policy_limit ?? current.insurance_response.policy_limit },
                    { label: 'Retention', cur: current.insurance_response.retention, rec: recommended.retention, live: liveData?.insurance_response.retention ?? current.insurance_response.retention },
                    { label: 'Expected recovery (EAL)', cur: current.insurance_response.insurer_payment, rec: recommended.insurer_payment, live: liveData?.insurance_response.insurer_payment ?? current.insurance_response.insurer_payment },
                    { label: 'Prob. exhaustion', cur: current.insurance_response.p_annual_limit_exhausted, rec: recommended.p_annual_limit_exhausted, live: liveData?.insurance_response.p_annual_limit_exhausted ?? current.insurance_response.p_annual_limit_exhausted, pct: true },
                    { label: 'Residual exposure', cur: current.client_retained_loss.residual_exposure_at_p99_9, rec: recommended.residual_exposure, live: liveData?.client_retained_loss.residual_exposure_at_p99_9 ?? current.client_retained_loss.residual_exposure_at_p99_9 },
                  ].map((row) => (
                    <tr key={row.label}>
                      <td className="py-2 pr-4 font-medium text-ink-700">{row.label}</td>
                      <td className="py-2 pr-4 text-ink-600">{row.pct ? formatPct(row.cur) : formatMoney(row.cur)}</td>
                      <td className="py-2 pr-4 text-ink-600">{row.pct ? formatPct(row.rec) : formatMoney(row.rec)}</td>
                      <td className="py-2 font-medium text-brand-700">{row.pct ? formatPct(row.live) : formatMoney(row.live)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-start gap-2 rounded-lg bg-ink-50 p-3 text-xs text-ink-600">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              <span>
                Every figure is computed by the CyberRisk engine. The recommended structure is the
                grid point that maximises insurance recovery per dollar of limit while minimising
                residual tail exposure — evaluated on the same simulation as your current policy.
              </span>
            </div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}
