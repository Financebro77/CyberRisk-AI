import { useEffect, useRef, useState } from 'react';
import { ArrowRight, BarChart3, PlayCircle, ShieldCheck } from 'lucide-react';

/** Animated count-up for KPI-style numbers. */
function useCountUp(target: number, duration = 1400, start = false) {
  const [value, setValue] = useState(0);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    if (!start) return;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(target * eased);
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [target, duration, start]);

  return value;
}

/** Small animated metric inside the hero visual. */
function HeroMetric({ label, value, icon: Icon, tone }: { label: string; value: string; icon: typeof ShieldCheck; tone: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 backdrop-blur">
      <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${tone}`}>
        <Icon className="h-4.5 w-4.5" />
      </div>
      <div>
        <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">{label}</div>
        <div className="text-lg font-semibold tabular-nums text-white">{value}</div>
      </div>
    </div>
  );
}

function HeroVisual() {
  const [started, setStarted] = useState(false);
  const score = useCountUp(62.4, 1500, started);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStarted(true);
          obs.disconnect();
        }
      },
      { threshold: 0.3 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div ref={ref} className="relative mx-auto w-full max-w-md">
      {/* Glow behind the panel. */}
      <div className="absolute -inset-10 rounded-full bg-brand-500/20 blur-3xl" />

      <div className="relative rounded-2xl border border-white/10 bg-ink-900/80 p-6 shadow-2xl backdrop-blur">
        {/* Panel header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-brand-400" />
            <span className="text-sm font-semibold text-white">CyberRisk AI · Live model</span>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-risk-low/15 px-2.5 py-1 text-xs font-semibold text-risk-low">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-risk-low" />
            HIGH
          </span>
        </div>

        {/* Gauge */}
        <div className="mt-6 flex flex-col items-center">
          <div className="relative h-32 w-32">
            <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
              <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="9" />
              <circle
                cx="50"
                cy="50"
                r="42"
                fill="none"
                stroke="url(#gaugeGrad)"
                strokeWidth="9"
                strokeLinecap="round"
                strokeDasharray={`${(score / 100) * 264} 264`}
                style={{ transition: 'stroke-dasharray 0.1s linear' }}
              />
              <defs>
                <linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#16a34a" />
                  <stop offset="45%" stopColor="#d97706" />
                  <stop offset="100%" stopColor="#dc2626" />
                </linearGradient>
              </defs>
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="text-3xl font-semibold tabular-nums text-white">{score.toFixed(1)}</div>
              <div className="text-[11px] uppercase tracking-widest text-ink-400">Risk score</div>
            </div>
          </div>
          <div className="mt-3 text-center text-xs text-ink-400">
            Composite score · weighted domains · evidence-scored
          </div>
        </div>

        {/* Mini bar chart */}
        <div className="mt-6 space-y-2.5">
          {[
            { label: 'Access control', v: 73 },
            { label: 'Threat exposure', v: 48 },
            { label: 'Endpoint resilience', v: 40 },
            { label: 'Governance', v: 34 },
          ].map((b, i) => (
            <div key={b.label} className="flex items-center gap-3">
              <span className="w-32 text-xs text-ink-400">{b.label}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-brand-600 to-brand-400"
                  style={{ width: started ? `${b.v}%` : '0%', transition: `width 1s cubic-bezier(0.22,1,0.36,1) ${0.2 + i * 0.15}s` }}
                />
              </div>
              <span className="w-8 text-right text-xs tabular-nums text-ink-400">{b.v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Floating secondary metrics */}
      <div className="absolute -left-10 top-16 hidden animate-[float-slow_6s_ease-in-out_infinite] sm:block">
        <HeroMetric label="Expected annual loss" value="$3.3M" icon={BarChart3} tone="bg-brand-500/20 text-brand-400" />
      </div>
      <div className="absolute -right-6 bottom-10 hidden animate-[float-slow_7s_ease-in-out_1s_infinite] sm:block">
        <HeroMetric label="1-in-1000 PML" value="$56.4M" icon={ShieldCheck} tone="bg-risk-high/20 text-risk-high" />
      </div>

      {/* Pulsing ring behind the score */}
      <div className="absolute -z-10 left-1/2 top-24 h-40 w-40 -translate-x-1/2 rounded-full border border-brand-400/40 animate-[pulse-ring_3s_ease-out_infinite]" />
    </div>
  );
}

export function Hero() {
  return (
    <section className="relative overflow-hidden bg-ink-950 text-white">
      {/* Grid backdrop */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.14]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(148,163,184,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.5) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          animation: 'grid-pan 24s linear infinite',
        }}
      />
      {/* Radial glows */}
      <div className="pointer-events-none absolute -top-32 left-1/2 h-[480px] w-[720px] -translate-x-1/2 rounded-full bg-brand-600/20 blur-[120px]" />
      <div className="pointer-events-none absolute -bottom-40 right-0 h-96 w-96 rounded-full bg-brand-500/10 blur-[100px]" />

      <div className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-14 px-8 py-24 lg:grid-cols-2 lg:py-32">
        <div>
          <div className="reveal is-visible inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-ink-300">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-400" />
            White-box stochastic model · DeepSeek-powered consultant
          </div>

          <h1 className="mt-6 font-serif text-6xl font-medium leading-[1.02] tracking-tight lg:text-7xl">
            CyberRisk AI
          </h1>

          <p className="mt-5 max-w-lg text-xl leading-relaxed text-ink-300">
            AI-powered commercial cyber risk assessment and insurance optimisation platform.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-4">
            <a
              href="/app/assess"
              className="group inline-flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition-all hover:bg-brand-500 hover:shadow-brand-500/30"
            >
              Start Assessment
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </a>
            <a
              href="/app/simulate"
              className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/[0.04] px-6 py-3 text-sm font-semibold text-ink-100 transition-colors hover:bg-white/10"
            >
              <PlayCircle className="h-4 w-4 text-brand-400" />
              View Demo
            </a>
          </div>

          <div className="mt-10 flex items-center gap-6 text-xs text-ink-400">
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-risk-low" /> 7 calibrated scenarios
            </span>
            <span className="inline-flex items-center gap-1.5">
              <BarChart3 className="h-3.5 w-3.5 text-brand-400" /> 100k-year Monte Carlo
            </span>
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-brand-400" /> Actuarial VaR / ES
            </span>
          </div>
        </div>

        <HeroVisual />
      </div>

      {/* Bottom fade into page background */}
      <div className="pointer-events-none absolute bottom-0 h-24 w-full bg-gradient-to-b from-transparent to-ink-50" />
    </section>
  );
}
