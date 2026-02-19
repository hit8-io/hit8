import type { ExecutionState, StreamEvent, Message } from '../types/execution'
import { extractToolCalls, extractTokenCount } from './formatStatus'

export type StepStatus = 'thinking' | 'completed' | 'error'
export type StepType = 'thinking' | 'tool_call' | 'llm_call' | 'node_execution' | 'state_change'

export interface ReasoningStep {
  id: string
  stepNumber: number
  title: string
  status: StepStatus
  type: StepType
  startTime: Date | null
  endTime: Date | null
  tokens: number | null
  node?: string
  toolName?: string
  toolArgs?: string
  toolResult?: string
  model?: string
  inputPreview?: string
  outputPreview?: string
  events: StreamEvent[]
  messages: Message[]
}

interface StepBuilder {
  steps: ReasoningStep[]
  currentStep: ReasoningStep | null
  stepCounter: number
  processedEventIds: Set<string>
  processedToolCallIds: Set<string>
  processedToolResultIds: Set<string>
}

function createStep(
  stepCounter: number,
  type: StepType,
  title: string,
  node?: string,
  stableId?: string
): ReasoningStep {
  // Use stable ID if provided (for tool calls, use tool name + args hash)
  // Otherwise generate based on type and counter
  const id = stableId || `step-${type}-${stepCounter}`
  
  return {
    id,
    stepNumber: stepCounter,
    title,
    status: 'thinking',
    type,
    startTime: new Date(),
    endTime: null,
    tokens: null,
    node,
    events: [],
    messages: [],
  }
}

function completeStep(step: ReasoningStep): ReasoningStep {
  return {
    ...step,
    status: 'completed',
    endTime: new Date(),
  }
}

function extractToolResultsFromMessages(messages: Message[] | undefined): Array<{ toolCallId: string; content: string; name?: string }> {
  if (!messages || !Array.isArray(messages)) return []
  
  const toolResults: Array<{ toolCallId: string; content: string; name?: string }> = []
  
  for (const msg of messages) {
    if (msg && typeof msg === 'object' && 'type' in msg) {
      const msgType = String(msg.type)
      if (msgType === 'ToolMessage') {
        const toolCallId = 'tool_call_id' in msg ? String(msg.tool_call_id) : ''
        const content = 'content' in msg ? String(msg.content) : ''
        const name = 'name' in msg ? String(msg.name) : undefined
        if (toolCallId) {
          toolResults.push({ toolCallId, content, name })
        }
      }
    }
  }
  
  return toolResults
}

