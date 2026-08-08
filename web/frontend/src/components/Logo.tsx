import { memo } from 'react';

interface LogoProps {
  /** Render the wordmark too (sidebar) vs just the mark (favicon/topbar compact). */
  withWordmark?: boolean;
  /** Size of the square mark in px. */
  size?: number;
  /** Light vs dark background (affects wordmark colour). */
  variant?: 'dark' | 'light';
  className?: string;
}

/**
 * CyberRisk AI logo — a shield mark with a risk pulse line, drawn in the blue
 * corporate palette.  The shield body is a corporate navy; the rising pulse
 * line is brand blue with a warning-gold risk marker, echoing a loss curve
 * trending up (risk exposure) inside a protective shield (insurance).
 */
export const Logo = memo(function Logo({
  withWordmark = true,
  size = 32,
  variant = 'dark',
  className = '',
}: LogoProps) {
  const wordmark = variant === 'dark' ? 'text-white' : 'text-ink-900';
  const sub = variant === 'dark' ? 'text-ink-500' : 'text-ink-500';

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label="CyberRisk AI logo"
      >
        <defs>
          <linearGradient id="cr-shield" x1="8" y1="4" x2="40" y2="44" gradientUnits="userSpaceOnUse">
            <stop stopColor="#1e3a8a" />
            <stop offset="1" stopColor="#0b1220" />
          </linearGradient>
          <linearGradient id="cr-pulse" x1="14" y1="34" x2="34" y2="14" gradientUnits="userSpaceOnUse">
            <stop stopColor="#60a5fa" />
            <stop offset="1" stopColor="#3b82f6" />
          </linearGradient>
        </defs>

        {/* Shield body */}
        <path
          d="M24 3 L42 10 V23 C42 34 34.5 42.5 24 45 C13.5 42.5 6 34 6 23 V10 Z"
          fill="url(#cr-shield)"
          stroke="#3b82f6"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        {/* Inner shield ring for depth */}
        <path
          d="M24 7.5 L38.5 13 V23 C38.5 31.5 32.5 38.8 24 41.2 C15.5 38.8 9.5 31.5 9.5 23 V13 Z"
          fill="none"
          stroke="#60a5fa"
          strokeOpacity="0.25"
          strokeWidth="1"
        />

        {/* Risk pulse line — trending upward, with the dot at the risk peak */}
        <path
          d="M14 29 L20 24 L23.5 26.5 L28 19 L31 22 L34 14"
          stroke="url(#cr-pulse)"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="34" cy="14" r="2.6" fill="#f59e0b" />
        <circle cx="34" cy="14" r="5.2" fill="#f59e0b" opacity="0.25" />
      </svg>

      {withWordmark && (
        <div className="leading-tight">
          <div className={`text-sm font-semibold tracking-tight ${wordmark}`}>
            CyberRisk <span className="text-brand-500">AI</span>
          </div>
          <div className={`text-[10px] font-medium tracking-wide ${sub}`}>Quant Risk Platform</div>
        </div>
      )}
    </div>
  );
});
