/**
 * The landing page's signature element: a big display headline with a CSS-only
 * RGB-split glitch on hover.  No per-frame JS — the clip-path jitter runs in
 * the compositor, so it is cheap and is killed by the global
 * prefers-reduced-motion override.
 *
 * Pass `children` to render styled sub-spans (e.g. the cyan→red two-tone
 * split); `text` then feeds the ghost layers via data-text.
 */
import type { ReactNode } from 'react';

export function GlitchText({
  text,
  className,
  children,
}: {
  text: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <span className={`glitch ${className ?? ''}`} data-text={text}>
      {children ?? text}
    </span>
  );
}
