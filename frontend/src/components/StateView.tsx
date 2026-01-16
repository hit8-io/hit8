import { FileText, Layers, BookOpen, FileCheck, Loader2, Download } from "lucide-react"
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card"
import { ScrollArea } from "./ui/scroll-area"
import { Progress } from "./ui/progress"
import type { ExecutionState, StreamEvent } from "../types/execution"
import { ClusterInspectionModal } from "./ClusterInspectionModal"
import { useState, useEffect, useMemo } from "react"
import { Button } from "./ui/button"
import { getApiHeaders } from "../utils/api"

interface Procedure {
  doc?: string;
  metadata?: {
    titel?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

interface Cluster {
  file_id?: string;
  department_name?: string;
  topic_name?: string;
  procedures?: unknown[];
  [key: string]: unknown;
}

interface ReportState {
  raw_procedures?: Procedure[];
  pending_clusters?: Cluster[];
  chapters?: string[];
  chapters_by_file_id?: Record<string, string>;
  final_report?: string | null;
}

interface StateViewProps {
  readonly state?: ReportState | null;
  readonly executionState?: ExecutionState | null;
  readonly token?: string;
  readonly threadId?: string | null;
}

export default function StateView({ state, executionState, token, threadId }: StateViewProps) {
  const [inspectionCluster, setInspectionCluster] = useState<Cluster | null>(null)
  const [downloadingReport, setDownloadingReport] = useState(false)
  const [taskHistory, setTaskHistory] = useState<Array<{
    task_key?: string
    node_name: string
    run_id: string
    started_at: number
    ended_at?: number
    input_preview?: string
    output_preview?: string
    metadata?: Record<string, unknown>
  }>>([])
  const [clusterStatus, setClusterStatus] = useState<Record<string, { status: string; started_at?: string; ended_at?: string; error?: string }>>({})

  // Extract task_history and cluster_status from state_snapshot events
  // Compute directly from streamEvents to avoid setState in useEffect
  const latestSnapshotForState = useMemo(() => {
    if (!executionState?.streamEvents) return null
    const snapshots = executionState.streamEvents.filter(
      (e): e is StreamEvent & { type: 'state_snapshot'; task_history?: Array<{
        task_key?: string
        node_name: string
        run_id: string
        started_at: number
        ended_at?: number
        input_preview?: string
        output_preview?: string
        metadata?: Record<string, unknown>
      }>; report_state?: { cluster_status?: Record<string, { status: string; started_at?: string; ended_at?: string; error?: string }> } } =>
        e.type === 'state_snapshot'
    )
    return snapshots.length > 0 ? snapshots[snapshots.length - 1] : null
  }, [executionState?.streamEvents]) // eslint-disable-line react-compiler/react-compiler

  // Update state from computed snapshot
  // Note: setState in useEffect is necessary here to extract data from stream events
  // eslint-disable-next-line react-hooks/exhaustive-deps, react-compiler/react-compiler
  useEffect(() => {
    if (latestSnapshotForState) {
      if (latestSnapshotForState.task_history && Array.isArray(latestSnapshotForState.task_history)) {
        // Type assertion: task_history is already validated in filter
        setTaskHistory(latestSnapshotForState.task_history as Array<{
          task_key?: string
          node_name: string
          run_id: string
          started_at: number
          ended_at?: number
          input_preview?: string
          output_preview?: string
          metadata?: Record<string, unknown>
        }>)
      }
      if (latestSnapshotForState.report_state?.cluster_status) {
        // Type assertion: cluster_status is already validated
        setClusterStatus(latestSnapshotForState.report_state.cluster_status as Record<string, { status: string; started_at?: string; ended_at?: string; error?: string }>)
      }
    }
  }, [latestSnapshotForState])

  const API_URL = import.meta.env.VITE_API_URL

  const handleDownloadFinalReport = async () => {
    if (!token || !threadId || !state.final_report) {
      alert("Cannot download final report: missing token, thread ID, or final report")
      return
    }

    if (!API_URL) {
      alert("API URL is not configured. Please check your environment settings.")
      return
    }

    setDownloadingReport(true)
    try {
      // For file downloads, we need auth headers but not Content-Type: application/json
      const headers: Record<string, string> = {}
      const apiHeaders = getApiHeaders(token)
      // Copy all headers except Content-Type (let the browser set it for file downloads)
      Object.keys(apiHeaders).forEach(key => {
        if (key.toLowerCase() !== 'content-type') {
          headers[key] = apiHeaders[key]
        }
      })

      const response = await fetch(`${API_URL}/report/${threadId}/final-report/download`, {
        method: 'GET',
        headers,
      })

      if (!response.ok) {
        let errorMessage = "Failed to download final report"
        try {
          const errorData = await response.json()
          if (errorData.detail) {
            errorMessage = errorData.detail
          }
        } catch {
          // If response is not JSON, use status text
          if (response.status === 401) {
            errorMessage = "Your session has expired. Please refresh the page and try again."
          } else if (response.status === 403) {
            errorMessage = "You do not have permission to download this report."
          } else if (response.status === 404) {
            errorMessage = "No final report available for download"
          } else {
            errorMessage = `Failed to download final report: ${response.status} ${response.statusText}`
          }
        }
        alert(errorMessage)
        return
      }

      // Get the blob and trigger download
      const blob = await response.blob()
      
      // Check if blob is empty or invalid
      if (blob.size === 0) {
        alert("Downloaded file is empty. Please try again.")
        return
      }

      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'final_report.docx'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "An unexpected error occurred while downloading the report"
      alert(`Error downloading final report: ${errorMessage}`)
      console.error("Error downloading final report:", error)
    } finally {
      setDownloadingReport(false)
    }
  }

  if (!state) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
        No state data available
      </div>
    )
  }

