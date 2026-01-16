import * as React from "react"

interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: React.ReactNode
}

interface DialogContentProps {
  children: React.ReactNode
  className?: string
}

interface DialogHeaderProps {
  children: React.ReactNode
}

interface DialogTitleProps {
  children: React.ReactNode
}

interface DialogDescriptionProps {
  children: React.ReactNode
}

export function Dialog({ open, onOpenChange, children }: DialogProps) {
  if (!open) return null

  // Handle Escape key to close dialog
  React.useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onOpenChange(false)
      }
    }

    if (open) {
      document.addEventListener('keydown', handleEscape)
      return () => {
        document.removeEventListener('keydown', handleEscape)
      }
    }
  }, [open, onOpenChange])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div 
        className="fixed inset-0 bg-black/50" 
        onClick={() => onOpenChange(false)}
      />
      <div className="relative z-50">
        {children}
      </div>
    </div>
  )
}

export function DialogContent({ children, className = "" }: DialogContentProps) {
  return (
    <div className={`bg-white dark:bg-gray-900 border rounded-lg shadow-lg max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col ${className}`}>
      {children}
    </div>
  )
}

export function DialogHeader({ children }: DialogHeaderProps) {
  return (
    <div className="px-6 py-4 border-b">
      {children}
    </div>
  )
}

export function DialogTitle({ children }: DialogTitleProps) {
  return (
    <h2 className="text-lg font-semibold">
      {children}
    </h2>
  )
}

export function DialogDescription({ children }: DialogDescriptionProps) {
  return (
    <p className="text-sm text-muted-foreground mt-1">
      {children}
    </p>
  )
}

export function DialogClose({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100 text-foreground"
    >
      <span className="sr-only">Close</span>
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  )
}
