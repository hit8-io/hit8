import * as React from "react"
import { LogOut } from "lucide-react"
import { Popover } from "./ui/popover"
import { Button } from "./ui/button"
import { cn } from "@/lib/utils"
import type { User } from "../types"
import { useUserConfig } from "../hooks/useUserConfig"
import { useAuth } from "../hooks/useAuth"

interface UserMenuProps {
  readonly user: User
  readonly onLogout: () => void
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
  const { idToken } = useAuth()
  const { config, loading: configLoading, selection, setSelection, isSelectionValid } = useUserConfig(idToken)

  const handleOrgChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newOrg = e.target.value
    if (config && config.projects[newOrg] && typeof config.projects[newOrg] === 'object') {
      // Auto-select first project for the new org
      const projectKeys = Object.keys(config.projects[newOrg])
      if (projectKeys.length > 0) {
        setSelection(newOrg, projectKeys[0])
      }
    }
  }

  const handleProjectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (selection) {
      setSelection(selection.org, e.target.value)
    }
  }

  // Extract project list from nested structure: projects[org] is an object with project keys
  const availableProjects = selection && config && config.projects[selection.org] && typeof config.projects[selection.org] === 'object'
    ? Object.keys(config.projects[selection.org])
    : []

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
              "w-10 h-10 min-w-[40px] min-h-[40px]",
              "bg-muted border-2 border-border",
              "shadow-sm"
            )}
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
        className="w-64"
      >
      <div className="p-2">
        <div className="px-2 py-1.5 text-sm font-medium text-foreground">{user.name}</div>
        <div className="px-2 py-1 text-xs text-muted-foreground truncate">
          {user.email}
        </div>
        {config && (
          <div className="px-2 py-1 text-xs text-muted-foreground">
            Account: {config.account}
          </div>
        )}
        <div className="h-px bg-border my-2" />
        
        {(() => {
          if (configLoading) {
            return <div className="px-2 py-2 text-xs text-muted-foreground">Loading config...</div>
          }
          
          if (!config) {
            return (
              <div className="px-2 py-2 text-xs text-destructive">
                Failed to load configuration
              </div>
            )
          }
          
          return (
            <div className="space-y-2">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1 px-2">
                  Organization
                </label>
                <select
                  value={selection?.org || ""}
                  onChange={handleOrgChange}
                  className={cn(
                    "w-full px-2 py-1.5 text-sm rounded-md border border-border",
                    "bg-background text-foreground",
                    "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                  )}
                >
                  <option value="">Select org...</option>
                  {Object.keys(config.projects).map((org) => (
                    <option key={org} value={org}>
                      {org}
                    </option>
                  ))}
                </select>
              </div>
              
              {selection && availableProjects.length > 0 && (
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1 px-2">
                    Project
                  </label>
                  <select
                    value={selection.project}
                    onChange={handleProjectChange}
                    className={cn(
                      "w-full px-2 py-1.5 text-sm rounded-md border border-border",
                      "bg-background text-foreground",
                      "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                    )}
                  >
                    {availableProjects.map((project) => (
                      <option key={project} value={project}>
                        {project}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              
              {!isSelectionValid && selection && (
                <div className="px-2 py-1 text-xs text-destructive">
                  Please select a valid org and project
                </div>
              )}
            </div>
          )
        })()}
        
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
