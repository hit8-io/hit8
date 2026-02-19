import dagre from 'dagre'
import { Node, Edge, Position } from 'reactflow'
import { GRAPH_NODE_WIDTH, GRAPH_NODE_HEIGHT, GRAPH_NODE_SEPARATION, GRAPH_RANK_SEPARATION } from '../constants'

export function getLayoutedElements(nodes: Node[], edges: Edge[], direction: 'TB' | 'LR' = 'TB'): { nodes: Node[]; edges: Edge[] } {
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({ rankdir: direction, nodesep: GRAPH_NODE_SEPARATION, ranksep: GRAPH_RANK_SEPARATION })

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: GRAPH_NODE_WIDTH, height: GRAPH_NODE_HEIGHT })
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
      x: nodeWithPosition.x - GRAPH_NODE_WIDTH / 2,
      y: nodeWithPosition.y - GRAPH_NODE_HEIGHT / 2,
    }
  })

  return { nodes, edges }
}

