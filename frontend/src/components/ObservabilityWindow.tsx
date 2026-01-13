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
 * Format bytes to megabytes (X.XX format, no "MB" suffix).
 */
function formatMb(bytes: number): string {
  if (bytes === 0) return ''
  const mb = bytes / 1_048_576
  return mb.toFixed(2)
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

interface TableRow {
  type: 'llm' | 'embedding' | 'web'
  model: string
  tokensInput: number | null
  tokensOutput: number | null
  tokensThinking: number | null
  calls: number | null
  mb: number | null
}

export default function ObservabilityWindow({
  apiUrl,
  token,
  executionState,
  isLoading,
}: ObservabilityWindowProps) {
  // Extract thread_id from execution state
  const threadId = useMemo(() => extractThreadId(executionState), [executionState])
  
  // Use polling hook - only fetch current execution metrics
  const { executionMetrics, error, isRefreshing } = useObservabilityPolling({
    apiUrl,
    token,
    threadId,
    viewMode: 'current',
    isLoading,
    enabled: !!apiUrl && !!token,
  })

  // Generate table rows from execution metrics
  const tableRows = useMemo(() => {
    if (!executionMetrics) return []

    const rows: TableRow[] = []

    // Collect unique LLM models and aggregate per model
    const llmModels = new Map<string, { input: number; output: number; thinking: number; calls: number }>()
    executionMetrics.llm_calls.forEach(call => {
      const existing = llmModels.get(call.model) || { input: 0, output: 0, thinking: 0, calls: 0 }
      existing.input += call.input_tokens
      existing.output += call.output_tokens
      existing.thinking += call.thinking_tokens || 0
      existing.calls += 1
      llmModels.set(call.model, existing)
    })

    // Add LLM rows
    Array.from(llmModels.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .forEach(([model, stats]) => {
        rows.push({
          type: 'llm',
          model,
          tokensInput: stats.input > 0 ? stats.input : null,
          tokensOutput: stats.output > 0 ? stats.output : null,
          tokensThinking: stats.thinking > 0 ? stats.thinking : null,
          calls: stats.calls > 0 ? stats.calls : null,
          mb: null,
        })
      })

    // Collect unique embedding models and aggregate per model
    const embeddingModels = new Map<string, { input: number; calls: number }>()
    executionMetrics.embedding_calls.forEach(call => {
      const existing = embeddingModels.get(call.model) || { input: 0, calls: 0 }
      existing.input += call.input_tokens
      existing.calls += 1
      embeddingModels.set(call.model, existing)
    })

    // Add embedding rows
    Array.from(embeddingModels.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .forEach(([model, stats]) => {
        rows.push({
          type: 'embedding',
          model,
          tokensInput: stats.input > 0 ? stats.input : null,
          tokensOutput: null,
          tokensThinking: null,
          calls: stats.calls > 0 ? stats.calls : null,
          mb: null,
        })
      })

    // Add Bright Data row if there are any calls
    if (executionMetrics.brightdata_calls && executionMetrics.brightdata_calls.call_count > 0) {
      rows.push({
        type: 'web',
        model: 'Bright Data',
        tokensInput: null,
        tokensOutput: null,
        tokensThinking: null,
        calls: executionMetrics.brightdata_calls.call_count > 0 ? executionMetrics.brightdata_calls.call_count : null,
        mb: executionMetrics.brightdata_calls.total_bytes > 0 ? executionMetrics.brightdata_calls.total_bytes : null,
      })
    }

    return rows
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
          
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left p-1 font-semibold">Type</th>
                  <th className="text-left p-1 font-semibold">Model</th>
                  <th className="text-right p-1 font-semibold">Tokens Input</th>
                  <th className="text-right p-1 font-semibold">Tokens Output</th>
                  <th className="text-right p-1 font-semibold">Tokens Thinking</th>
                  <th className="text-right p-1 font-semibold">Calls</th>
                  <th className="text-right p-1 font-semibold">Mb</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-2 text-center text-muted-foreground">
                      No metrics available
                    </td>
                  </tr>
                ) : (
                  tableRows.map((row, index) => (
                    <tr key={`${row.type}-${row.model}-${index}`} className="border-b border-border/50">
                      <td className="p-1">{row.type}</td>
                      <td className="p-1">{row.model}</td>
                      <td className="p-1 text-right">
                        {row.tokensInput !== null ? formatNumber(row.tokensInput) : ''}
                      </td>
                      <td className="p-1 text-right">
                        {row.tokensOutput !== null ? formatNumber(row.tokensOutput) : ''}
                      </td>
                      <td className="p-1 text-right">
                        {row.tokensThinking !== null ? formatNumber(row.tokensThinking) : ''}
                      </td>
                      <td className="p-1 text-right">
                        {row.calls !== null ? formatNumber(row.calls) : ''}
                      </td>
                      <td className="p-1 text-right">
                        {row.mb !== null ? formatMb(row.mb) : ''}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
