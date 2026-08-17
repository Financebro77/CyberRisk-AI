/**
 * Mock shell readout under the hero — the product "running live".  Lines are
 * statically staggered in on mount (CSS animation-delay) and the caret blinks.
 * No per-frame JS; reduced motion is handled by the global CSS override.
 *
 * The terminal is a constant near-black surface in both themes, so it uses
 * fixed Tailwind palette colors (cyan-300 / green-400 / slate) rather than the
 * theme tokens, which flip for page surfaces.  The caller controls the outer
 * layout via `className`.
 */

const LINES = [
  { text: '$ armageddon assess --retention 1M --limit 10M', cls: 'text-slate-300' },
  { text: '▸ loading 2,000,000 simulated loss paths…', cls: 'text-slate-500' },
  { text: '[ OK ] Expected annual loss (EAL) ........ $1.4M', cls: 'text-green-400' },
  { text: '[ ! ] 1-in-1000-year loss ................ $12.8M', cls: 'text-cyan-300' },
  { text: '[ + ] modelled policy limit .............. $10.0M', cls: 'text-cyan-300' },
];

export function Terminal({ className = '' }: { className?: string }) {
  return (
    <div
      className={`terminal w-full max-w-xl text-left font-mono text-xs sm:text-sm ${className}`}
      role="img"
      aria-label="Simulated cyber risk assessment terminal output"
    >
      <div className="terminal-chrome flex items-center gap-1.5 px-4 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-red-500/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-green-500/80" />
        <span className="ml-2 text-slate-500">armageddon — assess</span>
      </div>
      <div className="px-4 py-3">
        {LINES.map((l, i) => (
          <div
            key={l.text}
            className={`term-line ${l.cls}`}
            style={{ animationDelay: `${150 + i * 180}ms` }}
          >
            {l.text}
          </div>
        ))}
        <div className="caret" aria-hidden="true" />
      </div>
    </div>
  );
}