  // Extract active and completed cluster IDs from state_snapshot events (checkpoint-authoritative)
  const streamEvents = executionState?.streamEvents ?? []
  const activeClusterIds = new Set<string>()
  const completedClusterIds = new Set<string>()
  
  // Find the most recent state_snapshot event (most authoritative)
  let latestSnapshot: StreamEvent | null = null
  for (let i = streamEvents.length - 1; i >= 0; i--) {
    const event = streamEvents[i]
    if (event.type === 'state_snapshot') {
      latestSnapshot = event
      break
    }
  }
  
  // Use cluster_status from state_snapshot if available
  if (latestSnapshot && 'cluster_status' in latestSnapshot) {
    const clusterStatusData = (latestSnapshot as StreamEvent & { cluster_status?: { active_cluster_ids?: string[]; completed_cluster_ids?: string[] } }).cluster_status
    if (clusterStatusData) {
      if (Array.isArray(clusterStatusData.active_cluster_ids)) {
        clusterStatusData.active_cluster_ids.forEach((id: string) => activeClusterIds.add(id))
      }
      if (Array.isArray(clusterStatusData.completed_cluster_ids)) {
        clusterStatusData.completed_cluster_ids.forEach((id: string) => completedClusterIds.add(id))
      }
    }
  }
  
  // Fallback: also check if analyst_node is in next array
  const isAnalystActiveFromNext = executionState?.next?.includes('analyst_node') ?? false
  
  // Get clusters_all to determine the true total count and build the complete list
  // This is the authoritative source for all clusters (includes all: completed, active, and pending)
  const clustersAll = (state as Record<string, unknown>).clusters_all as Cluster[] | undefined || []
  
  // Calculate cluster progress
  const completedCount = state.chapters?.length ?? 0
  
  // Use clusters_all.length as the total (most reliable - includes all clusters)
  // Fallback to completedCount + pendingCount if clusters_all not available
  const pendingCount = state.pending_clusters?.length ?? 0
  const totalCount = clustersAll.length > 0 
    ? clustersAll.length 
    : (completedCount + pendingCount)
  
  const progressPercentage = totalCount > 0 ? (completedCount / totalCount) * 100 : 0

  // Create a unified list of all clusters from clusters_all (authoritative source)
  // This ensures all clusters always appear in the list, regardless of their status
  const allClusters: Array<{ 
    cluster: Cluster | null; 
    status: 'completed' | 'pending' | 'active'; 
    index: number;
    progress?: number; // Individual cluster progress (0-100)
  }> = []
  
