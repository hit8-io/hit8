import { useState, useEffect, useRef, useCallback } from 'react'
import type React from 'react'
import type { Message, ExecutionState, StreamEvent } from '../types'
import type { Message as ExecutionMessage } from '../types/execution'
import { getApiHeaders } from './api'
import { CHAT_CLEANUP_DELAY } from '../constants'
import { getUserFriendlyError, logError } from './errorHandling'
import { convertMessageContent, createExecutionState } from './eventHandlers'
import type { EventHandlerContext } from './eventHandlers'
import { readStream } from './streamProcessor'

/**
 * Error with HTTP status code information.
 */
interface ErrorWithStatusCode extends Error {
  statusCode: number
}

/**
 * Error with type classification.
 */
interface ErrorWithType extends Error {
  type: string
}

/**
 * Fetches and processes message history from the backend for a given thread.
 * 
 * @param apiUrl - The API base URL
 * @param threadId - The thread ID to fetch history for
 * @param token - Authentication token
 * @returns Promise resolving to processed UI messages or null if thread doesn't exist
 */
export async function fetchMessageHistory(
  apiUrl: string,
  threadId: string,
  token: string
): Promise<Message[] | null> {
  const response = await fetch(`${apiUrl}/graph/state?thread_id=${threadId}`, {
    headers: getApiHeaders(token)
  })

  if (!response.ok) {
    if (response.status === 404) {
      // Thread doesn't exist - start fresh
      return null
    }
    throw new Error(`Failed to load thread: ${response.status}`)
  }

  const jsonData: unknown = await response.json()
  const state = jsonData as ExecutionState | null

  if (!state || !state.values || !state.values.messages) {
    return null
  }

  // Map LangGraph messages to UI format
  // Backend returns messages with type: "HumanMessage", "AIMessage", "ToolMessage", etc.
  const rawMessages = state.values.messages
  const uiMessages = rawMessages
    .filter((msg: ExecutionMessage) => {
      // Filter out SystemMessage and ToolMessage, only show HumanMessage and AIMessage
      const msgType = msg.type || ''
      return msgType === 'HumanMessage' || msgType === 'AIMessage'
    })
    .map((msg: ExecutionMessage): Message => {
      return {
        id: crypto.randomUUID(),
        role: msg.type === 'HumanMessage' ? 'user' : 'assistant',
        content: convertMessageContent(msg.content)
      }
    })

  return uiMessages
}

/**
 * Options for the useChatStream hook.
 */
interface UseChatStreamOptions {
  /** API base URL */
  apiUrl: string
  /** Thread ID for the conversation */
  threadId: string
  /** Authentication token */
  token: string
  /** Organization identifier */
  org?: string
  /** Project identifier */
  project?: string
  /** Callback for execution state updates */
  onExecutionStateUpdate?: (state: ExecutionState | null) => void
  /** Callback for chat state changes */
  onChatStateChange?: (active: boolean, threadId?: string | null) => void
}

/**
 * Return value from the useChatStream hook.
 */
interface UseChatStreamReturn {
  // State
  /** Current chat messages */
  messages: Message[]
  /** Current input value */
  input: string
  /** Setter for input value */
  setInput: (value: string) => void
  /** Whether a request is in progress */
  isLoading: boolean
  /** Streaming content being received */
  streamingContent: string
  /** Array of visited node names */
  visitedNodes: string[]
  /** Currently active node name */
  activeNode: string | null
  /** Array of stream events */
  streamEvents: StreamEvent[]
  /** Selected files for upload */
  selectedFiles: File[]
  /** Setter for selected files */
  setSelectedFiles: React.Dispatch<React.SetStateAction<File[]>>
  
  // Actions
  /** Send a message and handle streaming response */
  handleSend: () => Promise<void>
  /** Clear all state */
  clearState: () => void
  /** Load message history for current thread */
  loadHistory: () => Promise<void>
}

/**
 * Custom hook for managing chat stream state and processing.
 * Handles message history, streaming responses, and execution state updates.
 * 
 * @param options - Configuration options for the hook
 * @returns State and handlers for chat interface
 */
