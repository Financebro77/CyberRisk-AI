import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  // Production is served from https://nohackers_allowed.com — build with a
  // domain base so asset URLs resolve under it.
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
