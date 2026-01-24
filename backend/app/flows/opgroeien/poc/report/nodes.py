"""
Nodes for the Report Engine Map-Reduce Graph.
"""
import asyncio
import json
import threading
from datetime import datetime
from typing import Any, List, Dict, Optional, TypedDict

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain.agents import create_agent
from langgraph.types import Send

from app.api.observability import _current_model_name
from app.api.utils import extract_message_content
from app.flows.common import get_agent_model, get_report_llm_semaphore, execute_llm_call_async
from app.flows.opgroeien.poc.chat.tools.get_procedure import get_procedure
from app.flows.opgroeien.poc.chat.tools.get_regelgeving import get_regelgeving
from app.flows.opgroeien.poc.constants import MAX_PARALLEL_WORKERS
from app.flows.opgroeien.poc.report.state import ReportState
from app.flows.opgroeien.poc.report.tools.chat import consult_general_knowledge
from app.prompts.loader import load_prompt
from app import constants
from app.constants import ANALYST_TIMEOUT_SECONDS, ANALYST_MAX_RETRIES

# Constant for the magic string used to pass Send objects in node outputs
# This is used by both nodes (to return Send objects) and graph (to extract them)
SENDS_KEY = "__sends__"

logger = structlog.get_logger(__name__)

# Serializes "take from pending" in batch_processor when two analysts complete
# at once and both trigger batch_processor, to avoid sending duplicate work.
# NOTE: batch_processor_node is synchronous, but LangGraph may run it in the event loop.
# Using threading.Lock() is safe here because:
# 1. The lock is only held briefly (just reading/updating pending list)
# 2. LangGraph handles sync nodes appropriately (either in thread pool or blocking)
# 3. The critical section is minimal (just list slicing and dict updates)
_batch_processor_lock = threading.Lock()


def _log_ts(msg: str) -> str:
    """Prefix a log message with [HH:mm:ss] for event log display."""
    return f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"


