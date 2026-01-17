import { getAuth } from 'firebase/auth'
import { getApps } from 'firebase/app'
import { logError } from './errorHandling'

const API_TOKEN = import.meta.env.VITE_API_TOKEN
const API_URL = import.meta.env.VITE_API_URL

/**
 * Refreshes the Firebase ID token by forcing a new token from the current user.
 * @returns A fresh ID token, or null if no user is authenticated
 */
async function refreshToken(): Promise<string | null> {
  try {
    const apps = getApps()
    if (apps.length === 0) {
      return null
    }

    const auth = getAuth(apps[0])
    const currentUser = auth.currentUser

    if (!currentUser) {
      return null
    }

    // Force refresh the token (true = force refresh even if not expired)
    const freshToken = await currentUser.getIdToken(true)
    return freshToken
  } catch (error) {
    logError('api: Failed to refresh token', error)
    return null
  }
}

/**
 * Fetches a resource with automatic retry on 401 errors.
 * On 401, refreshes the token and retries the request once.
 * 
 * @param url - The URL to fetch
 * @param options - Fetch options (headers, method, body, etc.)
 * @param token - The current authentication token
 * @param onTokenRefresh - Optional callback when token is refreshed (for updating state)
 * @returns The fetch Response
 */
export async function fetchWithRetry(
  url: string,
  options: RequestInit & { headers?: Record<string, string> },
  token: string | null,
  onTokenRefresh?: (newToken: string) => void
): Promise<Response> {
  // First attempt
  const response = await fetch(url, {
    ...options,
    headers: {
      ...getApiHeaders(token),
      ...options.headers,
    },
  })

  // If 401 and we have a token, try refreshing and retrying once
  if (response.status === 401 && token) {
    const freshToken = await refreshToken()
    
    if (freshToken && freshToken !== token) {
      // Token was refreshed, update callback if provided
      if (onTokenRefresh) {
        onTokenRefresh(freshToken)
      }

      // Retry the request with the fresh token
      return fetch(url, {
        ...options,
        headers: {
          ...getApiHeaders(freshToken),
          ...options.headers,
        },
      })
    }
  }

  return response
}

export function getApiHeaders(token: string | null): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Source-Token': API_TOKEN,
  }

  // Add auth token if provided
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // Add org/project headers from localStorage
  const org = localStorage.getItem('activeOrg')
  const project = localStorage.getItem('activeProject')

  if (org) {
    headers['X-Org'] = org
  }
  if (project) {
    headers['X-Project'] = project
  }

  return headers
}

export interface UserConfig {
  account: string
  orgs: string[]
  projects: Record<string, string[]>
}

export async function getUserConfig(token: string | null): Promise<UserConfig> {
  if (!token) {
    throw new Error('Authentication token is required')
  }

  if (!API_URL) {
    throw new Error('API URL is not configured')
  }

  const url = `${API_URL}/config/user`
  const method = 'GET'

  try {
    const response = await fetchWithRetry(
      url,
      { method },
      token
    )

    if (!response.ok) {
      const errorText = await response.text()
      const error = new Error(`Failed to fetch user config: ${response.status} ${errorText}`)
      // Add request context to error for Sentry
      ;(error as Error & { requestContext?: Record<string, unknown> }).requestContext = {
        url,
        method,
        statusCode: response.status,
        statusText: response.statusText,
      }
      throw error
    }

    return response.json()
  } catch (error) {
    // If it's a network error, add request context
    if (error instanceof Error && !(error as Error & { requestContext?: Record<string, unknown> }).requestContext) {
      ;(error as Error & { requestContext?: Record<string, unknown> }).requestContext = {
        url,
        method,
      }
    }
    throw error
  }
}

export async function getAggregatedMetrics(
  token: string | null
): Promise<import('../types/observability').AggregatedMetrics> {
  if (!token) {
    throw new Error('Authentication token is required')
  }

  if (!API_URL) {
    throw new Error('API URL is not configured')
  }

  const url = `${API_URL}/usage/aggregated`
  const method = 'GET'

  try {
    const response = await fetchWithRetry(
      url,
      { method },
      token
    )

    if (!response.ok) {
      const errorText = await response.text()
      const error = new Error(`Failed to fetch aggregated metrics: ${response.status} ${errorText}`)
      // Add request context to error for Sentry
      ;(error as Error & { requestContext?: Record<string, unknown> }).requestContext = {
        url,
        method,
        statusCode: response.status,
        statusText: response.statusText,
      }
      throw error
    }

    return response.json()
  } catch (error) {
    // If it's a network error, add request context
    if (error instanceof Error && !(error as Error & { requestContext?: Record<string, unknown> }).requestContext) {
      ;(error as Error & { requestContext?: Record<string, unknown> }).requestContext = {
        url,
        method,
      }
    }
    throw error
  }
}

export async function getChatHistory(
  token: string | null
): Promise<import('../types').ChatThread[]> {
  if (!token) {
    throw new Error('Authentication token is required')
  }

  if (!API_URL) {
    throw new Error('API URL is not configured')
  }

  const url = `${API_URL}/history`
  const method = 'GET'

  try {
    const response = await fetchWithRetry(
      url,
      { method },
      token
    )

    if (!response.ok) {
      const errorText = await response.text()
      const error = new Error(`Failed to fetch chat history: ${response.status} ${errorText}`)
      // Add request context to error for Sentry
      ;(error as Error & { requestContext?: Record<string, unknown> }).requestContext = {
        url,
        method,
        statusCode: response.status,
        statusText: response.statusText,
      }
      throw error
    }

    return response.json()
  } catch (error) {
    // If it's a network error, add request context
    if (error instanceof Error && !(error as Error & { requestContext?: Record<string, unknown> }).requestContext) {
      ;(error as Error & { requestContext?: Record<string, unknown> }).requestContext = {
        url,
        method,
      }
    }
    throw error
  }
}

