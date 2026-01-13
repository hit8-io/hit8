import { Brain, Wrench, Clock } from 'lucide-react'
import type { ReasoningStep } from '../../utils/reasoningSteps'

interface SummaryBarProps {
  steps: ReasoningStep[]
}

export function SummaryBar({ steps }: SummaryBarProps) {
  const totalTokens = steps.reduce((sum, step) => sum + (step.tokens || 0), 0)
  const toolSteps = steps.filter(s => s.type === 'tool_call')
  const uniqueTools = new Set(toolSteps.map(s => s.toolName).filter(Boolean))
  
  // Calculate duration (from first step start to last step end)
  let duration: number | null = null
  if (steps.length > 0) {
    const firstStart = steps[0].startTime?.getTime()
    const lastEnd = steps[steps.length - 1].endTime?.getTime() || steps[steps.length - 1].startTime?.getTime()
    if (firstStart && lastEnd) {
      duration = Math.round((lastEnd - firstStart) / 1000) // seconds
    }
  }

  return (
    <div className="flex items-center gap-4 px-4 py-2 border-b bg-muted/30 text-sm">
      {totalTokens > 0 && (
        <div className="flex items-center gap-1.5">
          <Brain className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">{totalTokens.toLocaleString()} tokens</span>
        </div>
      )}
      {uniqueTools.size > 0 && (
        <div className="flex items-center gap-1.5">
          <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">{uniqueTools.size} tool{uniqueTools.size !== 1 ? 's' : ''}</span>
        </div>
      )}
      {duration !== null && (
        <div className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">{duration}s</span>
        </div>
      )}
    </div>
  )
}
