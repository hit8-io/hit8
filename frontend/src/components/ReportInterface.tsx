import * as React from "react"
import { FileText, Play, Square, Loader2, CheckCircle } from "lucide-react"
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card"
import { getApiHeaders } from "../utils/api"

interface ReportProgress {
  chapters_completed: number;
  recent_logs: string[];
}

interface ReportStatus {
  status: 'running' | 'completed' | 'not_found' | 'cloud_run_job_submitted';
  progress?: ReportProgress;
  graph_state?: {
    visited_nodes: string[];
    next: string[];
  };
  result?: string;
}

interface ReportInterfaceProps {
  token: string;
  onExecutionStateUpdate?: (state: any) => void;
  org?: string;
  project?: string;
}

export default function ReportInterface({ token, onExecutionStateUpdate, org, project }: ReportInterfaceProps) {
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<ReportStatus | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [executionMode, setExecutionMode] = React.useState<'local' | 'cloud_run_service' | 'cloud_run_job'>(
    import.meta.env.DEV ? 'local' : 'cloud_run_service'
  );

  const API_URL = import.meta.env.VITE_API_URL;

  const startReport = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/report/start`, {
        method: 'POST',
        headers: getApiHeaders(token),
        body: JSON.stringify({
          procedures: [], // In a real case, we'd pass procedures here
          execution_mode: executionMode
        })
      });
      const data = await response.json();
      setJobId(data.job_id);
      setLoading(false);
    } catch (err) {
      console.error("Failed to start report", err);
      setLoading(false);
    }
  };

  const stopReport = async () => {
    if (!jobId) return;
    try {
      await fetch(`${API_URL}/report/${jobId}/stop`, {
        method: 'POST',
        headers: getApiHeaders(token)
      });
      setJobId(null);
      setStatus(null);
      if (onExecutionStateUpdate) onExecutionStateUpdate(null);
    } catch (err) {
      console.error("Failed to stop report", err);
    }
  };

  React.useEffect(() => {
    if (!jobId || status?.status === 'completed' || !org || !project) return;

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/report/${jobId}/status`, {
          headers: getApiHeaders(token)
        });
        const data = await response.json();
        setStatus(data);

        // Update global execution state for visualization
        if (onExecutionStateUpdate && data.graph_state) {
          onExecutionStateUpdate({
            next: data.graph_state.next,
            history: data.graph_state.visited_nodes.map((node: string) => ({ node })),
            values: {
              message_count: data.progress?.chapters_completed || 0,
              logs: data.progress?.recent_logs || []
            }
          });
        }
      } catch (err) {
        console.error("Failed to poll status", err);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [jobId, status, token, API_URL, org, project]);

  return (
    <div className="flex flex-col h-full space-y-4 overflow-hidden">
      <Card className="flex-shrink-0">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-lg font-bold flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Report Generation
          </CardTitle>
          <div className="flex items-center gap-2">
            <select 
              className="bg-background border rounded px-2 py-1 text-sm"
              value={executionMode}
              onChange={(e) => setExecutionMode(e.target.value as 'local' | 'cloud_run_service' | 'cloud_run_job')}
            >
              <option value="local">Local</option>
              <option value="cloud_run_service">Cloud Run Service</option>
              <option value="cloud_run_job">Cloud Run Job</option>
            </select>
            {!jobId ? (
              <button 
                onClick={startReport}
                disabled={loading}
                className="flex items-center gap-2 bg-primary text-primary-foreground px-3 py-1 rounded-md text-sm hover:bg-primary/90 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Start
              </button>
            ) : (
              <button 
                onClick={stopReport}
                className="flex items-center gap-2 bg-destructive text-destructive-foreground px-3 py-1 rounded-md text-sm hover:bg-destructive/90"
              >
                <Square className="h-4 w-4" />
                Stop
              </button>
            )}
          </div>
        </CardHeader>
      </Card>

      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {jobId && status && (
          <>
            <Card>
              <CardHeader className="py-3">
                <CardTitle className="text-sm font-medium">Job Status: {status.status.toUpperCase()}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pb-4">
                <div className="flex items-center gap-4">
                  <div className="flex-1 bg-secondary h-2 rounded-full overflow-hidden">
                    <div 
                      className="bg-primary h-full transition-all duration-500" 
                      style={{ width: `${(status.progress?.chapters_completed || 0) * 20}%` }} 
                    />
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {status.progress?.chapters_completed || 0} Chapters
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card className="flex-1">
              <CardHeader className="py-3 border-b">
                <CardTitle className="text-sm font-medium">Execution Logs</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="flex flex-col divide-y bg-muted/30">
                  {status.progress?.recent_logs.map((log, i) => (
                    <div key={i} className="px-4 py-2 flex items-center gap-3 text-xs">
                      {log.includes('finished') ? (
                        <CheckCircle className="h-3 w-3 text-green-500" />
                      ) : (
                        <Loader2 className="h-3 w-3 animate-spin text-primary" />
                      )}
                      <span className="text-muted-foreground font-mono">{new Date().toLocaleTimeString()}</span>
                      <span>{log}</span>
                    </div>
                  ))}
                  {!status.progress?.recent_logs.length && (
                    <div className="p-4 text-center text-xs text-muted-foreground italic">
                      Waiting for activity...
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {status.result && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-md">Final Report</CardTitle>
                </CardHeader>
                <CardContent className="prose prose-sm dark:prose-invert max-w-none">
                  <div className="bg-muted p-4 rounded-md border text-sm">
                    {status.result}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {!jobId && (
          <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center">
              <FileText className="h-8 w-8 text-muted-foreground" />
            </div>
            <div>
              <h3 className="font-semibold">No active report generation</h3>
              <p className="text-sm text-muted-foreground">Select procedures and click 'Start' to generate a new report.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
