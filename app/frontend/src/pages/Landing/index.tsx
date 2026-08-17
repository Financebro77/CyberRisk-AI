import { Link } from 'react-router-dom';
import { ShieldCheck, ArrowRight } from 'lucide-react';
import { GlitchText } from '../../components/GlitchText';
import { ArmageddonMark } from '../../components/ArmageddonMark';
import { Terminal } from '../../components/Terminal';
import { Marquee } from '../../components/Marquee';
import { SignalReadout } from '../../components/SignalReadout';

/**
 * Landing page — adapted to the four reference mockups ("网络风险AI网页着陆页设计").
 *
 * Shared language across the reference mockups: an ash-black battlefield
 * canvas, gold/amber as the divine-judgement accent, blood red as the threat/
 * attack accent, and a giant display "CYBER ATTACK" headline.  The signature
 * element is the two-tone headline — warm gold "CYBER" flowing into molten red
 * "ATTACK" — with everything else disciplined: a threat-detected pill, a gold
 * "Run Risk Scan" CTA, the terminal proof, a live dashboard panel, the threat
 * marquee, the loss-curve signal readout, and dark feature panels.
 */

function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-black/60 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2.5">
          <ArmageddonMark className="h-8 w-auto shrink-0" />
          <span className="font-display text-base font-bold tracking-wide text-white [filter:drop-shadow(0_0_6px_rgba(248,216,128,0.6))]">
            ARMAGEDDON
          </span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm text-white/60 md:flex">
          <Link to="/model" className="transition-colors hover:text-white">
            How the model works
          </Link>
          <Link to="/consult?tab=chat" className="transition-colors hover:text-white">
            AI Cyber Risk Consultant
          </Link>
        </nav>
        <Link to="/consult" className="scan-btn text-xs">
          Run assessment <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </header>
  );
}

