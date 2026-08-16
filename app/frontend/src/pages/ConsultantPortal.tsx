import { useState } from 'react';
import { api } from '../lib/api';
import { useApi } from '../lib/useApi';
import { CompanyForm } from '../components/CompanyForm';
import { ErrorBanner } from '../components/ErrorBanner';
import { RiskBadge } from '../components/RiskBadge';
import { MetricCard } from '../components/MetricCard';
import { SectionCard } from '../components/SectionCard';
import Consultant from './Consultant';
import { MessageSquare, ClipboardList } from 'lucide-react';
import type { CompanyBrief, ExecutiveReportResponse } from '../lib/types';
import { formatMoney, formatScore } from '../lib/format';

type Mode = 'assess' | 'chat';

function formatDrivers(drivers: string[]): string[] {
  return drivers.map((d) => d.replace(/_/g, ' '));
}

function AdvisoryReport({ data }: { data: ExecutiveReportResponse }) {
  const f = data.financial_exposure;
  const ins = data.insurance_analysis;
  const rating = data.risk_rating;

  return (
    <div className="panel-in space-y-6">
      {/* Executive summary */}
      <div className="card p-6">
        <div className="text-xs font-semibold uppercase tracking-[0.15em] text-accent">Executive summary</div>
        <p className="mt-3 font-serif text-lg leading-relaxed text-ink-900">{data.executive_summary.sentence}</p>
      </div>

      {/* Risk rating */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard label="Cyber risk score" value={formatScore(rating.score)} sub={<RiskBadge category={rating.category} />} accent />
        <MetricCard label="Expected annual loss" value={formatMoney(f.eal)} sub="average loss per year" />
        <MetricCard label="1-in-1000-year loss" value={formatMoney(f.pml_1in1000)} sub="extreme tail" />
      </div>

      {/* Main risk drivers */}
      <SectionCard title="Main risk drivers" subtitle="Factors above their domain average">
        <div className="flex flex-wrap gap-2">
          {formatDrivers(rating.risk_drivers).map((d) => (
            <span key={d} className="rounded-full border border-risk-high/30 bg-risk-high/5 px-3 py-1 text-xs font-medium text-risk-high">
              {d}
            </span>
          ))}
          {rating.risk_drivers.length === 0 && <span className="text-sm text-ink-500">No factors above domain average.</span>}
        </div>
      </SectionCard>

      {/* Loss measures */}
      <SectionCard title="Loss measures" subtitle="From the simulated annual loss distribution">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <MetricCard label="VaR 95%" value={formatMoney(f.var_95)} sub="stays below 95% of years" />
          <MetricCard label="VaR 99%" value={formatMoney(f.var_99)} sub="stays below 99% of years" />
          <MetricCard label="Expected Shortfall (99%)" value={formatMoney(f.es_99)} sub="average of the worst 1% of years" />
        </div>
      </SectionCard>

      {/* Insurance */}
      <SectionCard title="Insurance recommendations" subtitle="Modelled against the client's retained exposure">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <MetricCard label="Policy limit" value={formatMoney(ins.insurance_response.policy_limit)} sub="modelled" />
          <MetricCard label="Retention" value={formatMoney(ins.insurance_response.retention)} sub="client carries first" />
          <MetricCard
            label="Residual uncovered (1-in-1000)"
            value={formatMoney(ins.client_retained_loss.residual_exposure_at_p99_9)}
            sub="after insurance recovery"
          />
        </div>
        <div className="mt-4 rounded-lg border border-ink-200 bg-ink-50 p-4 text-sm leading-relaxed text-ink-600">
          {ins.evaluation.summary}
        </div>
      </SectionCard>

      {/* Mitigation */}
      <SectionCard title="Risk mitigation actions" subtitle="Recommended controls mapped to the main drivers">
        <ul className="space-y-2 text-sm text-ink-700">
          {data.mitigation_roadmap.map((m) => (
            <li key={m.scenario_key} className="flex items-start gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
              <span>
                <span className="font-medium text-ink-900">{m.scenario_name}</span>
                {' — '}
                {m.recommended_controls.join(', ')}
              </span>
            </li>
          ))}
          {data.mitigation_roadmap.length === 0 && <li>No mitigation roadmap available.</li>}
        </ul>
      </SectionCard>

      {/* Model limitations */}
      {data.model_limitations && (
        <SectionCard title={data.model_limitations.heading} subtitle="Mandatory disclosure">
          <ul className="list-inside list-disc space-y-1 text-sm text-ink-600">
            {data.model_limitations.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}

function AssessmentTab() {
  const { data, loading, error, run } = useApi<[CompanyBrief], ExecutiveReportResponse | undefined>(
    (brief) => api.executiveReport(brief).then((r) => (r.status === 'ok' ? r : undefined)),
  );

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-8">
      <div>
        <h1 className="font-serif text-2xl font-medium tracking-tight text-ink-900">Company assessment</h1>
        <p className="mt-1 text-sm text-ink-500">
          Enter the company profile and answer the security questions, then submit. The
          consultant returns a full advisory assessment.
        </p>
      </div>

      <CompanyForm submitLabel="Submit assessment" loading={loading} onSubmit={(brief) => run(brief)} />

      {error && <ErrorBanner message={error} />}
      {data && <AdvisoryReport data={data} />}
    </div>
  );
}

function ChatTab() {
  return (
    <div className="h-[calc(100vh-4rem)]">
      <Consultant />
    </div>
  );
}

export default function ConsultantPortal() {
  const [mode, setMode] = useState<Mode>('assess');

  return (
    <div className="min-h-screen bg-ink-50 font-sans">
      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b border-ink-200 bg-ink-50/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3 lg:px-8">
          <span className="text-sm font-semibold tracking-wide text-ink-900">CyberRisk AI Consultant</span>
          <nav className="flex items-center gap-1 rounded-lg border border-ink-200 bg-ink-50 p-0.5">
            <button
              type="button"
              onClick={() => setMode('assess')}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                mode === 'assess' ? 'bg-ink-100 text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-900'
              }`}
            >
              <ClipboardList className="h-3.5 w-3.5" /> Assess
            </button>
            <button
              type="button"
              onClick={() => setMode('chat')}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                mode === 'chat' ? 'bg-ink-100 text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-900'
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" /> Ask the consultant
            </button>
          </nav>
          <a href="/" className="text-xs font-medium text-ink-400 transition-colors hover:text-ink-900">
            ← Back
          </a>
        </div>
      </header>

      {mode === 'assess' ? <AssessmentTab /> : <ChatTab />}
    </div>
  );
}
