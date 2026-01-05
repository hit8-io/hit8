import * as React from "react"
import { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface MenuItemProps {
  icon?: LucideIcon
  label?: string
  active?: boolean
  onClick?: () => void
  children?: React.ReactNode // For future sub-menus
  className?: string
  showLabel?: boolean // Control label visibility (for collapsed sidebar)
}

export function MenuItem({
  icon: Icon,
  label,
  active = false,
  onClick,
  children,
  className,
  showLabel = true,
}: MenuItemProps) {
  const [showSubMenu, setShowSubMenu] = React.useState(false)

  const handleMouseEnter = () => {
    if (children) {
      setShowSubMenu(true)
    }
  }

  const handleMouseLeave = () => {
    if (children) {
      // Delay closing to allow moving to sub-menu
      setTimeout(() => {
        setShowSubMenu(false)
      }, 100)
    }
  }

  return (
    <div className="relative">
      <button
        onClick={onClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className={cn(
          "w-full flex items-center gap-3 px-3 py-2 rounded-md transition-colors",
          "hover:bg-accent hover:text-accent-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          active && "bg-accent text-accent-foreground",
          !showLabel && "justify-center",
          className
        )}
        aria-label={label}
        title={!showLabel ? label : undefined}
      >
        {Icon && <Icon className="h-5 w-5 flex-shrink-0" />}
        {showLabel && label && (
          <span className="text-sm font-medium truncate">{label}</span>
        )}
      </button>
      {children && showSubMenu && (
        <div
          className="absolute left-full top-0 ml-2 min-w-[12rem] rounded-md border bg-popover p-1 text-popover-foreground shadow-md z-50"
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {children}
        </div>
      )}
    </div>
  )
}

