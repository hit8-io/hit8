import { useState, useEffect, useRef } from 'react'
import { Send, LogOut, Maximize2, Minimize2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from './ui/button'
import { getApiHeaders } from '../utils/api'
import { getUserFriendlyError, logError, isBenignConnectionError } from '../utils/errorHandling'
import { Input } from './ui/input'
import { Card } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import type { ExecutionState, StreamEvent } from '../types/execution'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

interface User {
  id: string
  email: string
  name: string
  picture: string
}

interface ChatInterfaceProps {
  readonly token: string
  readonly user: User
  readonly onLogout: () => void
  readonly onChatStateChange?: (active: boolean, threadId?: string | null) => void
  readonly onExecutionStateUpdate?: (state: ExecutionState | null) => void
  readonly isExpanded?: boolean
  readonly onToggleExpand?: () => void
}

const API_URL = import.meta.env.VITE_API_URL

export default function ChatInterface({ token, user: _user, onLogout, onChatStateChange, onExecutionStateUpdate, isExpanded = false, onToggleExpand }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('') // Track incremental content while streaming
  const [visitedNodes, setVisitedNodes] = useState<string[]>([]) // Track visited nodes for history
  const [activeNode, setActiveNode] = useState<string | null>(null) // Track currently active node
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]) // Track stream events for real-time logging
  const timeoutRef = useRef<number | null>(null)
  const executionStateUpdateRef = useRef(onExecutionStateUpdate)
  const prevStateRef = useRef<{ visitedNodes: string[], activeNode: string | null }>({ visitedNodes: [], activeNode: null })
  
  // Update ref on each render (safe for refs, doesn't cause re-renders)
  executionStateUpdateRef.current = onExecutionStateUpdate
  
  // Cleanup timeout on unmount - must be called before any early returns
  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  // Sync execution state updates to parent (avoid calling during render) - must be called before any early returns
  useEffect(() => {
    if (!executionStateUpdateRef.current) return
    
    // Always update execution state when visitedNodes, activeNode, or streamEvents change
    // This ensures GraphView and StatusWindow always have the latest state
    const newState: ExecutionState = {
      next: activeNode ? [activeNode] : [],
      values: {},
      history: visitedNodes.map(node => ({ node })),
      streamEvents: streamEvents.length > 0 ? [...streamEvents] : undefined,
    }
    
    // Always send state update when streamEvents change (for real-time event logging)
    // Also send when visitedNodes or activeNode change
    const prevState = prevStateRef.current
    const stateChanged = 
      prevState.visitedNodes.length !== visitedNodes.length ||
      prevState.activeNode !== activeNode ||
      // eslint-disable-next-line security/detect-object-injection
      prevState.visitedNodes.some((node, i) => node !== visitedNodes[i]) ||
      streamEvents.length > 0 // Always update if there are stream events
    
    if (stateChanged) {
      prevStateRef.current = { visitedNodes, activeNode }
      executionStateUpdateRef.current(newState)
    }
  }, [visitedNodes, activeNode, streamEvents, onExecutionStateUpdate])

  // Fail fast if API URL is missing (after hooks)
  if (!API_URL) {
    return (
      <div className="flex flex-col h-screen max-w-4xl mx-auto p-4">
        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-lg">
          <p className="font-semibold">Configuration Error</p>
          <p>API URL is not configured. Please set VITE_API_URL environment variable.</p>
        </div>
      </div>
    )
  }

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = { 
      id: crypto.randomUUID(),
      role: 'user', 
      content: input 
    }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    // Generate thread_id on frontend
    const threadId = crypto.randomUUID()

    // Notify parent that chat is active with thread_id
    onChatStateChange?.(true, threadId)

    // Reset streaming state and events
    setStreamingContent('')
    setStreamEvents([])
    let accumulatedContent = '' // Track accumulated content from chunks
    let finalResponse = ''
    let hasError = false
    let graphEndReceived = false // Track if graph_end event was received

    try {
      // Use fetch for streaming SSE response
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: getApiHeaders(token),
        body: JSON.stringify({
          message: userMessage.content,
          thread_id: threadId,
        }),
      })

      if (!response.ok) {
        // Try to get error message from response
        let errorMessage = `Request failed with status ${response.status}`
        try {
          const errorData = await response.json()
          if (errorData.detail) {
            errorMessage = errorData.detail
          }
        } catch {
          // If response is not JSON, use default message
        }
        const error = new Error(errorMessage)
        ;(error as any).statusCode = response.status
        throw error
      }

      // Read the stream with timeout
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body reader available')
      }

      let buffer = ''
      const STREAM_TIMEOUT = 60000 // 60 seconds timeout
      const startTime = Date.now()
      let lastActivityTime = Date.now()

      while (true) {
        // Check for overall timeout
        if (Date.now() - startTime > STREAM_TIMEOUT) {
          throw new Error('Stream timeout: The request took too long to complete')
        }

        // Check for inactivity timeout (30 seconds without data)
        if (Date.now() - lastActivityTime > 30000) {
          throw new Error('Stream timeout: No data received for 30 seconds')
        }

        const { done, value } = await reader.read()
        
        if (done) break

        lastActivityTime = Date.now()
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const rawData = line.slice(6) // Remove 'data: ' prefix
              const data = JSON.parse(rawData)
              
              // Handle different event types
              if (data.type === 'graph_start') {
                // Graph execution started
                setStreamEvents([]) // Reset events for new execution
                setVisitedNodes([])
                setActiveNode(null)
              } else if (data.type === 'content_chunk') {
                // Incremental content chunk received
                const chunkContent = data.content || ''
                accumulatedContent += chunkContent
                setStreamingContent(accumulatedContent)
              } else if (data.type === 'state_update') {
                // Real-time state update from stream_events - no polling needed
                const stateEvent = data as StreamEvent & { type: 'state_update' }
                // Also update active node based on next nodes
                if (stateEvent.next && stateEvent.next.length > 0) {
                  setActiveNode(stateEvent.next[0])
                } else {
                  setActiveNode(null)
                }
                // Add state_update to streamEvents and let useEffect sync state
                setStreamEvents(prev => [...prev, stateEvent])
                // Also trigger immediate state update for state_update events
                executionStateUpdateRef.current?.({
                  next: stateEvent.next || [],
                  values: {
                    message_count: stateEvent.message_count || 0,
                  },
                  history: visitedNodes.map(node => ({ node })),
                  streamEvents: streamEvents.length > 0 ? [...streamEvents, stateEvent] : [stateEvent],
                })
              } else if (data.type === 'llm_start' || data.type === 'llm_end') {
                // LLM call event - add to stream events (useEffect will sync state)
                const llmEvent = data as StreamEvent & { type: 'llm_start' | 'llm_end' }
                setStreamEvents(prev => [...prev, llmEvent])
              } else if (data.type === 'tool_start' || data.type === 'tool_end') {
                // Tool invocation event - add to stream events (useEffect will sync state)
                const toolEvent = data as StreamEvent & { type: 'tool_start' | 'tool_end' }
                setStreamEvents(prev => [...prev, toolEvent])
              } else if (data.type === 'node_start') {
                // Node is starting - mark as active
                const nodeName = data.node
                setActiveNode(nodeName)
              } else if (data.type === 'node_end') {
                // Node completed - add to visited nodes and mark as inactive
                const nodeName = data.node
                setActiveNode(null)
                const updatedVisitedNodes = visitedNodes.includes(nodeName) 
                  ? visitedNodes 
                  : [...visitedNodes, nodeName]
                setVisitedNodes(updatedVisitedNodes)
              } else if (data.type === 'graph_end') {
                // Graph execution completed
                graphEndReceived = true
                finalResponse = data.response || accumulatedContent || ''
                // Ensure any active node is marked as visited before clearing
                const finalVisitedNodes = activeNode && !visitedNodes.includes(activeNode)
                  ? [...visitedNodes, activeNode]
                  : visitedNodes
                setVisitedNodes(finalVisitedNodes)
                setActiveNode(null) // Clear active node
                setStreamingContent('') // Clear streaming content
                
                // Final state will be sent via state_update events, no need to fetch
                // Clear state after a short delay to allow StatusWindow to process final events
                setTimeout(() => {
                  executionStateUpdateRef.current?.({
                    next: [],
                    values: {},
                    history: finalVisitedNodes.map(node => ({ node })),
                  })
                  // Clear stream events after processing
                  setStreamEvents([])
                }, 1000)
                
                // Update prevStateRef to ensure useEffect recognizes the change
                prevStateRef.current = { visitedNodes: finalVisitedNodes, activeNode: null }
              } else if (data.type === 'error') {
                const errorMessage = data.error && data.error.trim() ? data.error : 'Unknown error occurred'
                const errorType = data.error_type || 'Error'
                const error = new Error(errorMessage)
                ;(error as any).type = errorType
                
                // Check if this is a benign connection error
                const hasCompleted = accumulatedContent.length > 0 || finalResponse.length > 0 || graphEndReceived
                const isBenign = isBenignConnectionError(error, hasCompleted)
                
                if (isBenign) {
                  // Connection closed after successful completion - this is normal
                  // Silently ignore - don't log, don't set error, just continue
                } else {
                  // Actual error - log and throw
                  hasError = true
                  logError('ChatInterface: Stream error', {
                    error: errorMessage,
                    errorType,
                    threadId: data.thread_id,
                    data,
                  })
                  
                  throw error
                }
              }
            } catch {
              // Silently skip malformed SSE data
            }
          }
        }
      }

      // If stream ended without graph_end, use accumulated content if available
      if (!finalResponse && !hasError && accumulatedContent) {
        finalResponse = accumulatedContent
      }

      // Clear streaming content
      setStreamingContent('')

      // Add final assistant message
      if (finalResponse && !hasError) {
        const assistantMessage: Message = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: finalResponse,
        }
        setMessages((prev) => [...prev, assistantMessage])
      } else if (!finalResponse && !hasError) {
        // If no response was received, show an error
        const errorMsg: Message = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'No response received from the server. Please try again.',
        }
        setMessages((prev) => [...prev, errorMsg])
      }

    } catch (error) {
      hasError = true
      
      // Log error for debugging (only in development)
      logError('ChatInterface: Chat stream error', {
        error,
        threadId,
      })
      
      // Get user-friendly error message
      const apiError = getUserFriendlyError(error)
      const errorMessage = apiError.isUserFriendly 
        ? apiError.message 
        : 'Sorry, I encountered an error. Please try again.'
      
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: errorMessage,
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
      // Keep chat active briefly to allow final state update, then deactivate
      // Clear any existing timeout
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current)
      }
      timeoutRef.current = window.setTimeout(() => {
        // Reset visited nodes, active node, and stream events for next conversation
        setVisitedNodes([])
        setActiveNode(null)
        setStreamEvents([])
        // Clear execution state when chat becomes inactive
        executionStateUpdateRef.current?.(null)
        onChatStateChange?.(false)
        timeoutRef.current = null
      }, 1000)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      <Card className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex justify-between items-center">
          <h1 className="text-2xl font-bold">Hit8 Chat</h1>
          <div className="flex items-center gap-4">
            <Button variant="outline" size="icon" onClick={onLogout} title="Sign out">
              <LogOut className="h-4 w-4" />
            </Button>
            {onToggleExpand && (
              <Button variant="outline" size="icon" onClick={onToggleExpand} title={isExpanded ? "Show graph and status" : "Expand chat"}>
                {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </Button>
            )}
          </div>
        </div>
        
        <ScrollArea className="flex-1 p-4">
          <div className="space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-muted-foreground py-8">
                Start a conversation by sending a message below.
              </div>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-lg p-3 ${
                    message.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {message.role === 'assistant' ? (
                    <div className="markdown-content">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
                          ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1 ml-2">{children}</ul>,
                          ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1 ml-2">{children}</ol>,
                          li: ({ children }) => <li className="ml-2">{children}</li>,
                          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                          em: ({ children }) => <em className="italic">{children}</em>,
                          code: ({ children, className }) => {
                            const isInline = !className
                            return isInline ? (
                              <code className="bg-muted-foreground/20 px-1 py-0.5 rounded text-sm font-mono">
                                {children}
                              </code>
                            ) : (
                              <code className={className}>{children}</code>
                            )
                          },
                          pre: ({ children }) => (
                            <pre className="bg-muted-foreground/20 p-2 rounded overflow-x-auto mb-2 text-sm">
                              {children}
                            </pre>
                          ),
                          h1: ({ children }) => <h1 className="text-xl font-bold mb-2 mt-4 first:mt-0">{children}</h1>,
                          h2: ({ children }) => <h2 className="text-lg font-bold mb-2 mt-4 first:mt-0">{children}</h2>,
                          h3: ({ children }) => <h3 className="text-base font-bold mb-2 mt-4 first:mt-0">{children}</h3>,
                          hr: () => <hr className="my-4 border-muted-foreground/30" />,
                          blockquote: ({ children }) => (
                            <blockquote className="border-l-4 border-muted-foreground/30 pl-4 italic my-2">
                              {children}
                            </blockquote>
                          ),
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    message.content
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-muted text-muted-foreground rounded-lg p-3 max-w-[80%]">
                  {streamingContent ? (
                    <div className="markdown-content">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
                          ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1 ml-2">{children}</ul>,
                          ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1 ml-2">{children}</ol>,
                          li: ({ children }) => <li className="ml-2">{children}</li>,
                          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                          em: ({ children }) => <em className="italic">{children}</em>,
                          code: ({ children, className }) => {
                            const isInline = !className
                            return isInline ? (
                              <code className="bg-muted-foreground/20 px-1 py-0.5 rounded text-sm font-mono">
                                {children}
                              </code>
                            ) : (
                              <code className={className}>{children}</code>
                            )
                          },
                          pre: ({ children }) => (
                            <pre className="bg-muted-foreground/20 p-2 rounded overflow-x-auto mb-2 text-sm">
                              {children}
                            </pre>
                          ),
                          h1: ({ children }) => <h1 className="text-xl font-bold mb-2 mt-4 first:mt-0">{children}</h1>,
                          h2: ({ children }) => <h2 className="text-lg font-bold mb-2 mt-4 first:mt-4">{children}</h2>,
                          h3: ({ children }) => <h3 className="text-base font-bold mb-2 mt-4 first:mt-4">{children}</h3>,
                          hr: () => <hr className="my-4 border-muted-foreground/30" />,
                          blockquote: ({ children }) => (
                            <blockquote className="border-l-4 border-muted-foreground/30 pl-4 italic my-2">
                              {children}
                            </blockquote>
                          ),
                        }}
                      >
                        {streamingContent}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    'Thinking...'
                  )}
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="p-4 border-t">
          <div className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type your message..."
              disabled={isLoading}
              className="flex-1"
            />
            <Button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              size="icon"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}

