import type { Dispatch, SetStateAction } from 'react'
import type { StreamEvent, ExecutionState } from '../types'
import { CHAT_CLEANUP_DELAY } from '../constants'

/**
 * Type for mutable refs - equivalent to MutableRefObject but not deprecated.
 */
type MutableRef<T> = { current: T }

/**
 * Converts message content from various types to a string representation.
 * 
 * @param content - The content to convert (string, object, number, boolean, etc.)
 * @returns A string representation of the content
 */
export function convertMessageContent(content: unknown): string {
  if (typeof content === 'string') {
    return content
  }
  if (content !== null && content !== undefined) {
    if (typeof content === 'object') {
      return JSON.stringify(content)
    }
    if (typeof content === 'number' || typeof content === 'boolean' || typeof content === 'bigint') {
      return String(content)
    }
  }
  return ''
}

/**
 * Extracts thread ID from event data, falling back to provided default.
 * 
 * @param data - Event data that may contain thread_id
 * @param fallback - Fallback thread ID to use if not in data
 * @returns The thread ID from data or fallback
 */
export function getThreadId(data: { thread_id?: string }, fallback: string): string {
  return typeof data.thread_id === 'string' ? data.thread_id : fallback
}

/**
 * Creates an ExecutionState object with consistent structure.
 * 
 * @param options - Configuration for the execution state
 * @param options.next - Array of next node names
 * @param options.visitedNodes - Array of visited node names
 * @param options.messageCount - Current message count
 * @param options.streamEvents - Array of stream events
 * @returns A properly formatted ExecutionState object
 */
export function createExecutionState(options: {
  next?: string[]
  visitedNodes: string[]
  messageCount: number
  streamEvents: StreamEvent[]
}): ExecutionState {
  return {
    next: options.next || [],
    values: {
      message_count: options.messageCount,
    },
    history: options.visitedNodes.map(node => ({ node })),
    streamEvents: options.streamEvents.length > 0 ? options.streamEvents : undefined,
  }
}

/**
 * Adds a node to the visited nodes array if it's not already present.
 * 
 * @param nodes - Current array of visited nodes
 * @param node - Node name to add
 * @returns New array with the node added (if not already present)
 */
export function addNodeToVisited(nodes: string[], node: string): string[] {
  return nodes.includes(node) ? nodes : [...nodes, node]
}

/**
 * Context for event handlers - provides access to state setters and refs.
 */
export interface EventHandlerContext {
  setStreamEvents: Dispatch<SetStateAction<StreamEvent[]>>
  setVisitedNodes: Dispatch<SetStateAction<string[]>>
  setActiveNode: Dispatch<SetStateAction<string | null>>
  setStreamingContent: Dispatch<SetStateAction<string>>
  queueStateUpdate: (state: ExecutionState) => void
  prevStateRef: MutableRef<{ visitedNodes: string[]; activeNode: string | null }>
  lastMessageCountRef: MutableRef<number>
  timeoutRef: MutableRef<number | null>
  threadId: string
  activeNode: string | null
  visitedNodes: string[]
  onReportStateUpdate?: (reportState: {
    raw_procedures?: Array<Record<string, any>>;
    pending_clusters?: Array<Record<string, any>>;
    chapters?: string[];
    final_report?: string | null;
  }) => void
}

/**
 * Handles graph_start events - resets state and initializes new graph execution.
 * 
 * @param data - Event data containing thread ID
 * @param context - Handler context with state setters and refs
 */
export function handleGraphStart(
  data: { thread_id?: string },
  context: EventHandlerContext
): void {
  context.setStreamEvents([])
  context.setVisitedNodes([])
  context.setActiveNode(null)
  
  const eventThreadId = getThreadId(data, context.threadId || '')
  
  // Update threadId in context if it changed (for ReportInterface jobId updates)
  if (eventThreadId !== context.threadId && 'setThreadId' in context) {
    (context as any).setThreadId(eventThreadId)
  }
  
  const graphStartEvent: StreamEvent = {
    type: 'graph_start',
    thread_id: eventThreadId,
  }
  
  context.setStreamEvents([graphStartEvent])
  
  context.queueStateUpdate(createExecutionState({
    next: [],
    visitedNodes: [],
    messageCount: 0,
    streamEvents: [graphStartEvent],
  }))
}

/**
 * Handles content_chunk events - accumulates streaming content.
 * 
 * @param data - Event data containing content chunk
 * @param accumulatedContent - Previously accumulated content
 * @param context - Handler context with state setters
 * @returns Updated accumulated content
 */
export function handleContentChunk(
  data: { content?: string },
  accumulatedContent: string,
  context: EventHandlerContext
): string {
  const chunkContent = data.content || ''
  const newAccumulatedContent = accumulatedContent + chunkContent
  context.setStreamingContent(newAccumulatedContent)
  return newAccumulatedContent
}

