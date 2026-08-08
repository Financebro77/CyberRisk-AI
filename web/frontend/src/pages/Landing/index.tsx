import { Link } from 'react-router-dom';
import { ShieldCheck, ArrowRight } from 'lucide-react';

/**
 * Landing page — a professional consulting-style introduction.
 * Three value-prop sections + a CTA, in the Marsh/Aon advisory tone.
 */
function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-ink-200 bg-white/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
            <ShieldCheck className="h-4.5 w-4.5" />
          </div>
          <span className="text-sm font-semibold tracking-wide text-ink-900">CyberRisk AI</span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm text-ink-600 md:flex">
          <Link to="/model" className="transition-colors hover:text-ink-900">How the model works</Link>
          <Link to="/consult" className="transition-colors hover:text-ink-900">AI Cyber Risk Consultant</Link>
        </nav>
        <Link
          to="/consult"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-500"
        >
          Start assessment <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="border-b border-ink-100 bg-ink-50">
      <div className="mx-auto max-w-5xl px-6 py-20 text-center lg:px-8 lg:py-28">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-600">
          Quantitative cyber risk advisory
        </p>
        <h1 className="mx-auto mt-5 max-w-3xl font-serif text-4xl font-medium leading-tight tracking-tight text-ink-900 sm:text-5xl lg:text-6xl">
          Put a defensible number on cyber risk.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-ink-600">
          CyberRisk AI helps boards and risk leaders quantify cyber exposure in dollars,
          structure insurance, and act with confidence.
        </p>
        <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
          <Link
            to="/consult"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition-colors hover:bg-brand-500"
          >
            Start your assessment <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/model"
            className="inline-flex items-center gap-2 rounded-lg border border-ink-300 px-6 py-3 text-sm font-semibold text-ink-700 transition-colors hover:border-brand-500 hover:text-brand-600"
          >
            How the model works
          </Link>
        </div>
      </div>
    </section>
  );
}

function WhatIs() {
  return (
    <section className="py-16 lg:py-20">
      <div className="mx-auto max-w-5xl px-6 lg:px-8">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-600">01 — The risk</p>
        <h2 className="mt-4 font-serif text-3xl font-medium tracking-tight text-ink-900 lg:text-4xl">
          What cyber risk really means
        </h2>
        <div className="mt-6 grid gap-8 md:grid-cols-3">
          {[
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
          ].map((item) => (
            <div key={item.title} className="rounded-xl border border-ink-200 bg-white p-6">
              <h3 className="text-base font-semibold text-ink-900">{item.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-600">{item.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function WhyQuantify() {
  return (
    <section className="border-y border-ink-100 bg-ink-50 py-16 lg:py-20">
      <div className="mx-auto max-w-5xl px-6 lg:px-8">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-600">02 — Why it matters</p>
        <h2 className="mt-4 font-serif text-3xl font-medium tracking-tight text-ink-900 lg:text-4xl">
          Why quantifying cyber risk matters
        </h2>
        <div className="mt-6 space-y-4">
          {[
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
          ].map((item) => (
            <div key={item.title} className="rounded-xl border border-ink-200 bg-white p-6">
              <h3 className="text-base font-semibold text-ink-900">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-600">{item.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="py-16 lg:py-20">
      <div className="mx-auto max-w-3xl px-6 text-center lg:px-8">
        <h2 className="font-serif text-3xl font-medium tracking-tight text-ink-900 lg:text-4xl">
          Ready to see your cyber exposure in dollars?
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-lg text-ink-600">
          Answer a few questions about your company and the consultant will return a
          risk score, expected annual loss, tail risk, and insurance guidance.
        </p>
        <div className="mt-8">
          <Link
            to="/consult"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-7 py-3.5 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition-colors hover:bg-brand-500"
          >
            Start your assessment <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-ink-100 bg-ink-50 py-8">
      <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-3 px-6 text-xs text-ink-500 sm:flex-row lg:px-8">
        <span>CyberRisk AI — Commercial Cyber Risk Advisory Platform</span>
        <span className="flex items-center gap-2">
          <Link to="/model" className="transition-colors hover:text-ink-900">How the model works</Link>
          <span>·</span>
          <Link to="/consult" className="transition-colors hover:text-ink-900">AI Consultant</Link>
        </span>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen bg-white font-sans">
      <Nav />
      <Hero />
      <WhatIs />
      <WhyQuantify />
      <Cta />
      <Footer />
    </div>
  );
}
