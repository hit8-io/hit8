import { useState, useEffect, useRef } from 'react'
import { Send, LogOut } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from './ui/button'
import { getApiHeaders } from '../utils/api'
import { Input } from './ui/input'
import { Card } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import type { ExecutionState } from '../types/execution'

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
  token: string
  user: User
  onLogout: () => void
  onChatStateChange?: (active: boolean, threadId?: string | null) => void
  onExecutionStateUpdate?: (state: ExecutionState | null) => void
}

const API_URL = import.meta.env.VITE_API_URL

export default function ChatInterface({ token, user: _user, onLogout, onChatStateChange, onExecutionStateUpdate }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('') // Track incremental content while streaming
  const [visitedNodes, setVisitedNodes] = useState<string[]>([]) // Track visited nodes for history
  const [activeNode, setActiveNode] = useState<string | null>(null) // Track currently active node
  const timeoutRef = useRef<number | null>(null)
  const executionStateUpdateRef = useRef(onExecutionStateUpdate)
  const prevStateRef = useRef<{ visitedNodes: string[], activeNode: string | null }>({ visitedNodes: [], activeNode: null })
  
  // Update ref on each render (safe for refs, doesn't cause re-renders)
  executionStateUpdateRef.current = onExecutionStateUpdate
  
  // Fail fast if API URL is missing
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

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  // Sync execution state updates to parent (avoid calling during render)
  useEffect(() => {
    // Only update if state actually changed
    const prevState = prevStateRef.current
    const stateChanged = 
      prevState.visitedNodes.length !== visitedNodes.length ||
      prevState.activeNode !== activeNode ||
      prevState.visitedNodes.some((node, i) => node !== visitedNodes[i])
    
    if (stateChanged && executionStateUpdateRef.current) {
      prevStateRef.current = { visitedNodes, activeNode }
      executionStateUpdateRef.current({
        next: activeNode ? [activeNode] : [],
        values: {},
        history: visitedNodes.map(node => ({ node })),
      })
    }
  }, [visitedNodes, activeNode])

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

    // Generate thread_id on frontend so we can start polling immediately
    const threadId = crypto.randomUUID()

    // Notify parent that chat is active with thread_id for immediate polling
    onChatStateChange?.(true, threadId)

    // Reset streaming state
    setStreamingContent('')
    let accumulatedContent = '' // Track accumulated content from chunks
    let finalResponse = ''
    let hasError = false

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
        throw new Error(`HTTP error! status: ${response.status}`)
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
              const data = JSON.parse(line.slice(6)) // Remove 'data: ' prefix
              
              // Handle different event types
              if (data.type === 'content_chunk') {
                // Incremental content chunk received
                const chunkContent = data.content || ''
                accumulatedContent += chunkContent
                setStreamingContent(accumulatedContent)
              } else if (data.type === 'node_start') {
                // Node is starting - mark as active
                const nodeName = data.node
                setActiveNode(nodeName)
              } else if (data.type === 'node_end') {
                // Node completed - add to visited nodes and mark as inactive
                const nodeName = data.node
                setActiveNode(null)
                setVisitedNodes(prev => {
                  return prev.includes(nodeName) ? prev : [...prev, nodeName]
                })
              } else if (data.type === 'graph_end') {
                // Graph execution completed - get final response
                // Prefer graph_end.response, fallback to accumulated content
                finalResponse = data.response || accumulatedContent || ''
                setActiveNode(null)
                setStreamingContent('') // Clear streaming content
              } else if (data.type === 'error') {
                hasError = true
                const errorMessage = data.error && data.error.trim() ? data.error : 'Unknown error occurred'
                const errorType = data.error_type || 'Error'
                
                // Log error to console for debugging with full details
                console.error('🚨 Stream error received:', errorMessage)
                console.error('Error type:', errorType)
                console.error('Thread ID:', data.thread_id)
                console.error('Full error data:', JSON.stringify(data, null, 2))
                
                throw new Error(errorMessage)
              }
            } catch (parseError) {
              // Silently skip malformed SSE data
            }
          }
        }
      }

      // If stream ended without graph_end, use accumulated content if available
      if (!finalResponse && !hasError) {
        if (accumulatedContent) {
          // Use accumulated content as final response
          finalResponse = accumulatedContent
        } else {
          // Backend should always send graph_end, but handle gracefully if it doesn't
          if (import.meta.env.DEV) {
            console.warn('Stream ended without graph_end event and no accumulated content', { threadId })
          }
        }
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
      let errorMessage = 'Sorry, I encountered an error. Please try again.'
      if (error instanceof Error) {
        errorMessage = error.message
      }
      
      // Log error to console for debugging with full details
      console.error('🚨 Chat stream error:', errorMessage)
      console.error('Error object:', error)
      console.error('Thread ID:', threadId)
      console.error('Error type:', error instanceof Error ? error.constructor.name : typeof error)
      if (error instanceof Error && error.stack) {
        console.error('Stack trace:', error.stack)
      }
      
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: errorMessage,
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
      // Reset visited nodes and active node for next conversation
      setVisitedNodes([])
      setActiveNode(null)
      // Keep chat active briefly to allow final state update, then deactivate
      // Clear any existing timeout
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current)
      }
      timeoutRef.current = window.setTimeout(() => {
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