/**
 * Handles state_update events - updates node state and visited nodes.
 * 
 * @param data - State update event data
 * @param context - Handler context with state setters and refs
 */
/**
 * Handles state_snapshot events (checkpoint-authoritative state updates).
 * 
 * @param data - State snapshot event data
 * @param context - Handler context with state setters and refs
 */
export function handleStateSnapshot(
  data: StreamEvent & { type: 'state_snapshot' },
  context: EventHandlerContext
): void {
  const snapshot = data as any
  
  // Update execution state
  const next = snapshot.next || []
  const visitedNodes = snapshot.visited_nodes || []
  
  context.setActiveNode(next.length > 0 ? next[0] : null)
  context.setVisitedNodes(prev => {
    const allVisitedNodes = [...new Set([...prev, ...visitedNodes])]
    context.prevStateRef.current = { visitedNodes: allVisitedNodes, activeNode: next[0] || null }
    return allVisitedNodes
  })
  
  // Handle report state if present
  if (snapshot.report_state && context.onReportStateUpdate) {
    context.onReportStateUpdate(snapshot.report_state)
  }
  
  // Store snapshot in streamEvents for inspection
  context.setStreamEvents(prev => {
    const updatedEvents = [...prev, data]
    const stateUpdate = createExecutionState({
      next,
      visitedNodes,
      messageCount: 0,
      streamEvents: updatedEvents,
    })
    context.queueStateUpdate(stateUpdate)
    return updatedEvents
  })
}

export function handleStateUpdate(
  data: StreamEvent & { type: 'state_update' },
  context: EventHandlerContext
): void {
  // Check if there was a recent node_end that should clear the active node
  // If the previous active node is not in the new next array, it was ended
  const previousActiveNode = context.prevStateRef.current.activeNode
  const newNext = data.next || []
  const newActiveNode = newNext.length > 0 ? newNext[0] : null
  
  // If previous active node exists but is not in new next, it was ended
  // Don't set it as active even if it appears in visited_nodes
  if (previousActiveNode && !newNext.includes(previousActiveNode)) {
    // Node was ended, ensure it's cleared
    context.setActiveNode(null)
    context.prevStateRef.current.activeNode = null
  } else {
    context.setActiveNode(newActiveNode)
  }
  
  const eventVisitedNodes = data.visited_nodes || []
  context.setVisitedNodes(prev => {
    const allVisitedNodes = [...new Set([...prev, ...eventVisitedNodes])]
    const finalActiveNode = previousActiveNode && !newNext.includes(previousActiveNode) ? null : newActiveNode
    context.prevStateRef.current = { visitedNodes: allVisitedNodes, activeNode: finalActiveNode }
    return allVisitedNodes
  })
  
  const messageCount = data.message_count || 0
  context.lastMessageCountRef.current = messageCount
  
  // Handle report state if present
  if (data.report_state && context.onReportStateUpdate) {
    context.onReportStateUpdate(data.report_state)
  }
  
  context.setStreamEvents(prev => {
    const updatedEvents = prev.length > 0 ? [...prev, data] : [data]
    // Use the corrected active node (null if it was ended)
    const finalNext = previousActiveNode && !newNext.includes(previousActiveNode) ? [] : newNext
    const stateUpdate = createExecutionState({
      next: finalNext,
      visitedNodes: context.prevStateRef.current.visitedNodes,
      messageCount,
      streamEvents: updatedEvents,
    })
    context.queueStateUpdate(stateUpdate)
    return updatedEvents
  })
}

/**
 * Handles LLM and tool events (start/end) with shared logic.
 * 
 * @param data - The stream event data
 * @param context - Handler context with state setters and refs
 */
export function handleGenericEvent(
  data: StreamEvent & { type: 'llm_start' | 'llm_end' | 'tool_start' | 'tool_end' },
  context: EventHandlerContext
): void {
  context.setStreamEvents(prev => {
    const updatedEvents = [...prev, data]
    context.queueStateUpdate(createExecutionState({
      next: context.activeNode ? [context.activeNode] : [],
      visitedNodes: context.visitedNodes,
      messageCount: context.lastMessageCountRef.current,
      streamEvents: updatedEvents,
    }))
    return updatedEvents
  })
}

/**
 * Handles node start events - tracks node activation and updates state.
 * 
 * @param data - Event data containing node name and thread ID
 * @param context - Handler context with state setters and refs
 */
