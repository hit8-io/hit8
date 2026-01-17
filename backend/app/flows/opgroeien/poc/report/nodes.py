"""
Nodes for the Report Engine Map-Reduce Graph.
"""
import json
from datetime import datetime
from typing import Any, List, Dict, TypedDict

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent
from langgraph.types import Send

from app.flows.opgroeien.poc.report.state import ReportState
from app.flows.opgroeien.poc.report.tools.chat import consult_general_knowledge
from app.flows.opgroeien.poc.chat.tools.get_procedure import get_procedure
from app.flows.opgroeien.poc.chat.tools.get_regelgeving import get_regelgeving

logger = structlog.get_logger(__name__)
from app.flows.common import get_agent_model, _wrap_with_retry
from app.prompts.loader import load_prompt
from app.flows.opgroeien.poc.constants import MAX_PARALLEL_WORKERS
from app import constants
from app.api.utils import extract_message_content
from app.config import settings

# --- Input Schema for Worker Node ---
class ClusterInput(TypedDict):
    procedures: List[Dict]
    meta: Dict

# --- Node 1: Splitter (Map) ---
def get_metadata(proc: Dict) -> Dict[str, str]:
    """
    Returns metadata (department, topic, safe_key) based on procedure ID.
    """
    # Extract procedure ID - prefer 'id' field, fallback to 'doc'
    proc_id = (proc.get("id") or proc.get("doc") or "").upper()
    
    # Map procedure prefixes to metadata
    if proc_id.startswith("PR-AV"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "Aanbodsvormen",
            "safe_key": "PGJO_Aanbodsvormen"
        }
    if proc_id.startswith("PR-CA"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "Consultatiebureauarts",
            "safe_key": "PGJO_CB_Arts"
        }
    if proc_id.startswith("PR-CB"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "Consultatiebureau",
            "safe_key": "PGJO_CB_Algemeen"
        }
    if proc_id.startswith("PR-HK"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "Huizen van het Kind",
            "safe_key": "PGJO_Huizen_vh_Kind"
        }
    if proc_id.startswith("PR-OH"):
        return {
            "dept": "Preventieve Gezinsondersteuning (PGJO)",
            "topic": "OverKop",
            "safe_key": "PGJO_OverKop"
        }
    if proc_id.startswith("PR-VE"):
        return {
            "dept": "Opvang Baby's en Peuters",
            "topic": "Vergunnen",
            "safe_key": "Kinderopvang_Vergunnen"
        }
    if proc_id.startswith("PR-HA"):
        return {
            "dept": "Opvang Baby's en Peuters",
            "topic": "Handhaving",
            "safe_key": "Kinderopvang_Handhaving"
        }
    if proc_id.startswith("PR-SU"):
        return {
            "dept": "Opvang Baby's en Peuters",
            "topic": "Subsidiëren",
            "safe_key": "Kinderopvang_Subsidies"
        }
    if proc_id.startswith("PR-OV"):
        return {
            "dept": "Opvang Baby's en Peuters",
            "topic": "Overkoepelend",
            "safe_key": "Kinderopvang_Overkoepelend"
        }
    if proc_id.startswith("PR-JH"):
        return {
            "dept": "Jeugdhulp",
            "topic": "Algemeen",
            "safe_key": "Jeugdhulp_Algemeen"
        }
    if proc_id.startswith("PR-LL"):
        return {
            "dept": "Lokale Loketten",
            "topic": "Algemeen",
            "safe_key": "Lokale_Loketten"
        }
    
    # Default fallback
    return {
        "dept": "Overige Procedures",
        "topic": "Algemeen",
        "safe_key": "Overige_Procedures"
    }