  // Helper function to determine cluster status
  const determineClusterStatus = (cluster: Cluster | null, index: number): { isActive: boolean; isCompleted: boolean } => {
    let isActive = false
    let isCompleted = false
    
    if (cluster) {
      // First try to match by file_id (most reliable)
      if (cluster.file_id && typeof cluster.file_id === 'string') {
        isActive = activeClusterIds.has(cluster.file_id)
        isCompleted = completedClusterIds.has(cluster.file_id)
      }
      
      // If no match by file_id, try dept|topic (fallback for clusters without file_id)
      if (!isActive && !isCompleted) {
        // Extract department name safely
        let clusterDept = ''
        if (typeof cluster.department_name === 'string') {
          clusterDept = cluster.department_name
        } else if (cluster.department_name && typeof cluster.department_name === 'object') {
          const deptObj = cluster.department_name as Record<string, unknown>
          if ('text' in deptObj && typeof deptObj.text === 'string') {
            clusterDept = deptObj.text
          } else {
            clusterDept = JSON.stringify(cluster.department_name)
          }
        }
        
        // Extract topic name safely
        let clusterTopic = ''
        if (typeof cluster.topic_name === 'string') {
          clusterTopic = cluster.topic_name
        } else if (cluster.topic_name && typeof cluster.topic_name === 'object') {
          const topicObj = cluster.topic_name as Record<string, unknown>
          if ('text' in topicObj && typeof topicObj.text === 'string') {
            clusterTopic = topicObj.text
          } else {
            clusterTopic = JSON.stringify(cluster.topic_name)
          }
        }
        
        const clusterId = `${clusterDept}|${clusterTopic}`
        if (clusterId !== '|') {
          isActive = activeClusterIds.has(clusterId)
          isCompleted = completedClusterIds.has(clusterId)
        }
      }
    }
    
    // Fallback: if analyst_node is active but we couldn't match, mark first non-completed as active
    if (!isActive && !isCompleted && isAnalystActiveFromNext && index === 0) {
      isActive = true
    }
    
    return { isActive, isCompleted }
  }
  
  if (clustersAll.length > 0) {
    // Build list from clusters_all - this ensures all clusters are always visible
    clustersAll.forEach((cluster, i) => {
      const { isActive, isCompleted } = determineClusterStatus(cluster, i)
      
      // Determine status: completed > active > pending
      const status: 'completed' | 'pending' | 'active' = isCompleted ? 'completed' : (isActive ? 'active' : 'pending')
      const clusterProgress = isCompleted ? 100 : (isActive ? 50 : 0)
      
      allClusters.push({
        cluster,
        status,
        index: i,
        progress: clusterProgress
      })
    })
  } else {
    // Fallback: if clusters_all is not available, use the old logic
    // Add completed clusters from completedClusterIds
    completedClusterIds.forEach((fileId) => {
      allClusters.push({
        cluster: null,
        status: 'completed',
        index: allClusters.length,
        progress: 100
      })
    })
    
    // Also add any remaining completed clusters (by count)
    const completedFromCount = completedCount - completedClusterIds.size
    for (let i = 0; i < completedFromCount; i++) {
      allClusters.push({
        cluster: null,
        status: 'completed',
        index: allClusters.length,
        progress: 100
      })
    }
    
    // Add pending clusters
    if (state.pending_clusters) {
      state.pending_clusters.forEach((cluster, i) => {
        const { isActive, isCompleted } = determineClusterStatus(cluster, i)
        
        const clusterProgress = isCompleted ? 100 : (isActive ? 50 : 0)
        allClusters.push({
          cluster,
          status: isCompleted ? 'completed' : (isActive ? 'active' : 'pending'),
          index: completedCount + i,
          progress: clusterProgress
        })
      })
    }
  }

