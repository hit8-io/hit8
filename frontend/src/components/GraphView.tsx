import { useState, useEffect, useMemo } from 'react'
import ReactFlow, { Node, Edge, Background, Controls, useNodesState, useEdgesState, useReactFlow, Position } from 'reactflow'
import 'reactflow/dist/style.css'

// Suppress React Flow's false positive warning about nodeTypes/edgeTypes
// This warning is triggered by React Strict Mode even when props are stable
// We're not using custom nodeTypes/edgeTypes, so this warning is not applicable
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  const originalWarn = console.warn
  console.warn = (...args: unknown[]) => {
    const message = typeof args[0] === 'string' ? args[0] : String(args[0])
    // Suppress the specific React Flow warning about nodeTypes/edgeTypes
    if (message.includes('[React Flow]: It looks like you\'ve created a new nodeTypes or edgeTypes object')) {
      return // Suppress this specific warning
    }
    originalWarn.apply(console, args)
  }
}
import dagre from 'dagre'
import axios from 'axios'
import { Card, CardContent } from './ui/card'
import { getApiHeaders } from '../utils/api'
import type { ExecutionState } from '../types/execution'

interface GraphViewProps {
  apiUrl: string
  token: string | null
  executionState?: ExecutionState | null // Execution state from stream events
}

interface GraphStructure {
  nodes?: Array<{ id: string; name?: string; [key: string]: unknown }>
  edges?: Array<{ source: string; target: string; [key: string]: unknown }>
  [key: string]: unknown
}

const nodeWidth = 150
const nodeHeight = 50

// Removed all nodeTypes/edgeTypes code since we're using React Flow's defaults
// No custom node or edge types are needed for this implementation

// Component to fit view when nodes are loaded (must be inside ReactFlow context)
function FitViewOnLoad({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow()
  
  useEffect(() => {
    if (nodeCount > 0) {
      // Fit view after a short delay to ensure nodes are rendered
      const timeoutId = setTimeout(() => {
        fitView({ padding: 0.1, maxZoom: 1.5, minZoom: 0.5 })
      }, 100)
      return () => clearTimeout(timeoutId)
    }
  }, [nodeCount, fitView])
  
  return null
}

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

export default function GraphView({ apiUrl, token, executionState }: GraphViewProps) {
  
  const [graphStructure, setGraphStructure] = useState<GraphStructure | null>(null)
  
  // Use execution state from stream events (no polling)
  const currentExecutionState = executionState
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  // React Flow's useNodeOrEdgeTypes hook warns when it detects "new" objects
  // React Strict Mode can cause false positives for this warning
  // Memoize proOptions separately to ensure it's stable
  const proOptions = useMemo(() => ({ hideAttribution: true }), [])
  
  // Memoize the entire ReactFlow props object to ensure stable references
  // This prevents React Flow from detecting "new" props objects on each render
  const reactFlowProps = useMemo(() => ({
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    // Explicitly omit nodeTypes and edgeTypes - React Flow will use defaults
    proOptions,
  }), [nodes, edges, onNodesChange, onEdgesChange, proOptions])


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
          headers: getApiHeaders(token),
        })

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
      // Extract nodes and edges from LangGraph JSON structure
      // LangGraph JSON structure may vary, so we need to handle different formats
      let graphNodes: Node[] = []
      let graphEdges: Edge[] = []

      // Try to extract from common LangGraph JSON formats
      if (graphStructure.nodes && Array.isArray(graphStructure.nodes)) {
        graphNodes = graphStructure.nodes.map((node: { id: string; name?: string; [key: string]: unknown }) => ({
          id: node.id,
          data: { label: node.name || node.id },
          position: { x: 0, y: 0 }, // Temporary position, will be updated by dagre
        }))
      } else if (graphStructure.channels) {
        // Alternative format: channels-based
        const channelNodes = Object.keys(graphStructure.channels)
        graphNodes = channelNodes.map((id) => ({
          id,
          data: { label: id },
          position: { x: 0, y: 0 }, // Temporary position, will be updated by dagre
        }))
      } else {
        // Try to find nodes in other possible formats
        // Check if there's a 'nodes' key that's an object
        if (graphStructure.nodes && typeof graphStructure.nodes === 'object' && !Array.isArray(graphStructure.nodes)) {
          const nodeKeys = Object.keys(graphStructure.nodes)
          graphNodes = nodeKeys.map((id) => ({
            id,
            data: { label: id },
            position: { x: 0, y: 0 },
          }))
        }
      }

      if (graphStructure.edges && Array.isArray(graphStructure.edges)) {
        graphEdges = graphStructure.edges.map((edge: { source: string; target: string }) => ({
          id: `${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
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
                animated: false,
              })
            })
          }
        })
        graphEdges = channelEdges
      }

      // Apply layout
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(graphNodes, graphEdges)
      setNodes(layoutedNodes)
      setEdges(layoutedEdges)
    } catch {
      setError('Failed to process graph structure')
    }
  }, [graphStructure, setNodes, setEdges])

  // No polling needed - rely entirely on stream events for updates

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

    // Update node and edge styles based on execution state
    // Use functional updates to avoid needing nodes/edges in dependency array
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
      <CardContent className="flex-1 min-h-0 p-0 overflow-hidden">
        <div className="w-full h-full min-h-[400px]">
          <ReactFlow {...reactFlowProps}>
            <Background />
            <Controls />
            <FitViewOnLoad nodeCount={nodes.length} />
          </ReactFlow>
        </div>
      </CardContent>
    </Card>
  )
}

