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
      // Map Doppler secrets to VITE_ prefixed variables for the client
      // Only use exact environment variable names from Doppler, no fallbacks
      'import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY': JSON.stringify(
        env.GOOGLE_IDENTITY_PLATFORM_KEY || ''
      ),
      'import.meta.env.VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN': JSON.stringify(
        env.GOOGLE_IDENTITY_PLATFORM_DOMAIN || ''
      ),
      'import.meta.env.VITE_GCP_PROJECT': JSON.stringify(
        env.GCP_PROJECT || ''
      ),
      'import.meta.env.VITE_API_URL': JSON.stringify(
        env.VITE_API_URL || ''
      ),
    },
  }
})