def splitter_node(state: ReportState):
    """
    Analyzes input procedures and generates parallel tasks.
    Groups procedures by department/topic using safe_key for file storage.
    Processes first batch and stores remaining clusters for batching.
    """
    raw_data = state.get("raw_procedures", [])
    clusters: Dict[str, Dict] = {}
    
    # Group procedures by safe_key
    for proc in raw_data:
        if not proc:
            continue
        
        # Skip if no ID found
        proc_id = proc.get("id") or proc.get("doc")
        if not proc_id:
            continue
        
        meta = get_metadata(proc)
        safe_key = meta["safe_key"]
        
        # Initialize cluster if it doesn't exist
        if safe_key not in clusters:
            clusters[safe_key] = {
                "file_id": safe_key,  # Used for file storage
                "department_name": meta["dept"],
                "topic_name": meta["topic"],
                "procedures": []
            }
        
        clusters[safe_key]["procedures"].append(proc)
    
    # Convert to list for batching
    cluster_list = list(clusters.values())
    
    # Process first batch
    first_batch = cluster_list[:MAX_PARALLEL_WORKERS]
    remaining_clusters = cluster_list[MAX_PARALLEL_WORKERS:]
    
    # Initialize cluster_status for all clusters (all start as pending)
    from datetime import datetime
    cluster_status: Dict[str, Dict[str, Any]] = {}
    for cluster in cluster_list:
        file_id = cluster.get("file_id")
        if file_id:
            cluster_status[file_id] = {
                "status": "pending",
            }
    
    # Mark first batch as active
    for cluster in first_batch:
        file_id = cluster.get("file_id")
        if file_id and file_id in cluster_status:
            cluster_status[file_id]["status"] = "active"
            cluster_status[file_id]["started_at"] = datetime.utcnow().isoformat() + "Z"
    
    # Store remaining clusters and log in state
    # Initialize batch_count to 1 (first batch is being processed)
    state_update = {
        "clusters_all": cluster_list,  # Store full list for UI
        "cluster_status": cluster_status,  # Initialize status tracking
        "pending_clusters": remaining_clusters,
        "batch_count": 1,
        "logs": [f"Splitter: Processing {len(first_batch)} clusters in first batch, {len(remaining_clusters)} remaining"]
    }
    
    # Return state update dict with Send objects for routing
    # The conditional edge will extract the Send objects
    if not first_batch:
        return state_update
    
    # Attach Send objects to state update for conditional edge extraction
    # We'll use a special key that the conditional edge can extract
    send_objects = [
        Send("analyst_node", {"procedures": c["procedures"], "meta": c}) 
        for c in first_batch
    ]
    
    # Return dict with both state updates and routing information
    # The conditional edge function will extract the "__sends__" key
    return {
        **state_update,
        "__sends__": send_objects
    }

# --- Node 2: Analyst (Worker) ---
async def analyst_node(input_data: ClusterInput):
    """
    Analyzes a SINGLE cluster using the Chat Tool and direct lookup tools.
    """
    llm = get_agent_model()
    
    # GIVE TOOLS TO THE ANALYST
    # 1. Bridge to general chat knowledge
    # 2. Direct access to procedure/regulation content
    tools = [consult_general_knowledge, get_procedure, get_regelgeving]
    
    meta = input_data["meta"]
    procs = input_data["procedures"]
    topic = meta.get("topic_name", "General")
    department = meta.get("department_name", "Unknown Department")
    file_id = meta.get("file_id", "unknown")
    
    # Load system prompt from YAML file
    prompt_obj = load_prompt("opgroeien/poc/analyst_system_prompt")
    system_prompt = prompt_obj.render(
        department_name=department,
        topic_name=topic,
    )
    
    # Pass procedures directly as human message
    human_message_content = json.dumps(procs, ensure_ascii=False)
    
    # Validate content before creating message
    if not human_message_content or not human_message_content.strip():
        logger.error(
            "analyst_node_empty_content",
            procs=procs,
            procs_count=len(procs),
        )
        raise ValueError("Cannot create HumanMessage with empty content in analyst_node")
    
    # Create the ReAct agent for this specific slice
    # We use a simple prebuilt agent here
    agent_executor = create_agent(llm, tools, system_prompt=system_prompt)
    # Apply retry wrapper to agent executor
    agent_executor = _wrap_with_retry(agent_executor)
    
    # Invoke
    result = await agent_executor.ainvoke({
        "messages": [HumanMessage(content=human_message_content)]
    })
    
    # Extract content using utility function to handle structured formats (e.g., Gemini signatures)
    raw_content = result["messages"][-1].content
    chapter_text = extract_message_content(raw_content)
    
    # Append to state.chapters via operator.add
    # Also append a log entry
    log_entry = f"Analyst finished chapter: {topic} (Department: {department}, File ID: {file_id})"
    
    # Update cluster_status to mark this cluster as completed
    # This ensures checkpoint state is authoritative
    from datetime import datetime
    
    cluster_status_update = {
        file_id: {
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat() + "Z",
        }
    }
    
    # Also update chapters_by_file_id if that field exists
    chapters_by_file_id_update = {file_id: chapter_text} if file_id else {}
    
    logger.info(
        "analyst_node_completed",
        file_id=file_id,
        topic=topic,
        department=department,
        chapter_length=len(chapter_text),
        update_keys=list(chapters_by_file_id_update.keys()),
    )
    
    return {
        "chapters": [chapter_text],
        "chapters_by_file_id": chapters_by_file_id_update,
        "cluster_status": cluster_status_update,
        "logs": [log_entry]
    }

