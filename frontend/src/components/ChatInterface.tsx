import { useState, useEffect, useRef } from 'react'
import { Send, Maximize2, Minimize2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from './ui/button'
import { getApiHeaders } from '../utils/api'
import { getUserFriendlyError, logError, isBenignConnectionError } from '../utils/errorHandling'
import { Input } from './ui/input'
import { Card } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import type { Message, ExecutionState, StreamEvent } from '../types'
import { STREAM_TIMEOUT, STREAM_INACTIVITY_TIMEOUT, CHAT_CLEANUP_DELAY } from '../constants'

interface ChatInterfaceProps {
  readonly token: string
  readonly onChatStateChange?: (active: boolean, threadId?: string | null) => void
  readonly onExecutionStateUpdate?: (state: ExecutionState | null) => void
  readonly isExpanded?: boolean
  readonly onToggleExpand?: () => void
}

interface ErrorWithStatusCode extends Error {
  statusCode: number
}

interface ErrorWithType extends Error {
  type: string
}

const API_URL = import.meta.env.VITE_API_URL

export default function ChatInterface({ token, onChatStateChange, onExecutionStateUpdate, isExpanded = false, onToggleExpand }: ChatInterfaceProps) {
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

  const handleResponseError = async (response: Response): Promise<never> => {
    let errorMessage = `Request failed with status ${response.status}`
    try {
      const errorData = await response.json() as { detail?: string }
      if (errorData.detail) {
        errorMessage = errorData.detail
      }
    } catch {
      // If response is not JSON, use default message
    }
    const error: ErrorWithStatusCode = Object.assign(new Error(errorMessage), { statusCode: response.status })
    throw error
  }

  const checkTimeouts = (startTime: number, lastActivityTime: number): void => {
    const now = Date.now()
    
    if (now - startTime > STREAM_TIMEOUT) {
      throw new Error('Stream timeout: The request took too long to complete')
    }
    if (now - lastActivityTime > STREAM_INACTIVITY_TIMEOUT) {
      throw new Error('Stream timeout: No data received for 30 seconds')
    }
  }

  const handleGraphStart = (): void => {
    setStreamEvents([])
    setVisitedNodes([])
    setActiveNode(null)
  }

  const handleContentChunk = (data: { content?: string }, accumulatedContent: string): string => {
    const chunkContent = data.content || ''
    const newAccumulatedContent = accumulatedContent + chunkContent
    setStreamingContent(newAccumulatedContent)
    return newAccumulatedContent
  }

  const handleStateUpdate = (data: StreamEvent & { type: 'state_update' }): void => {
    setActiveNode(data.next && data.next.length > 0 ? data.next[0] : null)
    setStreamEvents(prev => [...prev, data])
    executionStateUpdateRef.current?.({
      next: data.next || [],
      values: { message_count: data.message_count || 0 },
      history: visitedNodes.map(node => ({ node })),
      streamEvents: streamEvents.length > 0 ? [...streamEvents, data] : [data],
    })
  }

  const handleLlmEvent = (data: StreamEvent & { type: 'llm_start' | 'llm_end' }): void => {
    setStreamEvents(prev => [...prev, data])
  }

  const handleToolEvent = (data: StreamEvent & { type: 'tool_start' | 'tool_end' }): void => {
    setStreamEvents(prev => [...prev, data])
  }

  const handleNodeStart = (data: { node?: string }): void => {
    const nodeName = typeof data.node === 'string' ? data.node : null
    if (nodeName) {
      setActiveNode(nodeName)
    }
  }

  const handleNodeEnd = (data: { node?: string }): void => {
    const nodeName = typeof data.node === 'string' ? data.node : null
    setActiveNode(null)
    if (nodeName && !visitedNodes.includes(nodeName)) {
      setVisitedNodes([...visitedNodes, nodeName])
    }
  }

  const handleGraphEnd = (data: { response?: string }, accumulatedContent: string): string => {
    const newFinalResponse = (typeof data.response === 'string' ? data.response : '') || accumulatedContent || ''
    const finalVisitedNodes = activeNode && !visitedNodes.includes(activeNode)
      ? [...visitedNodes, activeNode]
      : visitedNodes
    setVisitedNodes(finalVisitedNodes)
    setActiveNode(null)
    setStreamingContent('')
    
      setTimeout(() => {
        executionStateUpdateRef.current?.({
          next: [],
          values: {},
          history: finalVisitedNodes.map(node => ({ node })),
        })
        setStreamEvents([])
      }, CHAT_CLEANUP_DELAY)
    
    prevStateRef.current = { visitedNodes: finalVisitedNodes, activeNode: null }
    return newFinalResponse
  }

  const handleStreamError = (
    data: { error?: string; error_type?: string; thread_id?: string },
    accumulatedContent: string,
    finalResponse: string,
    graphEndReceived: boolean
  ): never => {
    const errorMessage = data.error && typeof data.error === 'string' && data.error.trim() ? data.error : 'Unknown error occurred'
    const errorType = data.error_type || 'Error'
    const error: ErrorWithType = Object.assign(new Error(errorMessage), { type: errorType })
    
    const hasCompleted = accumulatedContent.length > 0 || finalResponse.length > 0 || graphEndReceived
    const isBenign = isBenignConnectionError(error, hasCompleted)
    
    if (!isBenign) {
      logError('ChatInterface: Stream error', {
        error: errorMessage,
        errorType,
        threadId: data.thread_id,
        data,
      })
      throw error
    }
    throw error
  }

  const processStreamEvent = (
    data: Partial<StreamEvent> & { type?: string; content?: string; node?: string; response?: string; error?: string; error_type?: string; thread_id?: string },
    accumulatedContent: string,
    finalResponse: string,
    graphEndReceived: boolean,
    hasError: boolean
  ): { accumulatedContent: string; finalResponse: string; graphEndReceived: boolean; hasError: boolean } => {
    switch (data.type) {
      case 'graph_start':
        handleGraphStart()
        return { accumulatedContent, finalResponse, graphEndReceived, hasError }
      case 'content_chunk':
        return { accumulatedContent: handleContentChunk(data, accumulatedContent), finalResponse, graphEndReceived, hasError }
      case 'state_update':
        handleStateUpdate(data as StreamEvent & { type: 'state_update' })
        return { accumulatedContent, finalResponse, graphEndReceived, hasError }
      case 'llm_start':
      case 'llm_end':
        handleLlmEvent(data as StreamEvent & { type: 'llm_start' | 'llm_end' })
        return { accumulatedContent, finalResponse, graphEndReceived, hasError }
      case 'tool_start':
      case 'tool_end':
        handleToolEvent(data as StreamEvent & { type: 'tool_start' | 'tool_end' })
        return { accumulatedContent, finalResponse, graphEndReceived, hasError }
      case 'node_start':
        handleNodeStart(data)
        return { accumulatedContent, finalResponse, graphEndReceived, hasError }
      case 'node_end':
        handleNodeEnd(data)
        return { accumulatedContent, finalResponse, graphEndReceived, hasError }
      case 'graph_end':
        return { accumulatedContent, finalResponse: handleGraphEnd(data, accumulatedContent), graphEndReceived: true, hasError }
      case 'error':
        handleStreamError(data, accumulatedContent, finalResponse, graphEndReceived)
        return { accumulatedContent, finalResponse, graphEndReceived, hasError: true }
      default:
        return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    }
  }

  const addAssistantMessage = (content: string): void => {
    const assistantMessage: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content,
    }
    setMessages((prev) => [...prev, assistantMessage])
  }

  const handleStreamCompletion = (
    finalResponse: string,
    accumulatedContent: string,
    hasError: boolean
  ): void => {
    setStreamingContent('')

    if (hasError) {
      return
    }

    const responseToUse = finalResponse || accumulatedContent
    if (responseToUse) {
      addAssistantMessage(responseToUse)
    } else {
      addAssistantMessage('No response received from the server. Please try again.')
    }
  }

  const processStreamLine = (
    line: string,
    accumulatedContent: string,
    finalResponse: string,
    graphEndReceived: boolean,
    hasError: boolean
  ): { accumulatedContent: string; finalResponse: string; graphEndReceived: boolean; hasError: boolean } => {
    if (!line.startsWith('data: ')) {
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    }

    try {
      const rawData = line.slice(6)
      const data = JSON.parse(rawData) as Partial<StreamEvent> & { type?: string; content?: string; node?: string; response?: string; error?: string; error_type?: string; thread_id?: string }
      return processStreamEvent(data, accumulatedContent, finalResponse, graphEndReceived, hasError)
    } catch {
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    }
  }

  const readStream = async (
    reader: ReadableStreamDefaultReader<Uint8Array>,
    decoder: TextDecoder
  ): Promise<{ accumulatedContent: string; finalResponse: string; graphEndReceived: boolean; hasError: boolean }> => {
    let buffer = ''
    let accumulatedContent = ''
    let finalResponse = ''
    let graphEndReceived = false
    let hasError = false
    const startTime = Date.now()
    let lastActivityTime = Date.now()

    while (true) {
      checkTimeouts(startTime, lastActivityTime)

      const { done, value } = await reader.read()
      if (done) break

      lastActivityTime = Date.now()
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const result = processStreamLine(line, accumulatedContent, finalResponse, graphEndReceived, hasError)
        accumulatedContent = result.accumulatedContent
        finalResponse = result.finalResponse
        graphEndReceived = result.graphEndReceived
        hasError = result.hasError
      }
    }

    return { accumulatedContent, finalResponse, graphEndReceived, hasError }
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

    const threadId = crypto.randomUUID()
    onChatStateChange?.(true, threadId)

    setStreamingContent('')
    setStreamEvents([])

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: getApiHeaders(token),
        body: JSON.stringify({
          message: userMessage.content,
          thread_id: threadId,
        }),
      })

      if (!response.ok) {
        await handleResponseError(response)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body reader available')
      }

      const { accumulatedContent, finalResponse, hasError } = await readStream(reader, decoder)
      handleStreamCompletion(finalResponse, accumulatedContent, hasError)

    } catch (error) {
      logError('ChatInterface: Chat stream error', { error, threadId })
      
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
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current)
      }
      timeoutRef.current = window.setTimeout(() => {
        setVisitedNodes([])
        setActiveNode(null)
        setStreamEvents([])
        executionStateUpdateRef.current?.(null)
        onChatStateChange?.(false)
        timeoutRef.current = null
      }, CHAT_CLEANUP_DELAY)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      <Card className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex justify-between items-center">
          <h1 className="text-2xl font-bold">Hit8 Chat</h1>
          <div className="flex items-center gap-4">
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
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              disabled={isLoading}
              className="flex-1"
            />
            <Button
              onClick={() => void handleSend()}
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

