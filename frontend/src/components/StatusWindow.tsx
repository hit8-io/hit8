import { useState, useEffect, useRef, useMemo } from 'react'
import { Card, CardContent } from './ui/card'
import { ScrollArea } from './ui/scroll-area'
import type { ExecutionState } from '../types/execution'

interface LogEntry {
  id: string
  node: string // Single node name
  timestamp: Date
  messageCount: number
  status: 'active' | 'idle' | 'processing'
}

interface StatusWindowProps {
  executionState: ExecutionState | null
  isLoading?: boolean
}

export default function StatusWindow({ executionState, isLoading }: StatusWindowProps) {
  const [logEntries, setLogEntries] = useState<LogEntry[]>([])
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  // Track entries by node name for updates
  const entriesByNodeRef = useRef<Map<string, string>>(new Map()) // node -> entry id
  const hasInitializedRef = useRef<boolean>(false)

  // Extract and memoize state values for stable comparison
  // Use JSON.stringify for array comparison to avoid reference issues
  const nodesKey = JSON.stringify((executionState?.next || []).sort())
  const messageCount = executionState?.values?.message_count ?? executionState?.values?.messages?.length ?? 0
  
  const stateValues = useMemo(() => {
    const nodes = executionState?.next || []
    const sortedNodes = [...nodes].sort()
    
    // Status logic: prioritize active nodes, then loading state, then idle
    // "active" = nodes are executing
    // "processing" = waiting for execution to start (isLoading but no active nodes yet)
    // "idle" = no activity
    const status: 'active' | 'idle' | 'processing' = 
      nodes.length > 0 ? 'active' :  // Nodes are active
      (isLoading ? 'processing' : 'idle')  // Waiting for execution or idle
    
    return {
      nodes: sortedNodes,
      messageCount,
      status,
      stateKey: JSON.stringify({ nodes: sortedNodes, messageCount, status }),
    }
  }, [
    nodesKey, // Use stringified array for stable comparison
    messageCount,
    isLoading,
  ])

  // Update log entries: create new entry for each new node, update existing entries when status changes
  useEffect(() => {
    const currentNodes = stateValues.nodes
    const currentMessageCount = stateValues.messageCount
    const currentStatus = stateValues.status
    
    // Skip initial empty state
    if (!hasInitializedRef.current && 
        currentStatus === 'idle' && 
        currentMessageCount === 0 && 
        currentNodes.length === 0) {
      return
    }
    
    hasInitializedRef.current = true

    setLogEntries((prev) => {
      // Build map of existing entries by node name
      const entriesByNode = new Map<string, LogEntry>()
      prev.forEach(entry => {
        entriesByNode.set(entry.node, entry)
      })
      
      const updated: LogEntry[] = []
      const activeNodeSet = new Set(currentNodes)
      
      // Process all nodes that have ever been active (from previous entries)
      const allKnownNodes = new Set([
        ...Array.from(entriesByNode.keys()),
        ...currentNodes
      ])
      
      allKnownNodes.forEach(nodeName => {
        const existingEntry = entriesByNode.get(nodeName)
        const isCurrentlyActive = activeNodeSet.has(nodeName)
        
        if (existingEntry) {
          // Update existing entry
          updated.push({
            ...existingEntry,
            status: isCurrentlyActive ? 'active' : 'idle',
            messageCount: currentMessageCount,
          })
        } else if (isCurrentlyActive) {
          // Create new entry for newly active node
          const newEntry: LogEntry = {
            id: `${Date.now()}-${Math.random()}`,
            node: nodeName,
            timestamp: new Date(),
            messageCount: currentMessageCount,
            status: 'active',
          }
          updated.push(newEntry)
          entriesByNodeRef.current.set(nodeName, newEntry.id)
        }
        // If node is not active and never had an entry, don't create one
      })
      
      return updated
    })

    // Auto-scroll to bottom when entries are updated
    requestAnimationFrame(() => {
      if (scrollAreaRef.current) {
        scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight
      }
    })
  }, [
    nodesKey, // Use stringified nodes key for stable comparison
    stateValues.status,
    stateValues.messageCount, // Include messageCount to update it in entries
  ])

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardContent className="flex-1 min-h-0 p-4">
        <ScrollArea className="h-full" ref={scrollAreaRef}>
          <div className="space-y-2">
            {logEntries.length === 0 ? (
              <div className="text-xs text-muted-foreground py-4 text-center">No execution events yet</div>
            ) : (
              logEntries.map((entry) => (
                <div
                  key={entry.id}
                  className="border rounded p-2 bg-muted/30 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-muted-foreground">
                        {entry.timestamp.toLocaleTimeString()}
                      </span>
                      <span className="text-xs font-mono text-primary font-semibold">
                        {entry.node}
                      </span>
                    </div>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        entry.status === 'active'
                          ? 'bg-green-500/20 text-green-600'
                          : entry.status === 'processing'
                          ? 'bg-blue-500/20 text-blue-600'
                          : 'bg-gray-500/20 text-gray-600'
                      }`}
                    >
                      {entry.status}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Messages: <span className="font-mono">{entry.messageCount}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

