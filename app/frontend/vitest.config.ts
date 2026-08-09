import { defineConfig } from 'vitest/config';

/**
 * Vitest configuration for the voice-client tests.
 *
 * Kept separate from vite.config.ts so the production build never imports
 * vitest types (avoids the rollup/rolldown plugin-type conflict that mixing
 * `vite` and `vitest/config` in one file triggers).
 */
export default defineConfig({
  test: {
    // The voice-client tests run in a browser-like DOM without a full browser.
    environment: 'happy-dom',
    include: ['src/voice/**/*.test.{ts,tsx}'],
    setupFiles: ['src/voice/__tests__/setup.ts'],
  },
});
