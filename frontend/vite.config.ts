import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  
  // Map non-VITE_ prefixed vars to VITE_ prefixed ones
  // Check process.env first (for Docker/Doppler), then fall back to loadEnv (for .env files)
  process.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY = process.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY || process.env.GOOGLE_IDENTITY_PLATFORM_KEY || env.GOOGLE_IDENTITY_PLATFORM_KEY
  process.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN = process.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN || process.env.GOOGLE_IDENTITY_PLATFORM_DOMAIN || env.GOOGLE_IDENTITY_PLATFORM_DOMAIN
  process.env.VITE_GCP_PROJECT = process.env.VITE_GCP_PROJECT || process.env.GCP_PROJECT || env.GCP_PROJECT
  process.env.VITE_API_TOKEN = process.env.VITE_API_TOKEN || process.env.API_TOKEN || env.API_TOKEN
  process.env.VITE_API_URL = process.env.VITE_API_URL || process.env.API_URL || env.API_URL
  
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
      },
    },
  }
})

