import { useState, useEffect, useMemo, useRef } from 'react'
import { flushSync } from 'react-dom'
import ReactFlow, { Node, Edge, Background, Controls, useNodesState, useEdgesState, useReactFlow } from 'reactflow'
import 'reactflow/dist/style.css'
import axios from 'axios'
import { Card, CardContent } from './ui/card'
import { getApiHeaders } from '../utils/api'
import { getLayoutedElements } from '../utils/graphLayout'
import { GRAPH_VIEW_FIT_DELAY } from '../constants'
import type { ExecutionState } from '../types/execution'

// Suppress React Flow's false positive warning about nodeTypes/edgeTypes in React Strict Mode
// This is a known issue: https://github.com/xyflow/xyflow/issues/3923
// The warning appears even when nodeTypes/edgeTypes are properly defined outside the component
if (import.meta.env.DEV) {
  const originalWarn = console.warn
  console.warn = (...args: unknown[]) => {
    const message = typeof args[0] === 'string' ? args[0] : String(args[0])
    // Suppress only the specific React Flow nodeTypes/edgeTypes warning
    if (message.includes('[React Flow]: It looks like you\'ve created a new nodeTypes or edgeTypes object')) {
      return // Suppress this specific warning
    }
    originalWarn.apply(console, args)
  }
}

