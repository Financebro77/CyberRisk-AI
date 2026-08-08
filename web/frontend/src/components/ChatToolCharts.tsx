import type { ChatToolTrace } from '../lib/types';
import { ChartCard } from './ChartCard';
import {
  LossDistributionChart,
  LossExceedanceChart,
  ScenarioContributionChart,
  InsuranceWaterfallChart,
} from './charts';
import { formatMoney, formatPct } from '../lib/format';

interface DataShape {
  status?: string;
  prob_zero_loss?: number;
  loss_distribution?: Record<string, number>;
  loss_exceedance?: Array<{ loss: number; prob: number }>;
  scenario_contribution?: Record<string, number>;
  eal?: number;
  var_95?: number;
  var_99?: number;
  es_99?: number;
  ground_up_loss?: { eal: number; var_95: number; var_99: number; es_99: number; pml_1in1000: number };
  insurance_response?: { policy_limit: number; retention: number; covered_loss: number; insurer_payment: number };
  client_retained_loss?: { retained_eal: number; retained_es_99: number; gross_loss_at_p99_9: number; insurance_recovery_at_p99_9: number; residual_exposure_at_p99_9: number };
}

type ToolData = Record<string, unknown>;

function asData(data: ToolData): DataShape {
  return data as unknown as DataShape;
}

/**
 * Renders charts ONLY from figures a tool actually returned this turn.
 * If the tool trace has no chartable data, nothing renders — the answer
 * text is still shown, but no fabricated chart appears.
 */
export function ChatToolCharts({ trace }: { trace: ChatToolTrace[] }) {
  const charts: React.ReactNode[] = [];

  for (const t of trace) {
    if (!t.ok || !t.data) continue;
    const d = asData(t.data);
    if (d.status && d.status !== 'ok') continue;

    // Loss distribution (from run_loss_simulation)
    if (d.loss_distribution) {
      charts.push(
        <ChartCard key={`${t.name}-dist`} title="Loss distribution" subtitle="Annual loss quantiles (p50 → p99.9)">
          <LossDistributionChart quantiles={d.loss_distribution} />
        </ChartCard>,
      );
    }

    // Loss exceedance curve (from run_loss_simulation)
    if (d.loss_exceedance && d.loss_exceedance.length > 0) {
      charts.push(
        <ChartCard key={`${t.name}-exc`} title="Loss exceedance curve" subtitle="Probability of loss ≥ level">
          <LossExceedanceChart points={d.loss_exceedance} />
        </ChartCard>,
      );
    }

    // Scenario contribution (from run_loss_simulation)
    if (d.scenario_contribution && Object.keys(d.scenario_contribution).length > 0) {
      charts.push(
        <ChartCard key={`${t.name}-scen`} title="Scenario contribution" subtitle="Share of expected annual loss">
          <ScenarioContributionChart contribution={d.scenario_contribution} />
        </ChartCard>,
      );
    }

    // Insurance waterfall (from analyse_insurance_structure)
    if (d.insurance_response && d.client_retained_loss && d.ground_up_loss) {
      const groundUp = d.ground_up_loss.eal;
      const retention = d.insurance_response.retention ?? 0;
      const insurerPayment = d.insurance_response.insurer_payment ?? 0;
      const residual = d.client_retained_loss.residual_exposure_at_p99_9 ?? 0;
      if (groundUp > 0) {
        charts.push(
          <ChartCard key={`${t.name}-wf`} title="Insurance waterfall" subtitle="Ground-up → retention → insurer → residual">
            <InsuranceWaterfallChart
              groundUp={groundUp}
              retention={retention}
              insurerPayment={insurerPayment}
              residual={residual}
            />
          </ChartCard>,
        );
      }
    }
  }

  if (charts.length === 0) return null;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {charts}
    </div>
  );
}

/** Compact "the model used these figures" footer under a tool-driven answer. */
export function ToolTraceFooter({ trace }: { trace: ChatToolTrace[] }) {
  const sim = trace.find((t) => t.name === 'run_loss_simulation' && t.ok && t.data?.status === 'ok');
  if (!sim) return null;
  const d = asData(sim.data);
  const metrics = [
    { label: 'EAL', value: d.eal },
    { label: 'VaR 95', value: d.var_95 },
    { label: 'VaR 99', value: d.var_99 },
    { label: 'ES 99', value: d.es_99 },
  ];
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Modelled</span>
      {metrics.map((m) => (
        <span
          key={m.label}
          className="rounded-md bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-600"
        >
          {m.label} {formatMoney(m.value)}
        </span>
      ))}
      <span className="ml-auto text-[10px] text-slate-400">{formatPct(d.prob_zero_loss ?? 0)} prob. loss-free year</span>
    </div>
  );
}
