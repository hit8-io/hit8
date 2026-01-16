"""
Graph-related endpoints.
"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.graph_manager import get_graph
from app.auth import verify_google_token
from app.user_config import validate_user_access

logger = structlog.get_logger(__name__)
router = APIRouter()


from app.api.utils import serialize_messages


def _enhance_graph_structure(graph_structure: dict[str, Any], flow: str | None = None) -> dict[str, Any]:
    """Enhance graph structure by adding missing edges from conditional routes.
    
    LangGraph's to_json() doesn't include edges for conditional routes that use
    Send objects (dynamic routing). This function adds representative edges
    to ensure all nodes are properly connected in the visualization.
    
    Args:
        graph_structure: The graph structure dict from LangGraph's to_json()
        flow: Optional flow name to apply flow-specific enhancements
        
    Returns:
        Enhanced graph structure with additional edges for conditional routes
    """
    if not isinstance(graph_structure, dict):
        return graph_structure
    
    nodes = graph_structure.get("nodes", [])
    edges = graph_structure.get("edges", [])
    
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return graph_structure
    
    # Create sets for quick lookup
    node_ids = {node.get("id") for node in nodes if isinstance(node, dict) and "id" in node}
    existing_edges = {
        (edge.get("source"), edge.get("target"))
        for edge in edges
        if isinstance(edge, dict) and "source" in edge and "target" in edge
    }
    
    # Flow-specific enhancements
    if flow == "report":
        # Report graph conditional edges:
        # 1. splitter_node → analyst_node (via Send objects, dynamic routing)
        # 2. batch_processor_node → analyst_node OR editor_node (conditional)
        
        if "splitter_node" in node_ids and "analyst_node" in node_ids:
            if ("splitter_node", "analyst_node") not in existing_edges:
                edges.append({
                    "source": "splitter_node",
                    "target": "analyst_node",
                })
                existing_edges.add(("splitter_node", "analyst_node"))
        
        if "batch_processor_node" in node_ids:
            # Add edge to analyst_node (for when more batches exist)
            if "analyst_node" in node_ids:
                if ("batch_processor_node", "analyst_node") not in existing_edges:
                    edges.append({
                        "source": "batch_processor_node",
                        "target": "analyst_node",
                    })
                    existing_edges.add(("batch_processor_node", "analyst_node"))
            
            # Add edge to editor_node (for when all batches are done)
            if "editor_node" in node_ids:
                if ("batch_processor_node", "editor_node") not in existing_edges:
                    edges.append({
                        "source": "batch_processor_node",
                        "target": "editor_node",
                    })
                    existing_edges.add(("batch_processor_node", "editor_node"))
    
    return {
        **graph_structure,
        "edges": edges,
    }


def _extract_graph_history(state: Any, state_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract graph execution history from state."""
    history: list[dict[str, Any]] = []
    
    if hasattr(state, "tasks") and state.tasks:
        for task in state.tasks:
            task_name = None
            if hasattr(task, "name"):
                task_name = task.name
            elif isinstance(task, dict) and "name" in task:
                task_name = task["name"]
            if task_name:
                history.append({"node": task_name})
    
    return history


@router.get("/structure")
async def get_graph_structure(
    flow: str | None = None,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Get the LangGraph structure as JSON.
    
    Requires X-Org and X-Project headers to specify which org/project to use.
    Optional 'flow' parameter to specify which graph to return.
    Flow parameter may include a colon suffix (e.g., 'report:1') which will be stripped.
    """
    email = user_payload["email"]
    org = (x_org or "").strip()
    project = (x_project or "").strip()
    
    # Strip any colon suffix from flow parameter (e.g., "report:1" -> "report")
    if flow:
        flow = flow.split(":")[0].strip()
    
    if not org or not project:
        # Return empty structure if org/project not selected yet
        # This avoids 422 errors on initial load
        return {"nodes": [], "edges": []}
    
    # Validate user has access to the requested org/project
    if not validate_user_access(email, org, project):
        logger.warning(
            "user_access_denied",
            email=email,
            org=org,
            project=project,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    try:
        graph_json = get_graph(org, project, flow).get_graph().to_json()
        # Enhance structure with missing conditional edges
        enhanced_structure = _enhance_graph_structure(graph_json, flow=flow)
        return enhanced_structure
    except Exception as e:
        logger.exception(
            "graph_structure_export_failed",
            error=str(e),
            error_type=type(e).__name__,
            org=org,
            project=project,
            flow=flow,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export graph structure: {str(e)}"
        )


@router.get("/state")
async def get_graph_state(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Get the current execution state for a thread.
    
    Requires X-Org and X-Project headers to specify which org/project to use.
    """
    email = user_payload["email"]
    org = (x_org or "").strip()
    project = (x_project or "").strip()
    
    if not org or not project:
        # Return empty state if org/project not selected yet
        # This avoids 422 errors on initial load
        return {
            "values": {},
            "next": [],
            "history": [],
        }
    
    # Validate user has access to the requested org/project
    if not validate_user_access(email, org, project):
        logger.warning(
            "user_access_denied",
            email=email,
            org=org,
            project=project,
            thread_id=thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    try:
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        
        # Get state with history to track visited nodes
        # Use asyncio.to_thread to avoid AsyncPostgresSaver sync call error
        try:
            import asyncio
            state = await asyncio.to_thread(get_graph(org, project).get_state, config)
        except Exception as state_error:
            # If state retrieval fails, return empty state
            logger.debug(
                "graph_state_not_found",
                thread_id=thread_id,
                error=str(state_error),
                error_type=type(state_error).__name__,
            )
            return {
                "values": {},
                "next": [],
                "history": [],
            }
        
        # Convert state to dict, handling serialization
        state_dict: dict[str, Any] = {
            "values": {},
            "next": state.next if hasattr(state, "next") else [],
        }
        
        # Serialize messages if present
        messages = serialize_messages(state)
        if messages:
            state_dict["values"]["messages"] = messages
            state_dict["values"]["message_count"] = len(messages)
        
        # Add next nodes
        if hasattr(state, "next"):
            state_dict["next"] = list(state.next) if state.next else []
        
        # Get history by examining state and checkpoints
        try:
            state_dict["history"] = _extract_graph_history(state, state_dict)
        except Exception:
            state_dict["history"] = []
        
        return state_dict
    except Exception as e:
        logger.error(
            "graph_state_retrieval_failed",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve graph state: {str(e)}"
        )

