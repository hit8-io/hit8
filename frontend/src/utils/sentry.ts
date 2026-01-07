/**
 * Sentry error tracking configuration and initialization.
 * Only initializes in production builds.
 * Uses dynamic imports to prevent Sentry from loading when not needed.
 */

// Lazy-loaded Sentry module - only loaded when actually needed
// Using 'any' type to avoid Vite pre-transforming the import
let SentryModule: any = null
let isSentryInitialized = false

/**
 * Load Sentry module dynamically. Only loads in production.
 * Uses a dynamic import path to prevent Vite from pre-analyzing it.
 */
async function loadSentry(): Promise<any> {
  if (SentryModule) {
    return SentryModule
  }

  const isProduction = import.meta.env.PROD

  // Only load Sentry in production
  if (!isProduction) {
    return null
  }

  try {
    // Use dynamic import with a variable to prevent Vite from pre-analyzing
    const sentryModulePath = '@sentry/react'
    SentryModule = await import(/* @vite-ignore */ sentryModulePath)
    return SentryModule
  } catch (error) {
    console.error('[Sentry] Failed to load Sentry module:', error)
    return null
  }
}

/**
 * Initialize Sentry for error tracking.
 * Only runs in production builds. Always initializes in production.
 */
export async function initSentry(): Promise<void> {
  const isProduction = import.meta.env.PROD

  // Only initialize in production
  if (!isProduction) {
    console.debug('[Sentry] Not initializing in development mode')
    return
  }

  const Sentry = await loadSentry()
  if (!Sentry) {
    return
  }

  const dsn = import.meta.env.VITE_SENTRY_DSN

  try {
    Sentry.init({
      dsn: dsn || undefined, // Initialize even without DSN (will just not send events)
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
      beforeSend(event: any, hint: any) {
        // Filter out benign errors if needed
        const error = hint.originalException
        if (error instanceof Error) {
          // You can add custom filtering logic here
          // For example, filtering out specific error types
        }
        return event
      },
    })

    isSentryInitialized = true

    // Set up global error handlers
    setupGlobalErrorHandlers()

    if (dsn) {
      console.info('[Sentry] Initialized successfully in production mode')
    } else {
      console.warn('[Sentry] Initialized without DSN - events will not be sent')
    }
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
  if (!isSentryInitialized) {
    return
  }

  // Fire-and-forget: load Sentry and set user context asynchronously
  void loadSentry().then((Sentry) => {
    if (!Sentry) {
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
  }).catch((error) => {
    console.error('[Sentry] Failed to load Sentry for setUser:', error)
  })
}

/**
 * Capture an exception and send it to Sentry.
 * Safe to call even if Sentry is not initialized.
 */
export function captureException(error: unknown, context?: Record<string, unknown>): void {
  if (!isSentryInitialized) {
    return
  }

  // Fire-and-forget: load Sentry and capture exception asynchronously
  void loadSentry().then((Sentry) => {
    if (!Sentry) {
      return
    }

    try {
      if (context) {
        Sentry.withScope((scope: any) => {
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
  }).catch((err) => {
    console.error('[Sentry] Failed to load Sentry for captureException:', err)
  })
}

/**
 * Capture a message and send it to Sentry.
 * Safe to call even if Sentry is not initialized.
 */
export function captureMessage(message: string, level: 'debug' | 'info' | 'warning' | 'error' | 'fatal' = 'info'): void {
  if (!isSentryInitialized) {
    return
  }

  // Fire-and-forget: load Sentry and capture message asynchronously
  void loadSentry().then((Sentry) => {
    if (!Sentry) {
      return
    }

    try {
      Sentry.captureMessage(message, level)
    } catch (error) {
      // Non-blocking: if Sentry capture fails, don't break the app
      console.error('[Sentry] Failed to capture message:', error)
    }
  }).catch((error) => {
    console.error('[Sentry] Failed to load Sentry for captureMessage:', error)
  })
}

