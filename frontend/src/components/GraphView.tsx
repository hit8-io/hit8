import { useState, useEffect, useRef } from 'react'
import ReactFlow, { Node, Edge, Background, Controls, useNodesState, useEdgesState, Position } from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import axios from 'axios'
import { Card, CardContent } from './ui/card'

interface GraphViewProps {
  apiUrl: string
  token: string | null
  threadId?: string | null
  isChatActive?: boolean
  executionState?: ExecutionState | null // Accept execution state from parent (streaming)
  onExecutionStateChange?: (state: ExecutionState | null) => void
}

interface GraphStructure {
  nodes?: Array<{ id: string; name?: string; [key: string]: unknown }>
  edges?: Array<{ source: string; target: string; [key: string]: unknown }>
  [key: string]: unknown
}

interface ExecutionState {
  next?: string[]
  history?: unknown[]
  values?: {
    messages?: unknown[]
    message_count?: number
  }
}

const nodeWidth = 150
const nodeHeight = 50

function getLayoutedElements(nodes: Node[], edges: Edge[], direction = 'TB') {
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({ rankdir: direction, nodesep: 50, ranksep: 100 })

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight })
  })

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  dagre.layout(dagreGraph)

  nodes.forEach((node) => {
    const nodeWithPosition = dagreGraph.node(node.id)
    node.targetPosition = Position.Top
    node.sourcePosition = Position.Bottom
    node.position = {
      x: nodeWithPosition.x - nodeWidth / 2,
      y: nodeWithPosition.y - nodeHeight / 2,
    }
  })

  return { nodes, edges }
}

