import { useState, useEffect, useCallback } from 'react'
import { CheckCircle2, XCircle, AlertCircle, Wifi, WifiOff } from 'lucide-react'
import { getApiHeaders } from '../utils/api'
import { getUserFriendlyError, logError } from '../utils/errorHandling'
import { ERROR_AUTO_DISMISS_DELAY, HEALTH_CHECK_INTERVAL, METADATA_FETCH_INTERVAL, VERSION_FETCH_INTERVAL } from '../constants'

interface StatusBarProps {
  readonly apiUrl: string
  readonly token: string | null
  readonly userName?: string | null
}

interface ErrorItem {
  id: string
  message: string
  timestamp: Date
}

export default function StatusBar({ apiUrl, token, userName }: StatusBarProps) {
  const [apiHealth, setApiHealth] = useState<'healthy' | 'unhealthy' | 'unknown'>('unknown')
  // Initialize connection status based on apiUrl and token
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected'>('disconnected')
  const [errors, setErrors] = useState<ErrorItem[]>([])
  const [metadata, setMetadata] = useState<{ account?: string; org?: string; project?: string; environment?: string; log_level?: string } | null>(null)
  const [version, setVersion] = useState<string | null>(null)
  const [selectedOrg, setSelectedOrg] = useState<string | null>(null)
  const [selectedProject, setSelectedProject] = useState<string | null>(null)
  const [userAccount, setUserAccount] = useState<string | null>(null)

  // Define dismissError helper to reduce nesting
  const dismissError = useCallback((errorId: string) => {
    setErrors((prev) => prev.filter((e) => e.id !== errorId))
  }, [])

  // Define addError before useEffect to avoid hoisting issues
  const addError = useCallback((message: string) => {
    const errorItem: ErrorItem = {
      id: Date.now().toString(),
      message,
      timestamp: new Date(),
    }
    setErrors((prev) => [...prev.slice(-4), errorItem]) // Keep last 5 errors

    // Auto-dismiss after delay
    setTimeout(() => {
      dismissError(errorItem.id)
    }, ERROR_AUTO_DISMISS_DELAY)
  }, [dismissError])

  // Derive connection status from apiUrl and token instead of setting in effect
  const shouldBeConnected = !!(apiUrl && token)

  // Listen for org/project selection changes and user account
  useEffect(() => {
    const checkOrgProject = () => {
      setSelectedOrg(localStorage.getItem('activeOrg'))
      setSelectedProject(localStorage.getItem('activeProject'))
      // Try to get account from user config stored in localStorage
      try {
        const userConfigStr = localStorage.getItem('userConfig')
        if (userConfigStr) {
          const userConfig = JSON.parse(userConfigStr)
          if (userConfig?.account) {
            setUserAccount(userConfig.account)
          }
        }
      } catch {
        // Ignore parse errors
      }
    }

    // Check initially
    checkOrgProject()

    // Listen for storage events (from other tabs/windows)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'activeOrg' || e.key === 'activeProject' || e.key === 'userConfig') {
        checkOrgProject()
      }
    }

    // Poll for changes (since same-tab localStorage changes don't trigger storage events)
    const interval = setInterval(checkOrgProject, 500)

    window.addEventListener('storage', handleStorageChange)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    if (!shouldBeConnected) {
      return
    }

    const checkHealth = async () => {
      try {
        const response = await fetch(`${apiUrl}/health`, {
          method: 'GET',
          headers: getApiHeaders(null),
        })

        if (response.ok) {
          const data = await response.json() as { status?: string }
          if (data.status === 'healthy') {
            setApiHealth('healthy')
            setConnectionStatus('connected')
          } else {
            setApiHealth('unhealthy')
            setConnectionStatus('connected')
            addError(`Health check returned status: ${data.status || 'unknown'}`)
          }
        } else {
          setApiHealth('unhealthy')
          setConnectionStatus('connected')
          addError(`Health check failed with status: ${response.status}`)
        }
      } catch (error) {
        setApiHealth('unhealthy')
        setConnectionStatus('disconnected')
        logError('StatusBar: Health check error', error)
        const apiError = getUserFriendlyError(error)
        addError(apiError.message)
      }
    }

    const fetchMetadata = async () => {
      try {
        const response = await fetch(`${apiUrl}/metadata`, {
          method: 'GET',
          headers: getApiHeaders(token),
        })

        if (response.ok) {
          const data = await response.json() as { account?: string; org?: string; project?: string; environment?: string; log_level?: string }
          setMetadata(data)
        } else {
          // Log metadata fetch failure but don't show error to user (non-critical)
          logError('StatusBar: Metadata fetch failed', {
            status: response.status,
            statusText: response.statusText,
          })
        }
      } catch (error) {
        // Log metadata fetch error but don't show to user (non-critical)
        logError('StatusBar: Metadata fetch error', error)
      }
    }

    const fetchVersion = async () => {
      try {
        const response = await fetch(`${apiUrl}/version`, {
          method: 'GET',
          headers: getApiHeaders(null),
        })

        if (response.ok) {
          const data = await response.json() as { version?: string }
          setVersion(data.version ?? null)
        } else {
          // Log version fetch failure but don't show error to user (non-critical)
          logError('StatusBar: Version fetch failed', {
            status: response.status,
            statusText: response.statusText,
          })
        }
      } catch (error) {
        // Log version fetch error but don't show to user (non-critical)
        logError('StatusBar: Version fetch error', error)
      }
    }

    // Initial checks
    void checkHealth()
    void fetchMetadata()
    void fetchVersion()

    // Poll every 5 seconds
    const interval = setInterval(() => {
      void checkHealth()
    }, HEALTH_CHECK_INTERVAL)
    const metadataInterval = setInterval(() => {
      void fetchMetadata()
    }, METADATA_FETCH_INTERVAL)
    const versionInterval = setInterval(() => {
      void fetchVersion()
    }, VERSION_FETCH_INTERVAL)

    return () => {
      clearInterval(interval)
      clearInterval(metadataInterval)
      clearInterval(versionInterval)
    }
  }, [apiUrl, token, addError, shouldBeConnected])

  const getHealthIcon = () => {
    switch (apiHealth) {
      case 'healthy':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case 'unhealthy':
        return <XCircle className="h-4 w-4 text-red-500" />
      default:
        return <AlertCircle className="h-4 w-4 text-yellow-500" />
    }
  }

  const getConnectionIcon = () => {
    return connectionStatus === 'connected' ? (
      <Wifi className="h-4 w-4 text-green-500" />
    ) : (
      <WifiOff className="h-4 w-4 text-red-500" />
    )
  }

  return (
    <div className="border-t bg-muted/50 px-4 py-2 flex items-center gap-4 text-sm">
      {userName && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">User:</span>
          <span className="font-medium">{userName}</span>
        </div>
      )}

      {(userAccount || metadata?.account) && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Account:</span>
          <span className="font-medium">{userAccount || metadata.account}</span>
        </div>
      )}

      {selectedOrg && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Org:</span>
          <span className="font-medium">{selectedOrg}</span>
        </div>
      )}

      {selectedProject && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Project:</span>
          <span className="font-medium">{selectedProject}</span>
        </div>
      )}

      {metadata?.environment && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Environment:</span>
          <span className="font-medium">{metadata.environment}</span>
        </div>
      )}

      {metadata?.log_level && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Log Level:</span>
          <span className="font-medium">{metadata.log_level.toLowerCase()}</span>
        </div>
      )}

      {version && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Version:</span>
          <span className="font-medium">{version}</span>
        </div>
      )}

      <div className="flex items-center gap-2">
        {getHealthIcon()}
        <span className="text-muted-foreground">API:</span>
        {(() => {
          let apiHealthClass: string
          let apiHealthText: string
          if (apiHealth === 'healthy') {
            apiHealthClass = 'text-green-600'
            apiHealthText = 'Healthy'
          } else if (apiHealth === 'unhealthy') {
            apiHealthClass = 'text-red-600'
            apiHealthText = 'Unhealthy'
          } else {
            apiHealthClass = 'text-yellow-600'
            apiHealthText = 'Unknown'
          }
          return <span className={apiHealthClass}>{apiHealthText}</span>
        })()}
      </div>

      <div className="flex items-center gap-2">
        {shouldBeConnected ? (
          <>
            {getConnectionIcon()}
            <span className="text-muted-foreground">Connection:</span>
            {(() => {
              const connectionClass = connectionStatus === 'connected' ? 'text-green-600' : 'text-red-600'
              const connectionText = connectionStatus === 'connected' ? 'Connected' : 'Disconnected'
              return <span className={connectionClass}>{connectionText}</span>
            })()}
          </>
        ) : (
          <>
            <WifiOff className="h-4 w-4 text-red-500" />
            <span className="text-muted-foreground">Connection:</span>
            <span className="text-red-600">Disconnected</span>
          </>
        )}
      </div>

      {errors.length > 0 && (
        <div className="flex items-center gap-2 ml-auto">
          <AlertCircle className="h-4 w-4 text-destructive" />
          <span className="text-destructive text-xs">
            {errors[errors.length - 1].message}
          </span>
        </div>
      )}
    </div>
  )
}

