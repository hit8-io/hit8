import type { ReasoningStep } from '../../utils/reasoningSteps'

interface ProgressIndicatorProps {
  steps: ReasoningStep[]
  currentStepIndex: number
}

export function ProgressIndicator({ steps, currentStepIndex }: ProgressIndicatorProps) {
  const totalSteps = steps.length
  const completedSteps = steps.filter(s => s.status === 'completed').length
  const progress = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0

  if (totalSteps === 0) {
    return null
  }

  return (
    <div className="px-4 py-2 border-b bg-muted/20">
      <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
        <span>Step {currentStepIndex + 1} of {totalSteps}</span>
        <span>{completedSteps} completed</span>
      </div>
      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  )
}
