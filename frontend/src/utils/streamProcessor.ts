import type { StreamEvent, StreamEventEnvelope } from '../types/execution'
import { STREAM_TIMEOUT, STREAM_INACTIVITY_TIMEOUT } from '../constants'
import type { EventHandlerContext } from './eventHandlers'
import {
  handleGraphStart,
  handleContentChunk,
  handleStateUpdate,
  handleStateSnapshot,
  handleGenericEvent,
  handleNodeStart,
  handleNodeEnd,
  handleGraphEnd,
} from './eventHandlers'

interface ErrorWithType extends Error {
  type: string
}

/**
 * Handles stream error events - throws appropriate errors.
 * Error logging is handled by the catch block in state.ts to avoid duplicate logs.
 * 
 * @param data - Error event data
 * @throws Error with appropriate type
 */
function handleStreamError(
  data: { error?: string; error_type?: string; thread_id?: string }
): never {
  const errorMessage = data.error && typeof data.error === 'string' && data.error.trim() ? data.error : 'Unknown error occurred'
  const errorType = data.error_type || 'Error'
  const error: ErrorWithType = Object.assign(new Error(errorMessage), { type: errorType })
  
  // Always throw the error - let the catch block in state.ts handle logging
  // This avoids duplicate logging and ensures consistent error handling
  throw error
}

/**
 * Checks if stream timeouts have been exceeded.
 * 
 * @param startTime - Timestamp when stream started
 * @param lastActivityTime - Timestamp of last activity
 * @throws Error if timeout exceeded
 */
function checkTimeouts(startTime: number, lastActivityTime: number): void {
  const now = Date.now()
  
  if (now - startTime > STREAM_TIMEOUT) {
    throw new Error('Stream timeout: The request took too long to complete')
  }
  if (now - lastActivityTime > STREAM_INACTIVITY_TIMEOUT) {
    throw new Error('Stream timeout: No data received for 30 seconds')
  }
}

/**
 * Processes a single stream event and updates state accordingly.
 * 
 * @param data - Parsed stream event data
 * @param accumulatedContent - Current accumulated content
 * @param finalResponse - Current final response
 * @param graphEndReceived - Whether graph_end was received
 * @param hasError - Whether an error occurred
 * @param context - Event handler context
 * @returns Updated stream processing state
 */
/**
 * Type guard to check if data is a state_update event.
 */
function isStateUpdateEvent(data: Partial<StreamEvent>): data is StreamEvent & { type: 'state_update' } {
  return data.type === 'state_update'
}

/**
 * Type guard to check if data is a generic event (llm/tool start/end).
 */
function isGenericEvent(data: Partial<StreamEvent>): data is StreamEvent & { type: 'llm_start' | 'llm_end' | 'tool_start' | 'tool_end' } {
  return data.type === 'llm_start' || data.type === 'llm_end' || data.type === 'tool_start' || data.type === 'tool_end'
}

/**
 * Processes a single stream event and updates state accordingly.
 * 
 * @param data - Parsed stream event data
 * @param accumulatedContent - Current accumulated content
 * @param finalResponse - Current final response
 * @param graphEndReceived - Whether graph_end was received
 * @param hasError - Whether an error occurred
 * @param context - Event handler context
 * @returns Updated stream processing state
 */
export function processStreamEvent(
  data: Partial<StreamEvent> & { type?: string; content?: string; node?: string; response?: string; error?: string; error_type?: string; thread_id?: string },
  accumulatedContent: string,
  finalResponse: string,
  graphEndReceived: boolean,
  hasError: boolean,
  context: EventHandlerContext
): { accumulatedContent: string; finalResponse: string; graphEndReceived: boolean; hasError: boolean } {
  switch (data.type) {
    case 'graph_start':
      handleGraphStart(data, context)
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    case 'content_chunk':
      return { accumulatedContent: handleContentChunk(data, accumulatedContent, context), finalResponse, graphEndReceived, hasError }
    case 'state_update':
      if (isStateUpdateEvent(data)) {
        handleStateUpdate(data, context)
      }
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    case 'state_snapshot':
      // Handle checkpoint-authoritative state snapshot
      handleStateSnapshot(data as StreamEvent & { type: 'state_snapshot' }, context)
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    case 'llm_start':
    case 'llm_end':
    case 'tool_start':
    case 'tool_end':
      if (isGenericEvent(data)) {
        handleGenericEvent(data, context)
      }
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    case 'node_start':
      handleNodeStart(data, context)
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    case 'node_end':
      handleNodeEnd(data, context)
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    case 'graph_end':
      return { accumulatedContent, finalResponse: handleGraphEnd(data, accumulatedContent, context), graphEndReceived: true, hasError }
    case 'keepalive':
      // Keepalive event - just update activity time, no state changes needed
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
    case 'error':
      handleStreamError(data)
      return { accumulatedContent, finalResponse, graphEndReceived, hasError: true }
    default:
      return { accumulatedContent, finalResponse, graphEndReceived, hasError }
  }
}

