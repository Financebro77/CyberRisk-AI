import { Link } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';
import { Hero } from './Hero';
import { Features } from './Features';
import { Architecture } from './Architecture';
import { Demo } from './Demo';
import { Footer } from './Footer';
import { Reveal } from '../../components/Reveal';

function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-ink-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-8">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
            <ShieldCheck className="h-4.5 w-4.5" />
          </div>
          <span className="text-sm font-semibold tracking-wide text-white">CyberRisk AI</span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-ink-300 md:flex">
          <a href="#features" className="transition-colors hover:text-white">Capabilities</a>
          <a href="#architecture" className="transition-colors hover:text-white">Architecture</a>
        </nav>
        <Link
          to="/app"
          className="rounded-lg border border-white/15 bg-white/[0.04] px-4 py-2 text-sm font-semibold text-ink-100 transition-colors hover:bg-white/10"
        >
          Workspace
        </Link>
      </div>
    </header>
  );
}

function Cta() {
  return (
    <section className="bg-ink-50 py-20">
      <div className="mx-auto max-w-6xl px-8">
        <Reveal className="rounded-3xl bg-ink-950 px-8 py-14 text-center text-white shadow-2xl">
          <div className="mx-auto max-w-2xl">
            <h2 className="font-serif text-4xl font-medium tracking-tight">
              Ready to model a client's cyber risk?
            </h2>
            <p className="mt-4 text-lg text-ink-300">
              Start an assessment, run a Monte Carlo simulation and structure insurance —
              all deterministic, all white-box, in minutes.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
              <Link
                to="/app/assess"
                className="rounded-lg bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-600/25 transition-colors hover:bg-brand-500"
              >
                Start Assessment
              </Link>
              <Link
                to="/app"
                className="rounded-lg border border-white/15 bg-white/[0.04] px-6 py-3 text-sm font-semibold text-ink-100 transition-colors hover:bg-white/10"
              >
                View Demo
              </Link>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export default function Landing() {
  return (
    <div className="bg-ink-50 font-sans">
      <Nav />
      <Hero />
      <Features />
      <Architecture />
      <Demo />
      <Cta />
      <Footer />
    </div>
  );
}
