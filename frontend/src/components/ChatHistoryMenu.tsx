import * as React from "react"
import { useNavigate } from "react-router-dom"
import { MessageSquare } from "lucide-react"
import { Popover } from "./ui/popover"
import { cn } from "@/lib/utils"
import { getChatHistory } from "../utils/api"
import type { ChatThread } from "../types"
import { useAuth } from "../hooks/useAuth"
import { logError } from "../utils/errorHandling"

interface ChatHistoryMenuProps {
  currentThreadId?: string | null
  isActive?: boolean
  onTabChange?: () => void
}

export function ChatHistoryMenu({ currentThreadId, isActive, onTabChange }: ChatHistoryMenuProps) {
  const [open, setOpen] = React.useState(false)
  const [threads, setThreads] = React.useState<ChatThread[]>([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const { idToken } = useAuth()
  const navigate = useNavigate()

  // Fetch threads when popover opens
  React.useEffect(() => {
    if (!open || !idToken) return

    setLoading(true)
    setError(null)
    
    getChatHistory(idToken)
      .then((fetchedThreads) => {
        setThreads(fetchedThreads)
        setLoading(false)
      })
      .catch((err) => {
        const errorMessage = err instanceof Error ? err.message : "Failed to load chat history"
        setError(errorMessage)
        setLoading(false)
        logError("ChatHistoryMenu: Failed to fetch chat history", err)
      })
  }, [open, idToken])

  const handleThreadClick = (threadId: string) => {
    setOpen(false)
    navigate(`/chat/${threadId}`)
  }

  return (
    <div className="relative">
      <Popover
        open={open}
        onOpenChange={setOpen}
        trigger={
          <button
            onClick={() => {
              if (onTabChange) onTabChange();
            }}
            className={cn(
              "w-full flex items-center justify-center gap-3 px-3 py-2 rounded-md transition-colors",
              "hover:bg-accent hover:text-accent-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground"
            )}
            aria-label="Chat"
            title="Chat"
          >
            <MessageSquare className="h-5 w-5 flex-shrink-0" />
          </button>
        }
        side="bottom"
        align="start"
        className="w-64 max-h-[400px]"
      >
        <div className="p-2">
          <div className="px-2 py-1.5 text-sm font-medium text-foreground">Recent Chats</div>
          <div className="h-px bg-border my-2" />
          
          {loading ? (
            <div className="px-2 py-2 text-xs text-muted-foreground">Loading...</div>
          ) : error ? (
            <div className="px-2 py-2 text-xs text-destructive">{error}</div>
          ) : threads.length === 0 ? (
            <div className="px-2 py-2 text-xs text-muted-foreground">No chats yet</div>
          ) : (
            <div className="max-h-[300px] overflow-y-auto">
              {threads.map((thread) => {
                const isActive = currentThreadId === thread.thread_id
                const displayTitle = thread.title || "Untitled"
                
                return (
                  <button
                    key={thread.thread_id}
                    onClick={() => handleThreadClick(thread.thread_id)}
                    className={cn(
                      "w-full text-left px-2 py-1.5 rounded-md text-sm",
                      "hover:bg-accent hover:text-accent-foreground transition-colors",
                      "truncate",
                      isActive && "bg-accent text-accent-foreground font-medium"
                    )}
                    title={displayTitle}
                  >
                    {displayTitle}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </Popover>
    </div>
  )
}
