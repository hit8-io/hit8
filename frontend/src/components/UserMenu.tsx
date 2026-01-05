import * as React from "react"
import { LogOut } from "lucide-react"
import { Popover } from "./ui/popover"
import { Button } from "./ui/button"
import { cn } from "@/lib/utils"

interface UserMenuProps {
  user: {
    id: string
    email: string
    name: string
    picture: string
  }
  onLogout: () => void
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  }
  return name.substring(0, 2).toUpperCase()
}

export function UserMenu({ user, onLogout }: UserMenuProps) {
  const [open, setOpen] = React.useState(false)
  const [imageError, setImageError] = React.useState(false)

  return (
    <div className="relative">
      <Popover
        open={open}
        onOpenChange={setOpen}
        trigger={
          <div
            className={cn(
              "flex items-center justify-center rounded-full overflow-hidden",
              "hover:ring-2 hover:ring-ring transition-all cursor-pointer",
              "w-10 h-10",
              "bg-muted border-2 border-border",
              "shadow-sm"
            )}
            style={{ 
              minWidth: '40px', 
              minHeight: '40px',
              display: 'flex',
              visibility: 'visible',
              opacity: 1,
            }}
          >
            {user.picture && !imageError ? (
              <img
                src={user.picture}
                alt={user.name}
                className="w-full h-full object-cover block"
                onError={() => setImageError(true)}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-xs font-semibold text-foreground">
                {getInitials(user.name)}
              </div>
            )}
          </div>
        }
        side="bottom"
        align="start"
        className="w-56"
      >
      <div className="p-2">
        <div className="px-2 py-1.5 text-sm font-medium text-foreground">{user.name}</div>
        <div className="px-2 py-1 text-xs text-muted-foreground truncate">
          {user.email}
        </div>
        <div className="h-px bg-border my-2" />
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
          onClick={() => {
            setOpen(false)
            onLogout()
          }}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </Popover>
    </div>
  )
}

