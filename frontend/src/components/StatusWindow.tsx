import { useState, useEffect, useRef } from 'react'
import { Card, CardContent } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import type { ExecutionState } from '../types/execution'

interface LogEntry {
  id: string
  timestamp: Date
  type: 'node_execution' | 'state_change' | 'tool_call' | 'tool_result' | 'llm_call' | 'tool_invocation'
  message: string // Formatted log line
}

interface StatusWindowProps {
  executionState: ExecutionState | null
  isLoading?: boolean
}

function formatTimestamp(date: Date): string {
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  const seconds = date.getSeconds().toString().padStart(2, '0')
  const milliseconds = date.getMilliseconds().toString().padStart(3, '0')
  return `${hours}:${minutes}:${seconds}.${milliseconds}`
}

function formatNodeList(nodes: string[] | undefined): string {
  return nodes && nodes.length > 0 ? nodes.join(', ') : ''
}

function formatStateSummary(executionState: ExecutionState | null): string {
  if (!executionState) return 'next=[], messages=0'
  
  const nodes = formatNodeList(executionState.next)
  const messageCount = executionState.values?.message_count ?? executionState.values?.messages?.length ?? 0
  return `next=[${nodes}], messages=${messageCount}`
}

function extractToolCalls(messages: unknown[] | undefined): Array<{ name: string; args: string; id?: string }> {
  if (!messages || !Array.isArray(messages)) return []
  
  const toolCalls: Array<{ name: string; args: string; id?: string }> = []
  
  for (const msg of messages) {
    if (msg && typeof msg === 'object') {
      // Check for AIMessage with tool_calls
      const msgType = 'type' in msg ? String(msg.type) : ''
      if (msgType === 'AIMessage' || msgType === 'AIMessageChunk') {
        // Try multiple possible field names
        const toolCallsField = 
          ('tool_calls' in msg ? msg.tool_calls : null) ||
          ('toolCalls' in msg ? msg.toolCalls : null) ||
          ('tool_calls' in msg && Array.isArray(msg.tool_calls) ? msg.tool_calls : null)
        
        if (Array.isArray(toolCallsField)) {
          for (const toolCall of toolCallsField) {
            if (toolCall && typeof toolCall === 'object') {
              const name = ('name' in toolCall ? String(toolCall.name) : null) ||
                          ('function' in toolCall && typeof toolCall.function === 'object' && 'name' in toolCall.function
                            ? String(toolCall.function.name) : 'unknown')
              const args = ('args' in toolCall ? JSON.stringify(toolCall.args) : null) ||
                          ('function' in toolCall && typeof toolCall.function === 'object' && 'arguments' in toolCall.function
                            ? String(toolCall.function.arguments) : '{}')
              const id = ('id' in toolCall ? String(toolCall.id) : undefined) ||
                        ('tool_call_id' in toolCall ? String(toolCall.tool_call_id) : undefined)
              if (name && name !== 'unknown') {
                toolCalls.push({ name, args: args || '{}', id })
              }
            }
          }
        }
      }
    }
  }
  
  return toolCalls
}

