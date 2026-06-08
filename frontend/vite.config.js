import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Dev-only proxy: forwards API calls from the Vite dev server (port 5173)
    // to uvicorn (port 8000) so relative paths like /ask work locally.
    // This block is ignored by `vite build` — no effect in the container.
    proxy: {
      '/ask':          'http://localhost:8000',
      '/auth':         'http://localhost:8000',
      '/reset':        'http://localhost:8000',
      '/teach':        'http://localhost:8000',
      '/teach-memory': 'http://localhost:8000',
      '/cockpit-data': 'http://localhost:8000',
      '/fragments':    'http://localhost:8000',
      '/health':       'http://localhost:8000',
    },
  },
})
