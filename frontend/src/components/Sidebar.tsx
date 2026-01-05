import * as React from "react"
import { MessageSquare } from "lucide-react"
import { UserMenu } from "./UserMenu"
import { MenuItem } from "./MenuItem"
import { cn } from "@/lib/utils"

interface SidebarProps {
  user: {
    id: string
    email: string
    name: string
    picture: string
  }
  onLogout: () => void
}

export function Sidebar({ user, onLogout }: SidebarProps) {
  // Sidebar is always minimal (collapsed)
  const collapsed = true
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
        <UserMenu user={user} onLogout={onLogout} collapsed={collapsed} />
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
        <div className="px-3 py-2 flex items-center justify-center">
          {!iconError ? (
            <img
              src="/hit8-icon.png"
              alt="Hit8"
              className="h-8 w-8 object-contain"
              onError={() => setIconError(true)}
            />
          ) : (
            <div className="flex items-center justify-center h-8 w-8 rounded bg-muted text-muted-foreground text-xs font-semibold">
              H8
            </div>
          )}
        </div>
      </nav>
    </aside>
  )
}