function extractToolResults(messages: unknown[] | undefined): Array<{ toolCallId: string; content: string; name?: string }> {
  if (!messages || !Array.isArray(messages)) return []
  
  const toolResults: Array<{ toolCallId: string; content: string; name?: string }> = []
  
  for (const msg of messages) {
    if (msg && typeof msg === 'object') {
      // Check for ToolMessage
      const msgType = 'type' in msg ? msg.type : ''
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

function extractMessageContent(msg: unknown): string | null {
  if (!msg || typeof msg !== 'object') return null
  
  const content = 'content' in msg ? msg.content : null
  if (content === null || content === undefined) return null
  
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    // Handle multimodal content
    const textParts = content
      .filter((item: unknown) => item && typeof item === 'object' && 'text' in item)
      .map((item: { text: string }) => item.text)
    return textParts.length > 0 ? textParts.join(' ') : null
  }
  
  return String(content)
}

function extractTokenCount(msg: unknown): number | null {
  if (!msg || typeof msg !== 'object') return null
  
  // Check for usage information (common in LLM responses)
  if ('usage_metadata' in msg && msg.usage_metadata && typeof msg.usage_metadata === 'object') {
    const usage = msg.usage_metadata as { total_tokens?: number; input_tokens?: number; output_tokens?: number }
    if (usage.total_tokens !== undefined) return usage.total_tokens
    if (usage.input_tokens !== undefined && usage.output_tokens !== undefined) {
      return usage.input_tokens + usage.output_tokens
    }
  }
  
  // Check for response_metadata
  if ('response_metadata' in msg && msg.response_metadata && typeof msg.response_metadata === 'object') {
    const metadata = msg.response_metadata as { token_usage?: { total_tokens?: number } }
    if (metadata.token_usage?.total_tokens !== undefined) {
      return metadata.token_usage.total_tokens
    }
  }
  
  return null
}

function getNewMessages(prevMessages: unknown[] | undefined, currentMessages: unknown[] | undefined): Array<{ type: string; content: string; tokens?: number }> {
  if (!Array.isArray(currentMessages)) return []
  if (!Array.isArray(prevMessages)) {
    // First time - return all messages
    return currentMessages.map(msg => {
      const msgType = msg && typeof msg === 'object' && 'type' in msg ? String(msg.type) : 'Unknown'
      const content = extractMessageContent(msg)
      const tokens = extractTokenCount(msg)
      return {
        type: msgType,
        content: content || '',
        tokens: tokens || undefined,
      }
    })
  }
  
  // Find new messages (messages that weren't in previous state)
  const prevMessageCount = prevMessages.length
  const currentMessageCount = currentMessages.length
  
  if (currentMessageCount > prevMessageCount) {
    const newMessages = currentMessages.slice(prevMessageCount)
    return newMessages.map(msg => {
      const msgType = msg && typeof msg === 'object' && 'type' in msg ? String(msg.type) : 'Unknown'
      const content = extractMessageContent(msg)
      const tokens = extractTokenCount(msg)
      return {
        type: msgType,
        content: content || '',
        tokens: tokens || undefined,
      }
    })
  }
  
  return []
}

export default function StatusWindow({ executionState, isLoading }: StatusWindowProps) {
  const [logEntries, setLogEntries] = useState<LogEntry[]>([])
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const prevStateRef = useRef<ExecutionState | null>(null)
  const hasInitializedRef = useRef<boolean>(false)
  const loggedMessageIdsRef = useRef<Set<string>>(new Set()) // Track logged messages to prevent duplicates
  const loggedToolCallIdsRef = useRef<Set<string>>(new Set()) // Track logged tool calls
  const loggedToolResultIdsRef = useRef<Set<string>>(new Set()) // Track logged tool results
  const processedEventIdsRef = useRef<Set<string>>(new Set()) // Track processed stream events to prevent duplicates

  useEffect(() => {
    
    // Skip initial empty state
    if (!executionState && !prevStateRef.current) {
      if (!hasInitializedRef.current) {
      return
      }
    }
    
    hasInitializedRef.current = true

    const prev = prevStateRef.current
    const current = executionState

    // Detect new node execution
    const prevNodes = new Set(prev?.next || [])
    const currentNodes = new Set(current?.next || [])
    const newNodes = [...currentNodes].filter(n => !prevNodes.has(n))

    // Detect state changes
    const changes: string[] = []
    const prevNextStr = JSON.stringify((prev?.next || []).sort())
    const currentNextStr = JSON.stringify((current?.next || []).sort())
    
    if (prevNextStr !== currentNextStr) {
      const prevNext = formatNodeList(prev?.next)
      const currentNext = formatNodeList(current?.next)
      changes.push(`next: [${prevNext}] -> [${currentNext}]`)
    }

    const prevMessageCount = prev?.values?.message_count ?? prev?.values?.messages?.length ?? 0
    const currentMessageCount = current?.values?.message_count ?? current?.values?.messages?.length ?? 0
    
    if (prevMessageCount !== currentMessageCount) {
      changes.push(`messages: ${prevMessageCount} -> ${currentMessageCount}`)
    }

    // Add log entries for new node executions
    const newEntries: LogEntry[] = []
    
    if (newNodes.length > 0) {
      const timestamp = new Date()
      const stateSummary = formatStateSummary(current)
      
      // Get tool call count for agent node
      const toolCalls = extractToolCalls(current?.values?.messages)
      const toolCallCount = toolCalls.length
      
      newNodes.forEach(node => {
        let message = `[${formatTimestamp(timestamp)}] [NODE_EXEC] ${node}`
        
        // Add tool call count for agent node
        if (node === 'agent' && toolCallCount > 0) {
          message += ` | tools=${toolCallCount}`
        }
        
        message += ` | ${stateSummary}`
        
        newEntries.push({
          id: `${timestamp.getTime()}-${Math.random()}`,
          timestamp,
          type: 'node_execution',
          message,
        })
      })
    }

    // Detect new messages - only log HumanMessage, skip AIMessage content, summarize ToolMessage
    const newMessages = getNewMessages(prev?.values?.messages, current?.values?.messages)
    
    
    if (newMessages.length > 0) {
      const timestamp = new Date()
      
      for (const msg of newMessages) {
        // Create unique ID for this message to prevent duplicates
        const msgId = `${msg.type}-${msg.content?.substring(0, 50)}-${timestamp.getTime()}`
        
        if (loggedMessageIdsRef.current.has(msgId)) {
          continue // Skip if already logged
        }
        
        // Only log HumanMessage content, skip AIMessage content, summarize ToolMessage
        if (msg.type === 'HumanMessage' && msg.content) {
          const contentPreview = msg.content.length > 100 
            ? msg.content.substring(0, 100) + '...' 
            : msg.content
          
          let message = `[${formatTimestamp(timestamp)}] [MESSAGE] ${msg.type}: ${contentPreview}`
          
          if (msg.tokens) {
            message += ` | tokens=${msg.tokens}`
          }
          
          newEntries.push({
            id: `${timestamp.getTime()}-${Math.random()}`,
            timestamp,
            type: 'state_change',
            message,
          })
          loggedMessageIdsRef.current.add(msgId)
        } else if (msg.type === 'ToolMessage' && msg.content) {
          // Summarize tool message content
          const contentStr = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)
          const contentPreview = contentStr.length > 80 
            ? contentStr.substring(0, 80) + '...' 
            : contentStr
          
          newEntries.push({
            id: `${timestamp.getTime()}-${Math.random()}`,
            timestamp,
            type: 'tool_result',
            message: `[${formatTimestamp(timestamp)}] [TOOL_RESULT] ${contentPreview}`,
          })
          loggedMessageIdsRef.current.add(msgId)
        }
        // Skip AIMessage content logging - we'll log tool calls and tokens separately
      }
    }

    // Also extract and log tool calls from new AIMessages immediately
    if (Array.isArray(current?.values?.messages)) {
      const prevMessageCount = prev?.values?.messages?.length || 0
      const currentMessageCount = current.values.messages.length
      
      if (currentMessageCount > prevMessageCount) {
        const newRawMessages = current.values.messages.slice(prevMessageCount)
        const timestamp = new Date()
        
        for (const rawMsg of newRawMessages) {
          if (rawMsg && typeof rawMsg === 'object') {
            const msgType = 'type' in rawMsg ? String(rawMsg.type) : ''
            
            // For AIMessage, extract and log tool_calls and tokens (skip content)
            if (msgType === 'AIMessage') {
              const toolCalls = extractToolCalls([rawMsg])
              const tokens = extractTokenCount(rawMsg)
              
              // Log tool calls
              if (toolCalls.length > 0) {
                for (const toolCall of toolCalls) {
                  const toolCallId = toolCall.id || `${toolCall.name}-${toolCall.args.substring(0, 20)}`
                  
                  if (loggedToolCallIdsRef.current.has(toolCallId)) {
                    continue // Skip if already logged
                  }
                  
                  // Summarize args - show key/value pairs if JSON, otherwise truncate
                  let argsPreview = toolCall.args
                  try {
                    const argsObj = JSON.parse(toolCall.args)
                    if (typeof argsObj === 'object' && argsObj !== null) {
                      const keyValuePairs = Object.entries(argsObj)
                        .slice(0, 3) // Show first 3 key-value pairs
                        .map(([k, v]) => `${k}=${String(v).substring(0, 30)}`)
                      argsPreview = keyValuePairs.join(', ')
                      if (Object.keys(argsObj).length > 3) {
                        argsPreview += '...'
                      }
                    }
                  } catch {
                    // Not JSON, just truncate
                    argsPreview = toolCall.args.length > 100 
                      ? toolCall.args.substring(0, 100) + '...' 
                      : toolCall.args
                  }
                  
                  newEntries.push({
                    id: `${timestamp.getTime()}-${Math.random()}`,
                    timestamp,
                    type: 'tool_call',
                    message: `[${formatTimestamp(timestamp)}] [TOOL_CALL] ${toolCall.name}(${argsPreview})`,
                  })
                  loggedToolCallIdsRef.current.add(toolCallId)
                }
              }
              
              // Log AIMessage summary (tokens only, no content)
              if (tokens) {
                newEntries.push({
                  id: `${timestamp.getTime()}-${Math.random()}`,
                  timestamp,
                  type: 'state_change',
                  message: `[${formatTimestamp(timestamp)}] [AIMESSAGE] tokens=${tokens}`,
                })
              } else {
                // Log AIMessage even without tokens to show it was generated
                newEntries.push({
                  id: `${timestamp.getTime()}-${Math.random()}`,
                  timestamp,
                  type: 'state_change',
                  message: `[${formatTimestamp(timestamp)}] [AIMESSAGE] generated`,
                })
              }
            }
          }
        }
      }
    }


    // Add log entry for state changes (if any changes detected)
    if (changes.length > 0 && prev !== null) {
      const timestamp = new Date()
      const stateSummary = formatStateSummary(current)
      const changeText = changes.join(', ')
      
      // Extract all available information from current state
      const toolCalls = extractToolCalls(current?.values?.messages)
      const toolCallCount = toolCalls.length
      const toolResults = extractToolResults(current?.values?.messages)
      const toolResultCount = toolResults.length
      
      // Count message types
      const messageTypes: Record<string, number> = {}
      if (Array.isArray(current?.values?.messages)) {
        for (const msg of current.values.messages) {
          if (msg && typeof msg === 'object' && 'type' in msg) {
            const type = String(msg.type)
            messageTypes[type] = (messageTypes[type] || 0) + 1
          }
        }
      }
      
      let message = `[${formatTimestamp(timestamp)}] [STATE_CHANGE] ${changeText}`
      
      // Add message type breakdown
      const typeBreakdown = Object.entries(messageTypes)
        .map(([type, count]) => `${type}=${count}`)
        .join(', ')
      if (typeBreakdown) {
        message += ` | ${typeBreakdown}`
      }
      
      // Add tool information with tool names
      if (toolCallCount > 0 || toolResultCount > 0) {
        const toolInfo: string[] = []
        if (toolCallCount > 0) {
          const toolNames = toolCalls.map(tc => tc.name).join(', ')
          toolInfo.push(`tools_called=[${toolNames}]`)
        }
        if (toolResultCount > 0) {
          const toolResultNames = toolResults.map(tr => tr.name || 'unknown').filter((name, idx, arr) => arr.indexOf(name) === idx) // unique
          toolInfo.push(`tools_completed=[${toolResultNames.join(', ')}]`)
        }
        if (toolInfo.length > 0) {
          message += ` | ${toolInfo.join(', ')}`
        }
      }
      
      // Add token count if available in any message
      if (Array.isArray(current?.values?.messages)) {
        let totalTokens = 0
        for (const msg of current.values.messages) {
          const tokens = extractTokenCount(msg)
          if (tokens) {
            totalTokens += tokens
          }
        }
        if (totalTokens > 0) {
          message += ` | tokens=${totalTokens}`
        }
      }
      
      message += ` | ${stateSummary}`
      
      newEntries.push({
        id: `${timestamp.getTime()}-${Math.random()}`,
        timestamp,
        type: 'state_change',
        message,
      })
    }

    // Log detailed state summary when significant changes occur (like graph ending)
    // IMPORTANT: Capture state BEFORE it gets cleared (when messages go from >0 to 0)
    if (prev !== null && current !== null) {
      const prevActive = (prev.next || []).length > 0
      const currentActive = (current.next || []).length > 0
      const prevMessageCount = prev?.values?.message_count ?? prev?.values?.messages?.length ?? 0
      const currentMessageCount = current?.values?.message_count ?? current?.values?.messages?.length ?? 0
      
      // When graph completes (active nodes go to empty OR messages are being cleared)
      // Use PREVIOUS state to capture details before they're lost
      if ((prevActive && !currentActive) || (prevMessageCount > 0 && currentMessageCount === 0)) {
        const timestamp = new Date()
        
        // Use PREVIOUS state to get the final execution details before clearing
        const stateToAnalyze = prevMessageCount > 0 ? prev : current
        const toolCalls = extractToolCalls(stateToAnalyze?.values?.messages)
        const toolResults = extractToolResults(stateToAnalyze?.values?.messages)
        const allMessages = stateToAnalyze?.values?.messages || []
        
        // Count message types
        const messageTypeCounts: Record<string, number> = {}
        for (const msg of allMessages) {
          if (msg && typeof msg === 'object' && 'type' in msg) {
            const msgType = String(msg.type)
            messageTypeCounts[msgType] = (messageTypeCounts[msgType] || 0) + 1
          }
        }
        
        // Find last AIMessage tokens and collect all token counts
        let lastAITokens: number | null = null
        let totalTokens = 0
        for (let i = allMessages.length - 1; i >= 0; i--) {
          const msg = allMessages[i]
          if (msg && typeof msg === 'object') {
            const msgType = 'type' in msg ? String(msg.type) : ''
            if (msgType === 'AIMessage') {
              const tokens = extractTokenCount(msg)
              if (tokens && !lastAITokens) {
                lastAITokens = tokens
              }
              if (tokens) {
                totalTokens += tokens
              }
            }
          }
        }
        
        // Log comprehensive summary (concise format)
        const summaryParts: string[] = []
        summaryParts.push(`messages=${allMessages.length}`)
        
        // Add message type breakdown
        const typeBreakdown = Object.entries(messageTypeCounts)
          .map(([type, count]) => `${type}=${count}`)
          .join(', ')
        if (typeBreakdown) {
          summaryParts.push(`types: ${typeBreakdown}`)
        }
        
        // Add tool information (concise) with tool names
        if (toolCalls.length > 0) {
          const toolNames = toolCalls.map(tc => tc.name).join(', ')
          summaryParts.push(`tools_called=[${toolNames}]`)
        }
        if (toolResults.length > 0) {
          const toolResultNames = toolResults.map(tr => tr.name || 'unknown').filter((name, idx, arr) => arr.indexOf(name) === idx) // unique names
          summaryParts.push(`tools_completed=[${toolResultNames.join(', ')}] (${toolResults.length})`)
        }
        
        // Add token information
        if (lastAITokens) {
          summaryParts.push(`tokens=${lastAITokens}`)
        } else if (totalTokens > 0) {
          summaryParts.push(`tokens=${totalTokens}`)
        }
        
        newEntries.push({
          id: `${timestamp.getTime()}-${Math.random()}`,
          timestamp,
          type: 'state_change',
          message: `[${formatTimestamp(timestamp)}] [GRAPH_COMPLETE] ${summaryParts.join(' | ')}`,
        })
      }
    }

    // Detect new tool calls from messages (compare with previous state)
    const prevMessages = prev?.values?.messages
    const currentMessages = current?.values?.messages
    
    if (Array.isArray(currentMessages)) {
      const prevToolCalls = extractToolCalls(prevMessages)
      const currentToolCalls = extractToolCalls(currentMessages)
      
      // Create sets of tool call IDs to find new ones
      const prevToolCallIds = new Set(
        prevToolCalls.map(tc => tc.id || `${tc.name}-${tc.args}`)
      )
      
      const newToolCalls = currentToolCalls.filter(
        tc => !prevToolCallIds.has(tc.id || `${tc.name}-${tc.args}`)
      )
      
      if (newToolCalls.length > 0) {
        const timestamp = new Date()
        
        for (const toolCall of newToolCalls) {
          // Truncate args if too long
          const argsPreview = toolCall.args.length > 150 
            ? toolCall.args.substring(0, 150) + '...' 
            : toolCall.args
          
          newEntries.push({
            id: `${timestamp.getTime()}-${Math.random()}`,
            timestamp,
            type: 'tool_call',
            message: `[${formatTimestamp(timestamp)}] [TOOL_CALL] ${toolCall.name}(${argsPreview})`,
          })
        }
      }
      
      // Also check for tool calls in new AIMessages by examining the raw message objects
      // Sometimes tool_calls might be in a different format
      const prevMessageCount = prevMessages?.length || 0
      const currentMessageCount = currentMessages.length
      
      if (currentMessageCount > prevMessageCount) {
        const newRawMessages = currentMessages.slice(prevMessageCount)
        const timestamp = new Date()
        
        for (const rawMsg of newRawMessages) {
          if (rawMsg && typeof rawMsg === 'object') {
            const msgType = 'type' in rawMsg ? String(rawMsg.type) : ''
            
            // For AIMessage, try to extract tool_calls from any possible field
            if (msgType === 'AIMessage') {
              // Check all possible locations for tool_calls
              const possibleToolCalls = 
                (rawMsg as { tool_calls?: unknown }).tool_calls ||
                (rawMsg as { toolCalls?: unknown }).toolCalls ||
                (rawMsg as { [key: string]: unknown })['tool_calls']
              
              if (Array.isArray(possibleToolCalls) && possibleToolCalls.length > 0) {
                for (const tc of possibleToolCalls) {
                  if (tc && typeof tc === 'object') {
                    const toolName = 
                      ('name' in tc ? String(tc.name) : null) ||
                      ('function' in tc && typeof tc.function === 'object' && 'name' in tc.function
                        ? String(tc.function.name) : 'unknown')
                    const toolArgs = 
                      ('args' in tc ? JSON.stringify(tc.args) : null) ||
                      ('function' in tc && typeof tc.function === 'object' && 'arguments' in tc.function
                        ? String(tc.function.arguments) : '{}')
                    
                    if (toolName && toolName !== 'unknown') {
                      const argsPreview = toolArgs.length > 150 
                        ? toolArgs.substring(0, 150) + '...' 
                        : toolArgs
                      
                      newEntries.push({
                        id: `${timestamp.getTime()}-${Math.random()}`,
                        timestamp,
                        type: 'tool_call',
                        message: `[${formatTimestamp(timestamp)}] [TOOL_CALL] ${toolName}(${argsPreview})`,
                      })
                    }
                  }
                }
              }
            }
          }
        }
      }
    }

    // Detect new tool results from messages (compare with previous state)
    if (Array.isArray(currentMessages)) {
      const prevToolResults = extractToolResults(prevMessages)
      const currentToolResults = extractToolResults(currentMessages)
      
      // Create sets of tool result IDs to find new ones
      const prevToolResultIds = new Set(prevToolResults.map(tr => tr.toolCallId))
      
      const newToolResults = currentToolResults.filter(
        tr => !prevToolResultIds.has(tr.toolCallId) && !loggedToolResultIdsRef.current.has(tr.toolCallId)
      )
      
      if (newToolResults.length > 0) {
        const timestamp = new Date()
        
        for (const toolResult of newToolResults) {
          // Summarize content - show first line or first 60 chars
          let contentPreview = toolResult.content
          if (contentPreview.length > 60) {
            const firstLine = contentPreview.split('\n')[0]
            contentPreview = firstLine.length > 60 
              ? firstLine.substring(0, 60) + '...' 
              : firstLine + '...'
          }
          
          // Get tool name - prefer from toolResult.name, otherwise try to find from tool_call_id
          let toolName = toolResult.name || 'unknown'
          
          // Try to find tool name from corresponding tool call
          if (toolName === 'unknown' && Array.isArray(currentMessages)) {
            const toolCalls = extractToolCalls(currentMessages)
            for (const tc of toolCalls) {
              if (tc.id === toolResult.toolCallId) {
                toolName = tc.name
                break
              }
            }
          }
          
          newEntries.push({
            id: `${timestamp.getTime()}-${Math.random()}`,
            timestamp,
            type: 'tool_result',
            message: `[${formatTimestamp(timestamp)}] [TOOL_RESULT] ${toolName}: ${contentPreview}`,
          })
          loggedToolResultIdsRef.current.add(toolResult.toolCallId)
        }
      }
    }

    // Process stream events for real-time logging (llm_start/end, tool_start/end)
    if (current?.streamEvents && Array.isArray(current.streamEvents)) {
      const timestamp = new Date()
      
      for (const event of current.streamEvents) {
        // Create unique ID for this event to prevent duplicates
        const eventId = `${event.type}-${event.thread_id}-${JSON.stringify(event).substring(0, 50)}`
        
        if (processedEventIdsRef.current.has(eventId)) {
          continue // Skip if already processed
        }
        
        if (event.type === 'llm_start') {
          const llmEvent = event as StreamEvent & { type: 'llm_start' }
          const inputPreview = llmEvent.input_preview || ''
          newEntries.push({
            id: `${timestamp.getTime()}-${Math.random()}`,
            timestamp,
            type: 'llm_call',
            message: `[${formatTimestamp(timestamp)}] [LLM_START] model=${llmEvent.model} | input="${inputPreview}"`,
          })
          processedEventIdsRef.current.add(eventId)
        } else if (event.type === 'llm_end') {
          const llmEvent = event as StreamEvent & { type: 'llm_end' }
          const inputPreview = llmEvent.input_preview || ''
          const outputPreview = llmEvent.output_preview || ''
          let message = `[${formatTimestamp(timestamp)}] [LLM_END] model=${llmEvent.model}`
          if (llmEvent.token_usage) {
            const tokens = llmEvent.token_usage.total_tokens || 
                          (llmEvent.token_usage.input_tokens && llmEvent.token_usage.output_tokens 
                            ? llmEvent.token_usage.input_tokens + llmEvent.token_usage.output_tokens 
                            : null)
            if (tokens) {
              message += ` | tokens=${tokens}`
            }
          }
          if (llmEvent.tool_calls && llmEvent.tool_calls.length > 0) {
            const toolNames = llmEvent.tool_calls.map(tc => tc.name).join(', ')
            message += ` | tools=[${toolNames}]`
          }
          message += ` | input="${inputPreview}" | output="${outputPreview}"`
          newEntries.push({
            id: `${timestamp.getTime()}-${Math.random()}`,
            timestamp,
            type: 'llm_call',
            message,
          })
          processedEventIdsRef.current.add(eventId)
        } else if (event.type === 'tool_start') {
          const toolEvent = event as StreamEvent & { type: 'tool_start' }
          const argsPreview = toolEvent.args_preview || '{}'
          newEntries.push({
            id: `${timestamp.getTime()}-${Math.random()}`,
            timestamp,
            type: 'tool_invocation',
            message: `[${formatTimestamp(timestamp)}] [TOOL_START] ${toolEvent.tool_name}(${argsPreview})`,
          })
          processedEventIdsRef.current.add(eventId)
        } else if (event.type === 'tool_end') {
          const toolEvent = event as StreamEvent & { type: 'tool_end' }
          const argsPreview = toolEvent.args_preview || '{}'
          const resultPreview = toolEvent.result_preview || ''
          newEntries.push({
            id: `${timestamp.getTime()}-${Math.random()}`,
            timestamp,
            type: 'tool_invocation',
            message: `[${formatTimestamp(timestamp)}] [TOOL_END] ${toolEvent.tool_name}(${argsPreview}) | result="${resultPreview}"`,
          })
          processedEventIdsRef.current.add(eventId)
        }
      }
    }

    // Update log entries
    if (newEntries.length > 0) {
      setLogEntries(prev => [...prev, ...newEntries])
    }

    // Update previous state reference (deep copy to avoid reference issues)
    prevStateRef.current = current ? JSON.parse(JSON.stringify(current)) : null

    // Auto-scroll to bottom when entries are updated
    requestAnimationFrame(() => {
      if (scrollAreaRef.current) {
        scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight
      }
    })
  }, [executionState, isLoading])

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardContent className="flex-1 min-h-0 p-2">
        <ScrollArea className="h-full" ref={scrollAreaRef}>
            {logEntries.length === 0 ? (
            <div className="text-xs text-muted-foreground py-4 text-center font-mono">
              No execution events yet
            </div>
          ) : (
            <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
              {logEntries.map(entry => entry.message).join('\n')}
            </pre>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
