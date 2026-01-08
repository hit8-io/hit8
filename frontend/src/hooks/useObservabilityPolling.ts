/**
 * Custom hook for hybrid polling of observability metrics.
 * Polls frequently during execution, moderately when idle.
 */
import { useEffect, useRef, useState } from 'react'
import { getExecutionMetrics, getAggregatedMetrics } from '../utils/api'
import type { ExecutionMetrics, AggregatedMetrics } from '../types/observability'

interface UseObservabilityPollingOptions {
  apiUrl: string
  token: string | null
  threadId: string | null
  viewMode: 'current' | 'aggregated' | 'both'
  isLoading: boolean
  enabled?: boolean
}

interface UseObservabilityPollingResult {
  executionMetrics: ExecutionMetrics | null
  aggregatedMetrics: AggregatedMetrics | null
  error: string | null
  isRefreshing: boolean
}

export function useObservabilityPolling({
  apiUrl,
  token,
  threadId,
  viewMode,
  isLoading,
  enabled = true,
}: UseObservabilityPollingOptions): UseObservabilityPollingResult {
  const [executionMetrics, setExecutionMetrics] = useState<ExecutionMetrics | null>(null)
  const [aggregatedMetrics, setAggregatedMetrics] = useState<AggregatedMetrics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const intervalRef = useRef<number | null>(null)

  useEffect(() => {
    // Clear any existing interval
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }

    // Skip polling if disabled or missing required data
    if (!enabled || !apiUrl || !token) {
      return
    }

    // For current execution view, skip if no threadId
    if ((viewMode === 'current' || viewMode === 'both') && !threadId) {
      // Still fetch aggregated if in 'both' mode
      if (viewMode === 'both') {
        // Continue to fetch aggregated
      } else {
        return
      }
    }

    // Polling frequency: 2 seconds during execution, 15 seconds when idle
    const pollInterval = isLoading ? 2000 : 15000

    // Fetch function
    const fetchMetrics = async () => {
      try {
        setIsRefreshing(true)
        setError(null)

        if (viewMode === 'both') {
          // Fetch both metrics in parallel
          const [executionResult, aggregatedResult] = await Promise.allSettled([
            threadId ? getExecutionMetrics(token, threadId) : Promise.resolve(null),
            getAggregatedMetrics(token),
          ])

          if (executionResult.status === 'fulfilled') {
            setExecutionMetrics(executionResult.value)
          } else {
            // Don't clear existing metrics on error
            console.error('Failed to fetch execution metrics:', executionResult.reason)
          }

          if (aggregatedResult.status === 'fulfilled') {
            setAggregatedMetrics(aggregatedResult.value)
          } else {
            // Don't clear existing metrics on error
            console.error('Failed to fetch aggregated metrics:', aggregatedResult.reason)
            const errorMessage = aggregatedResult.reason instanceof Error 
              ? aggregatedResult.reason.message 
              : 'Failed to fetch aggregated metrics'
            setError(errorMessage)
          }
        } else if (viewMode === 'current' && threadId) {
          const metrics = await getExecutionMetrics(token, threadId)
          setExecutionMetrics(metrics)
          setAggregatedMetrics(null)
        } else {
          const metrics = await getAggregatedMetrics(token)
          setAggregatedMetrics(metrics)
          setExecutionMetrics(null)
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to fetch metrics'
        setError(errorMessage)
        
        // Don't clear existing metrics on error, just show the error
        // This prevents flickering when there's a temporary network issue
      } finally {
        setIsRefreshing(false)
      }
    }

    // Fetch immediately
    void fetchMetrics()

    // Set up polling interval
    intervalRef.current = window.setInterval(() => {
      void fetchMetrics()
    }, pollInterval)

    // Cleanup
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [apiUrl, token, threadId, viewMode, isLoading, enabled])

  return {
    executionMetrics,
    aggregatedMetrics,
    error,
    isRefreshing,
  }
}
