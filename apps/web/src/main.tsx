import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'
import { initSentry } from './utils/sentry'
import './index.css'
import 'reactflow/dist/style.css'

// Initialize Sentry before React renders
initSentry()

// Global error handler to suppress Firebase "missing initial state" errors
// This error occurs when Firebase tries to process a redirect that doesn't have proper state
// It's non-fatal and can be safely ignored
window.addEventListener('error', (event) => {
  const errorMessage = event.message || ''
  const errorSource = event.filename || ''
  
  // Suppress Firebase handler.js errors about missing initial state
  if (
    (errorMessage.includes('missing initial state') ||
      errorMessage.includes('Unable to process request due to missing initial state')) &&
    (errorSource.includes('handler.js') || errorSource.includes('firebase'))
  ) {
    event.preventDefault()
    event.stopPropagation()
    // Optionally log to console in dev mode for debugging
    if (import.meta.env.DEV) {
      console.debug('[Firebase] Suppressed missing initial state error (non-fatal)')
    }
    return false
  }
  
  return true
})

// Also handle unhandled promise rejections from Firebase
window.addEventListener('unhandledrejection', (event) => {
  const error = event.reason
  const errorMessage = error?.message || String(error) || ''
  
  // Suppress Firebase redirect state errors
  if (
    errorMessage.includes('missing initial state') ||
    errorMessage.includes('Unable to process request due to missing initial state') ||
    errorMessage.includes('auth/missing-or-invalid-nonce')
  ) {
    event.preventDefault()
    // Optionally log to console in dev mode for debugging
    if (import.meta.env.DEV) {
      console.debug('[Firebase] Suppressed missing initial state promise rejection (non-fatal)')
    }
  }
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)

