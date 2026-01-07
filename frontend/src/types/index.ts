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

export type { ExecutionState, StreamEvent } from './execution'

