import * as React from "react"
import { cn } from "@/lib/utils"

interface PopoverProps {
  children: React.ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
  trigger: React.ReactNode
  align?: "start" | "center" | "end"
  side?: "top" | "right" | "bottom" | "left"
  className?: string
}

export function Popover({
  children,
  open: controlledOpen,
  onOpenChange,
  trigger,
  align = "start",
  side = "bottom",
  className,
}: PopoverProps) {
  const [internalOpen, setInternalOpen] = React.useState(false)
  const triggerRef = React.useRef<HTMLDivElement>(null)
  const popoverRef = React.useRef<HTMLDivElement>(null)
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen

  const setOpen = React.useCallback(
    (newOpen: boolean) => {
      if (!isControlled) {
        setInternalOpen(newOpen)
      }
      onOpenChange?.(newOpen)
    },
    [isControlled, onOpenChange]
  )

  // Handle click outside
  React.useEffect(() => {
    if (!open) return

    const handleClickOutside = (event: MouseEvent) => {
      if (
        triggerRef.current &&
        popoverRef.current &&
        !triggerRef.current.contains(event.target as Node) &&
        !popoverRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false)
      }
    }

    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleEscape)

    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleEscape)
    }
  }, [open, setOpen])

  // Calculate position
  const [position, setPosition] = React.useState({ top: 0, left: 0 })

  React.useEffect(() => {
    if (!open || !triggerRef.current || !popoverRef.current) return

    const triggerRect = triggerRef.current.getBoundingClientRect()
    const popoverRect = popoverRef.current.getBoundingClientRect()
    const gap = 8

    let top = 0
    let left = 0

    switch (side) {
      case "bottom":
        top = triggerRect.bottom + gap
        break
      case "top":
        top = triggerRect.top - popoverRect.height - gap
        break
      case "right":
        left = triggerRect.right + gap
        top = triggerRect.top
        break
      case "left":
        left = triggerRect.left - popoverRect.width - gap
        top = triggerRect.top
        break
    }

    switch (align) {
      case "start":
        if (side === "top" || side === "bottom") {
          left = triggerRect.left
        } else {
          // For left/right, align top
          if (side === "right" || side === "left") {
            // Already set above
          }
        }
        break
      case "center":
        if (side === "top" || side === "bottom") {
          left = triggerRect.left + triggerRect.width / 2 - popoverRect.width / 2
        } else {
          top = triggerRect.top + triggerRect.height / 2 - popoverRect.height / 2
        }
        break
      case "end":
        if (side === "top" || side === "bottom") {
          left = triggerRect.right - popoverRect.width
        } else {
          top = triggerRect.bottom - popoverRect.height
        }
        break
    }

    setPosition({ top, left })
  }, [open, align, side])

  return (
    <div className="relative inline-block">
      <div
        ref={triggerRef}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => {
          // Delay closing on mouse leave to allow moving to popover
          setTimeout(() => {
            if (!popoverRef.current?.matches(":hover")) {
              setOpen(false)
            }
          }, 100)
        }}
        onClick={() => setOpen(!open)}
        style={{ display: 'inline-block' }}
      >
        {trigger}
      </div>
      {open && (
        <div
          ref={popoverRef}
          className={cn(
            "fixed z-50 min-w-[8rem] rounded-md border shadow-lg",
            "bg-white dark:bg-gray-900",
            className
          )}
          style={{
            top: `${position.top}px`,
            left: `${position.left}px`,
            backgroundColor: 'hsl(var(--card) / 1)',
            color: 'hsl(var(--card-foreground) / 1)',
            borderColor: 'hsl(var(--border) / 1)',
            opacity: 1,
            backdropFilter: 'none',
          }}
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  )
}

