import { useState, useEffect, useRef } from 'react'
import { Card, CardContent } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import type { ReasoningStep } from '../utils/reasoningSteps'
import type { ExecutionState, StreamEvent } from '../types/execution'
import { SummaryBar } from './StatusWindow/SummaryBar'
import { ProgressIndicator } from './StatusWindow/ProgressIndicator'
import { ReasoningStepCard } from './StatusWindow/ReasoningStepCard'

// Helper to build a step from a single event
function buildStepFromEvent(event: StreamEvent, stepCounterRef: React.MutableRefObject<number>): ReasoningStep | null {
  stepCounterRef.current++
  const counter = stepCounterRef.current
  
  // Create unique ID that includes event type, thread_id, and a hash of the event
  const eventHash = JSON.stringify(event).substring(0, 100).replace(/[^a-zA-Z0-9]/g, '')
  const uniqueId = `step-${event.type}-${event.thread_id}-${eventHash}-${Date.now()}-${counter}`
  
  if (event.type === 'llm_start') {
    const llmEvent = event as StreamEvent & { type: 'llm_start' }
    return {
      id: uniqueId,
      stepNumber: counter,
      title: 'Thinking...',
      status: 'thinking',
      type: 'llm_call',
      startTime: new Date(),
      endTime: null,
      tokens: null,
      model: llmEvent.model,
      inputPreview: llmEvent.input_preview,
      events: [event],
      messages: [],
    }
  } else if (event.type === 'llm_end') {
    const llmEvent = event as StreamEvent & { type: 'llm_end' }
    return {
      id: uniqueId,
      stepNumber: counter,
      title: llmEvent.tool_calls && llmEvent.tool_calls.length > 0
        ? `Calling tools: ${llmEvent.tool_calls.map((tc: { name: string }) => tc.name).join(', ')}`
        : 'Thinking',
      status: 'completed',
      type: 'llm_call',
      startTime: new Date(),
      endTime: new Date(),
      tokens: llmEvent.token_usage?.total_tokens || 
              ((llmEvent.token_usage?.input_tokens || 0) + (llmEvent.token_usage?.output_tokens || 0)) || null,
      model: llmEvent.model,
      inputPreview: llmEvent.input_preview,
      outputPreview: llmEvent.output_preview,
      events: [event],
      messages: [],
    }
  } else if (event.type === 'tool_start') {
    const toolEvent = event as StreamEvent & { type: 'tool_start' }
    return {
      id: uniqueId,
      stepNumber: counter,
      title: `Calling tool: ${toolEvent.tool_name}`,
      status: 'thinking',
      type: 'tool_call',
      startTime: new Date(),
      endTime: null,
      tokens: null,
      toolName: toolEvent.tool_name,
      toolArgs: toolEvent.args_preview,
      events: [event],
      messages: [],
    }
  } else if (event.type === 'tool_end') {
    const toolEvent = event as StreamEvent & { type: 'tool_end' }
    return {
      id: uniqueId,
      stepNumber: counter,
      title: `Calling tool: ${toolEvent.tool_name}`,
      status: 'completed',
      type: 'tool_call',
      startTime: new Date(),
      endTime: new Date(),
      tokens: null,
      toolName: toolEvent.tool_name,
      toolArgs: toolEvent.args_preview,
      toolResult: toolEvent.result_preview,
      events: [event],
      messages: [],
    }
  } else if (event.type === 'node_start') {
    const nodeEvent = event as StreamEvent & { type: 'node_start' }
    return {
      id: uniqueId,
      stepNumber: counter,
      title: `Executing: ${nodeEvent.node}`,
      status: 'thinking',
      type: 'node_execution',
      startTime: new Date(),
      endTime: null,
      tokens: null,
      node: nodeEvent.node,
      events: [event],
      messages: [],
    }
  } else if (event.type === 'node_end') {
    const nodeEvent = event as StreamEvent & { type: 'node_end' }
    return {
      id: uniqueId,
      stepNumber: counter,
      title: `Executing: ${nodeEvent.node}`,
      status: 'completed',
      type: 'node_execution',
      startTime: new Date(),
      endTime: new Date(),
      tokens: null,
      node: nodeEvent.node,
      events: [event],
      messages: [],
    }
  }
  
  return null
}

interface StatusWindowProps {
  readonly executionState: ExecutionState | null
  readonly isLoading?: boolean
}

