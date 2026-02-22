import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          icons: ['lucide-react'],
          sanity: ['@sanity/client'],
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5174, // Different port from apps/web (5173)
  },
})
