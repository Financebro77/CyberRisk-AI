import { useCallback, useRef, useState } from 'react';
import { api } from '../lib/api';
import { CompanyForm } from '../components/CompanyForm';
import { ErrorBanner } from '../components/ErrorBanner';
import { RiskBadge } from '../components/RiskBadge';
import { PageHeader } from '../components/PageHeader';
import { Skeleton } from '../components/Skeleton';
import {
  Download,
  FileSpreadsheet,
  Printer,
  Share2,
  AlertTriangle,
  ArrowUpRight,
  Building2,
} from 'lucide-react';
import type { CompanyBrief, ExecutiveReportResponse } from '../lib/types';
import { formatMoney, formatMoneyFull, formatPct, formatScore } from '../lib/format';

/** Domain label map for the risk-breakdown bars. */
const DOMAIN_LABELS: Record<string, string> = {
  threat_exposure: 'Threat exposure',
  vulnerability_mgmt: 'Vulnerability mgmt',
  access_control: 'Access control',
  endpoint_resilience: 'Endpoint resilience',
  third_party_risk: 'Third-party risk',
  resilience_governance: 'Resilience & governance',
};

const SCENARIO_LABELS: Record<string, string> = {
  breach: 'Data breach',
  ransomware: 'Ransomware',
  bec: 'BEC / fraud',
  cloud_outage: 'Cloud outage',
  bi: 'Business interruption',
  supply_chain: 'Supply chain',
  ot_physical: 'OT / physical',
};

