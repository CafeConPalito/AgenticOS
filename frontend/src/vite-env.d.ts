/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
}

/** The interface's version, from frontend/package.json (vite.config.ts). */
declare const __APP_VERSION__: string
