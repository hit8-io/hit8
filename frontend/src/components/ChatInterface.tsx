import { useState } from 'react'
import { Send, LogOut } from 'lucide-react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Card } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import { getApiHeaders } from '../utils/api'

interface Message {
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
  onExecutionStateUpdate?: (state: unknown) => void
}

const API_URL = import.meta.env.VITE_API_URL

export default function ChatInterface({ token, user: _user, onLogout, onChatStateChange, onExecutionStateUpdate }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [_visitedNodes, setVisitedNodes] = useState<string[]>([]) // Track visited nodes for history
  
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

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = { role: 'user', content: input }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    // Generate thread_id on frontend so we can start polling immediately
    const threadId = crypto.randomUUID()

    // Notify parent that chat is active with thread_id for immediate polling
    onChatStateChange?.(true, threadId)

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

      // Read the stream
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body reader available')
      }

      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)) // Remove 'data: ' prefix
              
              // Handle different event types
              if (data.type === 'node_start') {
                // Node is starting - mark as active
                const nodeName = data.node
                setVisitedNodes(prev => {
                  onExecutionStateUpdate?.({
                    next: [nodeName],
                    values: {},
                    history: prev.map(node => ({ node })),
                  })
                  return prev
                })
              } else if (data.type === 'node_end') {
                // Node completed - add to visited nodes and mark as inactive
                const nodeName = data.node
                setVisitedNodes(prev => {
                  const updated = prev.includes(nodeName) ? prev : [...prev, nodeName]
                  onExecutionStateUpdate?.({
                    next: [],
                    values: {},
                    history: updated.map(node => ({ node })),
                  })
                  return updated
                })
              } else if (data.type === 'graph_end') {
                // Graph execution completed - get final response
                finalResponse = data.response || ''
                console.log('Graph end received, response:', finalResponse)
                // Final state update with all visited nodes
                setVisitedNodes(prev => {
                  onExecutionStateUpdate?.({
                    next: [],
                    values: {},
                    history: prev.map(node => ({ node })),
                  })
                  return prev
                })
              } else if (data.type === 'error') {
                hasError = true
                const errorMessage = data.error && data.error.trim() ? data.error : 'Unknown error occurred'
                console.error('SSE error received:', errorMessage, data)
                throw new Error(errorMessage)
              }
            } catch (parseError) {
              console.error('Failed to parse SSE data:', parseError, line)
            }
          }
        }
      }

      // Add final assistant message
      console.log('Streaming complete, finalResponse:', finalResponse, 'hasError:', hasError)
      if (finalResponse && !hasError) {
        const assistantMessage: Message = {
          role: 'assistant',
          content: finalResponse,
        }
        setMessages((prev) => [...prev, assistantMessage])
      } else if (!finalResponse && !hasError) {
        // If no response was received, show an error
        console.error('No response received from server')
        const errorMsg: Message = {
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
      const errorMsg: Message = {
        role: 'assistant',
        content: errorMessage,
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
      // Reset visited nodes for next conversation
      setVisitedNodes([])
      // Keep chat active briefly to allow final state update, then deactivate
      setTimeout(() => {
        onChatStateChange?.(false)
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
            {messages.map((message, index) => (
              <div
                key={index}
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
                  {message.content}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-muted text-muted-foreground rounded-lg p-3">
                  Thinking...
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

