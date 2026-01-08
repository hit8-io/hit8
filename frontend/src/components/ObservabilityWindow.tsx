import { useMemo } from 'react'
import { Card, CardContent } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import { useObservabilityPolling } from '../hooks/useObservabilityPolling'
import type { ExecutionState } from '../types/execution'

interface ObservabilityWindowProps {
  apiUrl: string
  token: string | null
  executionState: ExecutionState | null
  isLoading: boolean
}

/**
 * Format number with comma separators.
 */
function formatNumber(num: number): string {
  return num.toLocaleString('en-US')
}

/**
 * Format duration in milliseconds to human-readable string.
 */
function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)}ms`
  }
  return `${(ms / 1000).toFixed(2)}s`
}

/**
 * Format cost as currency.
 */
function formatCost(cost: number | null): string {
  if (cost === null) return 'N/A'
  if (cost < 0.01) {
    return `$${cost.toFixed(4)}`
  }
  return `$${cost.toFixed(2)}`
}

/**
 * Extract thread_id from execution state.
 */
function extractThreadId(executionState: ExecutionState | null): string | null {
  if (!executionState) return null
  
  // Try to get thread_id from stream events
  if (executionState.streamEvents && Array.isArray(executionState.streamEvents)) {
    for (const event of executionState.streamEvents) {
      if (event && typeof event === 'object' && 'thread_id' in event) {
        const threadId = (event as { thread_id: string }).thread_id
        if (threadId) {
          return threadId
        }
      }
    }
  }
  
  return null
}

export default function ObservabilityWindow({
  apiUrl,
  token,
  executionState,
  isLoading,
}: ObservabilityWindowProps) {
  // Extract thread_id from execution state
  const threadId = useMemo(() => extractThreadId(executionState), [executionState])
  
  // Use polling hook - always fetch both
  const { executionMetrics, aggregatedMetrics, error, isRefreshing } = useObservabilityPolling({
    apiUrl,
    token,
    threadId,
    viewMode: 'both',
    isLoading,
    enabled: !!apiUrl && !!token,
  })

  // Combine all unique models from current and aggregated for LLM
  const allLLMModels = useMemo(() => {
    const models = new Set<string>()
    if (executionMetrics) {
      executionMetrics.llm_calls.forEach(call => models.add(call.model))
    }
    if (aggregatedMetrics) {
      Object.keys(aggregatedMetrics.llm.by_model).forEach(model => models.add(model))
    }
    return Array.from(models).sort()
  }, [executionMetrics, aggregatedMetrics])

  // Combine all unique models from current and aggregated for Embeddings
  const allEmbeddingModels = useMemo(() => {
    const models = new Set<string>()
    if (executionMetrics) {
      executionMetrics.embedding_calls.forEach(call => models.add(call.model))
    }
    if (aggregatedMetrics) {
      Object.keys(aggregatedMetrics.embeddings.by_model).forEach(model => models.add(model))
    }
    return Array.from(models).sort()
  }, [executionMetrics, aggregatedMetrics])

  // Calculate current execution totals for LLM
  const currentLLMTotals = useMemo(() => {
    if (!executionMetrics) return null
    return {
      calls: executionMetrics.llm_calls.length,
      input: executionMetrics.llm_calls.reduce((sum, call) => sum + call.input_tokens, 0),
      output: executionMetrics.llm_calls.reduce((sum, call) => sum + call.output_tokens, 0),
      thinking: executionMetrics.llm_calls.reduce((sum, call) => sum + (call.thinking_tokens || 0), 0),
      duration: executionMetrics.llm_calls.reduce((sum, call) => sum + call.duration_ms, 0),
    }
  }, [executionMetrics])

  // Calculate current execution totals for Embeddings
  const currentEmbeddingTotals = useMemo(() => {
    if (!executionMetrics) return null
    return {
      calls: executionMetrics.embedding_calls.length,
      input: executionMetrics.embedding_calls.reduce((sum, call) => sum + call.input_tokens, 0),
      duration: executionMetrics.embedding_calls.reduce((sum, call) => sum + call.duration_ms, 0),
    }
  }, [executionMetrics])

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardContent className="flex-1 min-h-0 p-3">
        <ScrollArea className="h-full">
          {error && (
            <div className="text-xs text-destructive mb-2 p-2 bg-destructive/10 rounded">
              Error: {error}
            </div>
          )}
          
          {isRefreshing && (
            <div className="text-xs text-muted-foreground mb-2">Refreshing...</div>
          )}
          
          <div className="space-y-4">
            {/* Combined LLM Table */}
            <div className="mb-3">
                <div className="text-xs font-semibold text-foreground mb-1">LLM</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left p-1 font-semibold" rowSpan={2}>Model</th>
                        <th className="text-center p-1 font-semibold border-l border-border" colSpan={5}>
                          Current Execution
                        </th>
                        <th className="text-center p-1 font-semibold border-l border-border" colSpan={5}>
                          Aggregated
                        </th>
                      </tr>
                      <tr className="border-b border-border">
                        <th className="text-right p-1 font-semibold border-l border-border">Input</th>
                        <th className="text-right p-1 font-semibold">Output</th>
                        <th className="text-right p-1 font-semibold">Thinking</th>
                        <th className="text-right p-1 font-semibold">TTFT</th>
                        <th className="text-right p-1 font-semibold">Duration</th>
                        <th className="text-right p-1 font-semibold border-l border-border">Calls</th>
                        <th className="text-right p-1 font-semibold">Input</th>
                        <th className="text-right p-1 font-semibold">Output</th>
                        <th className="text-right p-1 font-semibold">Thinking</th>
                        <th className="text-right p-1 font-semibold">Duration</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Total row */}
                      {(currentLLMTotals || aggregatedMetrics?.llm) && (
                        <tr className="border-b border-border/50 bg-muted/30">
                          <td className="p-1 font-medium">Total</td>
                          <td className="p-1 text-right border-l border-border">
                            {currentLLMTotals ? formatNumber(currentLLMTotals.input) : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {currentLLMTotals ? formatNumber(currentLLMTotals.output) : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {currentLLMTotals && currentLLMTotals.thinking > 0 ? formatNumber(currentLLMTotals.thinking) : '-'}
                          </td>
                          <td className="p-1 text-right">-</td>
                          <td className="p-1 text-right">
                            {currentLLMTotals ? formatDuration(currentLLMTotals.duration) : '-'}
                          </td>
                          <td className="p-1 text-right border-l border-border">
                            {aggregatedMetrics?.llm ? formatNumber(aggregatedMetrics.llm.total_calls) : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {aggregatedMetrics?.llm ? formatNumber(aggregatedMetrics.llm.total_input_tokens) : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {aggregatedMetrics?.llm ? formatNumber(aggregatedMetrics.llm.total_output_tokens) : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {aggregatedMetrics?.llm && aggregatedMetrics.llm.total_thinking_tokens > 0
                              ? formatNumber(aggregatedMetrics.llm.total_thinking_tokens)
                              : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {aggregatedMetrics?.llm ? formatDuration(aggregatedMetrics.llm.total_duration_ms) : '-'}
                          </td>
                        </tr>
                      )}
                      
                      {/* Model rows */}
                      {allLLMModels.map((model) => {
                        // Aggregate all calls for this model (not just the first one)
                        const modelCalls = executionMetrics?.llm_calls.filter(call => call.model === model) || []
                        const aggregatedStats = aggregatedMetrics?.llm.by_model[model]
                        
                        // Calculate aggregated metrics for current execution
                        const currentModelStats = modelCalls.length > 0 ? {
                          calls: modelCalls.length,
                          input: modelCalls.reduce((sum, call) => sum + call.input_tokens, 0),
                          output: modelCalls.reduce((sum, call) => sum + call.output_tokens, 0),
                          thinking: modelCalls.reduce((sum, call) => sum + (call.thinking_tokens || 0), 0),
                          duration: modelCalls.reduce((sum, call) => sum + call.duration_ms, 0),
                          // Average TTFT across all calls (only if all have TTFT)
                          avgTtft: (() => {
                            const ttfts = modelCalls.filter(call => call.ttft_ms !== null).map(call => call.ttft_ms!)
                            return ttfts.length > 0 ? ttfts.reduce((sum, ttft) => sum + ttft, 0) / ttfts.length : null
                          })(),
                        } : null
                        
                        return (
                          <tr key={model} className="border-b border-border/50">
                            <td className="p-1">{model}</td>
                            <td className="p-1 text-right border-l border-border">
                              {currentModelStats ? formatNumber(currentModelStats.input) : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {currentModelStats ? formatNumber(currentModelStats.output) : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {currentModelStats && currentModelStats.thinking > 0
                                ? formatNumber(currentModelStats.thinking)
                                : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {currentModelStats && currentModelStats.avgTtft !== null
                                ? formatDuration(currentModelStats.avgTtft)
                                : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {currentModelStats ? formatDuration(currentModelStats.duration) : '-'}
                            </td>
                            <td className="p-1 text-right border-l border-border">
                              {aggregatedStats ? formatNumber(aggregatedStats.call_count) : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {aggregatedStats ? formatNumber(aggregatedStats.total_input_tokens) : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {aggregatedStats ? formatNumber(aggregatedStats.total_output_tokens) : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {aggregatedStats && aggregatedStats.total_thinking_tokens > 0
                                ? formatNumber(aggregatedStats.total_thinking_tokens)
                                : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {aggregatedStats ? formatDuration(aggregatedStats.total_duration_ms) : '-'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
            </div>
            
            {/* Combined Embeddings Table */}
            <div className="mb-3">
                <div className="text-xs font-semibold text-foreground mb-1">Embeddings</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left p-1 font-semibold" rowSpan={2}>Model</th>
                        <th className="text-center p-1 font-semibold border-l border-border" colSpan={2}>
                          Current Execution
                        </th>
                        <th className="text-center p-1 font-semibold border-l border-border" colSpan={3}>
                          Aggregated
                        </th>
                      </tr>
                      <tr className="border-b border-border">
                        <th className="text-right p-1 font-semibold border-l border-border">Input</th>
                        <th className="text-right p-1 font-semibold">Duration</th>
                        <th className="text-right p-1 font-semibold border-l border-border">Calls</th>
                        <th className="text-right p-1 font-semibold">Input</th>
                        <th className="text-right p-1 font-semibold">Duration</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Total row */}
                      {(currentEmbeddingTotals || aggregatedMetrics?.embeddings) && (
                        <tr className="border-b border-border/50 bg-muted/30">
                          <td className="p-1 font-medium">Total</td>
                          <td className="p-1 text-right border-l border-border">
                            {currentEmbeddingTotals ? formatNumber(currentEmbeddingTotals.input) : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {currentEmbeddingTotals ? formatDuration(currentEmbeddingTotals.duration) : '-'}
                          </td>
                          <td className="p-1 text-right border-l border-border">
                            {aggregatedMetrics?.embeddings ? formatNumber(aggregatedMetrics.embeddings.total_calls) : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {aggregatedMetrics?.embeddings ? formatNumber(aggregatedMetrics.embeddings.total_input_tokens) : '-'}
                          </td>
                          <td className="p-1 text-right">
                            {aggregatedMetrics?.embeddings ? formatDuration(aggregatedMetrics.embeddings.total_duration_ms) : '-'}
                          </td>
                        </tr>
                      )}
                      
                      {/* Model rows */}
                      {allEmbeddingModels.map((model) => {
                        const currentCall = executionMetrics?.embedding_calls.find(call => call.model === model)
                        const aggregatedStats = aggregatedMetrics?.embeddings.by_model[model]
                        
                        return (
                          <tr key={model} className="border-b border-border/50">
                            <td className="p-1">{model}</td>
                            <td className="p-1 text-right border-l border-border">
                              {currentCall ? formatNumber(currentCall.input_tokens) : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {currentCall ? formatDuration(currentCall.duration_ms) : '-'}
                            </td>
                            <td className="p-1 text-right border-l border-border">
                              {aggregatedStats ? formatNumber(aggregatedStats.call_count) : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {aggregatedStats ? formatNumber(aggregatedStats.total_input_tokens) : '-'}
                            </td>
                            <td className="p-1 text-right">
                              {aggregatedStats ? formatDuration(aggregatedStats.total_duration_ms) : '-'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
            </div>
            
            {/* Combined Bright Data Table */}
            <div className="mb-3">
                <div className="text-xs font-semibold text-foreground mb-1">Bright Data</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left p-1 font-semibold">Metric</th>
                        <th className="text-center p-1 font-semibold border-l border-border" colSpan={3}>
                          Current Execution
                        </th>
                        <th className="text-center p-1 font-semibold border-l border-border" colSpan={3}>
                          Aggregated
                        </th>
                      </tr>
                      <tr className="border-b border-border">
                        <th className="text-left p-1 font-semibold"></th>
                        <th className="text-right p-1 font-semibold border-l border-border">Calls</th>
                        <th className="text-right p-1 font-semibold">Duration</th>
                        <th className="text-right p-1 font-semibold">Cost</th>
                        <th className="text-right p-1 font-semibold border-l border-border">Calls</th>
                        <th className="text-right p-1 font-semibold">Duration</th>
                        <th className="text-right p-1 font-semibold">Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-border/50">
                        <td className="p-1 font-medium">Total</td>
                        <td className="p-1 text-right border-l border-border">
                          {executionMetrics?.brightdata_calls ? formatNumber(executionMetrics.brightdata_calls.call_count) : '-'}
                        </td>
                        <td className="p-1 text-right">
                          {executionMetrics?.brightdata_calls
                            ? formatDuration(executionMetrics.brightdata_calls.total_duration_ms)
                            : '-'}
                        </td>
                        <td className="p-1 text-right">
                          {executionMetrics?.brightdata_calls
                            ? formatCost(executionMetrics.brightdata_calls.total_cost)
                            : '-'}
                        </td>
                        <td className="p-1 text-right border-l border-border">
                          {aggregatedMetrics?.brightdata ? formatNumber(aggregatedMetrics.brightdata.total_calls) : '-'}
                        </td>
                        <td className="p-1 text-right">
                          {aggregatedMetrics?.brightdata
                            ? formatDuration(aggregatedMetrics.brightdata.total_duration_ms)
                            : '-'}
                        </td>
                        <td className="p-1 text-right">
                          {aggregatedMetrics?.brightdata
                            ? formatCost(aggregatedMetrics.brightdata.total_cost)
                            : '-'}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
            </div>
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
