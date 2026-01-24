import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogClose } from './ui/dialog'
import { ScrollArea } from './ui/scroll-area'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'
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

interface Cluster {
  file_id?: string
  department_name?: string
  topic_name?: string
  procedures?: unknown[]
  [key: string]: unknown
}

interface ClusterInspectionModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  cluster: Cluster | null
  streamEvents: StreamEvent[]
  taskHistory?: TaskInfo[]
  chapters?: string[]
  chaptersByFileId?: Record<string, string>
  clusterStatus?: Record<string, { status: string; started_at?: string; ended_at?: string; error?: string; retry_count?: number }>
}

export function ClusterInspectionModal({
  open,
  onOpenChange,
  cluster,
  streamEvents,
  taskHistory = [],
  chapters = [],
  chaptersByFileId = {},
  clusterStatus = {},
}: ClusterInspectionModalProps) {
  if (!cluster) return null

  const fileId = cluster.file_id
  const departmentName = typeof cluster.department_name === 'string' 
    ? cluster.department_name 
    : (cluster.department_name as any)?.text || String(cluster.department_name || '')
  const topicName = typeof cluster.topic_name === 'string'
    ? cluster.topic_name
    : (cluster.topic_name as any)?.text || String(cluster.topic_name || '')
  const procedureCount = Array.isArray(cluster.procedures) ? cluster.procedures.length : 0

  // Find tasks associated with this cluster (by file_id)
  const clusterTasks = fileId
    ? taskHistory.filter(
        (task) =>
          task.node_name === 'analyst_node' &&
          task.metadata?.file_id === fileId
      )
    : []

  // Find chapter for this cluster
  // Use chapters_by_file_id if available (most reliable - maps file_id to chapter text)
  // If chaptersByFileId exists but doesn't have this file_id, return null (can't match reliably)
  // If chaptersByFileId doesn't exist at all, fallback to first chapter (legacy support)
  const clusterChapter = fileId
    ? (chaptersByFileId && Object.keys(chaptersByFileId).length > 0
        ? chaptersByFileId[fileId] || null
        : (chapters.length > 0 ? chapters[0] : null))
    : null

  // Get status information
  const status = fileId ? clusterStatus[fileId] : null
  const statusHistory: Array<{ status: string; timestamp: string }> = []
  if (status) {
    if (status.started_at) {
      statusHistory.push({ status: 'active', timestamp: status.started_at })
    }
    if (status.ended_at) {
      statusHistory.push({ status: 'completed', timestamp: status.ended_at })
    }
    if (status.error) {
      statusHistory.push({ status: 'error', timestamp: status.ended_at || status.started_at || '' })
    }
  }

  // Find events related to this cluster's tasks
  const relatedEvents = clusterTasks.length > 0
    ? streamEvents.filter(
        (event) =>
          clusterTasks.some((task) => 'run_id' in event && event.run_id === task.run_id)
      )
    : []

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString()
    } catch {
      return timestamp
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Cluster Inspection</DialogTitle>
          <DialogDescription>
            Detailed information about cluster processing, metadata, and associated tasks
          </DialogDescription>
          <DialogClose onClick={() => onOpenChange(false)} />
        </DialogHeader>

        <ScrollArea className="flex-1 px-6 py-4 max-h-[calc(90vh-120px)]">
          <div className="space-y-4">
            {/* Cluster Metadata */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Cluster Metadata</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {fileId && (
                  <div className="flex justify-between text-xs">
                    <span className="font-medium">File ID:</span>
                    <span className="font-mono text-muted-foreground">{fileId}</span>
                  </div>
                )}
                <div className="flex justify-between text-xs">
                  <span className="font-medium">Department:</span>
                  <span>{departmentName || 'N/A'}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="font-medium">Topic:</span>
                  <span>{topicName || 'N/A'}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="font-medium">Procedures:</span>
                  <span>{procedureCount}</span>
                </div>
                {status && (() => {
                  const isFailed = status.status === 'failed'
                  const retryCount = status.retry_count || 0
                  const hasRetries = retryCount > 0
                  
                  let statusColorClass: string
                  let statusDisplay: string
                  
                  if (isFailed) {
                    statusColorClass = 'text-red-600'
                    statusDisplay = 'Failed'
                  } else if (hasRetries) {
                    statusColorClass = 'text-orange-600'
                    statusDisplay = `Retrying (${retryCount})`
                  } else if (status.status === 'completed') {
                    statusColorClass = 'text-green-600'
                    statusDisplay = 'Completed'
                  } else if (status.status === 'active') {
                    statusColorClass = 'text-blue-600'
                    statusDisplay = 'Active'
                  } else {
                    statusColorClass = 'text-gray-600'
                    statusDisplay = status.status
                  }
                  
                  return (
                    <div className="flex justify-between text-xs">
                      <span className="font-medium">Status:</span>
                      <span className={`font-semibold ${statusColorClass}`}>
                        {statusDisplay}
                      </span>
                    </div>
                  )
                })()}
              </CardContent>
            </Card>

            {/* State Transitions */}
            {statusHistory.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">State Transitions</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {statusHistory.map((transition, idx) => {
                      const status = fileId ? clusterStatus[fileId] : null
                      const retryCount = status?.retry_count || 0
                      const hasRetries = retryCount > 0
                      const isFailed = transition.status === 'error' || transition.status === 'failed'
                      
                      let dotColorClass: string
                      if (isFailed) {
                        dotColorClass = 'bg-red-500'
                      } else if (hasRetries && transition.status === 'active') {
                        dotColorClass = 'bg-orange-500'
                      } else if (transition.status === 'completed') {
                        dotColorClass = 'bg-green-500'
                      } else if (transition.status === 'active') {
                        dotColorClass = 'bg-blue-500'
                      } else {
                        dotColorClass = 'bg-gray-500'
                      }
                      
                      return (
                        <div key={idx} className="flex items-center gap-2 text-xs border rounded p-2">
                          <span className={`w-2 h-2 rounded-full ${dotColorClass}`} />
                          <span className="font-medium capitalize">
                            {hasRetries && transition.status === 'active' ? `Retrying (${retryCount})` : transition.status}
                          </span>
                          <span className="text-muted-foreground ml-auto">
                            {formatTimestamp(transition.timestamp)}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Associated Tasks */}
            {clusterTasks.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Associated Node Executions ({clusterTasks.length})</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {clusterTasks.map((task, idx) => (
                    <div key={idx} className="border rounded p-3 space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-medium">Node:</span>
                        <span>{task.node_name}</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="font-medium">Run ID:</span>
                        <span className="font-mono text-muted-foreground">{task.run_id}</span>
                      </div>
                      {task.input_preview && (
                        <div>
                          <div className="text-xs font-medium mb-1">Input:</div>
                          <div className="text-xs bg-muted p-2 rounded border font-mono whitespace-pre-wrap break-words">
                            {task.input_preview}
                          </div>
                        </div>
                      )}
                      {task.output_preview && (
                        <div>
                          <div className="text-xs font-medium mb-1">Output:</div>
                          <div className="text-xs bg-muted p-2 rounded border font-mono whitespace-pre-wrap break-words">
                            {task.output_preview}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Chapter Content */}
            {clusterChapter && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Generated Chapter</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-xs bg-muted p-3 rounded border whitespace-pre-wrap break-words max-h-[300px] overflow-auto">
                    {typeof clusterChapter === 'string' 
                      ? clusterChapter 
                      : (clusterChapter && typeof clusterChapter === 'object'
                        ? ((clusterChapter as any)?.text || (clusterChapter as any)?.content || JSON.stringify(clusterChapter))
                        : String(clusterChapter ?? ''))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Related Events */}
            {relatedEvents.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Related Events ({relatedEvents.length})</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-1 max-h-[200px] overflow-auto">
                    {relatedEvents.map((event, idx) => (
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
            )}

            {/* Procedures List */}
            {procedureCount > 0 && Array.isArray(cluster.procedures) && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Procedures ({procedureCount})</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-1 max-h-[200px] overflow-auto">
                    {cluster.procedures.slice(0, 10).map((proc: any, idx: number) => (
                      <div key={idx} className="text-xs border rounded p-2">
                        <div className="font-medium">
                          {typeof proc.doc === 'string' ? proc.doc : JSON.stringify(proc.doc || {}).slice(0, 100)}
                        </div>
                      </div>
                    ))}
                    {procedureCount > 10 && (
                      <div className="text-xs text-muted-foreground text-center py-2">
                        ... and {procedureCount - 10} more procedures
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