export default function StatusWindow({ executionState, isLoading }: StatusWindowProps) {
  const [steps, setSteps] = useState<ReasoningStep[]>([])
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const prevStateRef = useRef<ExecutionState | null>(null)
  const executionIdRef = useRef<string | null>(null) // Track current thread_id to detect new chats
  const processedEventIdsRef = useRef<Set<string>>(new Set()) // Track all processed events across all messages
  const stepCounterRef = useRef<number>(0) // Global step counter across all messages in thread

  useEffect(() => {
    // Extract thread_id from execution state (same thread_id = same chat, append events)
    // Different thread_id = new chat, clear and start fresh
    let currentThreadId: string | null = null
    if (executionState?.streamEvents && Array.isArray(executionState.streamEvents)) {
      for (const event of executionState.streamEvents) {
        if (event && typeof event === 'object' && 'thread_id' in event) {
          const tid = (event as { thread_id: string }).thread_id
          if (tid) {
            currentThreadId = tid
            break
          }
        }
      }
    }

    // Detect if execution just finished (executionState goes from having data to null)
    const executionStateBecameNull = prevStateRef.current !== null && executionState === null

    if (!executionState) {
      // Don't clear steps when execution finishes - keep them for viewing
      if (executionStateBecameNull) {
        // Mark all steps as completed if they're still thinking
        setSteps(prevSteps => {
          return prevSteps.map(step => {
            if (step.status === 'thinking') {
              return {
                ...step,
                status: 'completed' as const,
                endTime: step.endTime || new Date(),
              }
            }
            return step
          })
        })
      }
      // Don't update prevStateRef when executionState is null - keep the last state
      // Steps are preserved in React state, so they'll remain visible
      return
    }

    const prev = prevStateRef.current
    const current = executionState

    // Only clear steps if this is a NEW CHAT (different thread_id)
    // Same thread_id = same chat = append events, don't clear
    const isNewChat = currentThreadId !== null && 
                      executionIdRef.current !== null &&
                      executionIdRef.current !== currentThreadId

    // Check if execution just finished (next nodes went from having items to empty)
    const executionJustFinished = (prev?.next && prev.next.length > 0) && 
                                  (current.next && current.next.length === 0)

    // Build only NEW steps from events we haven't processed yet
    // This ensures we append, not overwrite
    const newStepsToAdd: ReasoningStep[] = []
    
    if (current.streamEvents && Array.isArray(current.streamEvents)) {
      for (const event of current.streamEvents) {
        // Create unique event ID that includes timestamp/position to make it unique across messages
        const eventId = `${event.type}-${event.thread_id}-${JSON.stringify(event).substring(0, 100)}-${current.streamEvents.indexOf(event)}`
        
        // Skip if we've already processed this event
        if (processedEventIdsRef.current.has(eventId)) {
          continue
        }
        
        // Mark as processed
        processedEventIdsRef.current.add(eventId)
        
        // Build step from this event
        const stepFromEvent = buildStepFromEvent(event, stepCounterRef)
        if (stepFromEvent) {
          newStepsToAdd.push(stepFromEvent)
        }
      }
    }

    // Update steps - use functional update to avoid dependency on steps
    setSteps(prevSteps => {
      // If this is a new chat (different thread_id), clear everything and start fresh
      if (isNewChat) {
        executionIdRef.current = currentThreadId
        processedEventIdsRef.current.clear()
        stepCounterRef.current = 0
        return newStepsToAdd
      }

      // If this is the first execution (no previous thread ID), set it
      if (executionIdRef.current === null && currentThreadId) {
        executionIdRef.current = currentThreadId
      }

      // Same thread_id = same chat = append new steps, never clear existing ones
      const merged = [...prevSteps, ...newStepsToAdd]
      
      // If execution just finished, mark all thinking steps as completed
      if (executionJustFinished) {
        return merged.map(step => {
          if (step.status === 'thinking') {
            return {
              ...step,
              status: 'completed' as const,
              endTime: step.endTime || new Date(),
            }
          }
          return step
        })
      }
      
      return merged
    })

    // Update previous state reference
    try {
      const serialized = JSON.stringify(current)
      const parsed = JSON.parse(serialized) as ExecutionState
      prevStateRef.current = parsed
    } catch {
      // If JSON serialization fails, just store reference (less ideal but safe)
      prevStateRef.current = current
    }

    // Auto-scroll to bottom when steps are updated (only if not at top)
    requestAnimationFrame(() => {
      if (scrollAreaRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = scrollAreaRef.current
        // Only auto-scroll if user is near the bottom (within 100px)
        if (scrollHeight - scrollTop - clientHeight < 100) {
          scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight
        }
      }
    })
  }, [executionState, isLoading])

  // Find current step (first step that's not completed)
  const currentStepIndex = steps.findIndex(s => s.status !== 'completed')
  const activeStepIndex = currentStepIndex >= 0 ? currentStepIndex : steps.length - 1

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardContent className="flex-1 min-h-0 p-0 flex flex-col">
        {steps.length > 0 && (
          <>
            <SummaryBar steps={steps} />
            <ProgressIndicator steps={steps} currentStepIndex={activeStepIndex} />
          </>
        )}
        <ScrollArea className="flex-1" ref={scrollAreaRef}>
          <div className="p-4 space-y-3">
            {steps.length === 0 ? (
              <div className="text-sm text-muted-foreground py-8 text-center">
                No execution events yet
              </div>
            ) : (
              steps.map((step) => (
                <ReasoningStepCard key={step.id} step={step} />
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
