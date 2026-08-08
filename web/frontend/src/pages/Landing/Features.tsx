import {
  Activity,
  Bot,
  FileText,
  ShieldHalf,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { Reveal } from '../../components/Reveal';

const FEATURES = [
  {
    icon: Bot,
    title: 'AI Cyber Consultant',
    desc: 'A DeepSeek-powered consultant that elicits the client brief, decides when quantitative modelling is needed, and translates results into board-ready advice.',
    tag: 'DeepSeek agent',
  },
  {
    icon: Activity,
    title: 'Monte Carlo Risk Simulation',
    desc: 'A copula-coupled engine draws 100,000 annual loss scenarios across seven calibrated scenarios — breach, ransomware, BEC, cloud outage and more.',
    tag: '100k years',
  },
  {
    icon: TrendingUp,
    title: 'Expected Annual Loss',
    desc: 'The average annual loss (EAL) is computed directly from the simulated loss distribution, benchmark-calibrated and revenue-scaled per client.',
    tag: 'EAL',
  },
  {
    icon: ShieldCheck,
    title: 'Value at Risk',
    desc: '1-year VaR at 95% and 99% confidence, plus 1-in-200 and 1-in-1000-year PMLs read straight from the annual loss distribution.',
    tag: 'VaR 95 / 99',
  },
  {
    icon: Sparkles,
    title: 'Expected Shortfall',
    desc: 'Tail-consistent ES 95/99 — the average loss beyond the VaR threshold — with actuarial-standard wording your board will understand.',
    tag: 'ES 95 / 99',
  },
  {
    icon: ShieldHalf,
    title: 'Insurance Optimisation',
    desc: 'Test retentions, occurrence limits, aggregate limits and coinsurance; see the insurer response and the client residual exposure, strictly separated.',
    tag: 'Structure',
  },
  {
    icon: FileText,
    title: 'Executive Reports',
    desc: 'One-click Excel workbooks with Overview, Scenarios, Policy and the mandatory Model Limitations disclosure — engagement-ready.',
    tag: 'Excel',
  },
];

export function Features() {
  return (
    <section id="features" className="relative bg-ink-50 py-24">
      <div className="mx-auto max-w-6xl px-8">
        <Reveal>
          <div className="max-w-2xl">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-600">
              Platform capabilities
            </div>
            <h2 className="mt-3 font-serif text-4xl font-medium tracking-tight text-ink-900">
              From client brief to board-ready advice
            </h2>
            <p className="mt-4 text-lg leading-relaxed text-ink-500">
              Every feature is deterministic and auditable — a white-box engine where each
              reported number traces back to documented configuration.
            </p>
          </div>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, desc, tag }) => (
            <Reveal
              key={title}
              className="group rounded-2xl border border-ink-200 bg-white p-7 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-brand-500/30 hover:shadow-xl"
            >
              <div className="flex items-center justify-between">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600/10 text-brand-600 transition-colors group-hover:bg-brand-600 group-hover:text-white">
                  <Icon className="h-6 w-6" />
                </div>
                <span className="rounded-full bg-ink-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                  {tag}
                </span>
              </div>
              <h3 className="mt-5 text-lg font-semibold text-ink-900">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-500">{desc}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
