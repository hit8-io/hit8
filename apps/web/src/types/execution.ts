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
    logs?: string[]
  }
  history?: unknown[]
  streamEvents?: StreamEvent[]
}

import type { ExecutionMetrics } from './observability'

// Stream event type union
export type StreamEventType =
  | 'graph_start'
  | 'graph_end'
  | 'node_start'
  | 'node_end'
  | 'llm_start'
  | 'llm_end'
  | 'tool_start'
  | 'tool_end'
  | 'state_update'
  | 'state_snapshot'
  | 'content_chunk'
  | 'error'
  | 'keepalive'

// Event envelope structure
export interface StreamEventEnvelope {
  type: StreamEventType
  thread_id: string
  ts: number
  seq: number
  flow: 'chat' | 'report'
  run_id?: string
  task_id?: string
  payload?: Record<string, any>
}

// Legacy event types (for backwards compatibility during migration)
export type StreamEvent =
  | { type: 'graph_start'; thread_id: string; run_id?: string }
  | { type: 'graph_end'; thread_id: string; response: string; run_id?: string }
  | { type: 'node_start'; node: string; thread_id: string; run_id?: string; input_preview?: string }
  | { type: 'node_end'; node: string; thread_id: string; run_id?: string; output_preview?: string }
  | { type: 'llm_start'; model: string; input_preview: string; thread_id: string; run_id?: string; call_id?: string }
  | { type: 'llm_end'; model: string; input_preview: string; output_preview: string; token_usage?: TokenUsage; tool_calls?: ToolCall[]; thread_id: string; run_id?: string; execution_metrics?: ExecutionMetrics }
  | { type: 'tool_start'; tool_name: string; args_preview: string; thread_id: string; run_id?: string }
  | { type: 'tool_end'; tool_name: string; args_preview: string; result_preview: string; thread_id: string; run_id?: string }
  | { 
      type: 'state_update'; 
      next: string[]; 
      message_count: number; 
      thread_id: string; 
      visited_nodes?: string[];
      execution_metrics?: ExecutionMetrics;
      report_state?: {
        raw_procedures?: Array<Record<string, any>>;
        pending_clusters?: Array<Record<string, any>>;
        chapters?: string[];
        final_report?: string | null;
      };
    }
  | {
      type: 'state_snapshot';
      snapshot_id: string;
      next: string[];
      visited_nodes: string[];
      thread_id: string;
      report_state?: {
        raw_procedures?: Array<Record<string, any>>;
        pending_clusters?: Array<Record<string, any>>;
        chapters?: string[];
        chapters_by_file_id?: Record<string, string>;
        final_report?: string | null;
        cluster_status?: Record<string, { status: string; started_at?: string; ended_at?: string; error?: string }>;
      };
      cluster_status?: {
        active_cluster_ids: string[];
        completed_cluster_ids: string[];
      };
      task_history?: Array<{
        task_key?: string;
        node_name: string;
        run_id: string;
        started_at: number;
        ended_at?: number;
        input_preview?: string;
        output_preview?: string;
        metadata?: Record<string, any>;
      }>;
    }
  | { type: 'content_chunk'; content: string; accumulated: string; thread_id: string; run_id?: string }
  | { type: 'error'; error: string; error_type: string; thread_id: string }
  | { type: 'keepalive'; thread_id: string }

