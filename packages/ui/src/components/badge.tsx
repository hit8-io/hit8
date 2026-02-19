import * as React from "react"
import { cn } from "../lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'thinking' | 'completed' | 'error'
}

const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant = 'default', ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium transition-colors",
          {
            "bg-primary/10 text-primary": variant === 'default',
            "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400": variant === 'thinking',
            "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400": variant === 'completed',
            "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400": variant === 'error',
          },
          className
        )}
        {...props}
      />
    )
  }
)
Badge.displayName = "Badge"

export { Badge }