export function useChatStream({
  apiUrl,
  threadId,
  token,
  org,
  project,
  onExecutionStateUpdate,
  onChatStateChange,
}: UseChatStreamOptions): UseChatStreamReturn {
  // State
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [visitedNodes, setVisitedNodes] = useState<string[]>([])
  const [activeNode, setActiveNode] = useState<string | null>(null)
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([])
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  
  // Refs
  const timeoutRef = useRef<number | null>(null)
  const executionStateUpdateRef = useRef(onExecutionStateUpdate)
  const prevStateRef = useRef<{ visitedNodes: string[]; activeNode: string | null }>({
    visitedNodes: [],
    activeNode: null,
  })
  const lastMessageCountRef = useRef<number>(0)
  const pendingStateUpdateRef = useRef<ExecutionState | null>(null)
  
  // Update refs on each render
  executionStateUpdateRef.current = onExecutionStateUpdate
  
  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])
  
  // Process pending state updates in useEffect (outside render)
  // Intentionally runs on every render to flush pending state updates immediately
  // This avoids calling callbacks during render which can cause React warnings
  useEffect(() => {
    if (pendingStateUpdateRef.current && executionStateUpdateRef.current) {
      executionStateUpdateRef.current(pendingStateUpdateRef.current)
      pendingStateUpdateRef.current = null
    }
  })
  
  // Sync activeNode changes to execution state
  useEffect(() => {
    if (!executionStateUpdateRef.current) return
    
    const prevState = prevStateRef.current
    const activeNodeChanged = prevState.activeNode !== activeNode
    
    if (activeNodeChanged) {
      const currentVisitedNodes = prevStateRef.current.visitedNodes
      const newState = createExecutionState({
        next: activeNode ? [activeNode] : [],
        visitedNodes: currentVisitedNodes,
        messageCount: lastMessageCountRef.current,
        streamEvents: streamEvents.length > 0 ? [...streamEvents] : [],
      })
      
      prevStateRef.current = { visitedNodes: currentVisitedNodes, activeNode }
      pendingStateUpdateRef.current = newState
    }
  }, [activeNode, streamEvents])
  
  // Helper to queue state update
  const queueStateUpdate = useCallback((state: ExecutionState) => {
    pendingStateUpdateRef.current = state
  }, [])
  
  // Clear all state
  const clearState = useCallback(() => {
    setMessages([])
    setStreamingContent('')
    setStreamEvents([])
    setVisitedNodes([])
    setActiveNode(null)
    setInput('')
    setSelectedFiles([])
  }, [])
  
  // Load message history
  const loadHistory = useCallback(async () => {
    if (!threadId || !apiUrl || !org || !project) return
    
    clearState()
    
    try {
      const uiMessages = await fetchMessageHistory(apiUrl, threadId, token)
      if (uiMessages) {
        setMessages(uiMessages)
        lastMessageCountRef.current = uiMessages.length
      }
    } catch (err) {
      console.error('Failed to load thread:', err)
    }
  }, [threadId, apiUrl, token, org, project, clearState])
  
  // Load history when threadId, org, or project changes
  useEffect(() => {
    void loadHistory()
  }, [loadHistory])
  
  // Error handling
  const handleResponseError = useCallback(async (response: Response): Promise<never> => {
    let errorMessage = `Request failed with status ${response.status}`
    try {
      const jsonData: unknown = await response.json()
      if (typeof jsonData === 'object' && jsonData !== null && 'detail' in jsonData) {
        const errorData = jsonData as { detail?: string }
        if (errorData.detail) {
          errorMessage = errorData.detail
        }
      }
    } catch {
      // If response is not JSON, use default message
    }
    const error: ErrorWithStatusCode = Object.assign(new Error(errorMessage), { statusCode: response.status })
    throw error
  }, [])
  
  // Memoize readStream wrapper to create fresh context with current state values
  const memoizedReadStream = useCallback(async (
    reader: ReadableStreamDefaultReader<Uint8Array>,
    decoder: TextDecoder
  ): Promise<{ accumulatedContent: string; finalResponse: string; graphEndReceived: boolean; hasError: boolean }> => {
    // Create fresh context with current state values
    const currentContext: EventHandlerContext = {
      setStreamEvents,
      setVisitedNodes,
      setActiveNode,
      setStreamingContent,
      queueStateUpdate,
      prevStateRef,
      lastMessageCountRef,
      timeoutRef,
      threadId,
      activeNode,
      visitedNodes,
    }
    return readStream(reader, decoder, currentContext)
  }, [threadId, activeNode, visitedNodes, queueStateUpdate])
  
  const addAssistantMessage = useCallback((content: string): void => {
    const assistantMessage: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content,
    }
    setMessages((prev) => [...prev, assistantMessage])
  }, [])
  
  const handleStreamCompletion = useCallback((
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
  }, [addAssistantMessage])
  
  // Main send handler
  const handleSend = useCallback(async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = { 
      id: crypto.randomUUID(),
      role: 'user', 
      content: input 
    }
    setMessages((prev) => [...prev, userMessage])
    const messageContent = input
    setInput('')
    setIsLoading(true)

    const activeThreadId = threadId
    onChatStateChange?.(true, activeThreadId)

    setStreamingContent('')
    setStreamEvents([])

    try {
      const formData = new FormData()
      formData.append('message', messageContent)
      formData.append('thread_id', activeThreadId)
      selectedFiles.forEach(file => {
        formData.append('files', file)
      })

      const headers = getApiHeaders(token)
      delete headers['Content-Type']
      
      const response = await fetch(`${apiUrl}/chat`, {
        method: 'POST',
        headers,
        body: formData,
      })

      setSelectedFiles([])

      if (!response.ok) {
        await handleResponseError(response)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body reader available')
      }

      const { accumulatedContent, finalResponse, hasError } = await memoizedReadStream(reader, decoder)
      handleStreamCompletion(finalResponse, accumulatedContent, hasError)

    } catch (error) {
      // Type guard for ErrorWithType
      const isErrorWithType = (err: unknown): err is ErrorWithType => {
        return err instanceof Error && 'type' in err
      }
      
      const errorDetails = error instanceof Error 
        ? {
            message: error.message,
            type: isErrorWithType(error) ? error.type : error.constructor.name,
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
      timeoutRef.current = window.setTimeout(() => {
        setVisitedNodes([])
        setActiveNode(null)
        setStreamEvents([])
        onChatStateChange?.(false)
        timeoutRef.current = null
      }, CHAT_CLEANUP_DELAY)
    }
  }, [input, isLoading, threadId, selectedFiles, token, apiUrl, onChatStateChange, memoizedReadStream, handleStreamCompletion, handleResponseError])
  
  return {
    // State
    messages,
    input,
    setInput,
    isLoading,
    streamingContent,
    visitedNodes,
    activeNode,
    streamEvents,
    selectedFiles,
    setSelectedFiles,
    
    // Actions
    handleSend,
    clearState,
    loadHistory,
  }
}
