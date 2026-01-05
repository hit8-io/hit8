/**
 * Error handling utilities for API calls.
 */

export interface ApiError {
  message: string
  statusCode?: number
  type?: string
  isUserFriendly: boolean
}

/**
 * Get a user-friendly error message from an error.
 */
export function getUserFriendlyError(error: unknown): ApiError {
  // Handle Error objects
  if (error instanceof Error) {
    const message = error.message

    // Network errors
    if (message.includes('Failed to fetch') || message.includes('NetworkError')) {
      return {
        message: 'Unable to connect to the server. Please check your internet connection and try again.',
        isUserFriendly: true,
      }
    }

    // Timeout errors
    if (message.includes('timeout') || message.includes('Timeout')) {
      return {
        message: 'The request took too long to complete. Please try again.',
        isUserFriendly: true,
      }
    }

    // Stream errors
    if (message.includes('Stream timeout')) {
      return {
        message: 'The response took too long. Please try again with a shorter message.',
        isUserFriendly: true,
      }
    }

    // HTTP errors
    if (message.includes('HTTP error')) {
      const statusMatch = message.match(/status: (\d+)/)
      const statusCode = statusMatch ? parseInt(statusMatch[1], 10) : undefined
      
      if (statusCode === 401) {
        return {
          message: 'Your session has expired. Please refresh the page and try again.',
          statusCode: 401,
          isUserFriendly: true,
        }
      }
      
      if (statusCode === 403) {
        return {
          message: 'You do not have permission to perform this action.',
          statusCode: 403,
          isUserFriendly: true,
        }
      }
      
      if (statusCode === 404) {
        return {
          message: 'The requested resource was not found.',
          statusCode: 404,
          isUserFriendly: true,
        }
      }
      
      if (statusCode === 429) {
        return {
          message: 'Too many requests. Please wait a moment and try again.',
          statusCode: 429,
          isUserFriendly: true,
        }
      }
      
      if (statusCode && statusCode >= 500) {
        return {
          message: 'The server encountered an error. Please try again in a moment.',
          statusCode,
          isUserFriendly: true,
        }
      }
      
      return {
        message: 'An error occurred while processing your request. Please try again.',
        statusCode,
        isUserFriendly: true,
      }
    }

    // Return the error message if it's already user-friendly
    return {
      message,
      isUserFriendly: false,
    }
  }

  // Handle string errors
  if (typeof error === 'string') {
    return {
      message: error,
      isUserFriendly: false,
    }
  }

  // Unknown error type
  return {
    message: 'An unexpected error occurred. Please try again.',
    isUserFriendly: true,
  }
}

/**
 * Log error for debugging (only in development).
 */
export function logError(context: string, error: unknown): void {
  if (import.meta.env.DEV) {
    console.error(`[${context}]`, error)
    if (error instanceof Error && error.stack) {
      console.error('Stack trace:', error.stack)
    }
  }
}

/**
 * Check if an error is a benign connection closure after successful completion.
 */
export function isBenignConnectionError(error: unknown, hasContent: boolean): boolean {
  if (!hasContent) {
    return false
  }

  if (!(error instanceof Error)) {
    return false
  }

  const errorMessage = error.message.toLowerCase()
  const errorType = error.constructor.name

  const connectionClosedPatterns = [
    'connection is closed',
    'connection closed',
    'connection was closed',
    'connection has been closed',
    'server closed the connection',
  ]

  const isConnectionClosed = connectionClosedPatterns.some(pattern => 
    errorMessage.includes(pattern)
  )

  const isOperationalError = errorType === 'OperationalError' || 
    (errorType === 'Error' && errorMessage.includes('operational'))

  return isConnectionClosed || isOperationalError
}