  return (
    <>
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-4 p-1">
        {/* Procedures */}
        <Card className="flex-shrink-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Procedures ({state.raw_procedures?.length || 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[200px] overflow-y-auto">
              <div className="p-4 space-y-2">
                {state.raw_procedures && state.raw_procedures.length > 0 ? (
                  state.raw_procedures.map((proc, i) => {
                    // Safely convert doc to string - handle both string and object cases
                    let doc: string
                    if (typeof proc.doc === 'string') {
                      doc = proc.doc
                    } else if (proc.doc && typeof proc.doc === 'object') {
                      // If doc is an object, try to extract text or stringify it
                      const docObj = proc.doc as Record<string, unknown>
                      if ('text' in docObj && typeof docObj.text === 'string') {
                        doc = docObj.text
                      } else if ('content' in docObj && typeof docObj.content === 'string') {
                        doc = docObj.content
                      } else {
                        doc = JSON.stringify(proc.doc)
                      }
                    } else {
                      doc = ''
                    }
                    // Safely convert titel to string
                    let titel: string | null = null
                    const rawTitel = proc.metadata?.titel
                    if (rawTitel) {
                      if (typeof rawTitel === 'string') {
                        titel = rawTitel
                      } else if (typeof rawTitel === 'object') {
                        const titelObj = rawTitel as Record<string, unknown>
                        if ('text' in titelObj && typeof titelObj.text === 'string') {
                          titel = titelObj.text
                        } else if ('content' in titelObj && typeof titelObj.content === 'string') {
                          titel = titelObj.content
                        } else {
                          titel = JSON.stringify(rawTitel)
                        }
                      }
                    }
                    return (
                      <div key={i} className="text-xs bg-muted p-2 rounded border">
                        <div className="font-semibold mb-1">
                          {doc}
                        </div>
                        {titel && (
                          <div className="text-muted-foreground">
                            {titel}
                          </div>
                        )}
                      </div>
                    )
                  })
                ) : (
                  <div className="text-xs text-muted-foreground italic text-center py-4">
                    No procedures
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Chapters (formerly Clusters) */}
        <Card className="flex-shrink-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <BookOpen className="h-4 w-4" />
              Chapters ({totalCount > 0 ? `${completedCount}/${totalCount} completed` : '0'})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[300px] overflow-y-auto">
              <div className="p-4 space-y-2">
                {totalCount > 0 ? (
                  <>
                    {/* Overall Progress */}
                    <div className="mb-3">
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-muted-foreground">Overall Progress</span>
                        <span className="font-medium">{Math.round(progressPercentage)}%</span>
                      </div>
                      <Progress value={progressPercentage} className="h-2" />
                    </div>
                    
                    {/* Cluster List */}
                    {allClusters.map((item, i) => {
                      const { cluster, status, progress = 0 } = item
                      const isCompleted = status === 'completed'
                      const isActive = status === 'active'
                      
                      // Determine background and border colors
                      let bgClass: string
                      let borderClass: string
                      if (isActive) {
                        bgClass = 'bg-green-50 dark:bg-green-950'
                        borderClass = 'border-green-300 dark:border-green-700'
                      } else if (isCompleted) {
                        bgClass = 'bg-blue-50 dark:bg-blue-950'
                        borderClass = 'border-blue-200 dark:border-blue-800'
                      } else {
                        bgClass = 'bg-muted'
                        borderClass = 'border-border'
                      }
                      
                      // Determine status badge colors
                      let badgeBgClass: string
                      let badgeTextClass: string
                      let statusText: string
                      if (isActive) {
                        badgeBgClass = 'bg-green-200 dark:bg-green-800'
                        badgeTextClass = 'text-green-800 dark:text-green-200'
                        statusText = 'Processing'
                      } else if (isCompleted) {
                        badgeBgClass = 'bg-blue-200 dark:bg-blue-800'
                        badgeTextClass = 'text-blue-800 dark:text-blue-200'
                        statusText = 'Completed'
                      } else {
                        badgeBgClass = 'bg-gray-200 dark:bg-gray-800'
                        badgeTextClass = 'text-gray-800 dark:text-gray-200'
                        statusText = 'Pending'
                      }
                      
                      // Determine cluster name
                      const clusterName = cluster
                        ? cluster.file_id || cluster.department_name || `Cluster ${i + 1}`
                        : `Cluster ${i + 1} (Completed)`
                      
                      return (
                        <div
                          key={i}
                          className={`text-xs p-2 rounded border transition-colors cursor-pointer hover:opacity-80 ${bgClass} ${borderClass}`}
                          onClick={() => cluster && setInspectionCluster(cluster)}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <div className="font-semibold flex items-center gap-2">
                              {isActive && <Loader2 className="h-3 w-3 animate-spin text-green-600" />}
                              {isCompleted && <FileCheck className="h-3 w-3 text-blue-600" />}
                              {clusterName}
                            </div>
                            <div className={`text-xs px-2 py-0.5 rounded ${badgeBgClass} ${badgeTextClass}`}>
                              {statusText}
                            </div>
                          </div>
                          {/* Individual cluster progress */}
                          <div className="mt-2">
                            <div className="flex items-center justify-between text-xs mb-1">
                              <span className="text-muted-foreground">Progress</span>
                              <span className="font-medium">{Math.round(progress ?? 0)}%</span>
                            </div>
                            <Progress value={progress ?? 0} className="h-1.5" />
                          </div>
                          {cluster && (
                            <>
                              {cluster.department_name && (() => {
                                let deptName: string
                                if (typeof cluster.department_name === 'string') {
                                  deptName = cluster.department_name
                                } else if (cluster.department_name && typeof cluster.department_name === 'object') {
                                  const deptObj = cluster.department_name as Record<string, unknown>
                                  deptName = ('text' in deptObj && typeof deptObj.text === 'string') 
                                    ? deptObj.text 
                                    : JSON.stringify(cluster.department_name)
                                } else {
                                  deptName = String(cluster.department_name)
                                }
                                return (
                                  <div className="text-muted-foreground mb-1 text-xs">
                                    Department: {deptName}
                                  </div>
                                )
                              })()}
                              {cluster.topic_name && (() => {
                                let topicName: string
                                if (typeof cluster.topic_name === 'string') {
                                  topicName = cluster.topic_name
                                } else if (cluster.topic_name && typeof cluster.topic_name === 'object') {
                                  const topicObj = cluster.topic_name as Record<string, unknown>
                                  topicName = ('text' in topicObj && typeof topicObj.text === 'string') 
                                    ? topicObj.text 
                                    : JSON.stringify(cluster.topic_name)
                                } else {
                                  topicName = String(cluster.topic_name)
                                }
                                return (
                                  <div className="text-muted-foreground mb-1 text-xs">
                                    Topic: {topicName}
                                  </div>
                                )
                              })()}
                              <div className="text-muted-foreground text-xs">
                                Procedures: {Array.isArray(cluster.procedures) ? cluster.procedures.length : 0}
                              </div>
                            </>
                          )}
                          {isCompleted && (
                            <div className="text-muted-foreground text-xs mt-1">
                              Chapter {i + 1} completed
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </>
                ) : (
                  <div className="text-xs text-muted-foreground italic text-center py-4">
                    No clusters
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Final Report */}
        <Card className="flex-shrink-0">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <FileCheck className="h-4 w-4" />
                Final Report
              </CardTitle>
              {state.final_report && token && threadId && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownloadFinalReport}
                  disabled={downloadingReport}
                  className="h-7 px-2"
                >
                  {downloadingReport ? (
                    <>
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      Downloading...
                    </>
                  ) : (
                    <>
                      <Download className="h-3 w-3 mr-1" />
                      Download
                    </>
                  )}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[300px] overflow-y-auto">
              <div className="p-4">
                {state.final_report ? (() => {
                  // Safely convert final_report to string
                  let finalReportText: string
                  if (typeof state.final_report === 'string') {
                    finalReportText = state.final_report
                  } else if (state.final_report && typeof state.final_report === 'object') {
                    const reportObj = state.final_report as Record<string, unknown>
                    if ('text' in reportObj && typeof reportObj.text === 'string') {
                      finalReportText = reportObj.text
                    } else if ('content' in reportObj && typeof reportObj.content === 'string') {
                      finalReportText = reportObj.content
                    } else {
                      finalReportText = JSON.stringify(state.final_report)
                    }
                  } else {
                    finalReportText = String(state.final_report)
                  }
                  return (
                    <div className="text-xs whitespace-pre-wrap break-words bg-muted p-3 rounded border">
                      {finalReportText}
                    </div>
                  )
                })() : (
                  <div className="text-xs text-muted-foreground italic text-center py-4">
                    No final report available yet
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
    <ClusterInspectionModal
      open={inspectionCluster !== null}
      onOpenChange={(open) => !open && setInspectionCluster(null)}
      cluster={inspectionCluster}
      streamEvents={streamEvents}
      taskHistory={taskHistory}
      chapters={state.chapters}
      chaptersByFileId={state.chapters_by_file_id}
      clusterStatus={clusterStatus}
    />
    </>
  )
}
