import { useId } from 'react';
import type { CSSProperties } from 'react';

/**
 * ArmageddonMark — the brand emblem recovered from reference mockup (6).png:
 * three white/gray capsule drops merging through a horizontal band into a gold
 * teardrop (radial gold gradient, pale specular crescent, bright tail streak).
 * Drawn as a self-hosted inline SVG — no external assets; gradient IDs are
 * useId-unique so multiple instances can coexist on one page.
 */
export function ArmageddonMark({
  className,
  style,
  ariaLabel = 'Armageddon logo',
}: {
  className?: string;
  style?: CSSProperties;
  ariaLabel?: string;
}) {
  const uid = useId();
  const drop = `${uid}-drop`;
  const band = `${uid}-band`;
  const cap = `${uid}-cap`;
  const hl = `${uid}-hl`;

  return (
    <svg
      viewBox="0 0 860 781"
      className={className}
      style={style}
      role="img"
      aria-label={ariaLabel}
    >
      <defs>
        <radialGradient
          id={drop}
          cx="0.62"
          cy="0.34"
          r="0.8"
          fx="0.7"
          fy="0.28"
          gradientUnits="objectBoundingBox"
        >
          <stop offset="0%" stopColor="#FEF6D0" />
          <stop offset="30%" stopColor="#F6D68D" />
          <stop offset="58%" stopColor="#C38F50" />
          <stop offset="82%" stopColor="#6B4423" />
          <stop offset="100%" stopColor="#1E1204" />
        </radialGradient>
        <linearGradient id={band} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#5D5E63" />
          <stop offset="62%" stopColor="#817F7D" />
          <stop offset="100%" stopColor="#C38F50" />
        </linearGradient>
        <linearGradient id={cap} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#FFFFFF" />
          <stop offset="20%" stopColor="#FFFFFF" />
          <stop offset="30%" stopColor="#E9E9EC" />
          <stop offset="100%" stopColor="#61646B" />
        </linearGradient>
        <linearGradient id={hl} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#A9ADB6" stopOpacity="0" />
          <stop offset="55%" stopColor="#B0B3BC" />
          <stop offset="100%" stopColor="#A9ADB6" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Gold teardrop — rounded bulb tapering to a point at the bottom */}
      <path
        d="M 630 70 C 855 70 865 160 862 400 C 859 560 810 730 600 781 C 430 735 385 560 386 400 C 387 160 405 70 630 70 Z"
        fill={`url(#${drop})`}
      />
      {/* Specular highlight crescent on the bulb's upper-left */}
      <path
        d="M 505 200 C 430 235 400 320 412 450 C 420 520 470 545 500 520 C 465 500 442 450 448 360 C 452 290 478 230 505 200 Z"
        fill={`url(#${hl})`}
        stroke="#FFFFFF"
        strokeOpacity="0.85"
        strokeWidth="5"
      />
      {/* Bright tail streak */}
      <path
        d="M 585 560 C 592 640 598 700 597 758"
        stroke="#FBF1AC"
        strokeOpacity="0.85"
        strokeWidth="10"
        strokeLinecap="round"
        fill="none"
      />
      {/* Connecting band — merges the capsule bodies into the teardrop */}
      <rect x="-10" y="94" width="510" height="56" rx="6" fill={`url(#${band})`} />
      {/* Three capsule drops */}
      <rect x="5" y="0" width="52" height="150" rx="26" fill={`url(#${cap})`} />
      <rect x="154" y="0" width="52" height="150" rx="26" fill={`url(#${cap})`} />
      <rect x="299" y="0" width="52" height="150" rx="26" fill={`url(#${cap})`} />
    </svg>
  );
}
