/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Only needed outside Vite's dev proxy (see vite.config.ts) -- production
  // builds point this at the deployed backend directly.
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
