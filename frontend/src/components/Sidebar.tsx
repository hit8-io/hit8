import * as React from "react"
import { MessageSquare } from "lucide-react"
import { UserMenu } from "./UserMenu"
import { MenuItem } from "./MenuItem"
import { cn } from "@/lib/utils"
import type { User } from "../types"

interface SidebarProps {
  readonly user: User
  readonly onLogout: () => void
}

export function Sidebar({ user, onLogout }: SidebarProps) {
  // Sidebar is always minimal
  const [iconError, setIconError] = React.useState(false)

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

        <MenuItem
          icon={MessageSquare}
          label="Chat"
          active={true}
          showLabel={false}
        />

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

