/**
 * Sentry error tracking configuration and initialization.
 * Only initializes in production builds.
 */

import * as Sentry from '@sentry/react'

/**
 * Initialize Sentry for error tracking.
 * Only runs in production builds.
 */
export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  const isProduction = import.meta.env.PROD

  // Only initialize in production if DSN is provided
  if (!isProduction || !dsn) {
    if (!isProduction) {
      console.debug('[Sentry] Not initializing in development mode')
    } else if (!dsn) {
      console.warn('[Sentry] VITE_SENTRY_DSN is not set, Sentry will not be initialized')
    }
    return
  }

  try {
    Sentry.init({
      dsn,
      environment: 'production',
      integrations: [
        Sentry.browserTracingIntegration(),
        Sentry.replayIntegration({
          maskAllText: true,
          blockAllMedia: true,
        }),
      ],
      // Performance Monitoring
      tracesSampleRate: 1.0, // Capture 100% of transactions for performance monitoring
      // Session Replay
      replaysSessionSampleRate: 0.1, // 10% of sessions
      replaysOnErrorSampleRate: 1.0, // 100% of sessions with errors
      // Release tracking
      release: import.meta.env.VITE_APP_VERSION || undefined,
      // Error filtering - don't send certain errors
      beforeSend(event, hint) {
        // Filter out benign errors if needed
        const error = hint.originalException
        if (error instanceof Error) {
          // You can add custom filtering logic here
          // For example, filtering out specific error types
        }
        return event
      },
    })

    // Set up global error handlers
    setupGlobalErrorHandlers()

    console.info('[Sentry] Initialized successfully')
  } catch (error) {
    // Non-blocking: if Sentry initialization fails, don't break the app
    console.error('[Sentry] Failed to initialize:', error)
  }
}

/**
 * Set up global error handlers for unhandled errors and promise rejections.
 * These catch errors that escape React's error boundary.
 */
function setupGlobalErrorHandlers(): void {
  // Handle unhandled errors
  window.addEventListener('error', (event) => {
    // Sentry's default error handler will capture this, but we can add custom context
    if (event.error) {
      captureException(event.error, {
        errorBoundary: {
          type: 'unhandled_error',
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
        },
      })
    }
  })

  // Handle unhandled promise rejections
  window.addEventListener('unhandledrejection', (event) => {
    // Sentry's default handler will capture this, but we can add custom context
    const reason = event.reason
    captureException(reason, {
      errorBoundary: {
        type: 'unhandled_promise_rejection',
      },
    })
  })
}

/**
 * Set user context for Sentry events.
 * Call this after user authentication.
 */
export function setSentryUser(user: { id: string; email?: string; name?: string } | null): void {
  if (!import.meta.env.PROD) {
    return
  }

  try {
    if (user) {
      Sentry.setUser({
        id: user.id,
        email: user.email,
        username: user.name,
      })
    } else {
      Sentry.setUser(null)
    }
  } catch (error) {
    // Non-blocking: if setting user context fails, don't break the app
    console.error('[Sentry] Failed to set user context:', error)
  }
}

/**
 * Capture an exception and send it to Sentry.
 * Safe to call even if Sentry is not initialized.
 */
export function captureException(error: unknown, context?: Record<string, unknown>): void {
  if (!import.meta.env.PROD) {
    return
  }

  try {
    if (context) {
      Sentry.withScope((scope) => {
        Object.entries(context).forEach(([key, value]) => {
          // Sentry's setContext expects Context | null, where Context is a serializable object
          // Cast to the expected type - Sentry will handle serialization
          scope.setContext(key, value as Record<string, unknown> | null)
        })
        Sentry.captureException(error)
      })
    } else {
      Sentry.captureException(error)
    }
  } catch (err) {
    // Non-blocking: if Sentry capture fails, don't break the app
    console.error('[Sentry] Failed to capture exception:', err)
  }
}

/**
 * Capture a message and send it to Sentry.
 * Safe to call even if Sentry is not initialized.
 */
export function captureMessage(message: string, level: Sentry.SeverityLevel = 'info'): void {
  if (!import.meta.env.PROD) {
    return
  }

  try {
    Sentry.captureMessage(message, level)
  } catch (error) {
    // Non-blocking: if Sentry capture fails, don't break the app
    console.error('[Sentry] Failed to capture message:', error)
  }
}

