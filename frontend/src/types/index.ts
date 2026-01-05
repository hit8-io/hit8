export interface User {
  id: string
  email: string
  name: string
  picture: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export type { ExecutionState, StreamEvent } from './execution'

