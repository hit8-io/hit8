import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), '')
  
  return {
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
      // Map from Doppler secrets (without VITE_ prefix) to VITE_ prefixed variables
      // Doppler syncs GOOGLE_IDENTITY_PLATFORM_KEY -> Cloudflare Pages
      // We map it to VITE_GOOGLE_IDENTITY_PLATFORM_KEY for Vite to expose it
      'import.meta.env.API_URL': JSON.stringify(
        env.VITE_API_URL || env.API_URL || 'http://localhost:8000'
      ),
      'import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY': JSON.stringify(
        env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY || 
        env.GOOGLE_IDENTITY_PLATFORM_KEY || 
        ''
      ),
      'import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN': JSON.stringify(
        env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN || 
        env.GOOGLE_IDENTITY_PLATFORM_DOMAIN || 
        ''
      ),
      'import.meta.env.VITE_GCP_PROJECT': JSON.stringify(
        env.VITE_GCP_PROJECT || 
        env.GCP_PROJECT || 
        ''
      ),
    },
  }
})