/**
 * Processes a single line from the stream.
 * 
 * @param line - Raw line from stream
 * @param accumulatedContent - Current accumulated content
 * @param finalResponse - Current final response
 * @param graphEndReceived - Whether graph_end was received
 * @param hasError - Whether an error occurred
 * @param context - Event handler context
 * @returns Updated stream processing state
 */
export function processStreamLine(
  line: string,
  accumulatedContent: string,
  finalResponse: string,
  graphEndReceived: boolean,
  hasError: boolean,
  context: EventHandlerContext
): { accumulatedContent: string; finalResponse: string; graphEndReceived: boolean; hasError: boolean } {
  if (!line.startsWith('data: ')) {
    return { accumulatedContent, finalResponse, graphEndReceived, hasError }
  }

  try {
    const rawData = line.slice(6)
    const parsed = JSON.parse(rawData)
    // Validate that parsed data has expected structure
    if (typeof parsed === 'object' && parsed !== null) {
      // Check if this is the new envelope format
      if ('type' in parsed && 'seq' in parsed && 'flow' in parsed && 'payload' in parsed) {
        // New envelope format - extract payload and merge with envelope fields
        const envelope = parsed as StreamEventEnvelope
        const data: Partial<StreamEvent> & { type?: string; content?: string; node?: string; response?: string; error?: string; error_type?: string; thread_id?: string; run_id?: string } = {
          type: envelope.type,
          thread_id: envelope.thread_id,
          run_id: envelope.run_id,
          ...(envelope.payload || {}),
        }
        return processStreamEvent(data, accumulatedContent, finalResponse, graphEndReceived, hasError, context)
      } else {
        // Legacy format (for backwards compatibility)
        const data: Partial<StreamEvent> & { type?: string; content?: string; node?: string; response?: string; error?: string; error_type?: string; thread_id?: string } = parsed
        return processStreamEvent(data, accumulatedContent, finalResponse, graphEndReceived, hasError, context)
      }
    }
    return { accumulatedContent, finalResponse, graphEndReceived, hasError }
  } catch (err) {
    // Re-throw stream errors from handleStreamError, catch JSON parsing errors
    // Stream errors are ErrorWithType objects with a 'type' property
    if (err instanceof Error && (err as unknown as { type?: string }).type) {
      // This is a stream error from handleStreamError, re-throw it
      throw err
    }
    // JSON parsing error or other error - just return current state
    return { accumulatedContent, finalResponse, graphEndReceived, hasError }
  }
}

/**
 * Reads and processes a stream from a ReadableStream.
 * 
 * @param reader - Stream reader
 * @param decoder - Text decoder for stream data
 * @param context - Event handler context
 * @returns Final stream processing result
 */
export async function readStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  decoder: TextDecoder,
  context: EventHandlerContext
): Promise<{ accumulatedContent: string; finalResponse: string; graphEndReceived: boolean; hasError: boolean }> {
  let buffer = ''
  let accumulatedContent = ''
  let finalResponse = ''
  let graphEndReceived = false
  let hasError = false
  const startTime = Date.now()
  let lastActivityTime = Date.now()

  while (true) {
    checkTimeouts(startTime, lastActivityTime)

    const { done, value } = await reader.read()
    if (done) break

    lastActivityTime = Date.now()
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const result = processStreamLine(line, accumulatedContent, finalResponse, graphEndReceived, hasError, context)
      accumulatedContent = result.accumulatedContent
      finalResponse = result.finalResponse
      graphEndReceived = result.graphEndReceived
      hasError = result.hasError
    }
  }

  return { accumulatedContent, finalResponse, graphEndReceived, hasError }
}
