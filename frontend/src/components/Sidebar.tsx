import * as React from "react"
import { useParams } from "react-router-dom"
import { FileText } from "lucide-react"
import { UserMenu } from "./UserMenu"
import { ChatHistoryMenu } from "./ChatHistoryMenu"
import { cn } from "@/lib/utils"
import type { User } from "../types"

interface SidebarProps {
  readonly user: User
  readonly onLogout: () => void
  readonly activeTab: 'chat' | 'reports'
  readonly onTabChange: (tab: 'chat' | 'reports') => void
  readonly availableFlows: string[]
}

export function Sidebar({ user, onLogout, activeTab, onTabChange, availableFlows }: SidebarProps) {
  // Sidebar is always minimal
  const [iconError, setIconError] = React.useState(false)
  const { threadId } = useParams<{ threadId: string }>()
  
  // Simple, direct boolean checks - no memoization needed
  const hasChatFlow = availableFlows.includes('chat')
  const hasReportFlow = availableFlows.includes('report')

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 h-screen bg-card border-r border-border",
        "flex flex-col z-40 w-16"
      )}
    >
      {/* User Menu */}
      <div className="p-3 border-b border-border flex items-center justify-center">
        <UserMenu user={user} onLogout={onLogout} />
      </div>

      {/* Navigation Items */}
      <nav className="flex-1 overflow-y-auto p-2 space-y-1">
        {/* Divider */}
        <div className="h-px bg-border my-2" />

        {hasChatFlow && (
          <ChatHistoryMenu 
            currentThreadId={threadId} 
            onTabChange={() => onTabChange('chat')}
            isActive={activeTab === 'chat'}
          />
        )}

        {hasReportFlow && (
          <button
            onClick={() => onTabChange('reports')}
            className={cn(
              "w-full flex items-center justify-center gap-3 px-3 py-2 rounded-md transition-colors",
              "hover:bg-accent hover:text-accent-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              activeTab === 'reports' ? "bg-accent text-accent-foreground" : "text-muted-foreground"
            )}
            aria-label="Reports"
            title="Reports"
          >
            <FileText className="h-5 w-5 flex-shrink-0" />
          </button>
        )}

        {/* Divider */}
        <div className="h-px bg-border my-2" />

        {/* Hit8 Logo/Brand */}
        <div className="p-2 flex items-center justify-center">
          {!iconError ? (
            <img
              src="/hit8-icon.png"
              alt="Hit8"
              className="object-contain"
              style={{ width: '48px', height: '48px', display: 'block', minWidth: '48px', minHeight: '48px' }}
              onError={() => setIconError(true)}
            />
          ) : (
            <div className="w-12 h-12 min-w-[48px] min-h-[48px] flex items-center justify-center rounded bg-muted text-muted-foreground text-sm font-semibold">
              H8
            </div>
          )}
        </div>
      </nav>
    </aside>
  )
}

