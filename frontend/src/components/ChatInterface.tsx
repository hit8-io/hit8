import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Send, Maximize2, Minimize2, Paperclip, X, Plus } from 'lucide-react'
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
  readonly threadId: string
  readonly onChatStateChange?: (active: boolean, threadId?: string | null) => void
  readonly onExecutionStateUpdate?: (state: ExecutionState | null) => void
  readonly isExpanded?: boolean
  readonly onToggleExpand?: () => void
  readonly org?: string
  readonly project?: string
}

interface ErrorWithStatusCode extends Error {
  statusCode: number
}

interface ErrorWithType extends Error {
  type: string
}

const API_URL = import.meta.env.VITE_API_URL

export default function ChatInterface({ token, threadId, onChatStateChange, onExecutionStateUpdate, isExpanded = false, onToggleExpand, org, project }: ChatInterfaceProps) {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('') // Track incremental content while streaming
  const [visitedNodes, setVisitedNodes] = useState<string[]>([]) // Track visited nodes for history
  const [activeNode, setActiveNode] = useState<string | null>(null) // Track currently active node
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]) // Track stream events for real-time logging
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const timeoutRef = useRef<number | null>(null)
  const executionStateUpdateRef = useRef(onExecutionStateUpdate)
  const prevStateRef = useRef<{ visitedNodes: string[], activeNode: string | null }>({ visitedNodes: [], activeNode: null })
  const lastMessageCountRef = useRef<number>(0) // Track last message count to preserve in final state
  
  // Validate UUID format
  const isValidUUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(threadId || '')
  
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

  // Validate UUID and redirect if invalid
  useEffect(() => {
    if (threadId && !isValidUUID) {
      // Malformed URL? Redirect to new chat
      navigate('/', { replace: true })
    }
  }, [threadId, isValidUUID, navigate])

  // Mandatory: Restore conversation history when threadId, org, or project changes
  useEffect(() => {
    if (!threadId || !isValidUUID || !API_URL || !org || !project) return
    
    // 1. Clear current UI messages immediately
    setMessages([])
    setStreamingContent('')
    setStreamEvents([])
    setVisitedNodes([])
    setActiveNode(null)
    
    // 2. Fetch history from backend
    // Note: getApiHeaders() automatically includes X-Org and X-Project from localStorage
    fetch(`${API_URL}/graph/state?thread_id=${threadId}`, {
      headers: getApiHeaders(token)
    })
      .then(res => {
        if (!res.ok) {
          if (res.status === 404) {
            // Thread doesn't exist - start fresh
            console.log('Thread not found, starting fresh')
            return null
          }
          throw new Error(`Failed to load thread: ${res.status}`)
        }
        return res.json()
      })
      .then(state => {
        if (state && state.values && state.values.messages) {
          // 3. Rehydrate the chat UI
          // Map LangGraph messages to UI format
          // Backend returns messages with type: "HumanMessage", "AIMessage", "ToolMessage", etc.
          const uiMessages = state.values.messages
            .filter((msg: any) => {
              // Filter out SystemMessage and ToolMessage, only show HumanMessage and AIMessage
              const msgType = msg.type || ''
              return msgType === 'HumanMessage' || msgType === 'AIMessage'
            })
            .map((msg: any) => ({
              id: crypto.randomUUID(),
              role: msg.type === 'HumanMessage' ? 'user' : 'assistant',
              content: typeof msg.content === 'string' ? msg.content : (msg.content || '')
            }))
          setMessages(uiMessages)
          lastMessageCountRef.current = uiMessages.length
        }
      })
      .catch(err => {
        console.error('Failed to load thread:', err)
        // Start with empty state on error
      })
  }, [threadId, token, isValidUUID, org, project])

  // Sync execution state updates to parent (avoid calling during render) - must be called before any early returns
  // NOTE: visitedNodes updates are handled by handleStateUpdate, not this useEffect
  // This useEffect only syncs activeNode changes to avoid race conditions with async state updates
  useEffect(() => {
    if (!executionStateUpdateRef.current) return
    
    // Only update when activeNode changes, not when visitedNodes changes
    // visitedNodes updates are handled directly in handleStateUpdate to avoid stale state
    const prevState = prevStateRef.current
    const activeNodeChanged = prevState.activeNode !== activeNode
    
    if (activeNodeChanged) {
      // Use the visitedNodes from prevStateRef which is updated synchronously in handleStateUpdate
      const currentVisitedNodes = prevStateRef.current.visitedNodes
      const newState: ExecutionState = {
        next: activeNode ? [activeNode] : [],
        values: {},
        history: currentVisitedNodes.map(node => ({ node })),
        streamEvents: streamEvents.length > 0 ? [...streamEvents] : undefined,
      }
      
      prevStateRef.current = { visitedNodes: currentVisitedNodes, activeNode }
      executionStateUpdateRef.current(newState)
    }
  }, [activeNode, onExecutionStateUpdate]) // Removed visitedNodes and streamEvents from dependencies

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
    // Reset execution state when new execution starts
    executionStateUpdateRef.current?.(null)
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
    
    // Use visited_nodes from event if provided, otherwise use local visitedNodes
    const eventVisitedNodes = data.visited_nodes || []
    // Merge with local visitedNodes to ensure we don't lose any
    const allVisitedNodes = [...new Set([...visitedNodes, ...eventVisitedNodes])]
    
    
    // Update local visitedNodes state so useEffect can read the correct value
    setVisitedNodes(allVisitedNodes)
    
    // Update prevStateRef immediately so useEffect doesn't overwrite with stale state
    const newActiveNode = data.next && data.next.length > 0 ? data.next[0] : null
    prevStateRef.current = { visitedNodes: allVisitedNodes, activeNode: newActiveNode }
    
    // Track last message count for use in handleGraphEnd
    const messageCount = data.message_count || 0
    lastMessageCountRef.current = messageCount
    
    const stateUpdate = {
      next: data.next || [],
      values: { message_count: messageCount },
      history: allVisitedNodes.map(node => ({ node })),
      streamEvents: streamEvents.length > 0 ? [...streamEvents, data] : [data],
    }
    executionStateUpdateRef.current?.(stateUpdate)
  }

  const handleLlmEvent = (data: StreamEvent & { type: 'llm_start' | 'llm_end' }): void => {
    setStreamEvents(prev => [...prev, data])
  }

  const handleToolEvent = (data: StreamEvent & { type: 'tool_start' | 'tool_end' }): void => {
    setStreamEvents(prev => [...prev, data])
  }

  const handleNodeStart = (data: { node?: string; thread_id?: string }): void => {
    const nodeName = typeof data.node === 'string' ? data.node : null
    const eventThreadId = typeof data.thread_id === 'string' ? data.thread_id : (threadId || '')
    if (nodeName) {
      // Create node_start event and add to streamEvents
      const nodeStartEvent: StreamEvent = {
        type: 'node_start',
        node: nodeName,
        thread_id: eventThreadId,
      }
      
      setStreamEvents(prev => {
        const updatedEvents = [...prev, nodeStartEvent]
        // Send state update with updated streamEvents
        const updatedVisitedNodes = visitedNodes.includes(nodeName) 
          ? visitedNodes 
          : [...visitedNodes, nodeName]
        
        executionStateUpdateRef.current?.({
          next: [nodeName],
          values: { message_count: lastMessageCountRef.current },
          history: updatedVisitedNodes.map(node => ({ node })),
          streamEvents: updatedEvents,
        })
        
        return updatedEvents
      })
      
      setActiveNode(nodeName)
      // Track node in visitedNodes immediately so it's included in state updates
      if (!visitedNodes.includes(nodeName)) {
        const updatedVisitedNodes = [...visitedNodes, nodeName]
        setVisitedNodes(updatedVisitedNodes)
        // Update prevStateRef to ensure state updates include this node
        prevStateRef.current = { 
          visitedNodes: updatedVisitedNodes, 
          activeNode: nodeName 
        }
      } else {
        prevStateRef.current = { 
          visitedNodes, 
          activeNode: nodeName 
        }
      }
    }
  }

  const handleNodeEnd = (data: { node?: string; thread_id?: string }): void => {
    const nodeName = typeof data.node === 'string' ? data.node : null
    const eventThreadId = typeof data.thread_id === 'string' ? data.thread_id : (threadId || '')
    setActiveNode(null)
    
    // Create node_end event and add to streamEvents
    if (nodeName) {
      const nodeEndEvent: StreamEvent = {
        type: 'node_end',
        node: nodeName,
        thread_id: eventThreadId,
      }
      
      setStreamEvents(prev => {
        const updatedEvents = [...prev, nodeEndEvent]
        // Send state update with updated streamEvents
        const updatedVisitedNodes = visitedNodes.includes(nodeName) 
          ? visitedNodes 
          : [...visitedNodes, nodeName]
        
        executionStateUpdateRef.current?.({
          next: [],
          values: { message_count: lastMessageCountRef.current },
          history: updatedVisitedNodes.map(node => ({ node })),
          streamEvents: updatedEvents,
        })
        
        return updatedEvents
      })
      
      if (!visitedNodes.includes(nodeName)) {
        const updatedVisitedNodes = [...visitedNodes, nodeName]
        setVisitedNodes(updatedVisitedNodes)
        // Update prevStateRef to ensure state updates include this node
        prevStateRef.current = { 
          visitedNodes: updatedVisitedNodes, 
          activeNode: null 
        }
      } else {
        prevStateRef.current = { 
          visitedNodes, 
          activeNode: null 
        }
      }
    }
  }

  const handleGraphEnd = (data: { response?: string }, accumulatedContent: string): string => {
    const newFinalResponse = (typeof data.response === 'string' ? data.response : '') || accumulatedContent || ''
    // Use prevStateRef to get the most up-to-date visited nodes (not stale state)
    const currentVisitedNodes = prevStateRef.current.visitedNodes
    const finalVisitedNodes = activeNode && !currentVisitedNodes.includes(activeNode)
      ? [...currentVisitedNodes, activeNode]
      : currentVisitedNodes
    setVisitedNodes(finalVisitedNodes)
    setActiveNode(null)
    setStreamingContent('')
    
    // Send final state update immediately (don't wait for timeout) to preserve highlighting
    // Preserve last message count to avoid StatusWindow showing "messages: X -> 0"
    executionStateUpdateRef.current?.({
      next: [],
      values: { message_count: lastMessageCountRef.current },
      history: finalVisitedNodes.map(node => ({ node })),
    })
    
    setTimeout(() => {
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

  const handleNewChat = () => {
    // Let the router handle the generation logic defined in App.tsx
    navigate('/')
  }

  const handleSend = async () => {
    if (!input.trim() || isLoading || !isValidUUID) return

    const userMessage: Message = { 
      id: crypto.randomUUID(),
      role: 'user', 
      content: input 
    }
    setMessages((prev) => [...prev, userMessage])
    const messageContent = input
    setInput('')
    setIsLoading(true)

    // Use threadId from URL (required route param)
    const activeThreadId = threadId
    onChatStateChange?.(true, activeThreadId)

    setStreamingContent('')
    setStreamEvents([])

    try {
      // Use FormData for multipart/form-data
      const formData = new FormData()
      formData.append('message', messageContent)
      formData.append('thread_id', activeThreadId)
      selectedFiles.forEach(file => {
        formData.append('files', file)
      })

      const headers = getApiHeaders(token)
      // Remove Content-Type - browser must set it with boundary for FormData
      delete headers['Content-Type']
      
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers,
        body: formData,
      })

      // Clear files after send
      setSelectedFiles([])

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
      // Extract error details for logging
      const errorDetails = error instanceof Error 
        ? {
            message: error.message,
            type: (error as ErrorWithType).type || error.constructor.name,
            stack: error.stack,
            threadId: activeThreadId,
          }
        : {
            error: String(error),
            threadId: activeThreadId,
          }
      logError('ChatInterface: Chat stream error', errorDetails)
      
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
      // Only reset execution state on error - on success, handleGraphEnd will send final state
      // Don't reset execution state here as it clears the highlighting immediately after execution
      timeoutRef.current = window.setTimeout(() => {
        setVisitedNodes([])
        setActiveNode(null)
        setStreamEvents([])
        // Don't reset execution state here - let it persist for highlighting
        // executionStateUpdateRef.current?.(null)  // Removed - prevents highlighting from being cleared
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

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    // Filter to only allowed file types
    const allowedExtensions = ['.docx', '.xlsx', '.pptx', '.pdf', '.html', '.txt', '.csv', '.json', '.xml', '.epub']
    const validFiles = files.filter(file => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      return allowedExtensions.includes(ext)
    })
    setSelectedFiles(prev => [...prev, ...validFiles])
    // Reset input to allow selecting same file again
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleFileButtonClick = () => {
    fileInputRef.current?.click()
  }

  return (
    <div className="flex flex-col h-full">
      <Card className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex justify-between items-center">
          <h1 className="text-2xl font-bold">Hit8 Chat</h1>
          <div className="flex items-center gap-4">
            <Button 
              variant="outline" 
              size="icon" 
              onClick={handleNewChat}
              title="New Chat"
              disabled={isLoading}
            >
              <Plus className="h-4 w-4" />
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
          {selectedFiles.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {selectedFiles.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center gap-1 bg-muted px-2 py-1 rounded-md text-sm"
                >
                  <span className="truncate max-w-[200px]">{file.name}</span>
                  <button
                    type="button"
                    onClick={() => removeFile(index)}
                    className="ml-1 hover:bg-muted-foreground/20 rounded p-0.5"
                    disabled={isLoading}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".docx,.xlsx,.pptx,.pdf,.html,.txt,.csv,.json,.xml,.epub"
              onChange={handleFileSelect}
              className="hidden"
              disabled={isLoading}
            />
            <Button
              type="button"
              onClick={handleFileButtonClick}
              disabled={isLoading}
              size="icon"
              variant="outline"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
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

