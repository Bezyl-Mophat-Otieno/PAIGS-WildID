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
      // The backend mounts routers at root (no /api prefix of its own), but
      // several of those path names -- /runs, /config, /dashboard,
      // /reference-database -- collide with this SPA's own client-side
      // routes of the same name. Proxying those paths directly (as this
      // used to) intercepts a hard navigation or refresh on e.g.
      // /runs/:id: Vite's dev-server proxy matches the *document* request
      // itself and forwards it straight to the backend (unauthenticated,
      // no bearer token) instead of serving index.html, so the SPA never
      // loads. `/api` is a dev-only prefix that exists purely to keep the
      // two namespaces from colliding; it's stripped before reaching the
      // backend, which has no /api prefix of its own. See api/client.ts.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
      },
    },
  },
})
