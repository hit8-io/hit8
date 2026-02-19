import type { UserConfig } from '../types'

/**
 * Get available flows for a specific org/project combination.
 * 
 * Pure utility function that extracts flows from user config.
 * Returns empty array if config/org/project is missing, or ['chat'] as default
 * if org/project exists but flows are not configured.
 * 
 * @param config - User configuration object
 * @param org - Organization name
 * @param project - Project name
 * @returns Array of available flow names (e.g., ['chat', 'report'])
 */
export function getAvailableFlows(
  config: UserConfig | null,
  org: string | undefined,
  project: string | undefined
): string[] {
  if (!config || !org || !project) {
    return []
  }
  
  const orgProjects = config.projects[org]
  if (!orgProjects || typeof orgProjects !== 'object') {
    return ['chat'] // Default to chat if org not found
  }
  
  const flows = orgProjects[project]
  if (!Array.isArray(flows) || flows.length === 0) {
    return ['chat'] // Default to chat if project not found or no flows
  }
  
  return flows
}
