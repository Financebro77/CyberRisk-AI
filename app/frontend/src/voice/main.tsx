import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../index.css';
import { VoiceConsultant } from './VoiceConsultant';

/**
 * Apply the existing light/dark theme (same key as the web app's useTheme,
 * falling back to the system preference).  No toggle UI — the voice client is
 * a single screen and simply honours whatever the user already set.
 */
function applyTheme() {
  const dark =
    localStorage.getItem('cyberrisk-theme') === 'dark' ||
    (localStorage.getItem('cyberrisk-theme') === null &&
      window.matchMedia?.('(prefers-color-scheme: dark)').matches === true);
  document.documentElement.classList.toggle('dark', dark);
}

applyTheme();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <VoiceConsultant />
  </StrictMode>,
);

// Service worker (installable PWA) is registered only in production.  In dev
// it would cache stale assets and confuse iteration; production uses cache-first
// for same-origin GETs and NEVER touches /api (conversations are never cached).
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* SW is an enhancement — fail silently if the browser refuses it. */
    });
  });
}
