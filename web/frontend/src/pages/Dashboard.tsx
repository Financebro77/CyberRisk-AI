import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  FileText,
  Gauge,
  Network,
  ShieldHalf,
  SlidersHorizontal,
} from 'lucide-react';
import { api } from '../lib/api';
import { MetricCard } from '../components/MetricCard';
import { SectionCard } from '../components/SectionCard';
import type { ScenarioSummary } from '../lib/types';

const WORKFLOW = [
  {
    to: '/app/assess',
    icon: Gauge,
    title: 'Assess risk',
    desc: 'Score the client profile 0-100 and surface the top drivers.',
  },
  {
    to: '/app/simulate',
    icon: Activity,
    title: 'Model losses',
    desc: 'Monte Carlo EAL, VaR/ES and 1-in-1000-year PMLs across 7 scenarios.',
  },
  {
    to: '/app/insurance',
    icon: ShieldHalf,
    title: 'Structure insurance',
    desc: 'Test limits and retention; see the insurer response and residual exposure.',
  },
  {
    to: '/app/controls',
    icon: SlidersHorizontal,
    title: 'Improve controls',
    desc: 'Model the loss reduction from MFA, segmentation, backups and more.',
  },
  {
    to: '/app/report',
    icon: FileText,
    title: 'Generate report',
    desc: 'Export the Excel workbook with the mandatory limitations disclosure.',
  },
  {
    to: '/app/methodology',
    icon: Network,
    title: 'White-box model',
    desc: 'Every number traces to documented config and deterministic logic.',
  },
];

export default function Dashboard() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [health, setHealth] = useState<{ version: string; service: string } | null>(null);

  useEffect(() => {
    api.scenarios().then((r) => setScenarios(r.scenarios)).catch(() => {});
    api.health().then((h) => setHealth(h)).catch(() => {});
  }, []);

  const topRisks = [...scenarios].sort((a, b) => b.lambda_annual - a.lambda_annual).slice(0, 4);

  return (
    <div className="space-y-8">
      <section className="rounded-2xl bg-ink-950 px-8 py-10 text-white">
        <div className="font-serif text-5xl font-medium tracking-tight">CyberRisk AI</div>
        <p className="mt-3 max-w-2xl text-lg text-ink-300">
          A Marsh/Aon-style cyber risk consulting platform — deterministic scoring,
          Monte Carlo loss modelling and insurance structuring on a white-box engine.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to="/app/assess"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-400"
          >
            Start an assessment <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/app/methodology"
            className="inline-flex items-center gap-2 rounded-lg border border-ink-700 px-4 py-2 text-sm font-semibold text-ink-200 transition-colors hover:bg-ink-800"
          >
            <Network className="h-4 w-4" /> How the model works
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Platform" value="CyberRisk AI" sub="v{health?.version ?? '0.1.0'}" accent />
        <MetricCard label="Scenarios" value={scenarios.length || '—'} sub="calibrated loss models" />
        <MetricCard
          label="Composite score"
          value="0–100"
          sub="deterministic, evidence-scored"
        />
        <MetricCard
          label="Tail measure"
          value="VaR / ES"
          sub="95% & 99%, 1-year horizon"
        />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <SectionCard title="Consulting workflow" subtitle="From client brief to board-ready advice">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {WORKFLOW.map(({ to, icon: Icon, title, desc }) => (
                <Link
                  key={to}
                  to={to}
                  className="group rounded-xl border border-ink-200 bg-white p-5 transition-all hover:border-brand-500/40 hover:shadow-md"
                >
                  <div className="flex items-center gap-2 text-ink-900">
                    <Icon className="h-5 w-5 text-brand-600" />
                    <span className="text-sm font-semibold">{title}</span>
                  </div>
                  <p className="mt-2 text-sm text-ink-500">{desc}</p>
                  <div className="mt-3 flex items-center gap-1 text-xs font-medium text-brand-600 opacity-0 transition-opacity group-hover:opacity-100">
                    Open <ArrowRight className="h-3 w-3" />
                  </div>
                </Link>
              ))}
            </div>
          </SectionCard>
        </div>

        <SectionCard title="Top-frequency scenarios" subtitle="Baseline λ per year (config/scenarios.yaml)">
          <div className="space-y-3">
            {topRisks.map((s) => (
              <div key={s.key} className="flex items-center justify-between rounded-lg bg-ink-50 px-3 py-2.5">
                <div className="text-sm font-medium text-ink-700">{s.name}</div>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-200">
                    <div
                      className="h-full rounded-full bg-brand-500"
                      style={{ width: `${Math.min(100, (s.lambda_annual / 1.1) * 100)}%` }}
                    />
                  </div>
                  <span className="w-10 text-right text-xs tabular-nums text-ink-500">
                    {s.lambda_annual.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
            {scenarios.length === 0 && (
              <div className="text-sm text-ink-400">Loading scenario calibration…</div>
            )}
          </div>
        </SectionCard>
      </section>

      {health && (
        <p className="text-xs text-ink-400">
          {health.service} {health.version} · API connected
        </p>
      )}
    </div>
  );
}