def _extract_model_name_from_config(config: Optional[RunnableConfig]) -> Optional[str]:
    """
    Extract model_name from RunnableConfig in a consistent way.
    
    Args:
        config: Optional RunnableConfig object
        
    Returns:
        model_name string if found, None otherwise
    """
    if not config:
        return None
    
    # Try accessing as attribute first
    if hasattr(config, "configurable") and isinstance(getattr(config, "configurable", None), dict):
        return config.configurable.get("model_name")
    
    # Fallback: try accessing as dict
    if isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict):
            return configurable.get("model_name")
    
    return None

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
            # Initialize retry_count to 0 for new attempts
            if "retry_count" not in cluster_status[file_id]:
                cluster_status[file_id]["retry_count"] = 0
    
    # Store remaining clusters and log in state
    # Initialize batch_count to 1 (first batch is being processed)
    # last_batch_sent_count/last_send_size: only send next batch when we've received
    # last_send_size completions since last_batch_sent_count (avoids over-subscribing analysts)
    # Track all requested chapter IDs for failure recovery
    requested_chapter_ids = [c.get("file_id") for c in cluster_list if c.get("file_id")]
    state_update = {
        "clusters_all": cluster_list,  # Store full list for UI
        "cluster_status": cluster_status,  # Initialize status tracking
        "pending_clusters": remaining_clusters,
        "batch_count": 1,
        "last_batch_sent_count": 0,
        "last_send_size": len(first_batch),
        "requested_chapter_ids": requested_chapter_ids,  # Track all requested chapters for retry detection
        "logs": [_log_ts(f"Splitter: Processing {len(first_batch)} clusters in first batch, {len(remaining_clusters)} remaining")]
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
    # The conditional edge function will extract the SENDS_KEY
    return {
        **state_update,
        SENDS_KEY: send_objects
    }

# --- Node 2: Analyst (Worker) ---
async def _analyst_node_impl(input_data: ClusterInput, config: Optional[RunnableConfig] = None):
    """
    Internal implementation of analyst node.
    Analyzes a SINGLE cluster using the Chat Tool and direct lookup tools.
    
    Note: Flow control (semaphore, token bucket, rate limiter, retries, timeout,
    token counting, dynamic timeout) is handled by execute_llm_call_async() wrapper,
    not here. This function focuses on business logic only.
    """
    model_name = _extract_model_name_from_config(config)
    llm = get_agent_model(model_name=model_name)
    
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
    agent_executor = create_agent(llm, tools, system_prompt=system_prompt)

    # Cap agent loop iterations (model -> tools -> model -> ...) to avoid unbounded
    # ReAct loops when the model keeps calling tools without finishing.
    # Use constant from configuration - keep it simple and maintainable
    max_iter = constants.CONSTANTS.get("ANALYST_AGENT_MAX_ITERATIONS", 30)
    invoke_config = {**(dict(config) if config else {}), "recursion_limit": max_iter}

    # Invoke agent executor
    # Set _current_model_name so consult_general_knowledge uses the same model; reset after.
    tok = _current_model_name.set(model_name)
    try:
        result = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=human_message_content)]},
            config=invoke_config,
        )
    finally:
        _current_model_name.reset(tok)

    # Extract content using utility function to handle structured formats (e.g., Gemini signatures)
    raw_content = result["messages"][-1].content
    chapter_text = extract_message_content(raw_content)

    # Append to state.chapters via operator.add
    # Also append a log entry
    log_entry = f"Analyst finished chapter: {topic} (Department: {department}, File ID: {file_id})"

    # Update cluster_status to mark this cluster as completed
    # This ensures checkpoint state is authoritative
    # Reset retry_count on successful completion
    cluster_status_update = {
        file_id: {
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat() + "Z",
            "retry_count": 0,  # Reset retry count on success
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
        "logs": [_log_ts(log_entry)],
    }


async def analyst_node(input_data: ClusterInput, config: Optional[RunnableConfig] = None):
    """
    Analyst node - focuses on business logic (chapter generation).
    
    Flow control (token counting, dynamic timeout, token bucket, rate limiting, retries)
    is handled centrally by execute_llm_call_async() wrapper. This keeps nodes simple
    and maintainable.
    
    Returns structured failure response on timeout/errors to allow graph to continue.
    """
    meta = input_data.get("meta", {})
    file_id = meta.get("file_id", "unknown")
    
    # Extract model_name and determine provider
    model_name = _extract_model_name_from_config(config)
    provider = None
    if model_name:
        from app.flows.common import get_provider_for_model
        provider = get_provider_for_model(model_name=model_name)
    
    # Estimate input tokens from procedures (needed for dynamic timeout calculation)
    # Since _analyst_node_impl creates messages internally, execute_llm_call_async can't extract them
    # So we estimate here from the data that will be sent to the LLM
    input_tokens = None
    try:
        from app.flows.common import _count_tokens_from_messages
        from langchain_core.messages import HumanMessage, SystemMessage
        # Create sample messages matching what _analyst_node_impl will create
        procs = input_data.get("procedures", [])
        human_message_content = json.dumps(procs, ensure_ascii=False)
        # Load system prompt to include in count
        prompt_obj = load_prompt("opgroeien/poc/analyst_system_prompt")
        system_prompt = prompt_obj.render(
            department_name=meta.get("department_name", "Unknown Department"),
            topic_name=meta.get("topic_name", "General"),
        )
        sample_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_message_content)
        ]
        input_tokens = _count_tokens_from_messages(sample_messages, model_name=model_name)
    except Exception as e:
        logger.debug(
            "analyst_node_token_estimation_failed",
            error=str(e),
            error_type=type(e).__name__,
            file_id=file_id,
        )
    
    # Prepare call context for logging and flow control
    # Note: input_tokens is needed for dynamic timeout calculation in execute_llm_call_async
    call_context = {
        "file_id": file_id,
        "node": "analyst_node",
        "flow": "report",
        "topic": meta.get("topic_name", "Unknown"),
        "department": meta.get("department_name", "Unknown"),
    }
    if model_name:
        call_context["model_name"] = model_name
    if provider:
        call_context["provider"] = provider
    if input_tokens is not None:
        call_context["input_tokens"] = input_tokens
    
    try:
        # Use generic wrapper for all flow control
        # execute_llm_call_async handles:
        # - Token counting (from messages)
        # - Dynamic timeout calculation (based on tokens)
        # - Token bucket management
        # - Rate limiting
        # - Retries
        result = await execute_llm_call_async(
            _analyst_node_impl,
            input_data,
            config=config,
            call_context=call_context,
            timeout_seconds=None,  # Let common layer calculate dynamically based on tokens
        )
        
        # No wait needed - rate limiter already enforces 12 seconds between Pro model requests
        # With only 1 chapter at a time and LiteLLM Router handling rate limiting, the 120-second wait was excessive
        
        return result
    except asyncio.TimeoutError:
        # Timeout occurred - return failed status to allow graph to continue
        timeout_details = {
            "file_id": file_id,
            "topic": meta.get("topic_name", "Unknown"),
            "department": meta.get("department_name", "Unknown"),
            "input_tokens": call_context.get("input_tokens"),
            "model_name": call_context.get("model_name"),
            "provider": call_context.get("provider"),
            "error_category": "timeout",
        }
        
        # Token bucket state logging removed - LiteLLM Router handles rate limiting
        
        logger.error(
            "analyst_node_timeout",
            **timeout_details,
        )
        
        # No wait needed - rate limiter already enforces 12 seconds between Pro model requests
        
        # Mark cluster as failed in cluster_status
        # retry_count is tracked by batch_processor_node when scheduling retries
        # merge_cluster_status will handle preserving/incrementing retry_count based on status changes
        cluster_status_update = {
            file_id: {
                "status": "failed",
                "error": "timeout",
                "ended_at": datetime.utcnow().isoformat() + "Z",
                # Note: retry_count is not set here - it's managed by batch_processor_node and merge_cluster_status
            }
        }
        
        return {
            "chapters": [],
            "chapters_by_file_id": {},
            "cluster_status": cluster_status_update,
            "logs": [_log_ts(f"Analyst node timed out for {file_id}, will be retried")],
        }
    except Exception as e:
        # All retries exhausted or non-retryable exception
        # Log detailed failure information to help diagnose issues
        error_details = {
            "file_id": file_id,
            "topic": meta.get("topic_name", "Unknown"),
            "department": meta.get("department_name", "Unknown"),
            "error": str(e),
            "error_type": type(e).__name__,
            "input_tokens": call_context.get("input_tokens"),
            "model_name": call_context.get("model_name"),
            "provider": call_context.get("provider"),
        }
        
        # Token bucket state logging removed - LiteLLM Router handles rate limiting
        
        error_details["error_category"] = "llm_call_failed"
        logger.exception(
            "analyst_node_error",
            **error_details,
        )
        
        # No wait needed - rate limiter already enforces 12 seconds between Pro model requests
        
        # Mark cluster as failed in cluster_status
        # retry_count is tracked by batch_processor_node when scheduling retries
        # merge_cluster_status will handle preserving/incrementing retry_count based on status changes
        cluster_status_update = {
            file_id: {
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__,
                "ended_at": datetime.utcnow().isoformat() + "Z",
                # Note: retry_count is not set here - it's managed by batch_processor_node and merge_cluster_status
            }
        }
        
        return {
            "chapters": [],
            "chapters_by_file_id": {},
            "cluster_status": cluster_status_update,
            "logs": [_log_ts(f"Analyst node failed for {file_id}: {str(e)}, will be retried")],
        }

