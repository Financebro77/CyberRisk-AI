import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Resolve an absolute path for the multi-page HTML inputs (ESM-safe, works
// on Node 20 in the Docker build too — __dirname is not available in ESM).
const dir = fileURLToPath(new URL('.', import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  // Base path for built assets.  Set to the production deployment path if the
  // app is served from a sub-path (e.g. /cyberrisk/); the root '/'
  // is correct for a domain or subdomain deployment.
  base: '/',
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        // The existing web SPA entry.
        main: `${dir}index.html`,
        // The single-screen, voice-first consultant PWA entry.  Purely
        // additive — the web app is unchanged.
        voice: `${dir}voice.html`,
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Forward API calls to the FastAPI backend during development.
      // The backend runs on port 8000 via:
      //   .venv\Scripts\python -m uvicorn cyberrisk.api.main:app --port 8000
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
