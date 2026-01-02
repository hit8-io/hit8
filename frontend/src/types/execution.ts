export interface ExecutionState {
  next?: string[]
  values?: {
    messages?: unknown[]
    message_count?: number
  }
  history?: unknown[]
  streamEvents?: StreamEvent[] // Recent stream events for real-time logging
}

export type StreamEvent =
  | { type: 'graph_start'; thread_id: string }
  | { type: 'graph_end'; thread_id: string; response: string }
  | { type: 'node_start'; node: string; thread_id: string }
  | { type: 'node_end'; node: string; thread_id: string }
  | { type: 'llm_start'; model: string; input_preview: string; thread_id: string }
  | { type: 'llm_end'; model: string; input_preview: string; output_preview: string; token_usage?: any; tool_calls?: Array<{ name: string; args: any; id?: string }>; thread_id: string }
  | { type: 'tool_start'; tool_name: string; args_preview: string; thread_id: string }
  | { type: 'tool_end'; tool_name: string; args_preview: string; result_preview: string; thread_id: string }
  | { type: 'state_update'; next: string[]; message_count: number; thread_id: string }
  | { type: 'content_chunk'; content: string; thread_id: string }
  | { type: 'error'; error: string; error_type: string; thread_id: string }