# --- Node 2.5: Batch Processor (Handles subsequent batches) ---
def batch_processor_node(state: ReportState):
    """
    Processes the next batch of clusters if any remain.
    Only takes from pending and sends the next batch when ALL analysts in the
    current batch have completed (avoids over-subscribing and stalling).
    Returns Send objects for the next batch, or routes to editor if done,
    or SENDS_KEY=[] to wait for more completions.
    """
    pending = state.get("pending_clusters", [])
    current_batch_count = state.get("batch_count", 0)
    try:
        last_batch_sent_count = state["last_batch_sent_count"]
        last_send_size = state["last_send_size"]
    except KeyError as e:
        raise

    cluster_status = state.get("cluster_status", {})
    if not isinstance(cluster_status, dict):
        cluster_status = {}
    chapters_by_file_id = state.get("chapters_by_file_id", {})
    if not isinstance(chapters_by_file_id, dict):
        chapters_by_file_id = {}
    # Count both completed and failed clusters as "done" so batch processor can proceed
    # Failed clusters (e.g., timeout) are marked as failed but still count toward batch completion
    completed_file_ids = {
        file_id for file_id, status in cluster_status.items()
        if isinstance(status, dict) and status.get("status") in ("completed", "failed")
    }
    completed_count = len(completed_file_ids)

    if not pending:
        # No more clusters to assign. Only route to editor when we've received
        # all completions for the last batch (in-flight analysts are done).
        needed = last_batch_sent_count + last_send_size
        if completed_count < needed:
            return {
                "logs": [_log_ts(f"Batch processor: Waiting for {needed - completed_count} more chapters (have {completed_count}, need {needed})")],
                SENDS_KEY: [],
            }
        
        # PARTIAL FAILURE RECOVERY: Detect missing/failed chapters
        # Compare requested chapters against completed chapters
        requested_chapter_ids = state.get("requested_chapter_ids", [])
        if not isinstance(requested_chapter_ids, list):
            requested_chapter_ids = []
        
        # Get all file_ids that have completed chapters
        completed_chapter_ids = set(chapters_by_file_id.keys())
        requested_chapter_ids_set = set(requested_chapter_ids)
        
        # Identify missing chapters (requested but not completed)
        missing_chapter_ids = list(requested_chapter_ids_set - completed_chapter_ids)
        
        # Log the state of all chapters for monitoring
        logger.info(
            "batch_processor_chapter_status_check",
            requested_count=len(requested_chapter_ids),
            completed_count=len(completed_chapter_ids),
            missing_count=len(missing_chapter_ids),
            requested_ids=requested_chapter_ids,
            completed_ids=list(completed_chapter_ids),
            missing_ids=missing_chapter_ids,
            cluster_status_keys=list(cluster_status.keys()),
            message="Checking chapter completion status before routing",
        )
        
        # Check if missing chapters are failed (status="failed") or still in-flight
        # Check retry_count to prevent infinite loops from deterministically failing chapters
        failed_chapter_ids = []
        in_flight_chapter_ids = []
        max_retries_exceeded_ids = []
        for file_id in missing_chapter_ids:
            status_info = cluster_status.get(file_id, {})
            if isinstance(status_info, dict):
                status = status_info.get("status", "unknown")
                retry_count = status_info.get("retry_count", 0) or 0
                
                if status == "failed":
                    # Check retry count to prevent infinite loops
                    if retry_count >= ANALYST_MAX_RETRIES:
                        max_retries_exceeded_ids.append(file_id)
                        logger.error(
                            "batch_processor_max_retries_exceeded",
                            file_id=file_id,
                            retry_count=retry_count,
                            max_retries=ANALYST_MAX_RETRIES,
                            message=f"Chapter {file_id} has exceeded max retries ({ANALYST_MAX_RETRIES}). Will not retry.",
                        )
                    else:
                        failed_chapter_ids.append(file_id)
                        logger.info(
                            "batch_processor_scheduling_graph_level_retry",
                            retry_type="graph_level",  # Graph-level retry (batch_processor)
                            file_id=file_id,
                            graph_level_retry_count=retry_count,
                            max_graph_level_retries=ANALYST_MAX_RETRIES,
                            next_graph_level_retry_count=retry_count + 1,
                            message=f"Chapter {file_id} failed, scheduling graph-level retry {retry_count + 1}/{ANALYST_MAX_RETRIES}",
                        )
                elif status in ("active", "pending"):
                    in_flight_chapter_ids.append(file_id)
                else:
                    # Unknown status, treat as failed for retry (if retries available)
                    if retry_count >= ANALYST_MAX_RETRIES:
                        max_retries_exceeded_ids.append(file_id)
                        logger.warning(
                            "batch_processor_unknown_status_max_retries",
                            file_id=file_id,
                            status=status,
                            retry_count=retry_count,
                            max_retries=ANALYST_MAX_RETRIES,
                        )
                    else:
                        failed_chapter_ids.append(file_id)
            else:
                # No status info - chapter may have never started or status was lost
                # Treat as failed for retry (if retries available)
                # First attempt, so retry_count is 0, safe to retry
                logger.warning(
                    "batch_processor_missing_chapter_no_status_info",
                    file_id=file_id,
                    cluster_status_keys=list(cluster_status.keys()),
                    message=f"Chapter {file_id} is missing but has no status info - treating as failed for retry",
                )
                failed_chapter_ids.append(file_id)
        
        # If there are in-flight chapters, wait for them
        if in_flight_chapter_ids:
            return {
                "logs": [_log_ts(f"Batch processor: Waiting for {len(in_flight_chapter_ids)} in-flight chapters: {', '.join(in_flight_chapter_ids)}")],
                SENDS_KEY: [],
            }
        
        # Log chapters that exceeded max retries (won't be retried)
        if max_retries_exceeded_ids:
            logger.error(
                "batch_processor_max_retries_exceeded_chapters",
                max_retries_exceeded_ids=max_retries_exceeded_ids,
                max_retries=ANALYST_MAX_RETRIES,
                message="These chapters will be skipped - max retries exceeded",
            )
        
        # If there are failed chapters, retry them
        if failed_chapter_ids:
            logger.warning(
                "batch_processor_detected_failed_chapters",
                retry_type="graph_level",  # Graph-level retry (batch_processor)
                failed_chapter_ids=failed_chapter_ids,
                total_requested=len(requested_chapter_ids),
                total_completed=len(completed_chapter_ids),
                graph_level_retry_count_info={file_id: cluster_status.get(file_id, {}).get("retry_count", 0) for file_id in failed_chapter_ids},
                message=f"Detected {len(failed_chapter_ids)} failed chapters for graph-level retry",
            )
            # Reset status of failed chapters to "active" for retry
            # Explicitly increment retry_count when scheduling retry (more reliable than relying on merge function)
            # 
            # STATE PERSISTENCE: cluster_status_update is returned in the output dict and merged with state
            # via merge_cluster_status reducer. The retry_count is part of ClusterStatus (TypedDict) in ReportState,
            # so LangGraph will persist it to the checkpoint before the retry Send() objects execute.
            # This ensures retry_count is properly tracked across graph executions and prevents infinite loops.
            cluster_status_update = {}
            for file_id in failed_chapter_ids:
                if file_id in cluster_status:
                    current_status = cluster_status[file_id]
                    current_retry_count = current_status.get("retry_count", 0) or 0
                    # Increment retry_count when scheduling retry (this is attempt N+1)
                    next_retry_count = current_retry_count + 1
                    cluster_status_update[file_id] = {
                        "status": "active",
                        "started_at": datetime.utcnow().isoformat() + "Z",
                        "retry_count": next_retry_count,  # Increment when scheduling retry
                    }
                    logger.info(
                        "batch_processor_scheduling_graph_level_retry_with_count",
                        retry_type="graph_level",  # Graph-level retry (batch_processor)
                        file_id=file_id,
                        previous_graph_level_retry_count=current_retry_count,
                        next_graph_level_retry_count=next_retry_count,
                        max_graph_level_retries=ANALYST_MAX_RETRIES,
                        message=f"Scheduling graph-level retry {next_retry_count}/{ANALYST_MAX_RETRIES} for {file_id}",
                    )
                else:
                    # New chapter (shouldn't happen, but handle it)
                    cluster_status_update[file_id] = {
                        "status": "active",
                        "started_at": datetime.utcnow().isoformat() + "Z",
                        "retry_count": 1,  # First retry attempt
                    }
            
            # If all failed chapters exceeded retry count, don't retry
            if not cluster_status_update:
                logger.error(
                    "batch_processor_all_retries_exceeded",
                    failed_chapter_ids=failed_chapter_ids,
                    max_retries=ANALYST_MAX_RETRIES,
                    message="All failed chapters exceeded max retries - routing to editor",
                )
                return {
                    "status": "done",
                    "logs": [_log_ts(f"Batch processor: All failed chapters exceeded max retries ({ANALYST_MAX_RETRIES}). Routing to editor.")],
                }
            
            # Include clusters_all in output so route_batch_processor can reconstruct cluster data for retries
            clusters_all = state.get("clusters_all", [])
            if not isinstance(clusters_all, list) or not clusters_all:
                logger.error(
                    "batch_processor_missing_clusters_all_for_retry",
                    failed_chapter_ids=failed_chapter_ids,
                    clusters_all_type=type(clusters_all).__name__,
                    clusters_all_length=len(clusters_all) if isinstance(clusters_all, list) else 0,
                )
                return {
                    "status": "done",
                    "logs": [_log_ts(f"Batch processor: Cannot retry failed chapters - missing clusters_all data. Routing to editor.")],
                }
            
            # Deduplicate failed_chapter_ids to prevent duplicates from parallel failures
            failed_chapter_ids_dedup = list(dict.fromkeys(failed_chapter_ids))
            if len(failed_chapter_ids_dedup) != len(failed_chapter_ids):
                logger.warning(
                    "batch_processor_deduplicated_failed_chapters",
                    original_count=len(failed_chapter_ids),
                    deduplicated_count=len(failed_chapter_ids_dedup),
                    duplicates=len(failed_chapter_ids) - len(failed_chapter_ids_dedup),
                )
            
            return {
                "failed_chapter_ids": failed_chapter_ids_dedup,
                "status": "partial_failure",
                "clusters_all": clusters_all,
                "cluster_status": cluster_status_update,
                "logs": [_log_ts(f"Batch processor: Detected {len(failed_chapter_ids_dedup)} failed chapters, scheduling retry: {', '.join(failed_chapter_ids_dedup)}")],
            }
        
        # All chapters completed successfully (or max retries exceeded)
        # Check max_retries_exceeded_ids FIRST before checking for missing chapters
        if max_retries_exceeded_ids:
            logger.warning(
                "batch_processor_routing_to_editor_with_skipped_chapters",
                skipped_chapter_ids=max_retries_exceeded_ids,
                completed_count=len(completed_chapter_ids),
                requested_count=len(requested_chapter_ids),
                message=f"Routing to editor with {len(completed_chapter_ids)}/{len(requested_chapter_ids)} chapters. "
                       f"{len(max_retries_exceeded_ids)} chapters skipped (max retries exceeded)",
            )
            return {
                "logs": [_log_ts(f"Batch processor: Routing to editor with {len(completed_chapter_ids)}/{len(requested_chapter_ids)} completed chapters. "
                                f"{len(max_retries_exceeded_ids)} chapters skipped (max retries exceeded)")]
            }
        
        # If there are missing chapters but no failed_chapter_ids and no max_retries_exceeded_ids, something is wrong
        # Log error and route to editor to avoid infinite loops
        if missing_chapter_ids and not failed_chapter_ids and not in_flight_chapter_ids and not max_retries_exceeded_ids:
            logger.error(
                "batch_processor_missing_chapters_no_status",
                missing_chapter_ids=missing_chapter_ids,
                requested_count=len(requested_chapter_ids),
                completed_count=len(completed_chapter_ids),
                cluster_status_for_missing={
                    file_id: cluster_status.get(file_id, "NO_STATUS") for file_id in missing_chapter_ids
                },
                message="Missing chapters detected but they don't have 'failed' status and aren't in-flight. "
                       "These chapters may never have started or have an unknown status. Routing to editor.",
            )
            return {
                "logs": [_log_ts(f"Batch processor: WARNING - {len(missing_chapter_ids)} chapters are missing but don't have 'failed' status. "
                                f"Completed: {len(completed_chapter_ids)}/{len(requested_chapter_ids)}. Routing to editor.")],
            }
        
        # All chapters completed successfully
        if len(completed_chapter_ids) != len(requested_chapter_ids):
            logger.error(
                "batch_processor_chapter_count_mismatch",
                completed_count=len(completed_chapter_ids),
                requested_count=len(requested_chapter_ids),
                completed_ids=list(completed_chapter_ids),
                requested_ids=requested_chapter_ids,
                message="Chapter count mismatch - routing to editor",
            )
            return {
                "logs": [_log_ts(f"Batch processor: WARNING - Chapter count mismatch: {len(completed_chapter_ids)}/{len(requested_chapter_ids)}. Routing to editor.")],
            }
        
        logger.info(
            "batch_processor_all_chapters_ready",
            completed_clusters=len(completed_chapter_ids),
            chapters_count=len(chapters_by_file_id),
            file_ids=list(chapters_by_file_id.keys()),
            requested_count=len(requested_chapter_ids),
        )
        return {
            "logs": [_log_ts(f"Batch processor: All {len(completed_chapter_ids)}/{len(requested_chapter_ids)} clusters processed, routing to editor")]
        }
    
    # Check MAX_BATCHES limit (dev environment only)
    MAX_BATCHES = constants.CONSTANTS.get("MAX_BATCHES")
    if MAX_BATCHES is not None and current_batch_count >= MAX_BATCHES:
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
                completed_count=completed_count,
                chapters_count=len(chapters_by_file_id),
            )
            return {
                "logs": [_log_ts(f"Batch processor: MAX_BATCHES limit reached ({MAX_BATCHES}), but waiting for {len(missing_chapters)} chapters to complete")],
                SENDS_KEY: [],
            }
        logger.info(
            "batch_processor_max_batches_reached",
            current_batch_count=current_batch_count,
            max_batches=MAX_BATCHES,
            remaining_clusters=len(pending),
            chapters_count=len(chapters_by_file_id),
        )
        return {
            "logs": [_log_ts(f"Batch processor: MAX_BATCHES limit reached ({MAX_BATCHES}), routing to editor with {len(pending)} clusters remaining")]
        }

    # Only take from pending and send the next batch when we've received ALL
    # completions for the current batch (avoids over-subscribing analysts).
    if (completed_count - last_batch_sent_count) < last_send_size:
        return {
            "logs": [_log_ts(f"Batch processor: Waiting for {last_send_size - (completed_count - last_batch_sent_count)} more chapter(s) before next batch (have {completed_count - last_batch_sent_count}/{last_send_size})")],
            SENDS_KEY: [],
        }

    # Process next batch. Serialize with a lock so two analyst completions
    # that trigger batch_processor at once do not both take from pending.
    with _batch_processor_lock:
        next_batch = pending[:MAX_PARALLEL_WORKERS]
        remaining = pending[MAX_PARALLEL_WORKERS:]
        new_batch_count = current_batch_count + 1

        cluster_status = state.get("cluster_status", {})
        if not isinstance(cluster_status, dict):
            cluster_status = {}
        for cluster in next_batch:
            file_id = cluster.get("file_id")
            if file_id and file_id in cluster_status:
                cluster_status[file_id]["status"] = "active"
                if "started_at" not in cluster_status[file_id]:
                    cluster_status[file_id]["started_at"] = datetime.utcnow().isoformat() + "Z"
                # Initialize retry_count to 0 if not set (for new batches, not retries)
                if "retry_count" not in cluster_status[file_id]:
                    cluster_status[file_id]["retry_count"] = 0

        state_update = {
            "cluster_status": cluster_status,
            "pending_clusters": remaining,
            "batch_count": new_batch_count,
            "last_batch_sent_count": completed_count,
            "last_send_size": len(next_batch),
            "logs": [_log_ts(f"Batch processor: Processing batch {new_batch_count} ({len(next_batch)} clusters), {len(remaining)} remaining")],
        }
        send_objects = [
            Send("analyst_node", {"procedures": c["procedures"], "meta": c})
            for c in next_batch
        ]

    return {
        **state_update,
        SENDS_KEY: send_objects,
    }