export default function Report() {
  const [data, setData] = useState<ExecutiveReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [brief, setBrief] = useState<CompanyBrief | null>(null);
  const [copied, setCopied] = useState(false);
  const lastBrief = useRef<CompanyBrief | null>(null);

  const run = useCallback(async (b: CompanyBrief) => {
    lastBrief.current = b;
    setLoading(true);
    setError(null);
    try {
      const res = await api.executiveReport(b);
      if (res.status === 'ok') {
        setData(res);
        setBrief(b);
      } else if (res.status === 'insufficient_info') {
        setError('Add revenue and security controls to generate the report.');
      } else {
        setError('The model returned an error.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }, []);

  const downloadExcel = useCallback(async () => {
    if (!brief) return;
    try {
      // Generate the workbook server-side, then download the most recent one.
      const res = await api.report(brief);
      if (res.status === 'ok') {
        window.open(api.reportDownloadUrl(), '_blank');
      }
    } catch {
      /* surface nothing — Excel is a fallback */
    }
  }, [brief]);

  const downloadPdf = useCallback(() => {
    // Client-side print-to-PDF: a print stylesheet renders only the report.
    window.print();
  }, []);

  const shareReport = useCallback(async () => {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable */
    }
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <ReportHeader />
        <div className="card p-6">
          <Skeleton className="mb-3 h-8 w-64" />
          <Skeleton className="mb-6 h-4 w-full max-w-xl" />
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
          <Skeleton className="mt-6 h-44 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ReportHeader />

      <CompanyForm submitLabel="Generate report" loading={loading} onSubmit={run} />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={lastBrief.current ? () => void run(lastBrief.current!) : undefined}
        />
      )}
      {!data && !error && (
        <p className="text-sm text-ink-500">
          Enter a company profile and click <strong>Generate report</strong> to produce the
          board-ready executive summary.
        </p>
      )}

      {data && (
        <div className="report-document panel-in">
          {/* Toolbar */}
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
            <div className="flex items-center gap-2 text-xs text-ink-500">
              <Building2 className="h-4 w-4" />
              {data.firm_name} · Confidential
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={downloadPdf} className="report-action-btn bg-ink-950 text-white hover:bg-ink-800">
                <Download className="h-4 w-4" /> Download PDF
              </button>
              <button type="button" onClick={downloadExcel} className="report-action-btn border border-ink-300 bg-white text-ink-700 hover:border-brand-500 hover:text-brand-600">
                <FileSpreadsheet className="h-4 w-4" /> Download Excel
              </button>
              <button type="button" onClick={shareReport} className="report-action-btn border border-ink-300 bg-white text-ink-700 hover:border-brand-500 hover:text-brand-600">
                {copied ? <span className="text-emerald-600">✓ Copied</span> : <Share2 className="h-4 w-4" />}
                Share Report
              </button>
              <button type="button" onClick={() => window.print()} className="report-action-btn border border-ink-300 bg-white text-ink-700 hover:border-brand-500 hover:text-brand-600">
                <Printer className="h-4 w-4" /> Print
              </button>
            </div>
          </div>

          {/* Cover */}
          <div className="report-section border-t-4 border-brand-600 bg-ink-950 px-8 py-10 text-white">
            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-brand-300">
              Cyber Risk Consulting · Executive Report
            </div>
            <h1 className="mt-3 font-serif text-4xl font-semibold tracking-tight">
              {data.firm_name}
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-ink-300">
              Cyber risk assessment, financial exposure, and insurance analysis prepared on the
              CyberRisk AI stochastic engine.
            </p>
            <div className="mt-6 flex flex-wrap gap-x-10 gap-y-3 text-xs text-ink-400">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-ink-500">Prepared for</div>
                <div className="mt-0.5 font-medium text-white">Risk Management</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-ink-500">Prepared by</div>
                <div className="mt-0.5 font-medium text-white">CyberRisk AI</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-ink-500">Date</div>
                <div className="mt-0.5 font-medium text-white">{new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-ink-500">Confidentiality</div>
                <div className="mt-0.5 font-medium text-white">Internal — confidential</div>
              </div>
            </div>
          </div>

          {/* Executive Summary */}
          <ReportSection title="1 · Executive Summary">
            <p className="text-[15px] leading-relaxed text-ink-700">{data.executive_summary.sentence}</p>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <ReportKpi label="Risk score" value={formatScore(data.risk_rating.score)} sub={<RiskBadge category={data.risk_rating.category} />} />
              <ReportKpi label="Expected annual loss" value={formatMoney(data.financial_exposure.eal)} sub="modelled mean" />
              <ReportKpi label="VaR 99%" value={formatMoney(data.financial_exposure.var_99)} sub="1-in-100-year" />
              <ReportKpi label="ES 99%" value={formatMoney(data.financial_exposure.es_99)} sub="tail beyond VaR" />
            </div>
          </ReportSection>

          {/* Cyber Risk Rating */}
          <ReportSection title="2 · Cyber Risk Rating">
            <div className="grid gap-8 lg:grid-cols-2">
              <div>
                <div className="mb-4 flex items-center gap-3">
                  <div className="text-5xl font-bold tabular-nums text-ink-900">{formatScore(data.risk_rating.score)}</div>
                  <div className="flex items-center gap-2 text-lg font-semibold text-ink-700">
                    <RiskBadge category={data.risk_rating.category} />
                  </div>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-ink-100">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${data.risk_rating.score}%`, background: scoreColor(data.risk_rating.score) }}
                  />
                </div>
                <div className="mt-1.5 flex justify-between text-[11px] text-ink-400">
                  <span>0 · Low</span>
                  <span>50 · Medium</span>
                  <span>100 · Critical</span>
                </div>
              </div>
              <div>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Domain scores</div>
                <div className="space-y-2">
                  {Object.entries(data.risk_rating.domain_scores).map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2">
                      <span className="w-36 shrink-0 text-xs text-ink-600">{DOMAIN_LABELS[key] ?? key.replace(/_/g, ' ')}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-100">
                        <div className="h-full rounded-full" style={{ width: `${val}%`, background: scoreColor(val) }} />
                      </div>
                      <span className="w-8 text-right font-mono text-[11px] text-ink-500">{val.toFixed(0)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </ReportSection>

          {/* Financial Exposure */}
          <ReportSection title="3 · Financial Exposure">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <ReportKpi label="EAL" value={formatMoney(data.financial_exposure.eal)} sub="expected annual loss" />
              <ReportKpi label="VaR 95%" value={formatMoney(data.financial_exposure.var_95)} sub="1-in-20-year" />
              <ReportKpi label="VaR 99%" value={formatMoney(data.financial_exposure.var_99)} sub="1-in-100-year" />
              <ReportKpi label="ES 99%" value={formatMoney(data.financial_exposure.es_99)} sub="tail beyond VaR" />
              <ReportKpi label="PML 1-in-200" value={formatMoney(data.financial_exposure.pml_1in200)} sub="99.5th percentile" />
              <ReportKpi label="PML 1-in-1000" value={formatMoney(data.financial_exposure.pml_1in1000)} sub="99.9th percentile" />
            </div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-ink-200 bg-ink-50 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Loss distribution</div>
                <div className="flex items-end gap-1.5" style={{ height: 88 }}>
                  {Object.entries(data.financial_exposure.loss_distribution).map(([k, v], i) => (
                    <div key={k} className="flex flex-1 flex-col items-center gap-1">
                      <div
                        className="w-full rounded-t-sm transition-all duration-700"
                        style={{ height: `${Math.max(4, (v / data.financial_exposure.pml_1in1000) * 100)}%`, background: i >= 3 ? '#dc2626' : i >= 1 ? '#d97706' : '#2563eb' }}
                      />
                      <span className="text-[10px] text-ink-500">{k.replace('p', 'p').toUpperCase()}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-ink-200 bg-ink-50 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Scenario contribution</div>
                <div className="space-y-1.5">
                  {Object.entries(data.scenario_contributions).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2">
                      <span className="w-28 shrink-0 text-[11px] text-ink-600">{SCENARIO_LABELS[k] ?? k.replace(/_/g, ' ')}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-200">
                        <div className="h-full rounded-full bg-brand-600" style={{ width: `${v * 100}%` }} />
                      </div>
                      <span className="w-9 text-right font-mono text-[11px] text-ink-500">{formatPct(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </ReportSection>

          {/* Top Risk Drivers */}
          <ReportSection title="4 · Top Risk Drivers">
            <div className="flex flex-wrap gap-2">
              {data.risk_rating.risk_drivers.map((d) => (
                <span key={d} className="inline-flex items-center gap-1.5 rounded-full border border-risk-high/30 bg-risk-high/5 px-3 py-1 text-xs font-medium text-risk-high">
                  <AlertTriangle className="h-3 w-3" />
                  {d.replace(/_/g, ' ')}
                </span>
              ))}
              {data.risk_rating.risk_drivers.length === 0 && (
                <span className="text-sm text-ink-500">No factors above domain average.</span>
              )}
            </div>
            <p className="mt-4 text-sm text-ink-600">
              Drivers are the weighted factors whose scores exceed their domain average — the
              specific controls, dependencies, and posture items moving the composite score.
            </p>
          </ReportSection>

          {/* Insurance Analysis */}
          <ReportSection title="5 · Insurance Analysis">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <ReportKpi label="Policy limit" value={formatMoney(data.insurance_analysis.insurance_response.policy_limit)} sub="current program" />
              <ReportKpi label="Retention" value={formatMoney(data.insurance_analysis.insurance_response.retention)} sub="per occurrence" />
              <ReportKpi label="Expected recovery" value={formatMoney(data.insurance_analysis.insurance_response.insurer_payment)} sub="insurer pays (EAL)" />
              <ReportKpi label="Residual exposure" value={formatMoney(data.insurance_analysis.client_retained_loss.residual_exposure_at_p99_9)} sub="at 1-in-1000 loss" />
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-ink-200 bg-ink-50 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Coverage position</div>
                <div className="flex items-center gap-2 text-sm text-ink-700">
                  <span className={`h-2.5 w-2.5 rounded-full ${data.insurance_analysis.evaluation.residual_uncovered ? 'bg-risk-high' : 'bg-risk-low'}`} />
                  {data.insurance_analysis.evaluation.residual_uncovered
                    ? 'Residual uncovered exposure remains after insurance'
                    : 'No residual uncovered exposure at the modelled tail'}
                </div>
                <p className="mt-2 text-sm text-ink-600">{data.insurance_analysis.evaluation.summary}</p>
              </div>
              <div className="rounded-lg border border-ink-200 bg-ink-50 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Insurance recovery at tail</div>
                <div className="text-2xl font-semibold tabular-nums text-ink-900">
                  {formatMoney(data.insurance_analysis.client_retained_loss.insurance_recovery_at_p99_9)}
                </div>
                <p className="mt-1 text-sm text-ink-600">
                  Gross 1-in-1000 loss {formatMoney(data.insurance_analysis.client_retained_loss.gross_loss_at_p99_9)} ·
                  retained ES {formatMoney(data.insurance_analysis.client_retained_loss.retained_es_99)}
                </p>
              </div>
            </div>
          </ReportSection>

          {/* Mitigation Roadmap */}
          <ReportSection title="6 · Mitigation Roadmap">
            <div className="space-y-4">
              {data.mitigation_roadmap.map((s) => (
                <div key={s.scenario_key} className="rounded-lg border border-ink-200 bg-ink-50/60 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <ArrowUpRight className="h-4 w-4 text-brand-600" />
                      <span className="text-sm font-semibold text-ink-900">{s.scenario_name}</span>
                    </div>
                    <span className="font-mono text-[11px] text-ink-500">
                      {formatPct(s.contribution)} of EAL · {formatMoneyFull(s.aal)}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {s.recommended_controls.map((c) => (
                      <span key={c} className="rounded-md bg-brand-100 px-2 py-0.5 text-[11px] font-medium text-brand-700">{c}</span>
                    ))}
                    {s.recommended_controls.length === 0 && (
                      <span className="text-xs text-ink-400">No specific controls recommended by the model.</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </ReportSection>

          {/* Model Limitations */}
          <ReportSection title={`7 · ${data.model_limitations.heading}`}>
            <ul className="space-y-2">
              {data.model_limitations.limitations.map((l) => (
                <li key={l} className="flex items-start gap-2 text-sm text-ink-600">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-400" />
                  {l}
                </li>
              ))}
            </ul>
          </ReportSection>

          {/* Signature block */}
          <div className="mt-8 flex items-end justify-between border-t border-ink-200 pt-6 text-xs text-ink-500 print:pt-6">
            <div>
              <div className="font-semibold text-ink-700">CyberRisk AI</div>
              <div>Quantitative cyber risk consulting</div>
            </div>
            <div className="text-right">
              <div>Prepared with the CyberRisk AI stochastic engine</div>
              <div className="mt-0.5">Confidential — not for distribution</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* --------------------------- sub-components --------------------------- */

function ReportHeader() {
  return (
    <PageHeader
      eyebrow="Client deliverable"
      title="Executive report"
      description="Board-ready cyber risk assessment — exposure, insurance and mitigation, formatted for directors. Downloadable as PDF or Excel, or print directly."
    />
  );
}

function ReportSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="report-section border-b border-ink-100 px-8 py-7">
      <h3 className="mb-4 text-sm font-bold uppercase tracking-[0.14em] text-ink-900">{title}</h3>
      {children}
    </section>
  );
}

function ReportKpi({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-ink-200 bg-white p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-500">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-ink-900">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-ink-500">{sub}</div>}
    </div>
  );
}

function scoreColor(score: number): string {
  if (score >= 75) return '#7f1d1d';
  if (score >= 60) return '#dc2626';
  if (score >= 40) return '#d97706';
  if (score >= 20) return '#2563eb';
  return '#16a34a';
}
