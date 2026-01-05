import { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface MenuItemProps {
  readonly icon?: LucideIcon
  readonly label?: string
  readonly active?: boolean
  readonly onClick?: () => void
  readonly className?: string
  readonly showLabel?: boolean
}

export function MenuItem({
  icon: Icon,
  label,
  active = false,
  onClick,
  className,
  showLabel = true,
}: MenuItemProps) {
  return (
    <button
      onClick={onClick}
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
  )
}

