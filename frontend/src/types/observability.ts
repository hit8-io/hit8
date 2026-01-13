/**
 * TypeScript types for observability metrics matching backend Pydantic models.
 */

export interface LLMUsage {
  model: string
  config: Record<string, unknown> // temperature, thinking_level, etc.
  input_tokens: number
  output_tokens: number
  thinking_tokens: number | null
  ttft_ms: number | null // Time to first token in milliseconds
  duration_ms: number
  timestamp: string // ISO datetime string
}

export interface EmbeddingUsage {
  model: string
  input_tokens: number
  output_tokens: number
  duration_ms: number
  timestamp: string // ISO datetime string
}

export interface BrightDataUsage {
  call_count: number
  total_duration_ms: number
  total_cost: number | null
  total_bytes: number
}

export interface ExecutionMetrics {
  thread_id: string
  start_time: string // ISO datetime string
  end_time: string | null // ISO datetime string
  llm_calls: LLMUsage[]
  embedding_calls: EmbeddingUsage[]
  brightdata_calls: BrightDataUsage
}

export interface ModelUsageStats {
  call_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_thinking_tokens: number
  total_duration_ms: number
}

export interface LLMAggregatedMetrics {
  total_calls: number
  total_input_tokens: number
  total_output_tokens: number
  total_thinking_tokens: number
  total_duration_ms: number
  avg_ttft_ms: number | null
  by_model: Record<string, ModelUsageStats>
}

export interface EmbeddingAggregatedMetrics {
  total_calls: number
  total_input_tokens: number
  total_duration_ms: number
  by_model: Record<string, ModelUsageStats>
}

export interface BrightDataAggregatedMetrics {
  total_calls: number
  total_duration_ms: number
  total_cost: number | null
  total_bytes: number
}

export interface AggregatedMetrics {
  total_executions: number
  llm: LLMAggregatedMetrics
  embeddings: EmbeddingAggregatedMetrics
  brightdata: BrightDataAggregatedMetrics
}
