import * as React from "react"
import { FileText, Play, Square, Loader2, CheckCircle, AlertCircle, X, Plus } from "lucide-react"
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card"
import { ScrollArea } from "./ui/scroll-area"
import { Button } from "./ui/button"
import { getApiHeaders, getAvailableModels, getApiUrl } from "../utils/api"
import GraphView from "./GraphView"
import ObservabilityWindow from "./ObservabilityWindow"
import StateView from "./StateView"
import type { ExecutionState, StreamEvent } from "../types/execution"
import { readStream } from "../utils/streamProcessor"
import { 
  type EventHandlerContext
} from "../utils/eventHandlers"
import { getUserFriendlyError, logError } from "../utils/errorHandling"

interface ReportProgress {
  chapters_completed: number;
  recent_logs: string[];
}

interface ClusterStatusInfo {
  status: string;
  started_at?: string;
  ended_at?: string;
  error?: string;
  retry_count?: number;
}

interface ReportStatus {
  status: 'running' | 'completed' | 'not_found' | 'cloud_run_job_submitted' | 'stopped';
  progress?: ReportProgress;
  graph_state?: {
    visited_nodes: string[];
    next: string[];
  };
  state?: {
    raw_procedures: Array<Record<string, any>>;
    pending_clusters: Array<Record<string, any>>;
    clusters_all?: Array<Record<string, any>>;
    cluster_status?: Record<string, ClusterStatusInfo>;
    chapters: string[];
    chapters_by_file_id?: Record<string, string>;
    final_report?: string | null;
    execution_metrics?: Record<string, any>;
  };
  result?: string;
}

interface ReportInterfaceProps {
  token: string;
  onExecutionStateUpdate?: (state: ExecutionState | null) => void;
  org?: string;
  project?: string;
}

type EventLogEntry = { text: string; ts?: number }

