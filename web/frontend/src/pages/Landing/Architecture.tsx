import {
  Activity,
  Bot,
  Braces,
  FileText,
  Gauge,
  Monitor,
  ShieldCheck,
} from 'lucide-react';
import { Reveal } from '../../components/Reveal';

/**
 * Pipeline of the platform, drawn as a horizontal flow.  Each node is a
 * real module in the repository; the connector lines animate a data flow.
 */
const NODES = [
  { icon: Monitor, label: 'Web UI', sub: 'React · Vite' },
  { icon: Gauge, label: 'FastAPI', sub: 'REST layer' },
  { icon: Braces, label: 'Tools', sub: 'JSON contract' },
  { icon: Bot, label: 'AI Consultant', sub: 'DeepSeek' },
  { icon: Activity, label: 'Loss Engine', sub: 'Monte Carlo' },
  { icon: ShieldCheck, label: 'Metrics', sub: 'VaR · ES · PML' },
  { icon: FileText, label: 'Reports', sub: 'Excel workbook' },
];

function Pipeline() {
  const nodeW = 120;
  const gap = 28;
  const total = NODES.length * nodeW + (NODES.length - 1) * gap;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${total} 220`} className="h-auto w-full" role="img" aria-label="CyberRisk AI architecture pipeline">
        {/* Connector lines with animated dash flow */}
        {NODES.slice(0, -1).map((_, i) => {
          const x = i * (nodeW + gap) + nodeW;
          return (
            <g key={i}>
              <line
                x1={x}
                y1="110"
                x2={x + gap}
                y2="110"
                stroke="rgba(37,99,235,0.25)"
                strokeWidth="2"
                strokeDasharray="6 6"
              >
                <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.2s" repeatCount="indefinite" />
              </line>
              {/* arrowhead */}
              <circle cx={x + gap - 3} cy="110" r="3" fill="#2563eb" opacity="0.8" />
            </g>
          );
        })}

        {/* Node cards */}
        {NODES.map(({ icon: Icon, label, sub }, i) => {
          const x = i * (nodeW + gap);
          return (
            <g key={label} transform={`translate(${x} 0)`}>
              <rect
                x="6"
                y="70"
                width={nodeW - 12}
                height="80"
                rx="12"
                fill="#ffffff"
                stroke="#e2e8f0"
                strokeWidth="1"
              />
              <g transform={`translate(${nodeW / 2 - 8} 86)`}>
                <Icon className="h-4 w-4 text-brand-600" />
              </g>
              <text x={nodeW / 2} y="150" textAnchor="middle" className="fill-ink-900" fontSize="12" fontWeight="600">
                {label}
              </text>
              <text x={nodeW / 2} y="164" textAnchor="middle" className="fill-ink-500" fontSize="10">
                {sub}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function Architecture() {
  return (
    <section id="architecture" className="relative overflow-hidden bg-ink-950 py-24 text-white">
      {/* Grid backdrop */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(148,163,184,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.5) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />
      <div className="pointer-events-none absolute left-1/2 top-0 h-72 w-[640px] -translate-x-1/2 rounded-full bg-brand-600/15 blur-[120px]" />

      <div className="relative mx-auto max-w-6xl px-8">
        <Reveal>
          <div className="mx-auto max-w-2xl text-center">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-400">
              Architecture
            </div>
            <h2 className="mt-3 font-serif text-4xl font-medium tracking-tight">
              One pipeline, end to end
            </h2>
            <p className="mt-4 text-lg leading-relaxed text-ink-300">
              A typed React interface over a FastAPI REST layer, backed by the existing
              agent tooling and the quantitative loss engine — no black boxes.
            </p>
          </div>
        </Reveal>

        <Reveal className="mt-14">
          <Pipeline />
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-3">
          {[
            {
              title: 'Deterministic scoring',
              desc: 'The same client brief always yields the same composite score, category and drivers — auditable and reproducible.',
            },
            {
              title: 'Seeded Monte Carlo',
              desc: 'Bit-for-bit reproducible simulations: copula-coupled frequencies, revenue-scaled severities, catastrophe clustering.',
            },
            {
              title: 'Mandatory disclosure',
              desc: 'Every advisory report carries the model-limitations block — the numbers never stand without their caveats.',
            },
          ].map(({ title, desc }) => (
            <Reveal
              key={title}
              className="rounded-2xl border border-white/10 bg-white/[0.04] p-7 backdrop-blur transition-colors hover:border-white/20"
            >
              <h3 className="text-base font-semibold text-white">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-300">{desc}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
