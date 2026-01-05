import { useState, useEffect, useCallback } from 'react'
import { CheckCircle2, XCircle, AlertCircle, Wifi, WifiOff } from 'lucide-react'
import { getApiHeaders } from '../utils/api'
import { getUserFriendlyError, logError } from '../utils/errorHandling'

interface StatusBarProps {
  apiUrl: string
  token: string | null
  userName?: string | null
}

interface ErrorItem {
  id: string
  message: string
  timestamp: Date
}

export default function StatusBar({ apiUrl, token, userName }: StatusBarProps) {
  const [apiHealth, setApiHealth] = useState<'healthy' | 'unhealthy' | 'unknown'>('unknown')
  // Initialize connection status based on apiUrl and token
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected'>(() => 
    apiUrl && token ? 'disconnected' : 'disconnected'
  )
  const [errors, setErrors] = useState<ErrorItem[]>([])
  const [metadata, setMetadata] = useState<{ account?: string; org?: string; project?: string; environment?: string; log_level?: string } | null>(null)
  const [version, setVersion] = useState<string | null>(null)

  // Define addError before useEffect to avoid hoisting issues
  const addError = useCallback((message: string) => {
    const errorItem: ErrorItem = {
      id: Date.now().toString(),
      message,
      timestamp: new Date(),
    }
    setErrors((prev) => [...prev.slice(-4), errorItem]) // Keep last 5 errors

    // Auto-dismiss after 10 seconds
    setTimeout(() => {
      setErrors((prev) => prev.filter((e) => e.id !== errorItem.id))
    }, 10000)
  }, [])

  // Derive connection status from apiUrl and token instead of setting in effect
  const shouldBeConnected = !!(apiUrl && token)

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
          const data = await response.json()
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
          const data = await response.json()
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
          const data = await response.json()
          setVersion(data.version)
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
    checkHealth()
    fetchMetadata()
    fetchVersion()

    // Poll every 5 seconds
    const interval = setInterval(checkHealth, 5000)
    const metadataInterval = setInterval(fetchMetadata, 30000) // Fetch metadata every 30 seconds
    const versionInterval = setInterval(fetchVersion, 30000) // Fetch version every 30 seconds

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

      {metadata?.account && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Account:</span>
          <span className="font-medium">{metadata.account}</span>
        </div>
      )}

      {metadata?.org && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Org:</span>
          <span className="font-medium">{metadata.org}</span>
        </div>
      )}

      {metadata?.project && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Project:</span>
          <span className="font-medium">{metadata.project}</span>
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
        <span className={apiHealth === 'healthy' ? 'text-green-600' : apiHealth === 'unhealthy' ? 'text-red-600' : 'text-yellow-600'}>
          {apiHealth === 'healthy' ? 'Healthy' : apiHealth === 'unhealthy' ? 'Unhealthy' : 'Unknown'}
        </span>
      </div>

      <div className="flex items-center gap-2">
        {shouldBeConnected ? (
          <>
            {getConnectionIcon()}
            <span className="text-muted-foreground">Connection:</span>
            <span className={connectionStatus === 'connected' ? 'text-green-600' : 'text-red-600'}>
              {connectionStatus === 'connected' ? 'Connected' : 'Disconnected'}
            </span>
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

