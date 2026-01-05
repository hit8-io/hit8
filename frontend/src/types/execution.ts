export interface TokenUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  [key: string]: number | undefined
}

export interface ToolCall {
  name: string
  args: string
  id?: string
}

export interface Message {
  type?: string
  content?: unknown
  tokens?: number
  tool_calls?: ToolCall[]
  [key: string]: unknown
}

export interface ExecutionState {
  next?: string[]
  values?: {
    messages?: Message[]
    message_count?: number
  }
  history?: unknown[]
  streamEvents?: StreamEvent[]
}

export type StreamEvent =
  | { type: 'graph_start'; thread_id: string }
  | { type: 'graph_end'; thread_id: string; response: string }
  | { type: 'node_start'; node: string; thread_id: string }
  | { type: 'node_end'; node: string; thread_id: string }
  | { type: 'llm_start'; model: string; input_preview: string; thread_id: string }
  | { type: 'llm_end'; model: string; input_preview: string; output_preview: string; token_usage?: TokenUsage; tool_calls?: ToolCall[]; thread_id: string }
  | { type: 'tool_start'; tool_name: string; args_preview: string; thread_id: string }
  | { type: 'tool_end'; tool_name: string; args_preview: string; result_preview: string; thread_id: string }
  | { type: 'state_update'; next: string[]; message_count: number; thread_id: string; visited_nodes?: string[] }
  | { type: 'content_chunk'; content: string; thread_id: string }
  | { type: 'error'; error: string; error_type: string; thread_id: string }

