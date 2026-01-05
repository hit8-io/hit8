import type { ExecutionState, Message, ToolCall } from '../types/execution'
import { CONTENT_PREVIEW_LENGTH, ARGS_PREVIEW_LENGTH, TOOL_CALL_PREVIEW_LENGTH } from '../constants'

export function formatTimestamp(date: Date): string {
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  const seconds = date.getSeconds().toString().padStart(2, '0')
  const milliseconds = date.getMilliseconds().toString().padStart(3, '0')
  return `${hours}:${minutes}:${seconds}.${milliseconds}`
}

export function formatNodeList(nodes: string[] | undefined): string {
  return nodes && nodes.length > 0 ? nodes.join(', ') : ''
}

export function formatStateSummary(executionState: ExecutionState | null): string {
  if (!executionState) return 'next=[], messages=0'
  
  const nodes = formatNodeList(executionState.next)
  const messageCount = executionState.values?.message_count ?? executionState.values?.messages?.length ?? 0
  return `next=[${nodes}], messages=${messageCount}`
}

export function extractToolCalls(messages: Message[] | undefined): ToolCall[] {
  if (!messages || !Array.isArray(messages)) return []
  
  const toolCalls: ToolCall[] = []
  
  for (const msg of messages) {
    if (msg && typeof msg === 'object' && 'type' in msg) {
      const msgType = String(msg.type)
      if (msgType === 'AIMessage' || msgType === 'AIMessageChunk') {
        const toolCallsField = msg.tool_calls
        if (Array.isArray(toolCallsField)) {
          for (const toolCall of toolCallsField) {
            if (toolCall && typeof toolCall === 'object' && 'name' in toolCall && 'args' in toolCall) {
              toolCalls.push({
                name: String(toolCall.name),
                args: typeof toolCall.args === 'string' ? toolCall.args : JSON.stringify(toolCall.args),
                id: toolCall.id ? String(toolCall.id) : undefined,
              })
            }
          }
        }
      }
    }
  }
  
  return toolCalls
}

export function extractToolResults(messages: Message[] | undefined): Array<{ toolCallId: string; content: string; name?: string }> {
  if (!messages || !Array.isArray(messages)) return []
  
  const toolResults: Array<{ toolCallId: string; content: string; name?: string }> = []
  
  for (const msg of messages) {
    if (msg && typeof msg === 'object' && 'type' in msg) {
      const msgType = String(msg.type)
      if (msgType === 'ToolMessage') {
        const toolCallId = 'tool_call_id' in msg ? String(msg.tool_call_id) : ''
        const content = 'content' in msg ? String(msg.content) : ''
        const name = 'name' in msg ? String(msg.name) : undefined
        if (toolCallId) {
          toolResults.push({ toolCallId, content, name })
        }
      }
    }
  }
  
  return toolResults
}

export function extractTokenCount(msg: unknown): number | null {
  if (!msg || typeof msg !== 'object') return null
  
  if ('tokens' in msg && typeof msg.tokens === 'number') {
    return msg.tokens
  }
  
  if ('token_usage' in msg && typeof msg.token_usage === 'object' && msg.token_usage !== null) {
    const tokenUsage = msg.token_usage as { total_tokens?: number; prompt_tokens?: number; completion_tokens?: number }
    return tokenUsage.total_tokens ?? (((tokenUsage.prompt_tokens ?? 0) + (tokenUsage.completion_tokens ?? 0)) || null)
  }
  
  return null
}

export function formatContentPreview(content: string, maxLength: number = CONTENT_PREVIEW_LENGTH): string {
  if (content.length > maxLength) {
    return content.substring(0, maxLength) + '...'
  }
  return content
}

export function formatArgsPreview(args: string): string {
  try {
    const argsObj = JSON.parse(args)
    if (typeof argsObj === 'object' && argsObj !== null) {
      const keyValuePairs = Object.entries(argsObj)
        .slice(0, 3)
        .map(([k, v]) => `${k}=${String(v).substring(0, TOOL_CALL_PREVIEW_LENGTH)}`)
      let preview = keyValuePairs.join(', ')
      if (Object.keys(argsObj).length > 3) {
        preview += '...'
      }
      return preview
    }
  } catch {
    // Not JSON, just truncate
  }
  return formatContentPreview(args, ARGS_PREVIEW_LENGTH)
}

