import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import pkg from './package.json' with { type: 'json' }

// Tauri expects a fixed dev port and must not clear its own console output.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Phase 20: «Acerca de» shows the version of the interface.
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  envPrefix: ['VITE_', 'TAURI_ENV_'],
  build: { target: 'es2022' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Whole-app renders are slow on a busy machine: generous limits keep the tests stable.
    testTimeout: 15_000,
  },
})
