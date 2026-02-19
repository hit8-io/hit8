import { Brain, Wrench, CheckCircle2, Loader2 } from 'lucide-react'
import { Badge } from '@hit8/ui'
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '../ui/accordion'
import type { ReasoningStep } from '../../utils/reasoningSteps'
import { formatArgsPreview } from '../../utils/formatStatus'

interface ReasoningStepCardProps {
  step: ReasoningStep
}

function getStepIcon(type: ReasoningStep['type'], status: ReasoningStep['status']) {
  if (status === 'thinking') {
    return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
  }
  if (status === 'completed') {
    return <CheckCircle2 className="h-4 w-4 text-green-500" />
  }
  if (status === 'error') {
    return <CheckCircle2 className="h-4 w-4 text-red-500" />
  }
  
  switch (type) {
    case 'thinking':
    case 'llm_call':
      return <Brain className="h-4 w-4 text-muted-foreground" />
    case 'tool_call':
      return <Wrench className="h-4 w-4 text-muted-foreground" />
    default:
      return <div className="h-4 w-4 rounded-full bg-muted" />
  }
}

function getStatusBadgeVariant(status: ReasoningStep['status']): 'thinking' | 'completed' | 'error' {
  return status
}

export function ReasoningStepCard({ step }: ReasoningStepCardProps) {
  const hasDetails = step.toolArgs || step.toolResult || step.outputPreview || step.events.length > 0

  return (
    <div className="border rounded-lg bg-card hover:bg-accent/50 transition-colors">
      <div className="p-3">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 mt-0.5">
            {getStepIcon(step.type, step.status)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-medium text-muted-foreground">
                [{step.stepNumber}]
              </span>
              <span className="text-sm font-medium">{step.title}</span>
              <Badge variant={getStatusBadgeVariant(step.status)} className="ml-auto">
                {step.status}
              </Badge>
            </div>
            
            {/* Primary content */}
            <div className="text-sm text-muted-foreground space-y-1">
              {step.type === 'tool_call' && step.toolArgs && (
                <div className="truncate">
                  <span className="font-medium">{step.toolName}:</span>{' '}
                  <span className="font-mono text-xs">
                    {formatArgsPreview(step.toolArgs)}
                  </span>
                </div>
              )}
              
              {step.type === 'llm_call' && step.inputPreview && (
                <div className="truncate text-xs">
                  {step.inputPreview.substring(0, 100)}
                  {step.inputPreview.length > 100 ? '...' : ''}
                </div>
              )}
              
              {step.tokens && (
                <div className="text-xs">
                  Tokens: {step.tokens.toLocaleString()}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Expandable details */}
      {hasDetails && (
        <Accordion type="single">
          <AccordionItem value={`details-${step.id}`} className="border-0 border-t">
            <AccordionTrigger
              value={`details-${step.id}`}
              className="py-2 px-3 text-xs"
            >
              <span>Details</span>
            </AccordionTrigger>
            <AccordionContent value={`details-${step.id}`} className="px-3 pb-3">
              <div className="space-y-2 text-xs">
                {step.toolArgs && (
                  <div>
                    <div className="font-medium mb-1">Arguments:</div>
                    <pre className="p-2 bg-muted rounded text-xs font-mono overflow-x-auto">
                      {typeof step.toolArgs === 'string' 
                        ? (step.toolArgs.length > 500 
                            ? step.toolArgs.substring(0, 500) + '...' 
                            : step.toolArgs)
                        : JSON.stringify(step.toolArgs, null, 2)}
                    </pre>
                  </div>
                )}
                
                {step.toolResult && (
                  <div>
                    <div className="font-medium mb-1">Result:</div>
                    <pre className="p-2 bg-muted rounded text-xs font-mono overflow-x-auto max-h-40 overflow-y-auto">
                      {typeof step.toolResult === 'string' 
                        ? (step.toolResult.length > 1000 
                            ? step.toolResult.substring(0, 1000) + '...' 
                            : step.toolResult)
                        : JSON.stringify(step.toolResult, null, 2)}
                    </pre>
                  </div>
                )}
                
                {step.outputPreview && (
                  <div>
                    <div className="font-medium mb-1">Output:</div>
                    <div className="p-2 bg-muted rounded text-xs max-h-40 overflow-y-auto">
                      {step.outputPreview}
                    </div>
                  </div>
                )}
                
                {step.startTime && (
                  <div className="text-muted-foreground">
                    Started: {step.startTime.toLocaleTimeString()}
                    {step.endTime && (
                      <span>
                        {' • '}Duration: {Math.round((step.endTime.getTime() - step.startTime.getTime()) / 1000)}s
                      </span>
                    )}
                  </div>
                )}
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}
    </div>
  )
}