interface GraphViewProps {
  apiUrl: string
  token: string | null
  executionState?: ExecutionState | null // Execution state from stream events
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


export default function GraphView({ apiUrl, token, executionState }: GraphViewProps) {
  const [graphStructure, setGraphStructure] = useState<GraphStructure | null>(null)
  
  // Use execution state from stream events (no polling)
  const currentExecutionState = executionState
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const nodeUpdateVersionRef = useRef(0) // Track update version to force React Flow re-render

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
      if (!apiUrl || !token) {
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
          if (err.response?.status === 422 || err.response?.status === 400) {
            // Validation error - might be missing headers
            // Don't show error if org/project not selected (expected)
            const org = localStorage.getItem('activeOrg')
            const project = localStorage.getItem('activeProject')
            if (!org || !project) {
              setError(null)
              return
            }
          }
          // Handle error response - detail might be a string, object, or array
          let errorMessage = 'Failed to load graph structure'
          if (err.response?.data) {
            const detail = err.response.data.detail
            if (typeof detail === 'string') {
              errorMessage = detail
            } else if (Array.isArray(detail) && detail.length > 0) {
              // FastAPI validation errors are arrays
              const firstError = detail[0]
              if (typeof firstError === 'string') {
                errorMessage = firstError
              } else if (firstError && typeof firstError === 'object' && 'msg' in firstError) {
                errorMessage = String(firstError.msg)
              }
            } else if (detail && typeof detail === 'object' && 'msg' in detail) {
              errorMessage = String(detail.msg)
            } else if (typeof err.response.data === 'string') {
              errorMessage = err.response.data
            }
          }
          setError(errorMessage)
        } else {
          setError('Failed to load graph structure')
        }
      } finally {
        setLoading(false)
      }
    }

    fetchGraphStructure()
  }, [apiUrl, token, orgProjectKey])

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

      // Add all possible tool nodes from the start (we know what tools are available)
      const allToolNodeNames = [
        'node_procedures_vector_search',
        'node_regelgeving_vector_search',
        // Future tools (commented out until enabled):
        // 'node_fetch_webpage',
        // 'node_generate_docx',
        // 'node_generate_xlsx',
        // 'node_extract_entities',
        // 'node_query_knowledge_graph',
        // 'node_get_procedure',
        // 'node_get_regelgeving',
      ]
      
      const existingNodeIds = new Set(graphNodes.map((n) => n.id))
      
      // Add tool nodes that aren't already in the graph
      allToolNodeNames.forEach((toolNodeId) => {
        if (!existingNodeIds.has(toolNodeId)) {
          const label = toolNodeId
            .replace(/^node_/, '')
            .replace(/_/g, ' ')
            .replace(/\b\w/g, (l) => l.toUpperCase())
          graphNodes.push({
            id: toolNodeId,
            data: { label },
            position: { x: 0, y: 0 },
          })
        }
      })
      
      // Add edges for tool nodes: agent -> tool -> agent
      // Hide the generic "tools" node by not creating edges to/from it
      const agentNodeExists = existingNodeIds.has('agent')
      if (agentNodeExists) {
        allToolNodeNames.forEach((toolNodeId) => {
          // Edge from agent to tool node
          const agentToToolId = `agent-${toolNodeId}`
          const edgeExists = graphEdges.some((e) => e.id === agentToToolId)
          if (!edgeExists) {
            graphEdges.push({
              id: agentToToolId,
              source: 'agent',
              target: toolNodeId,
              animated: false,
            })
          }
          
          // Edge from tool node back to agent
          const toolToAgentId = `${toolNodeId}-agent`
          const edgeExists2 = graphEdges.some((e) => e.id === toolToAgentId)
          if (!edgeExists2) {
            graphEdges.push({
              id: toolToAgentId,
              source: toolNodeId,
              target: 'agent',
              animated: false,
            })
          }
        })
        
        // Remove edges to/from the generic "tools" node since we have individual tool nodes
        graphEdges = graphEdges.filter(
          (edge) => edge.source !== 'tools' && edge.target !== 'tools'
        )
      }
      
      // Hide the generic "tools" node if individual tool nodes exist
      graphNodes = graphNodes.map((node) => {
        if (node.id === 'tools' && allToolNodeNames.length > 0) {
          return {
            ...node,
            hidden: true,
            style: { ...node.style, opacity: 0, height: 0, width: 0 },
          }
        }
        return node
      })

      // Apply layout
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(graphNodes, graphEdges)
      setNodes(layoutedNodes)
      setEdges(layoutedEdges)
    } catch {
      setError('Failed to process graph structure')
    }
  }, [graphStructure, setNodes, setEdges])

  // No polling needed - rely entirely on stream events for updates

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
    

    // Tool nodes are now created from the start, so we don't need to add them dynamically
    // We only need to ensure the "tools" node stays hidden if tool nodes are visited
    setNodes((nds) => {
      // Hide "tools" node if any individual tool nodes are in visitedNodes
      const hasToolNodes = visitedNodes.some(
        (nodeId) => nodeId.startsWith('node_') && nodeId !== 'node_agent' && nodeId !== 'node_tools'
      )
      
      if (hasToolNodes) {
        return nds.map((node) => {
          if (node.id === 'tools' || node.id === 'node_tools') {
            return {
              ...node,
              hidden: true,
              style: { ...node.style, opacity: 0, height: 0, width: 0 },
            }
          }
          return node
        })
      }
      
      return nds
    })

    // Update node and edge styles based on execution state
    // Use functional updates to avoid needing nodes/edges in dependency array
    // Force new array reference to ensure React Flow detects the change
    // Increment version to force React Flow to treat nodes as completely new
    nodeUpdateVersionRef.current += 1
    const updateVersion = nodeUpdateVersionRef.current
    
    // Add a small delay to allow React Flow to process previous updates
    // This prevents updates from being batched together
    const updateDelay = 50 // 50ms delay between updates
    setTimeout(() => {
      // Use flushSync to force immediate visual update (not batched)
      flushSync(() => {
      setNodes((nds) => {
      // Create a new array to force React Flow to detect the change
      const updatedNodes = nds.map((node) => {
        const isActive = activeNodes.includes(node.id)
        const isVisited = visitedNodes.includes(node.id)

        // Only update nodes that have changed state (active or visited)
        // This prevents unnecessary updates to all nodes
        const needsUpdate = isActive || isVisited || 
          (node.style?.border !== (isActive ? '2px solid #22c55e' : isVisited ? '1px solid #94a3b8' : '1px solid #e2e8f0')) ||
          (node.style?.backgroundColor !== (isActive ? '#dcfce7' : isVisited ? '#f1f5f9' : '#ffffff'))
        
        if (!needsUpdate) {
          return node // Return unchanged node to avoid unnecessary re-renders
        }
        
        // Create new node object with updated style and className to force React Flow re-render
        // Use both style and className to ensure React Flow detects the change
        const updatedNode = {
          ...node,
          data: {
            ...node.data,
            _updateVersion: updateVersion, // Use version number to force re-render
          },
          // Add className to force React Flow to update the DOM element
          className: isActive ? 'node-active' : isVisited ? 'node-visited' : 'node-default',
          // Create completely new style object (don't spread old style)
          style: {
            border: isActive ? '2px solid #22c55e' : isVisited ? '1px solid #94a3b8' : '1px solid #e2e8f0',
            backgroundColor: isActive ? '#dcfce7' : isVisited ? '#f1f5f9' : '#ffffff',
            transition: 'border 0.1s ease-in-out, background-color 0.1s ease-in-out', // Add transition to force repaint
          },
        }
        return updatedNode
      })
      return updatedNodes
      })
    })

    flushSync(() => {
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
    })
    
    // Use requestAnimationFrame to ensure browser has a chance to repaint
    // This gives the browser a frame to render the visual updates
    requestAnimationFrame(() => {
      // Force a repaint by reading a layout property
      // This ensures the browser actually renders the changes
      if (document.body) {
        void document.body.offsetHeight
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

