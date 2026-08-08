import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  // Base path for built assets.  Set to the production deployment path if the
  // app is served from a sub-path (e.g. /cyberrisk/); the root '/'
  // is correct for a domain or subdomain deployment.
  base: '/',
  plugins: [react(), tailwindcss()],
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
