const API_TOKEN = import.meta.env.VITE_API_TOKEN

export function getApiHeaders(token: string | null): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'X-Source-Token': API_TOKEN,
  }

  // Add auth token if provided
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  return headers
}

