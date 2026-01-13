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

export interface UserConfig {
  account: string
  orgs: string[]
  projects: Record<string, string[]>
}

export interface OrgProjectSelection {
  org: string
  project: string
}

export interface ChatThread {
  thread_id: string
  user_id: string
  title: string | null
  created_at: string
  last_accessed_at: string
}

export type { ExecutionState, StreamEvent } from './execution'