export function buildReasoningSteps(
  executionState: ExecutionState | null,
  prevState: ExecutionState | null
): ReasoningStep[] {
  if (!executionState) return []

  const builder: StepBuilder = {
    steps: [],
    currentStep: null,
    stepCounter: 0,
    processedEventIds: new Set(),
    processedToolCallIds: new Set(),
    processedToolResultIds: new Set(),
  }

  const messages = executionState.values?.messages || []
  const streamEvents = executionState.streamEvents || []
  const nextNodes = executionState.next || []

  // Process stream events first (they provide real-time information)
  for (const event of streamEvents) {
    const eventId = `${event.type}-${event.thread_id}-${JSON.stringify(event).substring(0, 50)}`
    
    if (builder.processedEventIds.has(eventId)) {
      continue
    }
    builder.processedEventIds.add(eventId)

    if (event.type === 'llm_start') {
      // Complete any current step
      if (builder.currentStep) {
        builder.steps.push(completeStep(builder.currentStep))
        builder.currentStep = null
      }

      // Start new LLM step
      builder.stepCounter++
      const llmEvent = event as StreamEvent & { type: 'llm_start' }
      builder.currentStep = createStep(
        builder.stepCounter,
        'llm_call',
        `Thinking...`,
      )
      builder.currentStep.model = llmEvent.model
      builder.currentStep.inputPreview = llmEvent.input_preview
      builder.currentStep.events.push(event)

    } else if (event.type === 'llm_end') {
      if (builder.currentStep && builder.currentStep.type === 'llm_call') {
        const llmEvent = event as StreamEvent & { type: 'llm_end' }
        builder.currentStep.outputPreview = llmEvent.output_preview
        if (llmEvent.token_usage) {
          builder.currentStep.tokens = llmEvent.token_usage.total_tokens || 
            ((llmEvent.token_usage.input_tokens || 0) + (llmEvent.token_usage.output_tokens || 0)) || null
        }
        if (llmEvent.tool_calls && llmEvent.tool_calls.length > 0) {
          // Update title to show tool calls
          const toolNames = llmEvent.tool_calls.map((tc: { name: string }) => tc.name).join(', ')
          builder.currentStep.title = `Calling tools: ${toolNames}`
        } else {
          builder.currentStep.title = 'Thinking'
        }
        builder.currentStep.events.push(event)
        builder.steps.push(completeStep(builder.currentStep))
        builder.currentStep = null
      }

    } else if (event.type === 'tool_start') {
      // Complete any current step
      if (builder.currentStep) {
        builder.steps.push(completeStep(builder.currentStep))
        builder.currentStep = null
      }

      // Start new tool step
      builder.stepCounter++
      const toolEvent = event as StreamEvent & { type: 'tool_start' }
      // Create stable ID based on tool name and args
      const toolId = `tool-${toolEvent.tool_name}-${toolEvent.args_preview.substring(0, 50).replace(/[^a-zA-Z0-9]/g, '')}`
      builder.currentStep = createStep(
        builder.stepCounter,
        'tool_call',
        `Calling tool: ${toolEvent.tool_name}`,
        undefined,
        toolId
      )
      builder.currentStep.toolName = toolEvent.tool_name
      builder.currentStep.toolArgs = toolEvent.args_preview
      builder.currentStep.events.push(event)

    } else if (event.type === 'tool_end') {
      if (builder.currentStep && builder.currentStep.type === 'tool_call') {
        const toolEvent = event as StreamEvent & { type: 'tool_end' }
        builder.currentStep.toolResult = toolEvent.result_preview
        builder.currentStep.events.push(event)
        builder.steps.push(completeStep(builder.currentStep))
        builder.currentStep = null
      }

    } else if (event.type === 'node_start') {
      // Complete any current step
      if (builder.currentStep) {
        builder.steps.push(completeStep(builder.currentStep))
        builder.currentStep = null
      }

      // Start new node execution step
      builder.stepCounter++
      const nodeEvent = event as StreamEvent & { type: 'node_start' }
      builder.currentStep = createStep(
        builder.stepCounter,
        'node_execution',
        `Executing: ${nodeEvent.node}`,
        nodeEvent.node
      )
      builder.currentStep.events.push(event)

    } else if (event.type === 'node_end') {
      if (builder.currentStep && builder.currentStep.type === 'node_execution') {
        builder.currentStep.events.push(event)
        builder.steps.push(completeStep(builder.currentStep))
        builder.currentStep = null
      }
    }
  }

  // Process messages to extract tool calls and results
  const toolCalls = extractToolCalls(messages)
  const toolResults = extractToolResultsFromMessages(messages)

  // If we have tool calls but no corresponding steps, create steps for them
  for (const toolCall of toolCalls) {
    const toolCallId = toolCall.id || `${toolCall.name}-${toolCall.args.substring(0, 20)}`
    
    if (builder.processedToolCallIds.has(toolCallId)) {
      continue
    }
    builder.processedToolCallIds.add(toolCallId)

    // Check if we already have a step for this tool call
    const existingStep = builder.steps.find(
      s => s.type === 'tool_call' && s.toolName === toolCall.name
    )

    if (!existingStep) {
      // Complete any current step
      if (builder.currentStep) {
        builder.steps.push(completeStep(builder.currentStep))
        builder.currentStep = null
      }

      // Create new tool call step
      builder.stepCounter++
      // Create stable ID based on tool name and args
      const toolId = `tool-${toolCall.name}-${toolCall.args.substring(0, 50).replace(/[^a-zA-Z0-9]/g, '')}`
      const step = createStep(
        builder.stepCounter,
        'tool_call',
        `Calling tool: ${toolCall.name}`,
        undefined,
        toolId
      )
      step.toolName = toolCall.name
      step.toolArgs = toolCall.args
      
      // Find corresponding tool result
      const result = toolResults.find(tr => tr.toolCallId === toolCall.id)
      if (result) {
        step.toolResult = result.content
        step.status = 'completed'
        step.endTime = new Date()
        builder.processedToolResultIds.add(result.toolCallId)
      }
      
      builder.steps.push(step)
    }
  }

  // Process active nodes
  if (nextNodes.length > 0) {
    const prevNodes = new Set(prevState?.next || [])
    const newNodes = nextNodes.filter(n => !prevNodes.has(n))

    for (const node of newNodes) {
      // Check if we already have a step for this node
      const existingStep = builder.steps.find(
        s => s.type === 'node_execution' && s.node === node
      )

      if (!existingStep && !builder.currentStep) {
        builder.stepCounter++
        const step = createStep(
          builder.stepCounter,
          'node_execution',
          `Executing: ${node}`,
          node
        )
        
        // Check if node is still active
        if (!nextNodes.includes(node)) {
          step.status = 'completed'
          step.endTime = new Date()
        }
        
        builder.steps.push(step)
      }
    }
  }

  // Add current step if it exists (even if graph is done, we want to show it)
  if (builder.currentStep) {
    // If graph is done, mark as completed
    if (nextNodes.length === 0) {
      builder.steps.push(completeStep(builder.currentStep))
    } else {
      builder.steps.push(builder.currentStep)
    }
    builder.currentStep = null
  }

  // If graph is done (no active nodes), mark all thinking steps as completed
  if (nextNodes.length === 0) {
    for (const step of builder.steps) {
      if (step.status === 'thinking') {
        step.status = 'completed'
        step.endTime = step.endTime || new Date()
      }
    }
  }

  // Update token counts from messages
  for (const step of builder.steps) {
    if (!step.tokens) {
      let totalTokens = 0
      for (const msg of messages) {
        const tokens = extractTokenCount(msg)
        if (tokens) {
          totalTokens += tokens
        }
      }
      if (totalTokens > 0 && step.type === 'llm_call') {
        step.tokens = totalTokens
      }
    }
  }

  return builder.steps
}
