import { useRef, useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Send, Maximize2, Minimize2, Paperclip, X, Plus, MessageSquare } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from './ui/button'
import { useChatStream } from '../utils/state'
import { Input } from './ui/input'
import { Card } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import type { ExecutionState } from '../types'
import { getAvailableModels } from '../utils/api'

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

const API_URL = import.meta.env.VITE_API_URL

export default function ChatInterface({ token, threadId, onChatStateChange, onExecutionStateUpdate, isExpanded = false, onToggleExpand, org, project }: ChatInterfaceProps) {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const [availableModels, setAvailableModels] = useState<string[]>([])
  
  // Fetch available models on mount
  useEffect(() => {
    getAvailableModels(token)
      .then((models) => {
        setAvailableModels(models)
        if (models.length > 0) {
          setSelectedModel((prev) => prev || models[0])
        }
      })
      .catch((error) => {
        console.error('Failed to fetch available models:', error)
      })
  }, [token])
  
  const {
    messages,
    input,
    setInput,
    isLoading,
    streamingContent,
    selectedFiles,
    setSelectedFiles,
    handleSend,
  } = useChatStream({
    apiUrl: API_URL || '',
    threadId,
    token,
    org,
    project,
    onExecutionStateUpdate,
    onChatStateChange,
    model: selectedModel || undefined,
  })

  const handleNewChat = () => {
    navigate('/')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend().catch(console.error)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    // Filter to only allowed file types
    const allowedExtensions = ['.docx', '.xlsx', '.pptx', '.pdf', '.html', '.txt', '.csv', '.json', '.xml', '.epub']
    const validFiles = files.filter((file: File) => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      return allowedExtensions.includes(ext)
    })
    setSelectedFiles((prev: File[]) => [...prev, ...validFiles])
    // Reset input to allow selecting same file again
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const removeFile = (index: number) => {
    setSelectedFiles((prev: File[]) => prev.filter((_: File, i: number) => i !== index))
  }

  const handleFileButtonClick = () => {
    fileInputRef.current?.click()
  }

  return (
    <div className="flex flex-col h-full">
      <Card className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex justify-between items-center">
          <h1 className="text-lg font-bold flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Chat
          </h1>
          <div className="flex items-center gap-4">
            {availableModels.length > 0 && (
              <div className="flex items-center gap-2">
                <label htmlFor="model-select" className="text-sm text-muted-foreground">
                  Model:
                </label>
                <select
                  id="model-select"
                  value={selectedModel || ''}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  disabled={isLoading}
                  className="px-2 py-1 text-sm border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {availableModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </div>
            )}
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
              onClick={() => {
                handleSend().catch(console.error)
              }}
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

