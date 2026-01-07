import { useState, useEffect, useCallback } from 'react'
import { getUserConfig } from '../utils/api'
import { logError } from '../utils/errorHandling'
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
    const isCurrentSelectionValid = selection !== null && 
      selection.org in config.projects &&
      config.projects[selection.org]?.includes(selection.project) === true

    // Only auto-select if there's no valid selection
    if (isCurrentSelectionValid) {
      return
    }

    const orgs = Object.keys(config.projects)
    
    // Count total projects across all orgs
    let totalProjects = 0
    let singleProjectOrg: string | null = null
    let singleProject: string | null = null
    
    for (const org of orgs) {
      const projects = config.projects[org] || []
      totalProjects += projects.length
      if (projects.length === 1) {
        singleProjectOrg = org
        singleProject = projects[0]
      }
    }
    
    // Auto-select if only 1 org
    if (orgs.length === 1) {
      const singleOrg = orgs[0]
      const projects = config.projects[singleOrg] || []
      
      // Auto-select if only 1 project for that org
      if (projects.length === 1) {
        setSelection(singleOrg, projects[0])
      } else if (projects.length > 0) {
        // If multiple projects, auto-select the first one
        setSelection(singleOrg, projects[0])
      }
    } 
    // Auto-select if user has only 1 project total (across all orgs)
    else if (totalProjects === 1 && singleProjectOrg && singleProject) {
      setSelection(singleProjectOrg, singleProject)
    }
    // If org is already selected, check if only 1 project for that org
    else if (selection?.org && selection.org in config.projects) {
      const projects = config.projects[selection.org] || []
      if (projects.length === 1) {
        setSelection(selection.org, projects[0])
      } else if (projects.length > 0 && !config.projects[selection.org]?.includes(selection.project)) {
        // If current project is invalid, select first available
        setSelection(selection.org, projects[0])
      }
    }
  }, [config, selection, setSelection])

  // Validate that selection is valid (org exists in projects and project exists for that org)
  const isSelectionValid = config !== null && selection !== null && 
    selection.org in config.projects &&
    config.projects[selection.org]?.includes(selection.project) === true

  return {
    config,
    loading,
    error,
    selection,
    setSelection,
    isSelectionValid,
  }
}

