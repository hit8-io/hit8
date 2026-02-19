import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  
  // Map non-VITE_ prefixed vars to VITE_ prefixed ones
  // Check process.env first (for Docker/Doppler), then fall back to loadEnv (for .env files)
  // IMPORTANT: These must be set before Vite processes the config so they're available via import.meta.env
  if (!process.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY) {
    process.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY = process.env.GOOGLE_IDENTITY_PLATFORM_KEY || env.GOOGLE_IDENTITY_PLATFORM_KEY || ''
  }
  if (!process.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN) {
    process.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN = process.env.GOOGLE_IDENTITY_PLATFORM_DOMAIN || env.GOOGLE_IDENTITY_PLATFORM_DOMAIN || ''
  }
  if (!process.env.VITE_GCP_PROJECT) {
    process.env.VITE_GCP_PROJECT = process.env.GCP_PROJECT || env.GCP_PROJECT || ''
  }
  if (!process.env.VITE_API_TOKEN) {
    process.env.VITE_API_TOKEN = process.env.API_TOKEN || env.API_TOKEN || ''
  }
  if (!process.env.VITE_API_URL) {
    process.env.VITE_API_URL = process.env.API_URL || env.API_URL || ''
  }
  if (!process.env.VITE_SENTRY_DSN) {
    process.env.VITE_SENTRY_DSN = process.env.SENTRY_DSN || env.SENTRY_DSN || ''
  }
  
  // Debug: Log if Firebase config is missing (only in dev mode)
  if (mode === 'development' && !process.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY) {
    console.warn('⚠️  VITE_GOOGLE_IDENTITY_PLATFORM_KEY is not set. Check Doppler configuration.')
  }
  
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      headers: {
        'Cross-Origin-Opener-Policy': 'same-origin-allow-popups',
      },
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
        "@hit8/ui": path.resolve(__dirname, "../../packages/ui/src"),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: (id) => {
            // Code-split Sentry into a separate chunk
            if (id.includes('@sentry/react')) {
              return 'sentry'
            }
          },
        },
      },
    },
  }
})