export function handleNodeStart(
  data: { node?: string; thread_id?: string; input_preview?: string },
  context: EventHandlerContext
): void {
  const nodeName = typeof data.node === 'string' ? data.node : null
  if (!nodeName) return
  
  const eventThreadId = getThreadId(data, context.threadId || '')
  const nodeStartEvent: StreamEvent = {
    type: 'node_start',
    node: nodeName,
    thread_id: eventThreadId,
    input_preview: typeof data.input_preview === 'string' ? data.input_preview : undefined,
  }
  
  // Flatten nested state updates to avoid race conditions
  context.setVisitedNodes(prev => {
    const updatedVisitedNodes = addNodeToVisited(prev, nodeName)
    context.prevStateRef.current = { 
      visitedNodes: updatedVisitedNodes, 
      activeNode: nodeName 
    }
    return updatedVisitedNodes
  })
  
  context.setStreamEvents(prev => {
    const updatedEvents = [...prev, nodeStartEvent]
    context.queueStateUpdate(createExecutionState({
      next: [nodeName],
      visitedNodes: context.prevStateRef.current.visitedNodes,
      messageCount: context.lastMessageCountRef.current,
      streamEvents: updatedEvents,
    }))
    return updatedEvents
  })
  
  context.setActiveNode(nodeName)
}

/**
 * Handles node end events - tracks node completion and updates state.
 * 
 * @param data - Event data containing node name and thread ID
 * @param context - Handler context with state setters and refs
 */
export function handleNodeEnd(
  data: { node?: string; thread_id?: string; output_preview?: string },
  context: EventHandlerContext
): void {
  const nodeName = typeof data.node === 'string' ? data.node : null
  if (!nodeName) return
  
  const eventThreadId = getThreadId(data, context.threadId || '')
  const nodeEndEvent: StreamEvent = {
    type: 'node_end',
    node: nodeName,
    thread_id: eventThreadId,
    output_preview: typeof data.output_preview === 'string' ? data.output_preview : undefined,
  }
  
  // Clear active node immediately
  context.setActiveNode(null)
  
  // Flatten nested state updates to avoid race conditions
  context.setVisitedNodes(prev => {
    const updatedVisitedNodes = addNodeToVisited(prev, nodeName)
    context.prevStateRef.current = { 
      visitedNodes: updatedVisitedNodes, 
      activeNode: null 
    }
    return updatedVisitedNodes
  })
  
  context.setStreamEvents(prev => {
    const updatedEvents = [...prev, nodeEndEvent]
    // Ensure next is empty to clear active state, even if a state_update comes after
    // Filter out the ended node from next array if it exists
    const currentNext = context.prevStateRef.current.activeNode === nodeName ? [] : []
    context.queueStateUpdate(createExecutionState({
      next: currentNext,
      visitedNodes: context.prevStateRef.current.visitedNodes,
      messageCount: context.lastMessageCountRef.current,
      streamEvents: updatedEvents,
    }))
    return updatedEvents
  })
}

/**
 * Handles graph end events - finalizes the stream and cleans up state.
 * Uses refs to avoid stale closure issues with activeNode.
 * 
 * @param data - Event data containing response and thread ID
 * @param accumulatedContent - Accumulated content from stream
 * @param context - Handler context with state setters and refs
 * @returns The final response string
 */
export function handleGraphEnd(
  data: { response?: string; thread_id?: string },
  accumulatedContent: string,
  context: EventHandlerContext
): string {
  const newFinalResponse = (typeof data.response === 'string' ? data.response : '') || accumulatedContent || ''
  const currentVisitedNodes = context.prevStateRef.current.visitedNodes
  // Use ref to get current activeNode to avoid stale closure
  const currentActiveNode = context.prevStateRef.current.activeNode
  const finalVisitedNodes = currentActiveNode && !currentVisitedNodes.includes(currentActiveNode)
    ? [...currentVisitedNodes, currentActiveNode]
    : currentVisitedNodes
  context.setVisitedNodes(finalVisitedNodes)
  context.setActiveNode(null)
  context.setStreamingContent('')
  
  const eventThreadId = getThreadId(data, context.threadId || '')
  const graphEndEvent: StreamEvent = {
    type: 'graph_end',
    thread_id: eventThreadId,
    response: newFinalResponse,
  }
  
  context.setStreamEvents(prev => {
    const updatedEvents = [...prev, graphEndEvent]
    context.queueStateUpdate(createExecutionState({
      next: [],
      visitedNodes: finalVisitedNodes,
      messageCount: context.lastMessageCountRef.current,
      streamEvents: updatedEvents,
    }))
    return updatedEvents
  })
  
  // Only clear stream events for chat flow, not for report flow
  // Report flow needs to keep events for the event log display
  const isReportFlow = !!context.onReportStateUpdate
  if (!isReportFlow) {
    // Store timeout ID for cleanup (chat flow only)
    const cleanupTimeoutId = window.setTimeout(() => {
      context.setStreamEvents([])
    }, CHAT_CLEANUP_DELAY)
    
    // Store timeout ID in ref for cleanup on unmount
    if (context.timeoutRef.current !== null) {
      clearTimeout(context.timeoutRef.current)
    }
    context.timeoutRef.current = cleanupTimeoutId
  }
  
  context.prevStateRef.current = { visitedNodes: finalVisitedNodes, activeNode: null }
  return newFinalResponse
}