# --- Node 2.6: Noop (waiting for more completions) ---
def batch_processor_noop_node(_state: ReportState) -> dict:
    """No-op when batch_processor is waiting for more analyst completions; this branch ends."""
    return {}


# --- Node 3: Editor (Reducer) ---
async def editor_node(state: ReportState, config: Optional[RunnableConfig] = None):
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
            "logs": [_log_ts("Editor finished: No chapters to process.")]
        }
    
    logger.info(
        "editor_node_processing_chapters",
        chapters_count=len(chapters_list),
        file_ids=list(chapters_by_file_id.keys()),
        full_text_length=len(full_text),
    )
    
    # Extract model_name from config
    model_name = _extract_model_name_from_config(config)
    
    # Use model with high output token limit for long reports
    # Editor node needs higher limits to generate complete reports
    from app.flows.common import _get_first_available_llm_config, _get_provider_config, get_provider_for_model
    llm_config = _get_first_available_llm_config()
    provider = llm_config["PROVIDER"]
    provider_config = _get_provider_config(provider)
    
    # If model_name is provided, use it to determine provider (override default)
    if model_name:
        provider = get_provider_for_model(model_name=model_name)
        # Re-get provider config for the correct provider
        provider_config = _get_provider_config(provider)
    
    if provider == "ollama":
        max_output_tokens = provider_config.get("OLLAMA_EDITOR_NODE_MAX_OUTPUT_TOKENS")
    elif provider == "vertex":
        max_output_tokens = constants.CONSTANTS.get("EDITOR_NODE_MAX_OUTPUT_TOKENS_VERTEX")
    
    if max_output_tokens is not None:
        llm = get_agent_model(model_name=model_name, max_output_tokens=max_output_tokens)
    else:
        llm = get_agent_model(model_name=model_name)
    
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
    
    # Prepare call context for logging
    # Note: Token counting is handled by execute_llm_call_async()
    call_context = {
        "node": "editor_node",
        "flow": "report",
        "chapters_count": len(chapters_list),
    }
    if model_name:
        call_context["model_name"] = model_name
    if provider:
        call_context["provider"] = provider
    
    # Helper coroutine for LLM invocation
    async def _editor_llm_call():
        """Execute LLM call for editor node."""
        return await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_message)
        ])
    
    # Use generic wrapper with report-specific semaphore
    response = await execute_llm_call_async(
        _editor_llm_call,
        semaphore=get_report_llm_semaphore(),
        call_context=call_context,
    )
    
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
        "logs": [_log_ts(f"Editor finished final report with {len(chapters_list)} chapters.")]
    }
