export interface ExecutionState {
  next?: string[]
  values?: {
    messages?: unknown[]
    message_count?: number
  }
  history?: unknown[]
}