# --- Node 2.5: Batch Processor (Handles subsequent batches) ---
def batch_processor_node(state: ReportState):
    """
    Processes the next batch of clusters if any remain.
    Returns Send objects for the next batch, or routes to editor if done.
    """
    pending = state.get("pending_clusters", [])
    current_batch_count = state.get("batch_count", 0)
    
    if not pending:
        # Validate all chapters are present before routing to editor
        cluster_status = state.get("cluster_status", {})
        if not isinstance(cluster_status, dict):
            cluster_status = {}
        
        chapters_by_file_id = state.get("chapters_by_file_id", {})
        if not isinstance(chapters_by_file_id, dict):
            chapters_by_file_id = {}
        
        # Count completed clusters
        completed_file_ids = {
            file_id for file_id, status in cluster_status.items()
            if isinstance(status, dict) and status.get("status") == "completed"
        }
        
        # Verify all completed clusters have chapters
        missing_chapters = [
            file_id for file_id in completed_file_ids
            if file_id not in chapters_by_file_id
        ]
        
        if missing_chapters:
            logger.warning(
                "batch_processor_missing_chapters",
                missing_file_ids=missing_chapters,
                completed_count=len(completed_file_ids),
                chapters_count=len(chapters_by_file_id),
                completed_file_ids=list(completed_file_ids),
                chapter_file_ids=list(chapters_by_file_id.keys()),
            )
            # Don't route to editor yet - wait for more state updates
            return {
                "logs": [f"Batch processor: Waiting for {len(missing_chapters)} chapters to complete (missing: {', '.join(missing_chapters)})"]
            }
        
        logger.info(
            "batch_processor_all_chapters_ready",
            completed_clusters=len(completed_file_ids),
            chapters_count=len(chapters_by_file_id),
            file_ids=list(chapters_by_file_id.keys()),
        )
        
        # All chapters present, route to editor
        return {
            "logs": ["Batch processor: All clusters processed, routing to editor"]
        }
    
    # Check MAX_BATCHES limit (dev environment only)
    MAX_BATCHES = constants.CONSTANTS.get("MAX_BATCHES")
    if MAX_BATCHES is not None and current_batch_count >= MAX_BATCHES:
        # Even with MAX_BATCHES limit, validate chapters are present
        cluster_status = state.get("cluster_status", {})
        if not isinstance(cluster_status, dict):
            cluster_status = {}
        
        chapters_by_file_id = state.get("chapters_by_file_id", {})
        if not isinstance(chapters_by_file_id, dict):
            chapters_by_file_id = {}
        
        completed_file_ids = {
            file_id for file_id, status in cluster_status.items()
            if isinstance(status, dict) and status.get("status") == "completed"
        }
        
        missing_chapters = [
            file_id for file_id in completed_file_ids
            if file_id not in chapters_by_file_id
        ]
        
        if missing_chapters:
            logger.warning(
                "batch_processor_max_batches_missing_chapters",
                current_batch_count=current_batch_count,
                max_batches=MAX_BATCHES,
                remaining_clusters=len(pending),
                missing_file_ids=missing_chapters,
                completed_count=len(completed_file_ids),
                chapters_count=len(chapters_by_file_id),
            )
            return {
                "logs": [f"Batch processor: MAX_BATCHES limit reached ({MAX_BATCHES}), but waiting for {len(missing_chapters)} chapters to complete"]
            }
        
        logger.info(
            "batch_processor_max_batches_reached",
            current_batch_count=current_batch_count,
            max_batches=MAX_BATCHES,
            remaining_clusters=len(pending),
            chapters_count=len(chapters_by_file_id),
        )
        return {
            "logs": [f"Batch processor: MAX_BATCHES limit reached ({MAX_BATCHES}), routing to editor with {len(pending)} clusters remaining"]
        }
    
    # Process next batch
    next_batch = pending[:MAX_PARALLEL_WORKERS]
    remaining = pending[MAX_PARALLEL_WORKERS:]
    
    # Increment batch count
    new_batch_count = current_batch_count + 1
    
    # Update cluster_status: mark next batch as active
    cluster_status = state.get("cluster_status", {})
    if not isinstance(cluster_status, dict):
        cluster_status = {}
    
    for cluster in next_batch:
        file_id = cluster.get("file_id")
        if file_id and file_id in cluster_status:
            cluster_status[file_id]["status"] = "active"
            if "started_at" not in cluster_status[file_id]:
                cluster_status[file_id]["started_at"] = datetime.utcnow().isoformat() + "Z"
    
    # Update state with remaining clusters
    state_update = {
        "cluster_status": cluster_status,
        "pending_clusters": remaining,
        "batch_count": new_batch_count,
        "logs": [f"Batch processor: Processing batch {new_batch_count} ({len(next_batch)} clusters), {len(remaining)} remaining"]
    }
    
    # Return Send objects for next batch
    send_objects = [
        Send("analyst_node", {"procedures": c["procedures"], "meta": c}) 
        for c in next_batch
    ]
    
    return {
        **state_update,
        "__sends__": send_objects
    }

