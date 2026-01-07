const API_TOKEN = import.meta.env.VITE_API_TOKEN
const API_URL = import.meta.env.VITE_API_URL

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
    const response = await fetch(url, {
      method,
      headers: getApiHeaders(token),
    })

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

