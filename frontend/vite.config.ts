import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Allow access from lvh.me domain for OAuth
    allowedHosts: ['hit8.lvh.me', 'localhost'],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  define: {
    'import.meta.env.API_URL': JSON.stringify(
      process.env.VITE_API_URL || process.env.API_URL || 'http://localhost:8000'
    ),
    // Map from Doppler secrets (without VITE_ prefix) to VITE_ prefixed variables
    // Doppler syncs GOOGLE_IDENTITY_PLATFORM_KEY -> Cloudflare Pages
    // We map it to VITE_GOOGLE_IDENTITY_PLATFORM_KEY for Vite to expose it
    'import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY': JSON.stringify(
      process.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY || 
      process.env.GOOGLE_IDENTITY_PLATFORM_KEY || 
      ''
    ),
    'import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN': JSON.stringify(
      process.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN || 
      process.env.GOOGLE_IDENTITY_PLATFORM_DOMAIN || 
      ''
    ),
    'import.meta.env.VITE_GCP_PROJECT': JSON.stringify(
      process.env.VITE_GCP_PROJECT || 
      process.env.GCP_PROJECT || 
      ''
    ),
  },
})

