import { ShieldCheck } from 'lucide-react';

export function Footer() {
  return (
    <footer className="border-t border-ink-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-8 py-12 md:flex-row md:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-ink-950 text-white">
            <ShieldCheck className="h-5 w-5 text-brand-400" />
          </div>
          <div>
            <div className="text-sm font-semibold text-ink-900">CyberRisk AI</div>
            <div className="text-xs text-ink-500">Commercial cyber risk assessment platform</div>
          </div>
        </div>

        <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-ink-500">
          <a href="#features" className="transition-colors hover:text-brand-600">Capabilities</a>
          <a href="#architecture" className="transition-colors hover:text-brand-600">Architecture</a>
          <a href="/app/assess" className="transition-colors hover:text-brand-600">Assess risk</a>
          <a href="/app/methodology" className="transition-colors hover:text-brand-600">Methodology</a>
        </nav>
      </div>

      <div className="border-t border-ink-100 py-6">
        <div className="mx-auto max-w-6xl px-8 text-center text-xs leading-relaxed text-ink-400">
          CyberRisk AI is a white-box stochastic model. Outputs are estimates and not a
          guarantee of actual loss; model limitations are disclosed with every advisory
          report. Not investment or insurance advice.
        </div>
      </div>
    </footer>
  );
}
