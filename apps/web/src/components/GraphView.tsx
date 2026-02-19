import { useState, useEffect, useMemo, useRef } from 'react'
import { flushSync } from 'react-dom'
import ReactFlow, { Node, Edge, Background, Controls, useNodesState, useEdgesState, useReactFlow, NodeMouseHandler } from 'reactflow'
import 'reactflow/dist/style.css'
import axios from 'axios'
import { Card, CardContent } from './ui/card'
import { getApiHeaders } from '../utils/api'
import { getLayoutedElements } from '../utils/graphLayout'
import { GRAPH_VIEW_FIT_DELAY } from '../constants'
import type { ExecutionState, StreamEvent } from '../types/execution'
import { NodeInspectionModal } from './NodeInspectionModal'

// Suppress React Flow's false positive warnings in React Strict Mode
// These are known issues with React Flow and React Strict Mode double-rendering
if (import.meta.env.DEV) {
  const originalWarn = console.warn
  console.warn = (...args: unknown[]) => {
    const message = typeof args[0] === 'string' ? args[0] : String(args[0])
    // Suppress React Flow warnings that appear during initial render before dimensions are available
    if (
      message.includes('[React Flow]: It looks like you\'ve created a new nodeTypes or edgeTypes object') ||
      message.includes('[React Flow]: The React Flow parent container needs a width and a height to render the graph')
    ) {
      return // Suppress these specific warnings
    }
    originalWarn.apply(console, args)
  }
}

interface GraphViewProps {
  apiUrl: string
  token: string | null
  executionState?: ExecutionState | null // Execution state from stream events
  flow?: string // Flow name (e.g. 'chat' or 'report')
}

interface GraphNode {
  id: string
  name?: string
  [key: string]: unknown
}

interface GraphEdge {
  source: string
  target: string
  [key: string]: unknown
}

interface GraphStructure {
  nodes?: GraphNode[]
  edges?: GraphEdge[]
  [key: string]: unknown
}


// Define stable empty nodeTypes and edgeTypes objects outside the component
// This prevents React Flow from detecting "new" objects on each render
// React Flow will use its default node/edge types when these are empty objects
const nodeTypes = {}
const edgeTypes = {}

// Component to fit view when nodes are loaded (must be inside ReactFlow context)
function FitViewOnLoad({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow()
  
  useEffect(() => {
    if (nodeCount > 0) {
      // Fit view after a short delay to ensure nodes are rendered
      const timeoutId = setTimeout(() => {
        fitView({ padding: 0.1, maxZoom: 1.5, minZoom: 0.5 })
      }, GRAPH_VIEW_FIT_DELAY)
      return () => clearTimeout(timeoutId)
    }
  }, [nodeCount, fitView])
  
  return null
}

/**
 * Extract error message from API error response.
 * Handles various FastAPI error response formats.
 */
function extractErrorMessage(err: unknown): string {
  if (!axios.isAxiosError(err) || !err.response?.data) {
    return 'Failed to load graph structure'
  }

  // Access data safely without destructuring to avoid 'any' type issues
  const data = err.response.data as unknown
  const detail = (data as Record<string, unknown>)?.detail

  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const firstError = detail[0] as unknown
    if (typeof firstError === 'string') {
      return firstError
    }
    if (firstError && typeof firstError === 'object' && 'msg' in firstError) {
      return String((firstError as { msg: unknown }).msg)
    }
  }

  if (detail && typeof detail === 'object' && 'msg' in detail) {
    return String((detail as { msg: unknown }).msg)
  }

  if (typeof data === 'string') {
    return data
  }

  return 'Failed to load graph structure'
}

/**
 * Handle API error response with appropriate error state updates.
 */
function handleApiError(
  err: unknown,
  setError: (error: string | null) => void
): void {
  if (!axios.isAxiosError(err)) {
    setError('Failed to load graph structure')
    return
  }

  const status = err.response?.status

  // Handle 401 - token expired, wait for refresh
  if (status === 401) {
    setError(null)
    return
  }

  // Handle 422/400 - validation errors, check if org/project selected
  if (status === 422 || status === 400) {
    const org = localStorage.getItem('activeOrg')
    const project = localStorage.getItem('activeProject')
    if (!org || !project) {
      setError(null)
      return
    }
  }

  // Extract and set error message
  const errorMessage = extractErrorMessage(err)
  setError(errorMessage)
}


