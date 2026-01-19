import { useState, useEffect, useCallback } from 'react'
import { getUserConfig } from '../utils/api'
import { logError } from '../utils/errorHandling'
import { getAvailableFlows as getAvailableFlowsUtil } from '../utils/userConfig'
import type { UserConfig, OrgProjectSelection } from '../types'

const STORAGE_KEY_ORG = 'activeOrg'
const STORAGE_KEY_PROJECT = 'activeProject'

interface UseUserConfigResult {
  config: UserConfig | null
  loading: boolean
  error: string | null
  selection: OrgProjectSelection | null
  setSelection: (org: string, project: string) => void
  isSelectionValid: boolean
  getAvailableFlows: (org: string, project: string) => string[]
}

export function useUserConfig(token: string | null): UseUserConfigResult {
  const [config, setConfig] = useState<UserConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selection, setSelectionState] = useState<OrgProjectSelection | null>(null)

  // Load config from API
  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }

    let cancelled = false

    async function loadConfig() {
      try {
        setLoading(true)
        setError(null)
        const userConfig = await getUserConfig(token)
        if (!cancelled) {
          setConfig(userConfig)
          // Store in localStorage for StatusBar to access
          try {
            localStorage.setItem('userConfig', JSON.stringify(userConfig))
          } catch {
            // Ignore localStorage errors
          }
        }
      } catch (err) {
        if (!cancelled) {
          logError('useUserConfig: Failed to load user config', err)
          setError(err instanceof Error ? err.message : 'Failed to load user configuration')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadConfig()

    return () => {
      cancelled = true
    }
  }, [token])

  // Update selection and persist to localStorage
  const setSelection = useCallback((org: string, project: string) => {
    localStorage.setItem(STORAGE_KEY_ORG, org)
    localStorage.setItem(STORAGE_KEY_PROJECT, project)
    setSelectionState({ org, project })
  }, [])

  // Load saved selection from localStorage on mount
  useEffect(() => {
    const savedOrg = localStorage.getItem(STORAGE_KEY_ORG)
    const savedProject = localStorage.getItem(STORAGE_KEY_PROJECT)

    if (savedOrg && savedProject) {
      setSelectionState({
        org: savedOrg,
        project: savedProject,
      })
    }
  }, [])

  // Auto-select org/project when config is loaded
  useEffect(() => {
    if (!config) {
      return
    }

    // Check if current selection is valid
    // projects[org] is now an object where keys are project names
    const isCurrentSelectionValid = selection !== null && 
      selection.org in config.projects &&
      selection.project in (config.projects[selection.org] || {})

    // If selection is valid, no need to change it
    if (isCurrentSelectionValid) {
      return
    }

    // Find first available org and project
    const orgs = Object.keys(config.projects)
    if (orgs.length === 0) {
      return
    }

    const firstOrg = orgs[0]
    const firstOrgProjects = config.projects[firstOrg]
    if (firstOrgProjects && typeof firstOrgProjects === 'object') {
      const projectKeys = Object.keys(firstOrgProjects)
      if (projectKeys.length > 0) {
        setSelection(firstOrg, projectKeys[0])
      }
    }
  }, [config, selection, setSelection])

  // Helper function to get available flows for a specific org/project
  // Wraps the pure utility function with current config to maintain hook API
  const getAvailableFlows = useCallback(
    (org: string, project: string): string[] => {
      return getAvailableFlowsUtil(config, org, project)
    },
    [config]
  )

  // Validate that selection is valid (org exists in projects and project exists for that org)
  const isSelectionValid = config !== null && selection !== null && 
    selection.org in config.projects &&
    selection.project in (config.projects[selection.org] || {})

  return {
    config,
    loading,
    error,
    selection,
    setSelection,
    isSelectionValid,
    getAvailableFlows,
  }
}

