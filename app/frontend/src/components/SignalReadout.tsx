/**
 * The modelled annual loss distribution drawn as a signal readout — a cyan
 * curve on a faint grid with the tail shaded, marked at 1-in-100 and
 * 1-in-1000.  A dashed animated overlay (`.dash-flow`) gives it the "signal"
 * motion.  Colour comes from the theme tokens so it flips with dark mode.
 */
export function SignalReadout() {
  return (
    <div className="mx-auto mt-10 max-w-2xl">
      <div className="relative rounded-xl border border-ink-200 bg-ink-50/70 p-4 font-mono">
        <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.2em] text-ink-500">
          <span>signal :: annual loss distribution</span>
          <span className="text-signal">● live</span>
        </div>
        <svg
          viewBox="0 0 720 140"
          className="h-28 w-full text-accent"
          role="img"
          aria-label="Modelled annual loss distribution, marked at the 1-in-100 and 1-in-1000 year losses"
        >
          <defs>
            <linearGradient id="tail-fill" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0.28" />
            </linearGradient>
          </defs>
          {/* faint terminal grid */}
          <g stroke="currentColor" strokeOpacity="0.08">
            {[120, 240, 360, 480, 600].map((x) => (
              <line key={x} x1={x} y1="0" x2={x} y2="140" />
            ))}
            {[35, 70, 105].map((y) => (
              <line key={y} x1="0" y1={y} x2="720" y2={y} />
            ))}
          </g>
          {/* tail shading under the steep part of the curve */}
          <path d="M540 30 S 660 10, 720 5 L 720 140 L 540 140 Z" fill="url(#tail-fill)" />
          {/* the loss density: most years quiet, then the rare steep fall */}
          <path
            d="M0 116 C 140 114, 220 100, 300 86 C 380 72, 460 48, 540 30 C 600 18, 660 10, 720 5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          {/* animated dashed overlay — the live signal */}
          <path
            d="M0 116 C 140 114, 220 100, 300 86 C 380 72, 460 48, 540 30 C 600 18, 660 10, 720 5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="4 6"
            strokeLinecap="round"
            opacity="0.5"
            className="dash-flow"
          />
          {/* reference ticks on the tail */}
          <line
            x1="576"
            y1="0"
            x2="576"
            y2="132"
            stroke="currentColor"
            strokeOpacity="0.35"
            strokeDasharray="3 4"
          />
          <line
            x1="672"
            y1="0"
            x2="672"
            y2="132"
            stroke="var(--color-risk-high)"
            strokeOpacity="0.7"
            strokeDasharray="3 4"
          />
        </svg>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-[10px] font-medium uppercase tracking-[0.14em] text-ink-500">
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-5 rounded-full bg-accent" /> Loss distribution
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-px w-5 bg-accent/60" /> 1-in-100-year
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-px w-5 bg-risk-high" /> 1-in-1000-year
          </span>
        </div>
      </div>
    </div>
  );
}