/** Compact live dashboard panel — the reference mockups' threat/risk dashboard. */
function HeroDashboard() {
  return (
    <div
      className="rounded-xl border border-accent/25 bg-ink-100/70 p-4 font-mono"
      role="img"
      aria-label="Live cyber risk dashboard: risk score, active threats, shield status"
    >
      <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.2em] text-ink-600">
        <span>risk dashboard</span>
        <span className="flex items-center gap-1.5 text-signal">
          <span className="status-dot h-1.5 w-1.5 rounded-full bg-signal" /> live
        </span>
      </div>
      <svg viewBox="0 0 320 90" className="mt-3 h-20 w-full" aria-hidden="true">
        <defs>
          <linearGradient id="hd-line" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#f6c46a" />
            <stop offset="100%" stopColor="#e8c078" />
          </linearGradient>
          <linearGradient id="hd-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e8c078" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#e8c078" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path
          d="M0 70 L40 58 L80 62 L120 44 L160 50 L200 30 L240 36 L280 16 L320 10 L320 90 L0 90 Z"
          fill="url(#hd-fill)"
        />
        <path
          d="M0 70 L40 58 L80 62 L120 44 L160 50 L200 30 L240 36 L280 16 L320 10"
          fill="none"
          stroke="url(#hd-line)"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="280" cy="16" r="4" fill="#fe4543" />
      </svg>
      <div className="mt-3 grid grid-cols-2 gap-3 text-[11px]">
        <div>
          <div className="text-ink-600">RISK SCORE</div>
          <div className="text-xl font-bold text-white">92</div>
        </div>
        <div>
          <div className="text-ink-600">ACTIVE THREAT</div>
          <div className="text-xl font-bold text-alert">18</div>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2 rounded-lg border border-signal/30 bg-signal/10 px-3 py-2 text-[11px] text-signal">
        <ShieldCheck className="h-3.5 w-3.5" />
        AI SHIELD ONLINE
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden bg-black text-white">
      <div className="crt-scanlines pointer-events-none absolute inset-0" aria-hidden="true" />
      <div className="hero-glow pointer-events-none absolute inset-x-0 top-0 h-[75vh]" />
      <div className="relative mx-auto max-w-6xl px-6 pt-14 lg:px-8">
        {/* Reference #2's red threat pill, top-right. */}
        <div className="flex justify-end">
          <div className="threat-pill font-mono text-[11px] uppercase tracking-[0.18em]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/90" />
            <span>THREAT DETECTED</span>
            <span className="text-white/75">RISK LEVEL CRITICAL</span>
          </div>
        </div>

        <div className="mx-auto max-w-4xl pt-10 text-center lg:pt-16">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.35em] text-accent">
            Quantitative cyber risk advisory
          </p>
          <h1 className="mt-5 font-display text-[clamp(3.5rem,15vw,10rem)] font-bold uppercase leading-[0.92] tracking-tight">
            <GlitchText text="CYBER ATTACK">
              <span className="cyber-gradient">CYBER</span>
              <span className="cyber-red"> ATTACK</span>
            </GlitchText>
          </h1>
          <p className="mt-5 text-lg tracking-wide text-white/85 sm:text-xl">
            Identify. Analyze. Neutralize.
          </p>
          <p className="mx-auto mt-3 max-w-2xl text-base leading-relaxed text-white/60">
            Armageddon turns cyber exposure into a dollar number boards can
            defend: expected annual loss, tail risk, and insurance — quantified,
            not guessed.
          </p>

          <div className="mx-auto mt-8 flex max-w-xl flex-col gap-3 sm:flex-row">
            <label htmlFor="scan-domain" className="sr-only">
              Enter your company profile to scan
            </label>
            <input
              id="scan-domain"
              type="text"
              placeholder="Enter your company profile to scan…"
              className="w-full flex-1 rounded-full border border-ink-400/50 bg-ink-100/70 px-5 py-3 text-sm text-white placeholder:text-ink-600 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
            <Link to="/consult" className="scan-btn shrink-0">
              Run Risk Scan <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>

        {/* Live console: the terminal proof beside a compact dashboard panel. */}
        <div className="mx-auto flex max-w-4xl flex-col items-center gap-6 pb-16 pt-12 lg:flex-row lg:items-stretch">
          <div className="w-full flex-1">
            <Terminal />
          </div>
          <div className="w-full max-w-sm flex-1">
            <HeroDashboard />
          </div>
        </div>
      </div>
    </section>
  );
}

/** The model's loss curve as a signal readout section. */
function SignalSection() {
  return (
    <section className="py-16 lg:py-20">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        <p className="text-center font-mono text-xs font-semibold uppercase tracking-[0.2em] text-accent">
          &gt; the shape of the risk
        </p>
        <h2 className="mt-4 text-center font-display text-3xl font-bold uppercase tracking-wide text-ink-900 lg:text-4xl">
          A loss curve you can read at a glance
        </h2>
        <SignalReadout />
      </div>
    </section>
  );
}

const WHAT_IS = [
  {
    title: 'It is financial, not just technical',
    body: 'A breach is a cost event — response, notification, extortion, business interruption, regulatory fines, and lost revenue. The question a board asks is "what could this cost us?", not "how many alerts did we get?".',
  },
  {
    title: 'It is probabilistic, not binary',
    body: 'No company is "safe" or "hacked". There is a distribution of possible outcomes, from a quiet year to a catastrophic one. Managing cyber risk is managing the shape of that distribution.',
  },
  {
    title: 'It is concentrated in the tail',
    body: 'Most years are quiet. The risk lives in the rare, severe event that can exceed what a firm planned for — the one that threatens solvency or a licence to operate.',
  },
];

const WHY_QUANTIFY = [
  {
    title: 'It makes risk a business decision',
    body: 'Expected annual loss, a 1-in-100-year loss, and the residual exposure after insurance turn cyber from a security topic into a board decision with a budget, an owner, and a target.',
  },
  {
    title: 'It sizes insurance correctly',
    body: 'A limit, retention, and sub-limit chosen against a modelled loss distribution are defensible. One chosen by guesswork is a liability for the adviser and the firm.',
  },
  {
    title: 'It prioritises the controls that matter',
    body: 'Quantification shows which exposures drive the loss — ransomware, business interruption, data breach — so security investment follows the risk, not the vendor.',
  },
];

