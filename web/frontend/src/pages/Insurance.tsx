import { useState } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { CompanyForm } from '../components/CompanyForm';
import { ErrorBanner, NeedsMoreInfo } from '../components/ErrorBanner';
import { MetricCard } from '../components/MetricCard';
import { SectionCard } from '../components/SectionCard';
import type { CompanyBrief, InsuranceResponse, PolicyInput } from '../lib/types';
import { formatMoney } from '../lib/format';

const POLICY_DEFAULTS: PolicyInput = {
  per_occurrence_deductible: 250000,
  per_occurrence_limit: 5000000,
  annual_aggregate_deductible: 1000000,
  annual_aggregate_limit: 20000000,
  coinsurance: 0,
};

function PolicyFields({ value, onChange }: { value: PolicyInput; onChange: (p: PolicyInput) => void }) {
  const fields: Array<{ key: keyof PolicyInput; label: string; step: number }> = [
    { key: 'per_occurrence_deductible', label: 'Per-occurrence deductible', step: 100000 },
    { key: 'per_occurrence_limit', label: 'Per-occurrence limit', step: 1000000 },
    { key: 'annual_aggregate_deductible', label: 'Annual aggregate deductible', step: 100000 },
    { key: 'annual_aggregate_limit', label: 'Annual aggregate limit', step: 1000000 },
  ];
  const set = (k: keyof PolicyInput, v: string) =>
    onChange({ ...value, [k]: v === '' ? undefined : Number(v) });

  return (
    <div className="mt-6 rounded-lg border border-ink-200 bg-ink-50 p-4">
      <div className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-ink-500">
        Insurance structure
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {fields.map(({ key, label, step }) => (
          <label key={key} className="block">
            <span className="mb-1 block text-xs text-ink-600">{label}</span>
            <input
              type="number"
              step={step}
              value={value[key] === undefined ? '' : String(value[key])}
              onChange={(e) => set(key, e.target.value)}
              className="w-full rounded-lg border border-ink-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
          </label>
        ))}
        <label className="block">
          <span className="mb-1 block text-xs text-ink-600">Coinsurance (0–1)</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={value.coinsurance === undefined ? '' : String(value.coinsurance)}
            onChange={(e) => set('coinsurance', e.target.value)}
            className="w-full rounded-lg border border-ink-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
        </label>
      </div>
    </div>
  );
}

export default function Insurance() {
  const [policy, setPolicy] = useState<PolicyInput>(POLICY_DEFAULTS);

  const { data, loading, error, run } = useApi<[CompanyBrief], InsuranceResponse | 'insufficient' | undefined>(
    (brief) =>
      api.insurance({ ...brief, ...policy }).then((r) =>
        r.status === 'ok' ? r : r.status === 'insufficient_info' ? 'insufficient' : undefined,
      ),
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-ink-900">Insurance structuring</h2>
        <p className="mt-1 text-sm text-ink-500">
          Test a proposed program — retention, limits, aggregate — against the loss model.
          Ground-up loss, insurer response and the client's residual exposure are kept
          strictly separate.
        </p>
      </div>

      <CompanyForm
        submitLabel="Analyse structure"
        loading={loading}
        onSubmit={(brief) => run(brief)}
      >
        <PolicyFields value={policy} onChange={setPolicy} />
      </CompanyForm>

      {error && <ErrorBanner message={error} />}
      {data === 'insufficient' && <NeedsMoreInfo needed={['revenue_usd', 'security_controls']} />}

      {data && data !== 'insufficient' && (
        <div className="space-y-6">
          <SectionCard title="Ground-up loss" subtitle="Before insurance — the client's modelled exposure">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <MetricCard label="EAL" value={formatMoney(data.ground_up_loss.eal)} />
              <MetricCard label="VaR 99%" value={formatMoney(data.ground_up_loss.var_99)} />
              <MetricCard label="ES 99%" value={formatMoney(data.ground_up_loss.es_99)} />
              <MetricCard label="PML 1-in-1000" value={formatMoney(data.ground_up_loss.pml_1in1000)} />
            </div>
          </SectionCard>

          <SectionCard title="Insurance response" subtitle="What the program pays at this structure">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard label="Policy limit" value={formatMoney(data.insurance_response.policy_limit)} accent />
              <MetricCard label="Retention" value={formatMoney(data.insurance_response.retention)} />
              <MetricCard label="Covered loss (EAL)" value={formatMoney(data.insurance_response.covered_loss)} />
              <MetricCard label="Insurer payment (EAL)" value={formatMoney(data.insurance_response.insurer_payment)} />
            </div>
          </SectionCard>

          <SectionCard title="Client retained loss" subtitle="Gross loss − insurance recovery (residual uncovered exposure)">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard label="Retained EAL" value={formatMoney(data.client_retained_loss.retained_eal)} />
              <MetricCard label="Retained ES 99%" value={formatMoney(data.client_retained_loss.retained_es_99)} />
              <MetricCard label="Gross @ p99.9" value={formatMoney(data.client_retained_loss.gross_loss_at_p99_9)} />
              <MetricCard label="Residual @ p99.9" value={formatMoney(data.client_retained_loss.residual_exposure_at_p99_9)} />
            </div>

            <div className="mt-5 rounded-lg border border-ink-200 bg-ink-50 p-4">
              <div className="flex items-start gap-3">
                <span className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${data.evaluation.residual_uncovered ? 'bg-risk-high' : 'bg-risk-low'}`} />
                <div>
                  <div className="text-sm font-semibold text-ink-900">
                    {data.evaluation.residual_uncovered ? 'Residual uncovered exposure remains' : 'No residual uncovered exposure'}
                  </div>
                  <p className="mt-1 text-sm text-ink-600">{data.evaluation.summary}</p>
                </div>
              </div>
            </div>
          </SectionCard>
        </div>
      )}
    </div>
  );
}