export default function GraphView({ apiUrl, token, executionState, flow }: Readonly<GraphViewProps>) {
  const [graphStructure, setGraphStructure] = useState<GraphStructure | null>(null)
  
  // Use execution state from stream events (no polling)
  const currentExecutionState = executionState
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const nodeUpdateVersionRef = useRef(0) // Track update version to force React Flow re-render
  const dynamicallyAddedNodesRef = useRef<Set<string>>(new Set()) // Track dynamically added nodes

  // Inspection modal state
  const [inspectionNode, setInspectionNode] = useState<string | null>(null)
  const [taskHistory, setTaskHistory] = useState<Array<{
    task_key?: string
    node_name: string
    run_id: string
    started_at: number
    ended_at?: number
    input_preview?: string
    output_preview?: string
    metadata?: Record<string, any>
  }>>([])

  // Extract task_history from state_snapshot events
  useEffect(() => {
    if (currentExecutionState?.streamEvents) {
      const snapshots = currentExecutionState.streamEvents.filter(
        (e): e is StreamEvent & { type: 'state_snapshot'; task_history?: any[] } =>
          e.type === 'state_snapshot'
      )
      if (snapshots.length > 0) {
        const latestSnapshot = snapshots[snapshots.length - 1]
        if (latestSnapshot.task_history && Array.isArray(latestSnapshot.task_history)) {
          setTaskHistory(latestSnapshot.task_history)
        }
      }
    }
  }, [currentExecutionState?.streamEvents])

  // Handle node click for inspection
  const onNodeClick: NodeMouseHandler = (_event, node) => {
    setInspectionNode(node.id)
  }
  

  // React Flow's useNodeOrEdgeTypes hook warns when it detects "new" objects
  // React Strict Mode can cause false positives for this warning
  // Memoize proOptions separately to ensure it's stable
  const proOptions = useMemo(() => {
    return { hideAttribution: true };
  }, [])
  
  // Memoize all ReactFlow props including stable nodeTypes/edgeTypes
  // Include nodeTypes and edgeTypes in the memoized object using stable external references
  // This ensures React Flow sees consistent prop object structure
  const prevNodesRef = useRef(nodes)
  const reactFlowProps = useMemo(() => {
    prevNodesRef.current = nodes
    return {
      nodes,
      edges,
      onNodesChange,
      onEdgesChange,
      nodeTypes, // Use stable external reference
      edgeTypes, // Use stable external reference
      proOptions,
    };
  }, [nodes, edges, onNodesChange, onEdgesChange, proOptions])


  // Track org/project selection to trigger re-fetch
  const [orgProjectKey, setOrgProjectKey] = useState<string>('')

  // Listen for localStorage changes
  useEffect(() => {
    const checkOrgProject = () => {
      const org = localStorage.getItem('activeOrg')
      const project = localStorage.getItem('activeProject')
      setOrgProjectKey(`${org || ''}:${project || ''}`)
    }

    // Check initially
    checkOrgProject()

    // Listen for storage events (from other tabs/windows)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'activeOrg' || e.key === 'activeProject') {
        checkOrgProject()
      }
    }

    // Poll for changes (since same-tab localStorage changes don't trigger storage events)
    const interval = setInterval(checkOrgProject, 500)

    window.addEventListener('storage', handleStorageChange)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      clearInterval(interval)
    }
  }, [])

  // Fetch graph structure when org/project selection changes
  useEffect(() => {
    const fetchGraphStructure = async () => {
      if (!apiUrl || !token || !flow) {
        setLoading(false)
        return
      }

      // Check if org/project are selected
      const org = localStorage.getItem('activeOrg')
      const project = localStorage.getItem('activeProject')
      
      if (!org || !project) {
        // Don't fetch if org/project not selected - this is expected
        setLoading(false)
        setError(null)
        setGraphStructure(null) // Clear previous structure
        return
      }

      try {
        setLoading(true)
        const flowParam = flow ? `?flow=${flow}` : ''
        const response = await axios.get(`${apiUrl}/graph/structure${flowParam}`, {
          headers: getApiHeaders(token),
        })

        setGraphStructure(response.data as GraphStructure)
        setError(null)
      } catch (err) {
        handleApiError(err, setError)
      } finally {
        setLoading(false)
      }
    }

    void fetchGraphStructure()
  }, [apiUrl, token, orgProjectKey, flow])

  // Convert graph structure to React Flow format and apply layout
  useEffect(() => {
    if (!graphStructure) return

    try {
      // Extract nodes and edges from LangGraph JSON structure
      // LangGraph returns standard format: { nodes: [...], edges: [...] }
      if (!graphStructure.nodes || !Array.isArray(graphStructure.nodes)) {
        setError('Invalid graph structure: nodes must be an array')
        return
      }

      if (!graphStructure.edges || !Array.isArray(graphStructure.edges)) {
        setError('Invalid graph structure: edges must be an array')
        return
      }

      // Convert nodes to React Flow format
      const graphNodes: Node[] = graphStructure.nodes.map(
        (node: { id: string; name?: string; [key: string]: unknown }) => ({
          id: node.id,
          data: { label: node.name || node.id },
          position: { x: 0, y: 0 }, // Temporary position, will be updated by dagre
        })
      )

      // Convert edges to React Flow format
      const graphEdges: Edge[] = graphStructure.edges.map(
        (edge: { source: string; target: string }) => ({
          id: `${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          animated: false,
        })
      )

      // Apply layout
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(graphNodes, graphEdges)
      setNodes(layoutedNodes)
      setEdges(layoutedEdges)
    } catch {
      setError('Failed to process graph structure')
    }
  }, [graphStructure, setNodes, setEdges])

  // No polling needed - rely entirely on stream events for updates

  // Add dynamic nodes from execution state (nodes that appear in events but not in graph structure)
  useEffect(() => {
    if (!currentExecutionState || !graphStructure) return

    // Helper function to create node label (moved inside to avoid dependency issues)
    const createNodeLabel = (nodeId: string): string => {
      return nodeId
        .replace(/^node_/, '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (l) => l.toUpperCase())
    }

    // Extract all node names from execution state
    const nodeNamesFromState = new Set<string>()
    
    // Extract from history
    if (currentExecutionState.history && Array.isArray(currentExecutionState.history)) {
      currentExecutionState.history.forEach((entry: unknown) => {
        if (entry && typeof entry === 'object') {
          if ('tasks' in entry && Array.isArray((entry as { tasks: unknown[] }).tasks)) {
            const tasks = (entry as { tasks: unknown[] }).tasks
            tasks.forEach((task: unknown) => {
              if (task && typeof task === 'object' && 'name' in task) {
                const nodeName = (task as { name: string }).name
                if (nodeName) {
                  nodeNamesFromState.add(nodeName)
                }
              }
            })
          }
          if ('node' in entry && typeof (entry as { node: unknown }).node === 'string') {
            const nodeName = (entry as { node: string }).node
            if (nodeName) {
              nodeNamesFromState.add(nodeName)
            }
          }
        }
      })
    }

    // Extract from streamEvents (node_start events)
    if (currentExecutionState.streamEvents) {
      currentExecutionState.streamEvents.forEach((event) => {
        if (event.type === 'node_start' && 'node' in event) {
          const nodeName = (event as { node: string }).node
          if (nodeName) {
            nodeNamesFromState.add(nodeName)
          }
        }
      })
    }

    // Add active nodes
    const activeNodes = currentExecutionState.next || []
    activeNodes.forEach((nodeName) => {
      if (nodeName) {
        nodeNamesFromState.add(nodeName)
      }
    })

    // Find nodes that need to be added (not in graph structure and not already added dynamically)
    setNodes((currentNodes) => {
      const existingNodeIds = new Set(currentNodes.map((n) => n.id))
      const nodesToAdd: Node[] = []

      nodeNamesFromState.forEach((nodeId) => {
        if (!existingNodeIds.has(nodeId) && !dynamicallyAddedNodesRef.current.has(nodeId)) {
          nodesToAdd.push({
            id: nodeId,
            data: { label: createNodeLabel(nodeId) },
            position: { x: 0, y: 0 },
          })
          dynamicallyAddedNodesRef.current.add(nodeId)
        }
      })

      // If we have nodes to add, re-apply layout
      if (nodesToAdd.length > 0) {
        const newNodes = [...currentNodes, ...nodesToAdd]
        const { nodes: layoutedNodes } = getLayoutedElements(newNodes, edges)
        return layoutedNodes
      }

      return currentNodes
    })
  }, [currentExecutionState, graphStructure, setNodes, edges])

  // Update node styles based on execution state and add dynamic nodes
  useEffect(() => {
    if (!currentExecutionState) {
      // Reset all nodes to default style
      setNodes((nds) =>
        nds.map((node) => ({
          ...node,
          style: { ...node.style, border: '1px solid #e2e8f0' },
        }))
      )
      setEdges((eds) =>
        eds.map((edge) => ({
          ...edge,
          animated: false,
          style: { stroke: '#b1b1b7' },
        }))
      )
      return
    }

    // Determine active nodes from next array, but also check streamEvents for node_start without node_end
    let activeNodes = currentExecutionState.next || []
    
    // Also check streamEvents to find nodes that started but haven't ended yet
    // This handles cases where next array might be temporarily empty
    if (currentExecutionState.streamEvents && currentExecutionState.streamEvents.length > 0) {
      const startedNodes = new Set<string>()
      const endedNodes = new Set<string>()
      
      // Process events in order to track which nodes are currently active
      currentExecutionState.streamEvents.forEach((event) => {
        if (event.type === 'node_start' && 'node' in event) {
          const nodeName = (event as { node: string }).node
          if (nodeName) {
            startedNodes.add(nodeName)
          }
        } else if (event.type === 'node_end' && 'node' in event) {
          const nodeName = (event as { node: string }).node
          if (nodeName) {
            endedNodes.add(nodeName)
          }
        }
      })
      
      // Nodes that started but haven't ended are active
      const activeFromEvents = Array.from(startedNodes).filter(node => !endedNodes.has(node))
      
      // Merge with next array, preferring next array if it has values
      if (activeNodes.length === 0 && activeFromEvents.length > 0) {
        activeNodes = activeFromEvents
      } else if (activeNodes.length > 0 && activeFromEvents.length > 0) {
        // Combine both, removing duplicates
        activeNodes = Array.from(new Set([...activeNodes, ...activeFromEvents]))
      }
    }
    
    // Extract visited nodes from history and streamEvents
    // LangGraph history structure: array of state snapshots, each with tasks array
    const visitedNodes: string[] = []
    if (currentExecutionState.history && Array.isArray(currentExecutionState.history)) {
      currentExecutionState.history.forEach((entry: unknown) => {
        if (entry && typeof entry === 'object') {
          // Check for tasks array in history entry
          if ('tasks' in entry && Array.isArray((entry as { tasks: unknown[] }).tasks)) {
            const tasks = (entry as { tasks: unknown[] }).tasks
            tasks.forEach((task: unknown) => {
              if (task && typeof task === 'object' && 'name' in task) {
                const nodeName = (task as { name: string }).name
                if (nodeName && !visitedNodes.includes(nodeName)) {
                  visitedNodes.push(nodeName)
                }
              }
            })
          }
          // Also check for direct node references in the entry
          if ('node' in entry && typeof (entry as { node: unknown }).node === 'string') {
            const nodeName = (entry as { node: string }).node
            if (nodeName && !visitedNodes.includes(nodeName)) {
              visitedNodes.push(nodeName)
            }
          }
        }
      })
    }
    
    // Also extract visited nodes from streamEvents (node_end events indicate visited nodes)
    if (currentExecutionState.streamEvents && currentExecutionState.streamEvents.length > 0) {
      currentExecutionState.streamEvents.forEach((event) => {
        if (event.type === 'node_end' && 'node' in event) {
          const nodeName = (event as { node: string }).node
          if (nodeName && !visitedNodes.includes(nodeName)) {
            visitedNodes.push(nodeName)
          }
        }
      })
    }
    
    // Also include active nodes in visited nodes to ensure they're highlighted
    // This ensures that nodes in the 'next' array are always highlighted
    activeNodes.forEach((nodeName) => {
      if (nodeName && !visitedNodes.includes(nodeName)) {
        visitedNodes.push(nodeName)
      }
    })

    // Update node and edge styles based on execution state
    // Use functional updates to avoid needing nodes/edges in dependency array
    // Force new array reference to ensure React Flow detects the change
    // Increment version to force React Flow to treat nodes as completely new
    nodeUpdateVersionRef.current += 1
    const updateVersion = nodeUpdateVersionRef.current
    
    // Helper function to update a single node
    const updateNode = (node: Node): Node => {
      const isActive = activeNodes.includes(node.id)
      const isVisited = visitedNodes.includes(node.id)
      

      // Only update nodes that have changed state (active or visited)
      // This prevents unnecessary updates to all nodes
      // Extract nested ternary operations into independent statements
      let expectedBorder: string
      if (isActive) {
        expectedBorder = '2px solid #22c55e'
      } else if (isVisited) {
        expectedBorder = '1px solid #94a3b8'
      } else {
        expectedBorder = '1px solid #e2e8f0'
      }
      
      let expectedBackgroundColor: string
      if (isActive) {
        expectedBackgroundColor = '#dcfce7'
      } else if (isVisited) {
        expectedBackgroundColor = '#f1f5f9'
      } else {
        expectedBackgroundColor = '#ffffff'
      }
      
      let className: string
      if (isActive) {
        className = 'node-active'
      } else if (isVisited) {
        className = 'node-visited'
      } else {
        className = 'node-default'
      }
      
      const needsUpdate = isActive || isVisited || 
        (node.style?.border !== expectedBorder) ||
        (node.style?.backgroundColor !== expectedBackgroundColor)
      
      if (!needsUpdate) {
        return node // Return unchanged node to avoid unnecessary re-renders
      }
      
      // Create new node object with updated style and className to force React Flow re-render
      // Use both style and className to ensure React Flow detects the change
      const updatedNode = {
        ...node,
        data: {
          ...(node.data as Record<string, unknown>),
          _updateVersion: updateVersion, // Use version number to force re-render
        },
        // Add className to force React Flow to update the DOM element
        className,
        // Create completely new style object (don't spread old style)
        style: {
          border: expectedBorder,
          backgroundColor: expectedBackgroundColor,
          transition: 'border 0.1s ease-in-out, background-color 0.1s ease-in-out', // Add transition to force repaint
        },
      }
      return updatedNode
    }

    // Helper function to update a single edge
    const updateEdge = (edge: Edge): Edge => {
      const isActive = activeNodes.includes(edge.target)
      return {
        ...edge,
        animated: isActive,
        style: {
          stroke: isActive ? '#22c55e' : '#b1b1b7',
        },
      }
    }

    // Helper function to update all nodes
    const updateAllNodes = (nds: Node[]): Node[] => nds.map(updateNode)

    // Helper function to update all edges
    const updateAllEdges = (eds: Edge[]): Edge[] => eds.map(updateEdge)
    
    // Add a small delay to allow React Flow to process previous updates
    // This prevents updates from being batched together
    const updateDelay = 50 // 50ms delay between updates
    setTimeout(() => {
      // Use flushSync to force immediate visual update (not batched)
      flushSync(() => {
        setNodes(updateAllNodes)
      })

      flushSync(() => {
        setEdges(updateAllEdges)
      })
      
      // Use requestAnimationFrame to ensure browser has a chance to repaint
      // This gives the browser a frame to render the visual updates
      requestAnimationFrame(() => {
        // Force a repaint by reading a layout property
        // This ensures the browser actually renders the changes
        if (document.body) {
          // Property read forces browser repaint (value intentionally unused)
          // eslint-disable-next-line @typescript-eslint/no-unused-expressions
          document.body.offsetHeight
        }
      })
    }, updateDelay)
  }, [currentExecutionState, setNodes, setEdges])


  if (loading) {
    return (
      <Card className="h-full flex items-center justify-center">
        <CardContent>
          <p className="text-muted-foreground">Loading graph...</p>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="h-full flex items-center justify-center">
        <CardContent>
          <p className="text-destructive text-sm">{error}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardContent className="flex-1 min-h-0 p-0 overflow-hidden flex flex-col">
        <div 
          className="w-full flex-1 min-h-[400px]"
          style={{ 
            width: '100%', 
            height: '100%', 
            minHeight: '400px',
            position: 'relative'
          }}
        >
          <ReactFlow {...reactFlowProps} onNodeClick={onNodeClick}>
            <Background />
            <Controls />
            <FitViewOnLoad nodeCount={nodes.length} />
          </ReactFlow>
        </div>
      </CardContent>
      <NodeInspectionModal
        open={inspectionNode !== null}
        onOpenChange={(open) => !open && setInspectionNode(null)}
        nodeName={inspectionNode}
        streamEvents={currentExecutionState?.streamEvents || []}
        taskHistory={taskHistory}
      />
    </Card>
  )
}