/** A feature card on the dark panel — big stacked display title, prose body. */
function FeatureCard({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h3 className="font-display text-xl font-bold uppercase leading-tight tracking-wide text-ink-900">
        {title}
      </h3>
      <p className="mt-3 text-sm leading-relaxed text-ink-600">{body}</p>
    </div>
  );
}

/** A terminal-window card: quiet chrome dots, mono heading, prose body. */
function TerminalCard({ title, body }: { title: string; body: string }) {
  return (
    <div className="card p-5">
      <div className="mb-3 flex gap-1.5">
        <span className="h-2 w-2 rounded-full bg-ink-300" />
        <span className="h-2 w-2 rounded-full bg-ink-300" />
        <span className="h-2 w-2 rounded-full bg-ink-300" />
      </div>
      <h3 className="font-mono text-sm font-bold uppercase tracking-wider text-ink-900">
        {title}
      </h3>
      <p className="mt-3 text-sm leading-relaxed text-ink-600">{body}</p>
    </div>
  );
}

function WhatIs() {
  return (
    <section className="py-16 lg:py-24">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        <p className="text-center font-mono text-xs font-semibold uppercase tracking-[0.2em] text-accent">
          &gt; the risk
        </p>
        <h2 className="mt-4 text-center font-display text-3xl font-bold uppercase tracking-wide text-ink-900 lg:text-4xl">
          What cyber risk really means
        </h2>
        <div className="mt-8 rounded-2xl border border-ink-200/60 bg-gradient-to-b from-ink-200/70 via-ink-100/50 to-ink-100/30 p-8 md:p-10">
          <div className="grid gap-10 md:grid-cols-3">
            {WHAT_IS.map((item) => (
              <FeatureCard key={item.title} title={item.title} body={item.body} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function WhyQuantify() {
  return (
    <section className="border-y border-ink-200 bg-ink-50 py-16 lg:py-20">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-accent">
          &gt; why it matters
        </p>
        <h2 className="mt-4 font-display text-3xl font-bold uppercase tracking-wide text-ink-900 lg:text-4xl">
          Why quantifying cyber risk matters
        </h2>
        <div className="mt-6 space-y-4">
          {WHY_QUANTIFY.map((item) => (
            <TerminalCard key={item.title} title={item.title} body={item.body} />
          ))}
        </div>
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="py-16 lg:py-24">
      <div className="mx-auto max-w-3xl px-6 text-center lg:px-8">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-accent">
          &gt; ready when you are
        </p>
        <h2 className="mt-4 font-display text-3xl font-bold uppercase tracking-wide text-ink-900 lg:text-4xl">
          See your cyber exposure in dollars.
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-lg text-ink-600">
          Answer a few questions about your company and the consultant returns a
          risk score, expected annual loss, tail risk, and insurance guidance.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
          <Link to="/consult" className="scan-btn">
            Run Risk Scan <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/model"
            className="inline-flex items-center gap-2 rounded-full border border-ink-300 px-6 py-3 text-sm font-semibold text-ink-700 transition-colors hover:border-accent hover:text-accent"
          >
            How the model works
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-ink-200 bg-ink-100/50 py-8 font-mono text-xs text-ink-500">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 sm:flex-row lg:px-8">
        <span>ARMAGEDDON — Commercial Cyber Risk Advisory Platform</span>
        <span className="flex items-center gap-2">
          <Link to="/model" className="transition-colors hover:text-accent">
            how the model works
          </Link>
          <span>·</span>
          <Link to="/consult?tab=chat" className="transition-colors hover:text-accent">
            AI consultant
          </Link>
        </span>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen bg-ink-50 font-sans text-ink-900">
      <Nav />
      <Hero />
      <Marquee />
      <SignalSection />
      <WhatIs />
      <WhyQuantify />
      <Cta />
      <Footer />
    </div>
  );
}