export default function ReportInterface({ token, onExecutionStateUpdate, org, project }: ReportInterfaceProps) {
  const isDev = import.meta.env.DEV;
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<ReportStatus | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [executionState, setExecutionState] = React.useState<ExecutionState | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedModel, setSelectedModel] = React.useState<string | null>(null);
  const [availableModels, setAvailableModels] = React.useState<string[]>([]);
  const [executionMode, setExecutionMode] = React.useState<'local' | 'cloud_run_service' | 'cloud_run_job'>(
    'cloud_run_service'
  );
  const [streamEvents, setStreamEvents] = React.useState<StreamEvent[]>([]);
  const [visitedNodes, setVisitedNodes] = React.useState<string[]>([]);
  const [activeNode, setActiveNode] = React.useState<string | null>(null);
  const [eventLogs, setEventLogs] = React.useState<EventLogEntry[]>([]);
  const abortControllerRef = React.useRef<AbortController | null>(null);
  const prevStateRef = React.useRef<{ visitedNodes: string[]; activeNode: string | null }>({
    visitedNodes: [],
    activeNode: null,
  });
  const lastMessageCountRef = React.useRef<number>(0);
  const timeoutRef = React.useRef<number | null>(null);
  const pendingStateUpdateRef = React.useRef<ExecutionState | null>(null);
  const eventLogScrollRef = React.useRef<HTMLDivElement | null>(null);

  const API_URL = getApiUrl();

  // Fetch available models on mount
  React.useEffect(() => {
    getAvailableModels(token)
      .then((models) => {
        setAvailableModels(models);
        if (models.length > 0) {
          setSelectedModel((prev) => prev || models[0]);
        }
      })
      .catch((err) => {
        console.error("Failed to fetch available models:", err);
      });
  }, [token]);

  // Queue state updates to avoid calling callbacks during render
  const queueStateUpdate = React.useCallback((state: ExecutionState) => {
    pendingStateUpdateRef.current = state
  }, []);

  // Update status from report state (used by both streaming and polling)
  const handleReportStateUpdate = React.useCallback((reportState: {
    raw_procedures?: Array<Record<string, any>>;
    pending_clusters?: Array<Record<string, any>>;
    clusters_all?: Array<Record<string, any>>;
    cluster_status?: Record<string, ClusterStatusInfo>;
    chapters?: string[];
    chapters_by_file_id?: Record<string, string>;
    final_report?: string | null;
  }) => {
    setStatus(prev => {
      const newStatus: ReportStatus = {
        ...prev,
        status: reportState.final_report ? 'completed' : 'running',
        progress: {
          chapters_completed: reportState.chapters?.length || 0,
          recent_logs: prev?.progress?.recent_logs || [],
        },
        state: {
          // Use explicit checks - undefined means "keep previous", null/value means "update"
          raw_procedures: reportState.raw_procedures !== undefined ? reportState.raw_procedures : (prev?.state?.raw_procedures || []),
          pending_clusters: reportState.pending_clusters !== undefined ? reportState.pending_clusters : (prev?.state?.pending_clusters || []),
          clusters_all: reportState.clusters_all !== undefined ? reportState.clusters_all : (prev?.state?.clusters_all || []),
          cluster_status: reportState.cluster_status !== undefined ? reportState.cluster_status : prev?.state?.cluster_status,
          chapters: reportState.chapters !== undefined ? reportState.chapters : (prev?.state?.chapters || []),
          chapters_by_file_id: reportState.chapters_by_file_id !== undefined ? reportState.chapters_by_file_id : (prev?.state?.chapters_by_file_id || {}),
          final_report: reportState.final_report !== undefined ? reportState.final_report : prev?.state?.final_report,
        },
        result: reportState.final_report || prev?.result,
      }
      return newStatus
    })
  }, []);

  // Process pending state updates in useEffect (outside render)
  React.useEffect(() => {
    if (pendingStateUpdateRef.current) {
      setExecutionState(pendingStateUpdateRef.current)
      if (onExecutionStateUpdate) {
        onExecutionStateUpdate(pendingStateUpdateRef.current)
      }
      pendingStateUpdateRef.current = null
    }
  })

  // Load checkpoint on mount if thread ID exists in localStorage
  React.useEffect(() => {
    if (!org || !project || !token || jobId) {
      // Don't load if org/project not available, no token, or jobId already set
      return
    }

    const storageKey = `report_thread_${org}_${project}`
    const storedThreadId = localStorage.getItem(storageKey)

    if (!storedThreadId) {
      return
    }

    // Load checkpoint state
    const loadCheckpoint = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_URL}/report/${storedThreadId}/load`, {
          headers: getApiHeaders(token),
        })

        if (!response.ok) {
          // If checkpoint not found, clear localStorage
          if (response.status === 404) {
            localStorage.removeItem(storageKey)
          }
          return
        }

        const data = await response.json()

        if (data.status === 'not_found' || data.status === 'not_found_or_empty') {
          localStorage.removeItem(storageKey)
          return
        }

        // Restore state from checkpoint
        setJobId(storedThreadId)
        setStatus(data)

        // Update execution state from graph_state
        if (data.graph_state) {
          const newExecutionState: ExecutionState = {
            next: data.graph_state.next || [],
            history: data.graph_state.visited_nodes.map((node: string) => ({ node })),
            values: {
              message_count: data.progress?.chapters_completed || 0,
              logs: data.progress?.recent_logs || []
            },
            streamEvents: []
          }
          setExecutionState(newExecutionState)
          if (onExecutionStateUpdate) {
            onExecutionStateUpdate(newExecutionState)
          }
        }

        // Update report state
        if (data.state) {
          handleReportStateUpdate({
            raw_procedures: data.state.raw_procedures,
            pending_clusters: data.state.pending_clusters,
            clusters_all: data.state.clusters_all,
            chapters: data.state.chapters,
            final_report: data.state.final_report,
          })
        }
      } catch (err) {
        console.error("Failed to load checkpoint", err)
        // Clear localStorage on error
        localStorage.removeItem(storageKey)
      } finally {
        setLoading(false)
      }
    }

    void loadCheckpoint()
  }, [org, project, token, API_URL, jobId, onExecutionStateUpdate, handleReportStateUpdate])

  // Create event handler context with jobId setter
  // Note: This function is called fresh each time to get current state values
  const createEventHandlerContext = (): EventHandlerContext & { setThreadId?: (id: string) => void } => {
    return {
      setStreamEvents,
      setVisitedNodes,
      setActiveNode,
      setStreamingContent: () => {}, // Not used in reports
      queueStateUpdate,
      prevStateRef,
      lastMessageCountRef,
      timeoutRef,
      threadId: jobId || '',
      activeNode,
      visitedNodes,
      onReportStateUpdate: handleReportStateUpdate,
      setThreadId: (id: string) => {
        setJobId(id)
        // Store thread ID in localStorage for restoration after refresh
        if (org && project) {
          const storageKey = `report_thread_${org}_${project}`
          localStorage.setItem(storageKey, id)
        }
      },
    }
  }

  const startReport = async () => {
    setLoading(true)
    setError(null) // Clear any previous errors
    setJobId(null)
    setStatus(null)
    setExecutionState(null)
    setStreamEvents([])
    setVisitedNodes([])
    setActiveNode(null)
    setEventLogs([])

    // Cancel any existing stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(`${API_URL}/report/start`, {
        method: 'POST',
        headers: getApiHeaders(token),
        body: JSON.stringify({
          execution_mode: executionMode,
          ...(selectedModel && { model: selectedModel }),
        }),
        signal: abortControllerRef.current.signal,
      })

      // Check if response is OK before processing
      if (!response.ok) {
        const errorText = await response.text()
        let errorMessage = `Failed to start report: ${response.status}`
        try {
          const errorData = JSON.parse(errorText)
          errorMessage = errorData.detail || errorMessage
        } catch {
          errorMessage = errorText || errorMessage
        }
        throw new Error(errorMessage)
      }

      // Check if response is streaming (local mode) or JSON (cloud_run modes)
      const contentType = response.headers.get('content-type') || ''
      
      if (contentType.includes('text/event-stream')) {
        // Streaming mode (local)
        const reader = response.body?.getReader()
        const decoder = new TextDecoder()

        if (!reader) {
          throw new Error('No response body reader available')
        }

        // For streaming, we'll get thread_id from the first graph_start event
        // Set a temporary jobId that will be updated when we receive graph_start
        const tempJobId = crypto.randomUUID()
        setJobId(tempJobId)
        // Optimistically set status to 'running' so the Stop button shows immediately
        setStatus((prev) => ({ ...prev, status: 'running' as const }))

        // Initialize execution state
        const initialExecutionState: ExecutionState = {
          next: [],
          history: [],
          values: {
            message_count: 0,
            logs: []
          }
        }
        setExecutionState(initialExecutionState)
        if (onExecutionStateUpdate) {
          onExecutionStateUpdate(initialExecutionState)
        }

        // Create context for event handlers
        const context = createEventHandlerContext()
        
        // Process stream using shared readStream function
        try {
          const streamResult = await readStream(reader, decoder, context)
          
          // Update status with final report if available
          if (streamResult.finalResponse) {
            setStatus(prev => ({
              ...prev,
              status: 'completed',
              result: streamResult.finalResponse,
              state: {
                ...prev?.state,
                final_report: streamResult.finalResponse,
              },
            } as ReportStatus))
          }
        } catch (streamErr) {
          // Don't show error if it was an intentional abort
          if (streamErr instanceof Error && streamErr.name === 'AbortError') {
            // Stream was cancelled, ignore
            setLoading(false)
            return
          }
          // Stream errors are already logged in streamProcessor
          // Get user-friendly error message
          const apiError = getUserFriendlyError(streamErr)
          const errorMessage = apiError.isUserFriendly 
            ? apiError.message 
            : 'An error occurred while processing the report. Please try again.'
          setError(errorMessage)
        } finally {
          setLoading(false)
        }
      } else {
        // Non-streaming mode (cloud_run_job)
        const data = await response.json()
        setJobId(data.job_id)
        
        // Initialize status for cloud_run_job mode
        setStatus({
          status: 'cloud_run_job_submitted',
          progress: { chapters_completed: 0, recent_logs: [] },
          graph_state: { visited_nodes: [], next: [] },
        })
        
        // Initialize execution state so views render
        const initialExecutionState: ExecutionState = {
          next: [],
          history: [],
          values: { message_count: 0, logs: [] },
          streamEvents: []
        }
        setExecutionState(initialExecutionState)
        if (onExecutionStateUpdate) {
          onExecutionStateUpdate(initialExecutionState)
        }
        
        setLoading(false)
        // Polling will start via useEffect when jobId is set
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // Stream was cancelled, ignore
        return
      }
      logError('ReportInterface: Failed to start report', err)
      const apiError = getUserFriendlyError(err)
      const errorMessage = apiError.isUserFriendly 
        ? apiError.message 
        : 'Failed to start report. Please try again.'
      setError(errorMessage)
      setLoading(false)
    }
  }

  const stopReport = async () => {
    // Cancel stream if active
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    if (!jobId) {
      return
    }
    
    // Set loading state for visual feedback
    setLoading(true)
    
    try {
      await fetch(`${API_URL}/report/${jobId}/stop`, {
        method: 'POST',
        headers: getApiHeaders(token)
      })
    } catch (err) {
      console.error("Failed to stop report", err)
    } finally {
      // When stopping, preserve all state but mark as stopped
      // Only clear activeNode since nothing is running
      // Keep jobId so the report can be resumed
      setStatus(prev => prev ? { ...prev, status: 'stopped' as const } : null)
      setActiveNode(null) // Clear active node since execution is stopped
      setError(null) // Clear any error state when stopping
      setLoading(false)
      
      // Update execution state to clear active node but preserve history
      if (executionState) {
        const updatedExecutionState: ExecutionState = {
          ...executionState,
          next: [] // No active nodes when stopped
        }
        setExecutionState(updatedExecutionState)
        if (onExecutionStateUpdate) {
          onExecutionStateUpdate(updatedExecutionState)
        }
      }
      
      // Don't clear localStorage - preserve checkpoint for potential resume
      // Don't clear jobId - keep it so user can see what was stopped
      // Don't clear streamEvents, visitedNodes, or eventLogs - preserve UX state
    }
  }

  const resumeReport = async () => {
    if (!jobId || !org || !project) {
      return
    }

    setLoading(true)

    try {
      const response = await fetch(`${API_URL}/report/${jobId}/resume`, {
        method: 'POST',
        headers: getApiHeaders(token),
      })

      if (!response.ok) {
        throw new Error(`Failed to resume report: ${response.status}`)
      }

      // Optimistically update status to 'running' so Stop button shows immediately
      // The actual status will be updated via polling or stream events
      setStatus(prev => ({
        ...prev,
        status: 'running' as const,
      }))
      
      setLoading(false)
    } catch (err) {
      console.error("Failed to resume report", err)
      setLoading(false)
    }
  }

  const handleNewReport = () => {
    // Cancel any existing stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    // Clear all state
    setJobId(null)
    setStatus(null)
    setExecutionState(null)
    setStreamEvents([])
    setVisitedNodes([])
    setActiveNode(null)
    setEventLogs([])
    setError(null)
    setLoading(false)

    // Clear localStorage if org/project are available
    if (org && project) {
      const storageKey = `report_thread_${org}_${project}`
      localStorage.removeItem(storageKey)
    }

    // Notify parent component that execution state is cleared
    if (onExecutionStateUpdate) {
      onExecutionStateUpdate(null)
    }
  }

  // Polling only for cloud_run_job mode (no streaming available)
  // For local and cloud_run_service modes, state comes from stream events
  React.useEffect(() => {
    if (!jobId || !org || !project || executionMode !== 'cloud_run_job') return;
    
    // Stop polling if status is already stopped
    if (status?.status === 'stopped') return;

    let shouldStop = false;

    const pollStatus = async () => {
      if (shouldStop) return;
      
      try {
        const response = await fetch(`${API_URL}/report/${jobId}/status`, {
          headers: getApiHeaders(token)
        });
        const data = await response.json();

        // Don't stop polling on "not_found" - job may not have written state yet
        // Only stop if status is "completed" or we get an error
        if (data.status === 'completed') {
          shouldStop = true;
        }

        // Update state if available (job has started writing checkpoints)
        if (data.state) {
          handleReportStateUpdate(data.state);
        }

        // Update execution state from graph_state
        if (data.graph_state) {
          const newExecutionState: ExecutionState = {
            next: data.graph_state.next || [],
            history: data.graph_state.visited_nodes.map((node: string) => ({ node })),
            values: {
              message_count: data.progress?.chapters_completed || 0,
              logs: data.progress?.recent_logs || []
            },
            streamEvents: []
          };
          setExecutionState(newExecutionState);
          if (onExecutionStateUpdate) {
            onExecutionStateUpdate(newExecutionState);
          }
        }
        
        // Update full status including progress (for event logs) and status field
        // Don't overwrite 'stopped' status - if user stopped it, keep it stopped
        if (data.status && data.status !== 'not_found') {
          setStatus(prev => {
            // Don't overwrite 'stopped' status with API response
            if (prev?.status === 'stopped') {
              return prev;
            }
            return {
              ...prev,
              status: data.status,
              progress: data.progress || prev?.progress,
            };
          })
        }
      } catch (err) {
        console.error("Failed to poll status", err);
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 3000);

    return () => {
      shouldStop = true;
      clearInterval(interval);
    };
  }, [jobId, executionMode, token, API_URL, org, project, onExecutionStateUpdate, handleReportStateUpdate, status]);

  // Update event logs from stream events or status
  React.useEffect(() => {
    // When report is completed, prefer logs from status (most complete and persistent)
    if (status?.status === 'completed' && status?.progress?.recent_logs && Array.isArray(status.progress.recent_logs) && status.progress.recent_logs.length > 0) {
      setEventLogs(status.progress.recent_logs.map((s) => ({ text: s })))
      return
    }
    
    // Process stream events for both local and cloud_run_service modes (both use streaming)
    if ((executionMode === 'local' || executionMode === 'cloud_run_service') && streamEvents.length > 0) {
      // Build logs by processing events in order and replacing start with end events
      const logs: EventLogEntry[] = []
      const nodeLogIndices = new Map<string, number>()
      const llmLogIndices = new Map<string, number>()
      let llmFallback = 0

      const getTs = (e: StreamEvent): number | undefined => {
        const x = e as { ts?: number }
        return typeof x?.ts === 'number' ? x.ts : undefined
      }

      const handleGraphEvent = (event: StreamEvent) => {
        if (event.type === 'graph_start') {
          const logIndex = logs.length
          logs.push({ text: 'Starting: LangGraph', ts: getTs(event) })
          nodeLogIndices.set('LangGraph', logIndex)
        } else if (event.type === 'graph_end') {
          const existingIndex = nodeLogIndices.get('LangGraph')
          if (existingIndex !== undefined && existingIndex < logs.length) {
            logs[existingIndex] = { text: 'Completed: LangGraph', ts: getTs(event) }
          } else {
            logs.push({ text: 'Completed: LangGraph', ts: getTs(event) })
          }
        }
      }

      const handleNodeEvent = (event: StreamEvent) => {
        if (event.type === 'node_start' && 'node' in event) {
          const nodeName = event.node || 'unknown'
          const inputPreview = (event as { input_preview?: string }).input_preview
          if (!nodeLogIndices.has(nodeName)) {
            const logIndex = logs.length
            let logEntry = `Starting: ${nodeName}`
            if (inputPreview) {
              logEntry += `\n  Input: ${inputPreview}`
            }
            logs.push({ text: logEntry, ts: getTs(event) })
            nodeLogIndices.set(nodeName, logIndex)
          }
        } else if (event.type === 'node_end' && 'node' in event) {
          const nodeName = event.node || 'unknown'
          const outputPreview = (event as { output_preview?: string }).output_preview
          const existingIndex = nodeLogIndices.get(nodeName)

          if (existingIndex !== undefined && existingIndex < logs.length) {
            const existing = logs[existingIndex]
            const existingLines = existing.text.split('\n')
            let logEntry = `Completed: ${nodeName}`
            if (existingLines.length > 1 && existingLines[1].startsWith('  Input:')) {
              logEntry += `\n${existingLines[1]}`
            }
            if (outputPreview) {
              logEntry += `\n  Output: ${outputPreview}`
            }
            logs[existingIndex] = { text: logEntry, ts: getTs(event) }
          } else {
            let logEntry = `Completed: ${nodeName}`
            if (outputPreview) {
              logEntry += `\n  Output: ${outputPreview}`
            }
            logs.push({ text: logEntry, ts: getTs(event) })
          }
        }
      }

      const handleLLMEvent = (event: StreamEvent) => {
        if (event.type === 'llm_start' && 'model' in event) {
          const modelName = event.model || 'unknown'
          const inputPreview = event.input_preview || ''
          const runId = 'run_id' in event && typeof event.run_id === 'string' && event.run_id ? event.run_id : null
          const key = runId ?? `__fallback_${llmFallback++}`
          let logEntry = `Starting: model (${modelName})`
          if (inputPreview) {
            logEntry += `\n  Input: ${inputPreview}`
          }
          logs.push({ text: logEntry, ts: getTs(event) })
          llmLogIndices.set(key, logs.length - 1)
        } else if (event.type === 'llm_end' && 'model' in event) {
          const modelName = event.model || 'unknown'
          const outputPreview = event.output_preview || ''
          const rid = 'run_id' in event && typeof event.run_id === 'string' && event.run_id ? event.run_id : undefined

          const applyCompleted = (idx: number) => {
            const existing = logs[idx]
            const existingLines = existing.text.split('\n')
            let logEntry = `Completed: model (${modelName})`
            if (existingLines.length > 1 && existingLines[1].startsWith('  Input:')) {
              logEntry += `\n${existingLines[1]}`
            }
            if (outputPreview) {
              logEntry += `\n  Output: ${outputPreview}`
            }
            logs[idx] = { text: logEntry, ts: getTs(event) }
          }

          let existingIndex: number | undefined

          if (rid !== undefined && llmLogIndices.has(rid)) {
            existingIndex = llmLogIndices.get(rid)!
            llmLogIndices.delete(rid)
            applyCompleted(existingIndex)
            return
          }

          const fallbackEntries = [...llmLogIndices.entries()].filter(([k]) => k.startsWith('__fallback_'))
          if (fallbackEntries.length > 0) {
            const [key, idx] = fallbackEntries.reduce((a, b) => (a[1] < b[1] ? a : b))
            llmLogIndices.delete(key)
            applyCompleted(idx)
            return
          }

          let logEntry = `Completed: model (${modelName})`
          if (outputPreview) {
            logEntry += `\n  Output: ${outputPreview}`
          }
          logs.push({ text: logEntry, ts: getTs(event) })
        }
      }
      
      streamEvents.forEach(event => {
        if (event.type === 'graph_start' || event.type === 'graph_end') {
          handleGraphEvent(event)
        } else if (event.type === 'node_start' || event.type === 'node_end') {
          handleNodeEvent(event)
        } else if (event.type === 'llm_start' || event.type === 'llm_end') {
          handleLLMEvent(event)
        }
      })
      
      setEventLogs(logs)
    } else if (status?.progress?.recent_logs) {
      setEventLogs(status.progress.recent_logs.map((s) => ({ text: s })))
    }
  }, [streamEvents, status, executionMode])

  // Auto-scroll event log to bottom when new messages are added
  React.useEffect(() => {
    requestAnimationFrame(() => {
      if (eventLogScrollRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = eventLogScrollRef.current
        // Only auto-scroll if user is near the bottom (within 100px)
        if (scrollHeight - scrollTop - clientHeight < 100) {
          eventLogScrollRef.current.scrollTop = eventLogScrollRef.current.scrollHeight
        }
      }
    })
  }, [eventLogs])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Error Banner */}
      {error && (
        <Card className="flex-shrink-0 border-destructive bg-destructive">
          <CardContent className="p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-destructive-foreground">
                <AlertCircle className="h-4 w-4" />
                <span className="text-sm">{error}</span>
              </div>
              <button
                onClick={() => setError(null)}
                className="text-destructive-foreground hover:text-destructive-foreground/80"
                aria-label="Dismiss error"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </CardContent>
        </Card>
      )}
      {/* Title Bar */}
      <Card className="flex-shrink-0">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-lg font-bold flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Report
          </CardTitle>
          <div className="flex items-center gap-4">
            {availableModels.length > 0 && (
              <div className="flex items-center gap-2">
                <label htmlFor="report-model-select" className="text-sm text-muted-foreground">
                  Model:
                </label>
                <select
                  id="report-model-select"
                  value={selectedModel || ""}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  disabled={loading}
                  className="px-2 py-1 text-sm border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {availableModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <select 
              className="bg-background border rounded px-2 py-1 text-sm"
              value={executionMode}
              onChange={(e) => setExecutionMode(e.target.value as 'local' | 'cloud_run_service' | 'cloud_run_job')}
            >
              {isDev ? (
                <>
                  <option value="cloud_run_service">Streaming</option>
                  <option value="cloud_run_job">Polling</option>
                </>
              ) : (
                <>
                  <option value="cloud_run_service">Cloud Run Service</option>
                  <option value="cloud_run_job">Cloud Run Job</option>
                </>
              )}
            </select>
            <Button 
              variant="outline" 
              size="icon" 
              onClick={handleNewReport}
              title="New Report"
              disabled={loading}
            >
              <Plus className="h-4 w-4" />
            </Button>
            {!jobId || status?.status === 'completed' ? (
              <button 
                onClick={startReport}
                disabled={loading}
                className="flex items-center gap-2 bg-primary text-primary-foreground px-3 py-1 rounded-md text-sm hover:bg-primary/90 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Start
              </button>
            ) : status && status.status !== 'running' && status.status !== 'cloud_run_job_submitted' ? (
              // Show Resume button if checkpoint exists but not running (and not completed)
              <button 
                onClick={resumeReport}
                disabled={loading}
                className="flex items-center gap-2 bg-primary text-primary-foreground px-3 py-1 rounded-md text-sm hover:bg-primary/90 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Resume
              </button>
            ) : (
              <button 
                onClick={stopReport}
                disabled={false}
                className="flex items-center gap-2 bg-destructive text-destructive-foreground px-3 py-1 rounded-md text-sm hover:bg-destructive/90"
              >
                <Square className="h-4 w-4" />
                Stop
              </button>
            )}
          </div>
        </CardHeader>
      </Card>

      {!jobId ? (
        <div className="flex-1 flex flex-col items-center justify-center py-20 text-center space-y-4">
          <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center">
            <FileText className="h-8 w-8 text-muted-foreground" />
          </div>
          <div>
            <h3 className="font-semibold">No active report generation</h3>
            <p className="text-sm text-muted-foreground">Select procedures and click 'Start' to generate a new report.</p>
          </div>
        </div>
      ) : (
        <>
          {/* Graph View + State View Side-by-Side */}
          <div className="flex-[2] flex gap-4 mt-4 flex-shrink-0" style={{ minHeight: '500px', minWidth: '100%' }}>
            <div className="flex-[3] flex-shrink-0" style={{ minHeight: '400px', minWidth: '60%', display: 'flex', flexDirection: 'column' }}>
              {API_URL && (
                <GraphView
                  apiUrl={API_URL}
                  token={token}
                  executionState={executionState || undefined}
                  flow="report"
                />
              )}
            </div>
            <div className="flex-[2] flex-shrink-0">
              <StateView 
                state={status?.state} 
                executionState={executionState}
                token={token}
                threadId={jobId}
              />
            </div>
          </div>

          {/* Event Log + Observability Side-by-Side */}
          <div className="flex-[1] min-h-0 flex gap-4 mt-4">
            {/* Event Log */}
            <Card className="flex-1 flex flex-col min-h-0">
              <CardHeader className="py-3 border-b flex-shrink-0">
                <CardTitle className="text-sm font-medium">Event Log</CardTitle>
              </CardHeader>
              <CardContent className="p-0 flex-1 min-h-0">
                <ScrollArea className="h-full" ref={eventLogScrollRef}>
                  <div className="flex flex-col divide-y bg-muted/30">
                    {eventLogs.length > 0 ? (
                      eventLogs.map((log, i) => {
                        // Prefer stream ts (ms); else parse [HH:mm:ss] from backend log format
                        const timeMatch = log.text.match(/^\[(\d{2}:\d{2}:\d{2})\]\s+/)
                        const timeStr =
                          log.ts != null
                            ? new Date(log.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
                            : timeMatch
                              ? timeMatch[1]
                              : null
                        const message = timeMatch && log.ts == null ? log.text.slice(timeMatch[0].length) : log.text
                        const isCompleted =
                          status?.status === 'completed' ||
                          message.toLowerCase().startsWith('completed:') ||
                          message.toLowerCase().includes('finished')
                        const logLines = message.split('\n')
                        const isMultiLine = logLines.length > 1

                        return (
                          <div key={i} className="px-4 py-2 flex items-start gap-3 text-xs">
                            {isCompleted ? (
                              <CheckCircle className="h-3 w-3 text-green-500 flex-shrink-0 mt-0.5" />
                            ) : (
                              <Loader2 className="h-3 w-3 animate-spin text-primary flex-shrink-0 mt-0.5" />
                            )}
                            <div className="flex-1 min-w-0">
                              {isMultiLine ? (
                                <div className="flex flex-col gap-1">
                                  {logLines.map((line, lineIdx) => (
                                    <span key={lineIdx} className={lineIdx === 0 ? "font-medium break-words" : "text-muted-foreground break-words"}>
                                      {line}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <span className="break-words">{message}</span>
                              )}
                            </div>
                            <span className="text-muted-foreground font-mono flex-shrink-0 text-[10px]">{timeStr ?? '—'}</span>
                          </div>
                        )
                      })
                    ) : (
                      <div className="p-4 text-center text-xs text-muted-foreground italic">
                        Waiting for activity...
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Observability */}
            <div className="flex-1 min-h-0">
              <ObservabilityWindow 
                executionState={executionState || null} 
                statusMetrics={status?.state?.execution_metrics}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
