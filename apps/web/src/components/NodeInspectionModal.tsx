import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogClose } from './ui/dialog'
import { ScrollArea, Card, CardContent, CardHeader, CardTitle } from '@hit8/ui'
import type { StreamEvent } from '../types/execution'

interface TaskInfo {
  task_key?: string
  node_name: string
  run_id: string
  started_at: number
  ended_at?: number
  input_preview?: string
  output_preview?: string
  metadata?: Record<string, any>
}

interface NodeInspectionModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  nodeName: string | null
  streamEvents: StreamEvent[]
  taskHistory?: TaskInfo[]
}

export function NodeInspectionModal({
  open,
  onOpenChange,
  nodeName,
  streamEvents,
  taskHistory = [],
}: NodeInspectionModalProps) {
  if (!nodeName) return null

  // Find all events related to this node
  const nodeEvents = streamEvents.filter(
    (event) =>
      (event.type === 'node_start' && 'node' in event && event.node === nodeName) ||
      (event.type === 'node_end' && 'node' in event && event.node === nodeName) ||
      (event.type === 'llm_start' && 'run_id' in event) ||
      (event.type === 'llm_end' && 'run_id' in event) ||
      (event.type === 'tool_start' && 'run_id' in event) ||
      (event.type === 'tool_end' && 'run_id' in event)
  )

  // Find tasks for this node from task_history
  const nodeTasks = taskHistory.filter((task) => task.node_name === nodeName)

  // Find LLM calls associated with this node (by run_id)
  const llmCalls = streamEvents.filter(
    (event) =>
      (event.type === 'llm_start' || event.type === 'llm_end') &&
      nodeTasks.some((task) => 'run_id' in event && event.run_id === task.run_id)
  )

  // Find tool calls associated with this node
  const toolCalls = streamEvents.filter(
    (event) =>
      (event.type === 'tool_start' || event.type === 'tool_end') &&
      nodeTasks.some((task) => 'run_id' in event && event.run_id === task.run_id)
  )

  // Get input/output previews from node events
  const nodeStartEvent = nodeEvents.find((e) => e.type === 'node_start' && 'node' in e && e.node === nodeName) as any
  const nodeEndEvent = nodeEvents.find((e) => e.type === 'node_end' && 'node' in e && e.node === nodeName) as any

  const inputPreview = nodeStartEvent?.input_preview || 'No input preview available'
  const outputPreview = nodeEndEvent?.output_preview || 'No output preview available'

  // Calculate total duration from tasks
  const totalDuration = nodeTasks.reduce((sum, task) => {
    if (task.ended_at && task.started_at) {
      return sum + (task.ended_at - task.started_at)
    }
    return sum
  }, 0)

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Node Inspection: {nodeName}</DialogTitle>
          <DialogDescription>
            Detailed information about node execution, tasks, and associated operations
          </DialogDescription>
          <DialogClose onClick={() => onOpenChange(false)} />
        </DialogHeader>

        <ScrollArea className="flex-1 px-6 py-4 max-h-[calc(90vh-120px)]">
          <div className="space-y-4">
            {/* Task Information */}
            {nodeTasks.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Task Information</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {nodeTasks.map((task, idx) => (
                    <div key={idx} className="border rounded p-3 space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-medium">Run ID:</span>
                        <span className="font-mono text-muted-foreground">{task.run_id}</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="font-medium">Started:</span>
                        <span>{formatTimestamp(task.started_at)}</span>
                      </div>
                      {task.ended_at && (
                        <>
                          <div className="flex justify-between text-xs">
                            <span className="font-medium">Ended:</span>
                            <span>{formatTimestamp(task.ended_at)}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="font-medium">Duration:</span>
                            <span>{formatDuration((task.ended_at - task.started_at) * 1000)}</span>
                          </div>
                        </>
                      )}
                      {task.metadata && Object.keys(task.metadata).length > 0 && (
                        <div className="mt-2 pt-2 border-t">
                          <div className="text-xs font-medium mb-1">Metadata:</div>
                          <pre className="text-xs bg-muted p-2 rounded overflow-auto">
                            {JSON.stringify(task.metadata, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  ))}
                  {nodeTasks.length > 1 && (
                    <div className="pt-2 border-t">
                      <div className="flex justify-between text-sm font-medium">
                        <span>Total Duration:</span>
                        <span>{formatDuration(totalDuration * 1000)}</span>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Input/Output Previews */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Input/Output</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <div className="text-xs font-medium mb-1">Input Preview:</div>
                  <div className="text-xs bg-muted p-2 rounded border font-mono whitespace-pre-wrap break-words">
                    {inputPreview}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-medium mb-1">Output Preview:</div>
                  <div className="text-xs bg-muted p-2 rounded border font-mono whitespace-pre-wrap break-words">
                    {outputPreview}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* LLM Calls */}
            {llmCalls.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">LLM Calls ({llmCalls.length / 2})</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {llmCalls
                    .filter((e) => e.type === 'llm_start')
                    .map((event, idx) => {
                      const llmStart = event as any
                      const llmEnd = llmCalls.find(
                        (e) => e.type === 'llm_end' && 'run_id' in e && e.run_id === llmStart.run_id
                      ) as any
                      return (
                        <div key={idx} className="border rounded p-3 space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="font-medium">Model:</span>
                            <span>{llmStart.model || 'Unknown'}</span>
                          </div>
                          {llmStart.input_preview && (
                            <div>
                              <div className="text-xs font-medium mb-1">Input:</div>
                              <div className="text-xs bg-muted p-2 rounded border font-mono whitespace-pre-wrap break-words">
                                {llmStart.input_preview}
                              </div>
                            </div>
                          )}
                          {llmEnd?.output_preview && (
                            <div>
                              <div className="text-xs font-medium mb-1">Output:</div>
                              <div className="text-xs bg-muted p-2 rounded border font-mono whitespace-pre-wrap break-words">
                                {llmEnd.output_preview}
                              </div>
                            </div>
                          )}
                          {llmEnd?.token_usage && (
                            <div className="flex justify-between text-xs pt-1 border-t">
                              <span>Tokens:</span>
                              <span>{JSON.stringify(llmEnd.token_usage)}</span>
                            </div>
                          )}
                        </div>
                      )
                    })}
                </CardContent>
              </Card>
            )}

            {/* Tool Calls */}
            {toolCalls.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Tool Calls ({toolCalls.length / 2})</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {toolCalls
                    .filter((e) => e.type === 'tool_start')
                    .map((event, idx) => {
                      const toolStart = event as any
                      const toolEnd = toolCalls.find(
                        (e) => e.type === 'tool_end' && 'tool_name' in e && e.tool_name === toolStart.tool_name
                      ) as any
                      return (
                        <div key={idx} className="border rounded p-3 space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className="font-medium">Tool:</span>
                            <span className="font-mono">{toolStart.tool_name || 'Unknown'}</span>
                          </div>
                          {toolStart.args_preview && (
                            <div>
                              <div className="text-xs font-medium mb-1">Arguments:</div>
                              <div className="text-xs bg-muted p-2 rounded border font-mono whitespace-pre-wrap break-words">
                                {toolStart.args_preview}
                              </div>
                            </div>
                          )}
                          {toolEnd?.result_preview && (
                            <div>
                              <div className="text-xs font-medium mb-1">Result:</div>
                              <div className="text-xs bg-muted p-2 rounded border font-mono whitespace-pre-wrap break-words">
                                {toolEnd.result_preview}
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                </CardContent>
              </Card>
            )}

            {/* Event Timeline */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Event Timeline</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {nodeEvents.map((event, idx) => (
                    <div key={idx} className="text-xs border rounded p-2">
                      <div className="flex justify-between">
                        <span className="font-medium">{event.type}</span>
                        {'run_id' in event && event.run_id && (
                          <span className="font-mono text-muted-foreground text-[10px]">{event.run_id}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
