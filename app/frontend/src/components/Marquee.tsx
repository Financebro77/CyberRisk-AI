/**
 * Infinite CSS ticker of threat terms between the hero and the model section.
 * Purely decorative (aria-hidden) — the track is duplicated and translated by
 * the `marquee` keyframe.  Reduced motion is handled by the global override.
 */

const TERMS = [
  'RANSOMWARE',
  'BREACH',
  'EXTORTION',
  'BUSINESS INTERRUPTION',
  'PHISHING',
  'SUPPLY-CHAIN',
  'OUTAGE',
  'DDoS',
  'DATA THEFT',
  'INSIDER THREAT',
];

export function Marquee() {
  return (
    <div
      className="relative overflow-hidden border-y border-ink-200 py-3"
      aria-hidden="true"
    >
      <div className="marquee-track flex w-max whitespace-nowrap font-mono text-xs font-semibold tracking-[0.3em] text-accent/70">
        {[0, 1].map((dup) => (
          <div key={dup} className="flex shrink-0 items-center">
            {TERMS.map((t) => (
              <span key={`${dup}-${t}`} className="mx-6 flex items-center gap-6">
                {t}
                <span className="text-brand-500">▸</span>
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