export default function GraphView({ apiUrl, token, threadId, isChatActive, executionState: propExecutionState, onExecutionStateChange }: GraphViewProps) {
  const [graphStructure, setGraphStructure] = useState<GraphStructure | null>(null)
  const [executionState, setExecutionState] = useState<ExecutionState | null>(null)
  
  // Use prop execution state (from streaming) when available, otherwise use internal state (from polling)
  const currentExecutionState = propExecutionState ?? executionState
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 })

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  // Update container dimensions using ResizeObserver for accurate initial measurement
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        // Only update if we have valid dimensions
        if (rect.width > 0 && rect.height > 0) {
          setDimensions({ width: rect.width, height: rect.height })
        }
      }
    }

    // Use ResizeObserver to detect container size changes (triggers immediately if element has size)
    const resizeObserver = new ResizeObserver(() => {
      updateDimensions()
    })

    // Set up observer when ref is available
    const setupObserver = () => {
      if (containerRef.current) {
        resizeObserver.observe(containerRef.current)
        // Initial measurement
        updateDimensions()
        // Try multiple times to catch layout completion
        requestAnimationFrame(() => {
          updateDimensions()
          setTimeout(updateDimensions, 0)
          setTimeout(updateDimensions, 100)
        })
      }
    }

    // Try to set up immediately, or wait a bit if ref isn't ready
    if (containerRef.current) {
      setupObserver()
    } else {
      // Wait a bit for ref to be attached
      const timeoutId = setTimeout(setupObserver, 0)
      return () => {
        clearTimeout(timeoutId)
        resizeObserver.disconnect()
      }
    }

    // Also listen to window resize as fallback
    window.addEventListener('resize', updateDimensions)

    return () => {
      resizeObserver.disconnect()
      window.removeEventListener('resize', updateDimensions)
    }
  }, [graphStructure]) // Re-run when graph structure loads (ensures container is rendered)

  // Fetch graph structure on mount
  useEffect(() => {
    const fetchGraphStructure = async () => {
      if (!apiUrl || !token) {
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        const response = await axios.get(`${apiUrl}/graph/structure`, {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })

        console.log('Graph structure received:', JSON.stringify(response.data, null, 2))
        setGraphStructure(response.data)
        setError(null)
      } catch (err) {
        if (axios.isAxiosError(err)) {
          if (err.response?.status === 401) {
            // Token expired or invalid - don't show error, just wait for token refresh
            setError(null)
            return
          }
          const errorMessage = err.response?.data?.detail || 'Failed to load graph structure'
          setError(errorMessage)
        } else {
          setError('Failed to load graph structure')
        }
        console.error('Failed to fetch graph structure:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchGraphStructure()
  }, [apiUrl, token])

  // Convert graph structure to React Flow format and apply layout
  useEffect(() => {
    if (!graphStructure) return

    try {
      console.log('Processing graph structure:', graphStructure)
      // Extract nodes and edges from LangGraph JSON structure
      // LangGraph JSON structure may vary, so we need to handle different formats
      let graphNodes: Node[] = []
      let graphEdges: Edge[] = []

      // Try to extract from common LangGraph JSON formats
      if (graphStructure.nodes && Array.isArray(graphStructure.nodes)) {
        console.log('Found nodes array format')
        graphNodes = graphStructure.nodes.map((node: { id: string; name?: string; [key: string]: unknown }) => ({
          id: node.id,
          data: { label: node.name || node.id },
          type: 'default',
          position: { x: 0, y: 0 }, // Temporary position, will be updated by dagre
        }))
      } else if (graphStructure.channels) {
        console.log('Found channels format')
        // Alternative format: channels-based
        const channelNodes = Object.keys(graphStructure.channels)
        graphNodes = channelNodes.map((id) => ({
          id,
          data: { label: id },
          type: 'default',
          position: { x: 0, y: 0 }, // Temporary position, will be updated by dagre
        }))
      } else {
        // Try to find nodes in other possible formats
        console.log('Unknown format, checking all keys:', Object.keys(graphStructure))
        
        // Check if there's a 'nodes' key that's an object
        if (graphStructure.nodes && typeof graphStructure.nodes === 'object' && !Array.isArray(graphStructure.nodes)) {
          console.log('Found nodes object format')
          const nodeKeys = Object.keys(graphStructure.nodes)
          graphNodes = nodeKeys.map((id) => ({
            id,
            data: { label: id },
            type: 'default',
            position: { x: 0, y: 0 },
          }))
        }
        
        // If still no nodes, try to extract from the graph structure itself
        // LangGraph might store nodes differently
        if (graphNodes.length === 0) {
          console.warn('No nodes found in graph structure. Full structure:', JSON.stringify(graphStructure, null, 2))
        }
      }
      
      console.log('Extracted nodes:', graphNodes.map(n => n.id))

      if (graphStructure.edges && Array.isArray(graphStructure.edges)) {
        graphEdges = graphStructure.edges.map((edge: { source: string; target: string }) => ({
          id: `${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          type: 'smoothstep',
          animated: false,
        }))
      } else if (graphStructure.channels) {
        // Build edges from channels
        const channelEdges: Edge[] = []
        Object.entries(graphStructure.channels).forEach(([target, channel]: [string, unknown]) => {
          if (channel && typeof channel === 'object' && 'sources' in channel) {
            const sources = (channel as { sources: string[] }).sources
            sources.forEach((source: string) => {
              channelEdges.push({
                id: `${source}-${target}`,
                source,
                target,
                type: 'smoothstep',
                animated: false,
              })
            })
          }
        })
        graphEdges = channelEdges
      }

      // Apply layout
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(graphNodes, graphEdges)
      console.log('Final nodes after layout:', layoutedNodes.map(n => ({ id: n.id, label: n.data.label })))
      console.log('Final edges after layout:', layoutedEdges.map(e => ({ id: e.id, source: e.source, target: e.target })))
      setNodes(layoutedNodes)
      setEdges(layoutedEdges)
    } catch (err) {
      console.error('Failed to process graph structure:', err)
      setError('Failed to process graph structure')
    }
  }, [graphStructure, setNodes, setEdges])

  // Poll for execution state when chat is active
  useEffect(() => {
    if (!isChatActive || !threadId || !apiUrl || !token) return

    const pollState = async () => {
      try {
        const response = await axios.get(`${apiUrl}/graph/state`, {
          params: { thread_id: threadId },
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })

        console.log('Graph state response:', JSON.stringify(response.data, null, 2))
        setExecutionState(response.data)
        // Notify parent of state changes
        onExecutionStateChange?.(response.data)
      } catch (err) {
        // Silently fail - state polling is optional
        console.log('Failed to fetch graph state:', err)
      }
    }

    // Initial poll
    pollState()

    // Poll every 2-3 seconds
    const interval = setInterval(pollState, 2500)

    return () => clearInterval(interval)
  }, [isChatActive, threadId, apiUrl, token, onExecutionStateChange])

  // Update node styles based on execution state
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

    const activeNodes = currentExecutionState.next || []
    
    // Extract visited nodes from history
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

    // Debug logging - log full state to understand structure
    console.log('Execution state update:', {
      fullState: JSON.stringify(currentExecutionState, null, 2),
      activeNodes: JSON.stringify(activeNodes),
      visitedNodes: JSON.stringify(visitedNodes),
      messageCount: currentExecutionState.values?.message_count,
      historyLength: currentExecutionState.history?.length,
      history: JSON.stringify(currentExecutionState.history),
      nodeCount: nodes.length,
      nodeIds: JSON.stringify(nodes.map(n => n.id)),
      matchingActiveNodes: JSON.stringify(activeNodes.filter(id => nodes.some(n => n.id === id))),
      matchingVisitedNodes: JSON.stringify(visitedNodes.filter(id => nodes.some(n => n.id === id))),
    })

    setNodes((nds) =>
      nds.map((node) => {
        const isActive = activeNodes.includes(node.id)
        const isVisited = visitedNodes.includes(node.id)

        return {
          ...node,
          style: {
            ...node.style,
            border: isActive ? '2px solid #22c55e' : isVisited ? '1px solid #94a3b8' : '1px solid #e2e8f0',
            backgroundColor: isActive ? '#dcfce7' : isVisited ? '#f1f5f9' : '#ffffff',
          },
        }
      })
    )

    setEdges((eds) =>
      eds.map((edge) => {
        const isActive = activeNodes.includes(edge.target)
        return {
          ...edge,
          animated: isActive,
          style: {
            stroke: isActive ? '#22c55e' : '#b1b1b7',
          },
        }
      })
    )
  }, [currentExecutionState, setNodes, setEdges, nodes])

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
      <CardContent className="flex-1 min-h-0 p-0 overflow-hidden">
        <div 
          ref={containerRef}
          className="w-full h-full min-h-[400px]"
        >
          {dimensions.width > 0 && dimensions.height > 0 ? (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              fitView
              fitViewOptions={{ padding: 0.1, maxZoom: 1.5, minZoom: 0.5 }}
              proOptions={{ hideAttribution: true }}
            >
              <Background />
              <Controls />
            </ReactFlow>
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <p className="text-muted-foreground text-sm">Initializing graph view...</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

