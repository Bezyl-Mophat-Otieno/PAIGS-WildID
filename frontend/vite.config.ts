import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    proxy: {
      // Backend mounts routers at root (no /api prefix) -- proxy every
      // path the API actually uses. See DESIGN.md / CLAUDE.md API shape.
      '/auth': 'http://localhost:8000',
      '/runs': 'http://localhost:8000',
      '/config': 'http://localhost:8000',
      '/dashboard': 'http://localhost:8000',
      '/reference-database': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
