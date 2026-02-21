// Simple module-level cache for homepage data
// Cache persists for the session (until page refresh)

export interface HomeData {
  hero: {
    badge: string
    headline: string
    subHeadline: string
    description: string
  }
  features: Array<{
    _key?: string
    title: string
    description: string
    icon: string
  }>
}

let homeDataCache: HomeData | null = null

export function getCachedHomeData(): HomeData | null {
  return homeDataCache
}

export function setCachedHomeData(data: HomeData): void {
  homeDataCache = data
}