# --- Node 3: Editor (Reducer) ---
async def editor_node(state: ReportState):
    """
    Aggregates all chapters into the final report.
    Uses chapters_by_file_id as the single source of truth for all chapters.
    """
    # Use chapters_by_file_id as the single source of truth
    chapters_by_file_id = state.get("chapters_by_file_id", {})
    if not isinstance(chapters_by_file_id, dict):
        chapters_by_file_id = {}
    
    # Validate chapters match completed clusters
    cluster_status = state.get("cluster_status", {})
    if not isinstance(cluster_status, dict):
        cluster_status = {}
    
    clusters_all = state.get("clusters_all", [])
    
    completed_file_ids = {
        file_id for file_id, status in cluster_status.items()
        if isinstance(status, dict) and status.get("status") == "completed"
    }
    
    chapter_file_ids = set(chapters_by_file_id.keys())
    
    # Log validation results
    if completed_file_ids != chapter_file_ids:
        missing = completed_file_ids - chapter_file_ids
        extra = chapter_file_ids - completed_file_ids
        logger.warning(
            "editor_node_chapter_mismatch",
            completed_clusters=len(completed_file_ids),
            chapters_present=len(chapter_file_ids),
            missing_file_ids=list(missing),
            extra_file_ids=list(extra),
            completed_file_ids=list(completed_file_ids),
            chapter_file_ids=list(chapter_file_ids),
        )
    else:
        logger.info(
            "editor_node_chapters_validated",
            completed_clusters=len(completed_file_ids),
            chapters_count=len(chapter_file_ids),
            file_ids=list(chapter_file_ids),
        )
    
    # Extract all chapter texts from the dict (values are chapter texts)
    chapters_list = list(chapters_by_file_id.values())
    full_text = "\n\n---\n\n".join(chapters_list)
    
    # Handle empty chapters case - return early with a default message
    if not full_text or not full_text.strip():
        logger.warning(
            "editor_node_no_chapters",
            chapters_by_file_id_count=len(chapters_by_file_id),
        )
        return {
            "final_report": "No procedures were provided to generate a report. Please select procedures before starting report generation.",
            "logs": ["Editor finished: No chapters to process."]
        }
    
    logger.info(
        "editor_node_processing_chapters",
        chapters_count=len(chapters_list),
        file_ids=list(chapters_by_file_id.keys()),
        full_text_length=len(full_text),
    )
    
    # Use model with high output token limit for long reports
    # Editor node needs higher limits to generate complete reports
    if settings.LLM_PROVIDER == "ollama":
        max_output_tokens = constants.CONSTANTS.get("EDITOR_NODE_MAX_OUTPUT_TOKENS_OLLAMA")
    elif settings.LLM_PROVIDER == "vertex":
        max_output_tokens = constants.CONSTANTS.get("EDITOR_NODE_MAX_OUTPUT_TOKENS_VERTEX")
    
    if max_output_tokens is not None:
        llm = get_agent_model(max_output_tokens=max_output_tokens)
    else:
        llm = get_agent_model()
    
    # Format date
    formatted_date = datetime.now().strftime("%d %B %Y")
    
    # Load system prompt from YAML file
    # NOTE: We do NOT include full_report_body in the system prompt to avoid confusion
    # The full text is only in the human message
    prompt_obj = load_prompt("opgroeien/poc/editor_system_prompt")
    system_prompt = prompt_obj.render(
        date=formatted_date,
    )
    
    # Human message contains the full report body with all chapters
    # Format: Each chapter is separated by "\n\n---\n\n"
    human_message = full_text
    
    # Apply retry wrapper for direct model invocation
    llm_with_retry = _wrap_with_retry(llm)
    response = await llm_with_retry.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_message)
    ])
    
    # Extract content using utility function to handle structured formats (e.g., Gemini signatures)
    final_report_text = extract_message_content(response.content)
    
    # Log final report length to detect truncation issues
    logger.info(
        "editor_node_final_report_generated",
        final_report_length=len(final_report_text),
        chapters_count=len(chapters_list),
        max_output_tokens=max_output_tokens,
    )
    
    # Warn if report seems truncated (less than 1000 chars for multiple chapters)
    if len(chapters_list) > 1 and len(final_report_text) < 1000:
        logger.warning(
            "editor_node_report_may_be_truncated",
            final_report_length=len(final_report_text),
            chapters_count=len(chapters_list),
            max_output_tokens=max_output_tokens,
        )
    
    return {
        "final_report": final_report_text,
        "logs": [f"Editor finished final report with {len(chapters_list)} chapters."]
    }
